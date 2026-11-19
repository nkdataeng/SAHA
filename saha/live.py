"""Live detection for the dashboard: read the wristband (or replay recordings), score each
3-second window with the personal model, and decide when to show a gentle prompt.

A quick scratch for an itch is normal, so SAHA doesn't prompt on single windows. It prompts
when BFRB-like movement lasts a while, or keeps coming back (see PromptRule).
"""

import csv
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import joblib
import pandas as pd
import serial

from saha.features import add_channels, summarise
from saha.personal import to_cmi_axes
from saha.wristband import BAUD, READING, parse_reading, reset_esp32

RAW_HZ = 50               # readings per second from the ESP32
SCORE_EVERY = 25          # score a new window every 25 readings = 0.5 s (the model's step)


class Detector:
    """Scores the latest 3 seconds of readings with a saved model (models/personal_model.joblib)."""

    def __init__(self, model_path: Path):
        saved = joblib.load(model_path)
        self.model, self.features = saved["model"], saved["features"]
        self.window, self.every = saved["window"], saved.get("every", 5)
        self.to_cmi = saved.get("to_cmi")
        self.trained_on = len(saved.get("recordings", []))
        self.needs = self.window * self.every  # raw readings in one window (150 = 3 s)

    def score(self, readings: list) -> float | None:
        """BFRB-like probability (0 to 1) of the latest window, or None until there's enough data."""
        if len(readings) < self.needs:
            return None
        df = pd.DataFrame(readings[-self.needs:], columns=READING)
        if self.to_cmi is not None:
            df = to_cmi_axes(df, self.to_cmi)
        # Every 5th reading, ending on the newest one: 50 a second -> 10, like training
        window = add_channels(df.iloc[self.every - 1::self.every].reset_index(drop=True))
        features = summarise(window).to_frame().T[self.features]
        return float(self.model.predict_proba(features)[0, 1])


@dataclass
class PromptSettings:
    threshold: float = 0.5        # a window counts as BFRB-like at this probability or above
    prompt_after: float = 10.0    # seconds of BFRB-like movement before a prompt
    gap: float = 2.5              # short breaks allowed inside one episode
    repeat_count: int = 3         # ...or this many episodes...
    repeat_within: float = 300.0  # ...within this many seconds
    quiet: float = 120.0          # no new prompt for this long after one


class PromptRule:
    """Decides when to prompt: a long episode, or several shorter ones close together."""

    def __init__(self, settings: PromptSettings):
        self.s = settings
        self.episode_start = None   # when the current BFRB-like episode began
        self.last_bfrb = None       # last time a window was BFRB-like
        self.counted = False        # has the current episode been counted toward "repeated"?
        self.recent = deque()       # start times of recent episodes
        self.quiet_until = -1.0

    def episode_seconds(self, t: float) -> float:
        return 0.0 if self.episode_start is None else t - self.episode_start

    def update(self, t: float, prob: float) -> str | None:
        """Feed one window's probability at time t (seconds); returns 'long' or 'repeated' to prompt."""
        s = self.s
        if prob >= s.threshold:
            if self.episode_start is None or t - self.last_bfrb > s.gap:
                self.episode_start, self.counted = t, False
            self.last_bfrb = t
            # An episode counts once it's 2 windows in a row (the old alert rule), so a single blip doesn't
            if not self.counted and t - self.episode_start >= 0.5:
                self.recent.append(t)
                self.counted = True
        elif self.episode_start is not None and t - self.last_bfrb > s.gap:
            self.episode_start = None
        while self.recent and t - self.recent[0] > s.repeat_within:
            self.recent.popleft()

        if t < self.quiet_until:
            return None
        if self.episode_start is not None and t - self.episode_start >= s.prompt_after:
            reason = "long"
        elif len(self.recent) >= s.repeat_count:
            reason = "repeated"
        else:
            return None
        self.quiet_until = t + s.quiet
        self.recent.clear()
        if self.episode_start is not None:
            self.episode_start = t  # keep watching, but count this episode afresh
        return reason


class Monitor:
    """Runs a source (wristband or replay) in a background thread and keeps the latest results."""

    def __init__(self, detector: Detector, settings: PromptSettings, log_dir: Path = Path("data/sessions")):
        self.detector, self.settings = detector, settings
        self.log_dir = log_dir
        self.readings = deque(maxlen=RAW_HZ * 20)       # last 20 s of raw readings
        self.scores = deque(maxlen=2 * 120)             # (t, probability) for the last 2 minutes
        self.messages = deque(maxlen=20)                # status lines from the ESP32
        self.prompt = None                              # dict(t, reason, prob) while a prompt is showing
        self.source, self.error, self.t = None, None, 0.0
        self.received = 0
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.Lock()
        self.rule = PromptRule(settings)

    # ---------- sources ----------
    def start_wristband(self, port: str) -> None:
        self._start(f"wristband on {port}", lambda: self._read_serial(port))

    def start_replay(self, files: list[Path], loop: bool = True, speed: float = 1.0) -> None:
        names = ", ".join(f.stem.rsplit("_", 2)[0] for f in files)
        self._start(f"replay: {names}", lambda: self._replay(files, loop, speed))

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=3)
        self._thread, self.source = None, None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _start(self, name: str, target) -> None:
        self.stop()
        self._stop.clear()
        self.readings.clear(); self.scores.clear(); self.messages.clear()
        self.prompt, self.error, self.t, self.received = None, None, 0.0, 0
        self.rule = PromptRule(self.settings)
        self.source = name
        self._thread = threading.Thread(target=self._guard(target), daemon=True)
        self._thread.start()

    def _guard(self, target):
        def run():
            try:
                target()
            except Exception as e:  # shown on the dashboard instead of crashing silently
                self.error = str(e)
        return run

    def _read_serial(self, port: str) -> None:
        with serial.Serial(port, BAUD, timeout=1) as ser:
            reset_esp32(ser)
            start = time.monotonic()
            while not self._stop.is_set():
                line = ser.readline().decode(errors="replace").strip()
                if line.startswith("#"):
                    self.messages.append(line)
                    if line.startswith("# ERROR"):
                        self.error = line[2:]
                    continue
                reading = parse_reading(line)
                if reading:
                    self._add(reading, time.monotonic() - start)

    def _replay(self, files: list[Path], loop: bool, speed: float) -> None:
        data = [pd.read_csv(f)[READING].to_numpy() for f in files]
        start, n = time.monotonic(), 0
        while not self._stop.is_set():
            for rows in data:
                for row in rows:
                    if self._stop.is_set():
                        return
                    t = n / RAW_HZ
                    wait = start + t / speed - time.monotonic()
                    if wait > 0:
                        time.sleep(wait)
                    self._add(list(row), t)
                    n += 1
            if not loop:
                self.messages.append("# replay finished")
                return

    # ---------- scoring ----------
    def _add(self, reading: list, t: float) -> None:
        with self._lock:
            self.readings.append(reading)
            self.received += 1
            self.t = t
        if self.received % SCORE_EVERY:
            return
        prob = self.detector.score(list(self.readings))
        if prob is None:
            return
        with self._lock:
            self.scores.append((t, prob))
            reason = self.rule.update(t, prob)
            if reason and self.prompt is None:
                self.prompt = dict(t=t, reason=reason, prob=prob)
                self._log("prompt", reason, prob)

    def respond(self, answer: str) -> None:
        """Record the wearer's answer to a prompt (e.g. 'take a break' or 'okay') and clear it.

        The quiet time restarts from the answer, so the next prompt can't follow straight after.
        """
        with self._lock:
            if self.prompt:
                self._log("answer", answer, self.prompt["prob"])
            self.prompt = None
            self.rule.quiet_until = self.t + self.settings.quiet

    def test_prompt(self) -> None:
        with self._lock:
            self.prompt = dict(t=self.t, reason="test", prob=float("nan"))

    def snapshot(self) -> dict:
        with self._lock:
            return dict(readings=list(self.readings), scores=list(self.scores), t=self.t,
                        prompt=self.prompt, episode=self.rule.episode_seconds(self.t),
                        messages=list(self.messages), error=self.error, source=self.source,
                        running=self.running, received=self.received)

    def _log(self, event: str, detail: str, prob: float) -> None:
        """Prompts and answers go to data/sessions/ (never uploaded; data/ is in .gitignore)."""
        self.log_dir.mkdir(parents=True, exist_ok=True)
        path = self.log_dir / f"prompts_{datetime.now():%Y%m%d}.csv"
        new = not path.exists()
        with open(path, "a", newline="") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["time", "event", "detail", "probability", "source"])
            w.writerow([f"{datetime.now():%H:%M:%S}", event, detail, f"{prob:.2f}", self.source])

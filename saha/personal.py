"""Personal calibration: learn one person's BFRB-like movements from their own wristband.

The CMI model alone missed every BFRB-like gesture on our wristband, because the
sensor's axes point differently from the Helios watch's. After rotating our axes
into CMI's (TO_CMI), a model trained on our own labelled recordings caught all of
them and stopped mistaking texting for hair pulling. See scripts/train_personal.py.
"""

import re
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.spatial.transform import Rotation
from sklearn.ensemble import HistGradientBoostingClassifier

from saha.features import ACC, ROT, FEATURES, WINDOW, STEP, add_channels, summarise, window_starts

# Our MPU6050 axes -> CMI axes: CMI x = -our y, CMI y = +our z, CMI z = -our x.
# Found on 9 Nov by matching where gravity points during each gesture, with the
# sensor worn chip side down on the back of the right wrist, wires toward the elbow.
# Wear it differently (or switch to the BNO085) and this needs finding again.
TO_CMI = np.array([[0, -1, 0], [0, 0, 1], [-1, 0, 0]], float)

# Recording labels that count as BFRB-like; every other label is ordinary
BFRB_LABELS = {"eyebrow_pull_hair", "above_ear_pull_hair", "forehead_pull_hairline", "forehead_scratch",
               "eyelash_pull_hair", "neck_pinch_skin", "neck_scratch", "cheek_pinch_skin"}
EVERY = 5            # our 50 Hz -> about 10 Hz, CMI's (assumed) rate
GESTURE_START = 3.5  # seconds: record.py says "NOW" at 3 s; allow half a second to start


def label_of(path: Path) -> str:
    """'eyebrow_pull_hair_20261109_132944.csv' -> 'eyebrow_pull_hair'"""
    return re.sub(r"_\d{8}_\d{6}$", "", Path(path).stem)


def to_cmi_axes(df: pd.DataFrame, M: np.ndarray = TO_CMI) -> pd.DataFrame:
    """Rotate a recording's acceleration and orientation into CMI's sensor axes."""
    out = df.copy()
    out[ACC] = df[ACC].to_numpy() @ M.T
    q = df[ROT].to_numpy()  # w, x, y, z
    rotated = (Rotation.from_quat(q[:, [1, 2, 3, 0]]) * Rotation.from_matrix(M.T)).as_quat()
    out[ROT] = rotated[:, [3, 0, 1, 2]]
    return out


def recording_windows(df: pd.DataFrame, bfrb: bool) -> pd.DataFrame:
    """One row of features per sliding window, like the CMI model, plus its label and end time."""
    d = to_cmi_axes(df).iloc[::EVERY].reset_index(drop=True)
    t = ((d.t_ms - d.t_ms.iloc[0]) / 1000).to_numpy()
    ch = add_channels(d)
    rows = []
    for start in window_starts(len(ch)):
        feats = summarise(ch.iloc[start:start + WINDOW]).to_dict()
        in_gesture = (t[start:start + WINDOW] >= GESTURE_START).mean()
        feats.update(label=int(bfrb and in_gesture >= 0.5), end_t=t[min(start + WINDOW, len(ch)) - 1])
        rows.append(feats)
    return pd.DataFrame(rows)


def load_recordings(folder: Path = Path("data/recordings")) -> list[dict]:
    """All recordings in the folder, each with its windows and a repetition number.

    Labels starting with "test" are skipped: they're hardware checks (e.g. the sensor
    lying on the table), not the sensor being worn.

    The repetition number counts recordings of the same label in time order (0, 1, 2...),
    so a fair test can hold out one round of recordings at a time.
    """
    recs = []
    for path in sorted(Path(folder).glob("*.csv")):
        label = label_of(path)
        if label.startswith("test"):
            continue
        df = pd.read_csv(path)
        if len(df) < 2 * WINDOW * EVERY:
            continue
        bfrb = label in BFRB_LABELS
        recs.append(dict(file=path.name, label=label, bfrb=bfrb, windows=recording_windows(df, bfrb)))
    for label in {r["label"] for r in recs}:
        for i, r in enumerate(r for r in recs if r["label"] == label):
            r["rep"] = i
    return recs


def new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0)


def alerts(prob: np.ndarray, threshold: float = 0.5, in_a_row: int = 2) -> np.ndarray:
    """True where `in_a_row` windows in a row are BFRB-like (filters single noisy windows)."""
    hit = (np.asarray(prob) >= threshold).astype(int)
    if len(hit) < in_a_row:
        return np.zeros(1, bool)
    return np.convolve(hit, np.ones(in_a_row, int), "valid") >= in_a_row


__all__ = ["TO_CMI", "BFRB_LABELS", "EVERY", "GESTURE_START", "FEATURES", "WINDOW", "STEP",
           "label_of", "to_cmi_axes", "recording_windows", "load_recordings", "new_model", "alerts"]

"""SAHA live dashboard: live wristband readings, the BFRB-like level, and a gentle "Hey, is everything okay?" prompt.

Run from the project folder (close the Arduino Serial Monitor first):
    .\\.venv\\Scripts\\streamlit run dashboard.py

It uses the personal model (models/personal_model.joblib, made by scripts/train_personal.py),
or the mixed CMI + personal model (models/mixed_model.joblib, made by scripts/train_mixed.py)
when you pick it in the sidebar.
"Replay recordings" plays saved recordings instead of the wristband: for testing, or as a
backup at a demo. Prompts and answers are saved to data/sessions/ on this computer only.
"""

from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st
from serial.tools import list_ports

from saha.live import Detector, Monitor, PromptSettings

MODEL = Path("models/personal_model.joblib")
MODELS = {"Personal (my recordings only)": MODEL,
          "Mixed (CMI's 81 people + my recordings)": Path("models/mixed_model.joblib")}
RECORDINGS = Path("data/recordings")
DEMO = ("still_", "text_on_phone_", "eyebrow_pull_hair_", "wave_hello_", "forehead_scratch_")

st.set_page_config(page_title="SAHA", page_icon=":raised_hand:", layout="wide")

if not MODEL.exists():
    st.error("No personal model yet. Record some gestures, then train it:")
    st.code(r".\.venv\Scripts\python scripts\train_personal.py")
    st.stop()


@st.cache_resource
def get_monitor() -> Monitor:
    mixed = MODELS["Mixed (CMI's 81 people + my recordings)"]
    return Monitor(Detector(mixed if mixed.exists() else MODEL), PromptSettings())


monitor = get_monitor()
settings = monitor.settings

# ---------- sidebar: where the data comes from, and when to prompt ----------
with st.sidebar:
    st.header("Source")
    mode = st.radio("Read from", ["Wristband (USB)", "Replay recordings"], disabled=monitor.running)
    if mode == "Wristband (USB)":
        ports = [p.device for p in list_ports.comports()]
        port = st.selectbox("Port", ports or ["COM4"], disabled=monitor.running)
        if not ports:
            st.warning("No ports found. Is the ESP32 plugged in with a data cable?")
        st.caption("Close the Arduino Serial Monitor first. Keep your arm still for 2 seconds while it calibrates.")
        if st.button("Start", type="primary", disabled=monitor.running, use_container_width=True):
            monitor.start_wristband(port)
            st.rerun()
    else:
        names = [f.name for f in sorted(RECORDINGS.glob("*.csv"))]
        default = [next((n for n in names if n.startswith(p)), None) for p in DEMO]
        picked = st.multiselect("Recordings, played one after another", names, default=[n for n in default if n],
                                disabled=monitor.running)
        loop = st.checkbox("Loop", value=True, disabled=monitor.running)
        speed = st.select_slider("Speed", options=[1.0, 2.0, 4.0], value=1.0, format_func=lambda x: f"{x:g}×",
                                 disabled=monitor.running)
        if st.button("Start replay", type="primary", disabled=monitor.running or not picked, use_container_width=True):
            monitor.start_replay([RECORDINGS / n for n in picked], loop, speed)
            st.rerun()
    if st.button("Stop", disabled=not monitor.running, use_container_width=True):
        monitor.stop()
        st.rerun()

    st.header("Prompt settings")
    settings.prompt_after = st.slider("Prompt after this many seconds of BFRB-like movement", 3, 30,
                                      int(settings.prompt_after))
    settings.repeat_count = st.slider("...or after this many episodes within 5 minutes", 2, 6, settings.repeat_count)
    settings.quiet = st.slider("Quiet time after a prompt (seconds)", 10, 300, int(settings.quiet), step=10)
    settings.threshold = st.slider("Counts as BFRB-like from this model level", 0.3, 0.9, settings.threshold, 0.05)
    if st.button("Show a test prompt", use_container_width=True):
        monitor.test_prompt()

    st.header("Model")
    available = {name: path for name, path in MODELS.items() if path.exists()}
    current = next((n for n, p in available.items() if p == monitor.detector.path), next(iter(available)))
    choice = st.radio("Recognise movements with", list(available), index=list(available).index(current),
                      disabled=monitor.running, help="Stop first to switch.")
    if available[choice] != monitor.detector.path:
        monitor.detector = Detector(available[choice])
    st.caption(f"Trained on {monitor.detector.trained_on} of my recordings"
               + (" plus the CMI data." if "Mixed" in choice else "."))

# ---------- main page ----------
st.title("SAHA")
st.caption("A wrist-worn awareness prototype for body-focused repetitive behaviors. "
           "An awareness tool, not a medical device.")

REASONS = {
    "long": "Your hand has been making a BFRB-like movement for a while.",
    "repeated": "BFRB-like movements have come back a few times in the last few minutes.",
    "test": "This is a test prompt.",
}


@st.fragment(run_every=0.5)
def live() -> None:
    snap = monitor.snapshot()
    if snap["error"]:
        st.error(f"Problem: {snap['error']}")
    if not snap["running"] and not snap["received"]:
        st.info("Choose a source in the sidebar and press Start.")
        return

    prompt = snap["prompt"]
    if prompt:
        with st.container(border=True):
            st.markdown("## Hey, is everything okay?")
            st.markdown("#### Would you like to take a break?")
            st.caption(REASONS.get(prompt["reason"], ""))
            brk, okay = st.columns(2)
            if brk.button("Take a break", type="primary", use_container_width=True):
                monitor.respond("take a break")
                st.rerun(scope="fragment")
            if okay.button("I'm okay", use_container_width=True):
                monitor.respond("okay")
                st.rerun(scope="fragment")

    scores, now = snap["scores"], snap["t"]
    prob = scores[-1][1] if scores else None
    readings = snap["readings"]
    rate = 0.0
    if len(readings) > 50:
        # median gap between readings, so a jump between replayed files doesn't matter
        gap = np.median(np.diff([r[0] for r in readings[-51:]]))
        rate = 1000 / gap if gap > 0 else 0.0

    a, b, c, d = st.columns(4)
    a.metric("BFRB-like now", "warming up" if prob is None else f"{prob:.0%}")
    b.metric("BFRB-like for", f"{snap['episode']:.0f} s")
    c.metric("Readings per second", f"{rate:.0f}")
    d.metric("Source", "running" if snap["running"] else "stopped")
    st.caption(snap["source"] or "")
    st.progress(0.0 if prob is None else min(max(prob, 0.0), 1.0))

    left, right = st.columns(2)
    with left:
        st.markdown("**BFRB-like level, last 60 seconds**")
        if scores:
            df = pd.DataFrame(scores, columns=["t", "BFRB-like"])
            df["seconds ago"] = (df.t - now).round(1)
            df["threshold"] = settings.threshold
            st.line_chart(df[df["seconds ago"] >= -60].set_index("seconds ago")[["BFRB-like", "threshold"]],
                          height=240, y_label="level (0 to 1)")
        else:
            st.caption("The first 3 seconds fill the first window...")
    with right:
        st.markdown("**Wrist acceleration, last 10 seconds**")
        if readings:
            r = np.asarray(readings[-500:])
            # count back from the newest reading (50 a second); replayed files each restart t_ms
            ago = (np.arange(len(r)) - (len(r) - 1)) / 50
            df = pd.DataFrame({"seconds ago": ago.round(2), "x": r[:, 1], "y": r[:, 2], "z": r[:, 3]})
            st.line_chart(df.set_index("seconds ago"), height=240, y_label="m/s²")

    if snap["messages"]:
        with st.expander("Messages from the wristband"):
            st.text("\n".join(snap["messages"]))


live()

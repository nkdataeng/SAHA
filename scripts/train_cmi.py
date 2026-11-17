"""Train the CMI model with left-handed people mirrored, test it fairly, and save it.

Usage (from the project folder, with the virtual environment active):
    python scripts/train_cmi.py

The CMI watch was worn on the dominant wrist, so the 10 left-handed people's data is a
mirror image of everyone else's. Mirroring their windows on the x axis made their wrist
tilts match right-handed people's, and in the fair test it cut their false alarms from
32% to 13% (overall from 16% to 13%).

Saves models/window_model_mirrored.joblib. The original models/window_model.joblib
(notebook 03, no mirroring) is kept for comparison. Takes about 10 minutes.
"""

import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.model_selection import StratifiedGroupKFold

sys.path.append(str(Path(__file__).resolve().parents[1]))
from saha.features import ACC, ROT, FEATURES, WINDOW, STEP, add_channels, mirror, summarise, window_starts  # noqa: E402

DATA = Path("data/cmi-detect-behavior-with-sensor-data")
OUT = Path("models/window_model_mirrored.joblib")
MIRROR_AXIS = "x"


def new_model() -> HistGradientBoostingClassifier:
    return HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, random_state=0)


def build_windows() -> pd.DataFrame:
    """One row per 3-second window of every CMI recording, like notebook 03."""
    cols = ["sequence_id", "subject", "sequence_type", "phase", "gesture"]
    df = pd.read_csv(DATA / "train.csv", usecols=cols + ACC + ROT)
    rows = []
    for sid, seq in df.groupby("sequence_id", sort=False):
        g = add_channels(seq.reset_index(drop=True))
        target = g.sequence_type.iloc[0] == "Target"
        in_gesture = (g.phase == "Gesture").to_numpy()
        for start in window_starts(len(g)):
            feats = summarise(g.iloc[start:start + WINDOW]).to_dict()
            feats.update(sequence_id=sid, subject=g.subject.iloc[0], gesture=g.gesture.iloc[0], target=target,
                         label=int(target and in_gesture[start:start + WINDOW].mean() >= 0.5))
            rows.append(feats)
    win = pd.DataFrame(rows)
    hand = pd.read_csv(DATA / "train_demographics.csv").set_index("subject").handedness
    win["left_handed"] = win.subject.map(hand).eq(0)
    return win


def alerted(win: pd.DataFrame) -> pd.DataFrame:
    """Per recording: did 2 windows in a row reach 50%? (For BFRB-like: inside the gesture part.)"""
    rows = []
    for sid, s in win.groupby("sequence_id", sort=False):
        hit = s.prob.to_numpy() >= 0.5
        pairs = hit[:-1] & hit[1:]
        if s.target.iloc[0]:
            pairs = pairs & (s.label.to_numpy()[1:] == 1)
        rows.append(dict(target=s.target.iloc[0], left_handed=s.left_handed.iloc[0], alert=bool(pairs.any())))
    return pd.DataFrame(rows)


def main() -> None:
    warnings.simplefilter("ignore", RuntimeWarning)
    print("Building windows from the CMI data (a few minutes)...", flush=True)
    win = build_windows()
    win.loc[win.left_handed, FEATURES] = mirror(win.loc[win.left_handed, FEATURES], MIRROR_AXIS)
    print(f"{len(win)} windows; left-handed people mirrored on {MIRROR_AXIS}: "
          f"{win[win.left_handed].subject.nunique()} of {win.subject.nunique()}")

    print("Fair test: 5 folds, each tested on people the model hasn't seen...", flush=True)
    prob = np.zeros(len(win))
    cv = StratifiedGroupKFold(n_splits=5, shuffle=True, random_state=0)
    for train, test in cv.split(win[FEATURES], win.label, win.subject):
        prob[test] = new_model().fit(win[FEATURES].iloc[train], win.label.iloc[train]) \
                                .predict_proba(win[FEATURES].iloc[test])[:, 1]
    res = alerted(win.assign(prob=prob))
    for who, r in (("right-handed", res[~res.left_handed]), ("left-handed", res[res.left_handed]), ("everyone", res)):
        print(f"  {who:13s} BFRB-like caught {r[r.target].alert.mean():6.1%}   "
              f"ordinary with a false alarm {r[~r.target].alert.mean():6.1%}")

    final = new_model().fit(win[FEATURES], win.label)
    OUT.parent.mkdir(exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES, "window": WINDOW, "step": STEP,
                 "mirror_axis": MIRROR_AXIS,
                 "note": "Right-wrist frame: mirror left-wrist windows with saha.features.mirror() before scoring."},
                OUT)
    print(f"\nTrained on all {win.sequence_id.nunique()} recordings and saved {OUT}")


if __name__ == "__main__":
    main()

"""Train SAHA's mixed model: the CMI data (81 people) plus your own recordings.

Usage (from the project folder, with the virtual environment active):
    python scripts/train_mixed.py

Simply adding your recordings to CMI's caught every BFRB-like gesture, but texting set off
false alarms: some CMI people held their wrist during BFRBs at the same tilt you hold yours
while texting. So before training, this drops the CMI BFRB-like windows whose average wrist
tilt (gravity direction) is close to your texting tilt, then adds your recordings, each
window counted 30 times so your movements outweigh any one CMI person's.

Fair test: the same as train_personal.py. Each round of your recordings is judged by a model
that never saw that round, and the texting tilts used for the filter come only from the
training rounds.

Saves models/mixed_model.joblib (the dashboard can use it instead of the personal model).
The first run builds the CMI windows and caches them in data/cmi_windows.pkl (git-ignored,
not to be shared: Kaggle data). Takes about 10-15 minutes the first time.
"""

import sys
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.spatial import cKDTree

sys.path.append(str(Path(__file__).resolve().parents[1]))
sys.path.append(str(Path(__file__).resolve().parent))
from saha.features import FEATURES, WINDOW, STEP, mirror  # noqa: E402
from saha.personal import EVERY, GESTURE_START, TO_CMI, load_recordings, new_model  # noqa: E402
from train_cmi import MIRROR_AXIS, build_windows  # noqa: E402
from train_personal import alerted  # noqa: E402

CACHE = Path("data/cmi_windows.pkl")
OUT = Path("models/mixed_model.joblib")
TILT = ["grav_x_mean", "grav_y_mean", "grav_z_mean"]
RADIUS = 0.25   # m/s²: how close a CMI window's tilt must be to your texting to be dropped (best of 0.25 and 0.4)
WEIGHT = 30     # each of your windows counts this many times


def cmi_windows() -> pd.DataFrame:
    if CACHE.exists():
        return pd.read_pickle(CACHE)
    print("Building windows from the CMI data (a few minutes, once)...", flush=True)
    win = build_windows()
    win.loc[win.left_handed, FEATURES] = mirror(win.loc[win.left_handed, FEATURES], MIRROR_AXIS)
    win = win[FEATURES + ["label"]]
    CACHE.parent.mkdir(exist_ok=True)
    win.to_pickle(CACHE)
    return win


def texting_tilts(recs: list[dict]) -> np.ndarray:
    """Wrist tilt of every window in your texting recordings, after "NOW"."""
    tilts = [r["windows"].loc[r["windows"].end_t >= GESTURE_START + 1, TILT]
             for r in recs if "text" in r["label"]]
    return pd.concat(tilts).to_numpy()


def fit_mixed(cmi: pd.DataFrame, own: list[dict]) -> tuple:
    """Drop CMI BFRB-like windows near your texting tilt, add your windows, train."""
    tilt = cmi[TILT].to_numpy()
    ok = np.isfinite(tilt).all(axis=1)          # windows with missing orientation can't be compared: keep them
    near = np.full(len(cmi), np.inf)
    near[ok], _ = cKDTree(texting_tilts(own)).query(tilt[ok], k=1)
    keep = ~((cmi.label.to_numpy() == 1) & (near < RADIUS))
    mine = pd.concat([r["windows"] for r in own])
    X = pd.concat([cmi.loc[keep, FEATURES], mine[FEATURES]])
    y = np.r_[cmi.label.to_numpy()[keep], mine.label.to_numpy()]
    weight = np.r_[np.ones(keep.sum()), np.full(len(mine), WEIGHT)]
    return new_model().fit(X, y, sample_weight=weight), int((~keep).sum())


def main() -> None:
    warnings.simplefilter("ignore", RuntimeWarning)
    recs = load_recordings()
    if not recs:
        raise SystemExit("No recordings found in data/recordings/. Record some with scripts/record.py first.")
    cmi = cmi_windows()
    rounds = sorted({r["rep"] for r in recs})
    print(f"{len(cmi)} CMI windows ({int(cmi.label.sum())} BFRB-like); "
          f"{len(recs)} of your recordings, {len(rounds)} rounds", flush=True)

    results = []
    for k in rounds:
        model, dropped = fit_mixed(cmi, [r for r in recs if r["rep"] != k])
        print(f"  round {k}: dropped {dropped} CMI BFRB-like windows that look like your texting", flush=True)
        for r in (r for r in recs if r["rep"] == k):
            prob = model.predict_proba(r["windows"][FEATURES])[:, 1]
            results.append(dict(label=r["label"], bfrb=r["bfrb"], alert=alerted(r, prob)))

    res = pd.DataFrame(results)
    print("\nFair test (each recording judged by a model that never saw its round):")
    table = res.groupby(["bfrb", "label"]).alert.agg(alerts="sum", recordings="size")
    table.index = table.index.set_levels(["ordinary", "BFRB-like"], level=0)
    print(table.to_string())
    print(f"\n  BFRB-like caught:            {res[res.bfrb].alert.mean():.0%}")
    print(f"  ordinary with a false alarm: {res[~res.bfrb].alert.mean():.0%}")

    final, dropped = fit_mixed(cmi, recs)
    OUT.parent.mkdir(exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES, "window": WINDOW, "step": STEP,
                 "every": EVERY, "to_cmi": TO_CMI, "recordings": [r["file"] for r in recs],
                 "note": f"CMI (minus {dropped} texting-like BFRB windows) + your recordings x{WEIGHT}"}, OUT)
    print(f"\nTrained on CMI (minus {dropped} texting-like windows) plus all {len(recs)} of your "
          f"recordings and saved {OUT}")


if __name__ == "__main__":
    main()

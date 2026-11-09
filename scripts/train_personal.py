"""Train SAHA's personal model on your own labelled wristband recordings.

Usage (from the project folder, with the virtual environment active):
    python scripts/train_personal.py

Reads every CSV in data/recordings/ (the label is the file name before the date,
e.g. eyebrow_pull_hair_20261109_132944.csv), tests the model fairly, then trains
on everything and saves models/personal_model.joblib.

Fair test: recordings are grouped into rounds (your 1st, 2nd, 3rd... recording of
each gesture). Each round is tested by a model trained on the other rounds only.
Record each gesture at least 3 times so every round has something to learn from.
"""

import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.append(str(Path(__file__).resolve().parents[1]))
from saha.personal import (FEATURES, WINDOW, STEP, EVERY, GESTURE_START, TO_CMI,  # noqa: E402
                           alerts, load_recordings, new_model)


def alerted(r: dict, prob: np.ndarray) -> bool:
    """Did an alert fire? For BFRB-like recordings it must come after "NOW"."""
    fired = alerts(prob)
    if r["bfrb"]:
        end_t = r["windows"].end_t.to_numpy()[1:len(fired) + 1]
        fired = fired & (end_t >= GESTURE_START + 1)
    return bool(fired.any())


def main() -> None:
    recs = load_recordings()
    if not recs:
        raise SystemExit("No recordings found in data/recordings/. Record some with scripts/record.py first.")
    rounds = sorted({r["rep"] for r in recs})
    print(f"{len(recs)} recordings, {len({r['label'] for r in recs})} labels, {len(rounds)} rounds")

    results = []
    for k in rounds:
        train = pd.concat([r["windows"] for r in recs if r["rep"] != k])
        if train.label.nunique() < 2:
            continue
        model = new_model().fit(train[FEATURES], train.label)
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

    everything = pd.concat([r["windows"] for r in recs])
    final = new_model().fit(everything[FEATURES], everything.label)
    out = Path("models/personal_model.joblib")
    out.parent.mkdir(exist_ok=True)
    joblib.dump({"model": final, "features": FEATURES, "window": WINDOW, "step": STEP,
                 "every": EVERY, "to_cmi": TO_CMI, "recordings": [r["file"] for r in recs]}, out)
    print(f"\nTrained on all {len(recs)} recordings and saved {out}")


if __name__ == "__main__":
    main()

"""Motion features that work the same on CMI data and on the ESP32 + MPU6050.

All features avoid heading (yaw), which drifts on the MPU6050, and avoid the
raw quaternion, whose sign can flip (q and -q are the same orientation).
See HARDWARE.md.
"""

import warnings

import numpy as np
import pandas as pd

G = 9.81
ACC = ["acc_x", "acc_y", "acc_z"]
ROT = ["rot_w", "rot_x", "rot_y", "rot_z"]

# Per-reading channels, summarised over each window
CHANNELS = ["grav_x", "grav_y", "grav_z", "lin_x", "lin_y", "lin_z", "lin_mag", "acc_mag", "ang_speed"]
STATS = ["mean", "std", "min", "max"]
FEATURES = [f"{c}_{stat}" for c in CHANNELS for stat in STATS]

# Sliding window, in readings. A CMI gesture part is about 31 readings long.
WINDOW = 30
STEP = 5


def add_channels(seq: pd.DataFrame) -> pd.DataFrame:
    """Add per-reading feature channels to one sequence (rows in time order)."""
    acc = seq[ACC].to_numpy(float)
    q = seq[ROT].to_numpy(float)
    q = q / np.linalg.norm(q, axis=1, keepdims=True)
    w, x, y, z = q.T

    # Direction of "up" in the sensor's own axes (which way the wrist is tilted).
    # Third row of the body-to-world rotation matrix; unchanged if q flips sign.
    grav = np.column_stack([2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)])

    # Acceleration with gravity removed
    lin = acc - G * grav

    # Rotation between consecutive readings, in radians per reading
    dot = np.abs(np.sum(q[1:] * q[:-1], axis=1)).clip(max=1)
    ang = np.concatenate([[np.nan], 2 * np.arccos(dot)])

    out = seq.copy()
    out[["grav_x", "grav_y", "grav_z"]] = grav
    out[["lin_x", "lin_y", "lin_z"]] = lin
    out["lin_mag"] = np.linalg.norm(lin, axis=1)
    out["acc_mag"] = np.linalg.norm(acc, axis=1)
    out["ang_speed"] = ang
    return out


def summarise(window: pd.DataFrame) -> pd.Series:
    """Turn a window of readings (output of add_channels) into one row of features."""
    a = window[CHANNELS].to_numpy(float)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)  # all-NaN columns when rot is missing
        s = np.stack([np.nanmean(a, 0), np.nanstd(a, 0, ddof=1), np.nanmin(a, 0), np.nanmax(a, 0)], axis=1)
    return pd.Series(s.ravel(), index=FEATURES)


def window_starts(n: int, size: int = WINDOW, step: int = STEP) -> list[int]:
    """Start positions of sliding windows over n readings.

    The last window always ends on the last reading, and there is one window if n < size.
    """
    last = max(n - size, 0)
    starts = list(range(0, last + 1, step))
    if starts[-1] != last:
        starts.append(last)
    return starts

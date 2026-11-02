"""Motion features that work the same on CMI data and on the ESP32 + MPU6050.

All features avoid heading (yaw), which drifts on the MPU6050, and avoid the
raw quaternion, whose sign can flip (q and -q are the same orientation).
See HARDWARE.md.
"""

import numpy as np
import pandas as pd

G = 9.81
ACC = ["acc_x", "acc_y", "acc_z"]
ROT = ["rot_w", "rot_x", "rot_y", "rot_z"]

# Per-reading channels, summarised over each window
CHANNELS = ["grav_x", "grav_y", "grav_z", "lin_x", "lin_y", "lin_z", "lin_mag", "acc_mag", "ang_speed"]
STATS = ["mean", "std", "min", "max"]


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
    s = window[CHANNELS].agg(STATS)
    return pd.Series({f"{c}_{stat}": s.at[stat, c] for c in CHANNELS for stat in STATS})

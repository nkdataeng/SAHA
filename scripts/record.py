"""Record MPU6050 readings from the ESP32 to a CSV file.

Usage (from the project folder, with the virtual environment active):
    python -m serial.tools.list_ports                     # find the ESP32's port
    python scripts/record.py --port COM3 --label wave_hello --seconds 20

Saves to data/recordings/<label>_<date-time>.csv, with the same column names as
CMI (acc_* in m/s² with gravity, rot_* quaternion), then prints a quality check.
"""

import argparse
import csv
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import serial

sys.path.append(str(Path(__file__).resolve().parents[1]))
from saha.features import ACC, ROT, add_channels  # noqa: E402

BAUD = 230400
# The MotionApps20 DMP packet reports acceleration at 8192 counts per g.
# check() below warns if this looks wrong for your sensor.
ACC_COUNTS_PER_G = 8192
G = 9.81
COLUMNS = ["t_ms", *ACC, "gyro_x_raw", "gyro_y_raw", "gyro_z_raw", *ROT, "label"]


def parse_line(line: str, label: str) -> list | None:
    """Turn one line from the ESP32 into a CSV row, or None if it isn't a reading."""
    parts = line.strip().split(",")
    if len(parts) != 11 or line.startswith("#"):
        return None
    try:
        t = int(parts[0])
        acc = [int(v) / ACC_COUNTS_PER_G * G for v in parts[1:4]]
        gyro = [int(v) for v in parts[4:7]]
        quat = [float(v) for v in parts[7:11]]
    except ValueError:
        return None
    return [t, *(round(v, 4) for v in acc), *gyro, *quat, label]


def record(port: str, label: str, seconds: float, out: Path) -> None:
    with serial.serial_for_url(port, BAUD, timeout=2) as ser:
        print("Waiting for the ESP32 (it restarts and calibrates: keep the sensor flat and still)...")
        while True:
            line = ser.readline().decode(errors="replace").strip()
            if line:
                print("  ", line)
            if line == "# ready":
                break

        input(f"Put the sensor on your wrist, then press Enter to record '{label}' for {seconds:g} s...")
        ser.reset_input_buffer()
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = 0
        end = time.monotonic() + seconds
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(COLUMNS)
            while time.monotonic() < end:
                row = parse_line(ser.readline().decode(errors="replace"), label)
                if row:
                    w.writerow(row)
                    rows += 1
    print(f"Saved {rows} readings to {out}")


def check(path: Path) -> None:
    """Print simple quality checks for a recording."""
    df = pd.read_csv(path)
    if len(df) < 10:
        print("Too few readings to check.")
        return
    dt = np.diff(df.t_ms.to_numpy())
    rate = 1000 / np.median(dt)
    gaps = int((dt > 1.5 * np.median(dt)).sum())
    acc_total = np.linalg.norm(df[ACC].to_numpy(), axis=1)
    feats = add_channels(df)
    # Gravity seen through the quaternion: about +9.8 if it matches CMI (Z up)
    up = (feats[["grav_x", "grav_y", "grav_z"]].to_numpy() * df[ACC].to_numpy()).sum(axis=1)

    print("Quality check:")
    print(f"  sample rate:            {rate:.1f} Hz")
    print(f"  gaps (missed readings): {gaps}")
    print(f"  total acceleration:     median {np.median(acc_total):.2f} m/s² (expect about 9.8 when still)")
    print(f"  gravity along 'up':     median {np.median(up):.2f} m/s² (expect about +9.8, like CMI)")
    if not 8.5 < np.median(acc_total) < 11:
        print("  ! Acceleration scale looks off. Try ACC_COUNTS_PER_G = 16384 in scripts/record.py.")
    if np.median(up) < 0:
        print("  ! The quaternion's 'up' points down compared with CMI. Note this for the axis mapping.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", required=True, help="serial port, e.g. COM3")
    p.add_argument("--label", required=True, help="what you're doing, e.g. wave_hello or forehead_scratch")
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--out", type=Path, help="CSV path (default: data/recordings/<label>_<date-time>.csv)")
    args = p.parse_args()

    out = args.out or Path("data/recordings") / f"{args.label}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    record(args.port, args.label, args.seconds, out)
    check(out)


if __name__ == "__main__":
    main()

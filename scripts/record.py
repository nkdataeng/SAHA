"""Record BNO085 (or MPU6050) readings from the ESP32 to a CSV file.

Usage (from the project folder, with the virtual environment active):
    python -m serial.tools.list_ports                     # find the ESP32's port
    python scripts/record.py --port COM3 --label wave_hello --seconds 20
    python scripts/record.py --port COM3 --label wave_hello --sensor mpu6050   # backup sensor

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
from saha.features import ACC, add_channels  # noqa: E402
from saha.wristband import BAUD, READING, crc8, parse_reading, reset_esp32  # noqa: E402, F401

WAIT_MSG = {
    "bno085": "Waiting for the ESP32 (it restarts when the recorder connects)...",
    "mpu6050": "Waiting for the ESP32 (it restarts and calibrates: keep the sensor flat and still)...",
}


def columns() -> list[str]:
    return [*READING, "label"]


def parse_line(line: str, label: str) -> list | None:
    """Turn one line from the ESP32 into a CSV row, or None if it isn't a good reading."""
    reading = parse_reading(line)
    return None if reading is None else [*reading, label]


def record(port: str, label: str, seconds: float, out: Path, sensor: str = "bno085", rest: float = 3) -> None:
    with serial.serial_for_url(port, BAUD, timeout=2) as ser:
        print(WAIT_MSG[sensor])
        reset_esp32(ser)
        readings = 0
        while True:
            line = ser.readline().decode(errors="replace").strip()
            if line == "# ready":
                print("  ", line)
                break
            if line.startswith("# ERROR"):
                print("  ", line)
                raise SystemExit("The ESP32 reported an error (see above). Check the wiring and try again.")
            if parse_line(line, label):
                # Readings without "# ready": the ESP32 didn't restart, but it's already running
                readings += 1
                if readings >= 50:
                    print("   (the ESP32 was already running, so it keeps its earlier calibration)")
                    break
            elif line.startswith("#"):
                print("  ", line)  # status messages only; start-up noise is skipped

        input(f"Put the sensor on your wrist, then press Enter to record '{label}' for {seconds:g} s...")
        ser.reset_input_buffer()
        out.parent.mkdir(parents=True, exist_ok=True)
        rows = resets = bad = 0
        start = time.monotonic()
        end = start + seconds
        go = rest > 0
        print(f"Recording. Rest your hand for {rest:g} seconds..." if rest > 0 else "Recording. Do the gesture now!")
        with open(out, "w", newline="") as f:
            w = csv.writer(f)
            w.writerow(columns())
            while time.monotonic() < end:
                if go and time.monotonic() - start >= rest:
                    print(f"\a>>> NOW: do the gesture ({label}) until it says Done <<<")
                    go = False
                line = ser.readline().decode(errors="replace")
                if line.startswith("# sensor reset"):
                    resets += 1
                row = parse_line(line, label)
                if row:
                    w.writerow(row)
                    rows += 1
                elif line.strip() and not line.startswith("#"):
                    bad += 1
    print("Done. You can stop.")
    print(f"Saved {rows} readings to {out}")
    if bad:
        print(f"  ! Skipped {bad} garbled line(s). A few are fine; many means a loose USB cable or a too-fast serial speed.")
    if resets:
        print(f"  ! The sensor reset {resets} time(s) during recording, so this recording has gaps.")


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
        print("  ! Acceleration looks off. Was the sensor moving the whole time? Try a recording that starts still.")
    if np.median(up) < 0:
        print("  ! The quaternion's 'up' points down compared with CMI. Note this for the axis mapping.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", required=True, help="serial port, e.g. COM3")
    p.add_argument("--label", required=True, help="what you're doing, e.g. wave_hello or forehead_scratch")
    p.add_argument("--seconds", type=float, default=20)
    p.add_argument("--rest", type=float, default=3, help="seconds of resting before the 'NOW' prompt (0 = start straight away)")
    p.add_argument("--sensor", choices=["bno085", "mpu6050"], default="bno085", help="which sketch is on the ESP32")
    p.add_argument("--wrist", choices=["right", "left"], default="right",
                   help="which wrist the sensor is on; left-wrist recordings are mirrored, so they're kept in data/recordings/left/")
    p.add_argument("--out", type=Path, help="CSV path (default: data/recordings[/left]/<label>_<date-time>.csv)")
    args = p.parse_args()

    folder = Path("data/recordings") / ("left" if args.wrist == "left" else "")
    out = args.out or folder / f"{args.label}_{datetime.now():%Y%m%d_%H%M%S}.csv"
    try:
        record(args.port, args.label, args.seconds, out, args.sensor, args.rest)
    except serial.SerialException as e:
        if "denied" in str(e).lower():
            raise SystemExit(f"{args.port} is busy. Close the Arduino Serial Monitor (or the whole Arduino IDE) and try again.")
        raise SystemExit(f"Could not open {args.port}. Is the ESP32 plugged in? Check the port with: python -m serial.tools.list_ports")
    check(out)


if __name__ == "__main__":
    main()

"""Reading the wristband: the ESP32 sends one line per reading, ending in a CRC-8 checksum.

Shared by scripts/record.py (saving recordings) and the live dashboard.
"""

import time

from saha.features import ACC, ROT

BAUD = 115200
# Both sketches send acceleration in m/s² and gyro in rad/s.
GYRO = ["gyro_x", "gyro_y", "gyro_z"]
READING = ["t_ms", *ACC, *GYRO, *ROT]


def crc8(text: str) -> int:
    """CRC-8 (polynomial 0x07), the same as printWithChecksum() in the sketches."""
    crc = 0
    for ch in text.encode(errors="replace"):
        crc ^= ch
        for _ in range(8):
            crc = ((crc << 1) ^ 0x07) & 0xFF if crc & 0x80 else (crc << 1) & 0xFF
    return crc


def checksum_ok(line: str) -> str | None:
    """Return the reading without its '*HH' checksum, or None if the checksum doesn't match.

    The ESP32 sends a CRC-8 of everything before the '*', so a line that lost
    or changed characters in the cable is caught here.
    """
    body, star, code = line.strip().rpartition("*")
    if not star or len(code) != 2:
        return None
    try:
        return body if crc8(body) == int(code, 16) else None
    except ValueError:
        return None


def parse_reading(line: str) -> list | None:
    """One line from the ESP32 as [t_ms, acc x3, gyro x3, quaternion x4], or None if it isn't a good reading."""
    body = checksum_ok(line)
    if body is None:
        return None
    parts = body.split(",")
    if len(parts) != 11:
        return None
    try:
        return [int(parts[0]), *(float(v) for v in parts[1:11])]
    except ValueError:
        return None


def reset_esp32(ser) -> None:
    """Restart the ESP32 the way the Arduino IDE does: pulse EN low through RTS.

    DTR stays off so the ESP32 boots normally instead of waiting for an upload.
    Opening the port alone doesn't always restart it.
    """
    ser.dtr = False
    ser.rts = True
    time.sleep(0.1)
    ser.rts = False

# SAHA: hardware guide

How to build the wearable so the model trained on the CMI dataset also works on its data.

**Parts:** ESP32, MPU6050 motion sensor, wires, breadboard. No vibration motor: alerts are shown on the dashboard.

## What the CMI data looks like

Checked by reading all of `train.csv` (November 1).

- **Size:** 574,945 rows, 8,151 recordings ("sequences"), 81 people. Each recording is a transition movement followed by the gesture itself.
- **Gestures:** 8 BFRB-like (hair pulling, scratching, pinching skin) and 10 ordinary (waving, texting, drinking, scratching your leg, and others). Each was done in 4 body positions: sitting up, leaning forward, lying on your back, lying on your side.
- **Columns to use:** only 7 of the 341 columns are motion data: `acc_x/y/z` and `rot_w/x/y/z`. The other 325 (`thm_*`, `tof_*`) come from heat and distance sensors we don't have, so leave them out.
- **Acceleration (`acc_*`):** in **m/s² with gravity included**. At rest the total is about 9.9. The largest single value is about 46 m/s² (about 4.7 g).
- **Orientation (`rot_*`):** a unit quaternion that turns the sensor's axes into the room's axes, with **Z pointing up**. Rotating the acceleration by it puts gravity at (−0.1, 0.1, 9.6).
  - 3,692 rows have no `rot` values, so the model needs to cope with gaps.
- **Wrist:** the device was worn on the **dominant wrist**. 71 of the 81 people are right-handed.
- **The CMI device also had a magnetometer** (compass). Ours doesn't, so our heading (yaw) will drift over time.
- **Sample rate:** not in the data (no timestamps). The rhythm of the waving gestures suggests roughly 10–20 Hz, but that's a rough guess. Check the Kaggle competition's Data page for the exact number.

## Sensor chip

Check the text printed on the chip. It should say **MPU-6050** (often on a small blue board labelled GY-521). An **MPU-3050** has a gyroscope but no accelerometer, so it can't produce the `acc_*` data and won't work.

## Matching the CMI data

1. **Placement:** dominant wrist, on the back of the wrist like a watch face. Strap it on tightly with velcro or tape so it can't wobble. Keep the breadboard and ESP32 on the table, with long, slack wires up to the sensor.
2. **Acceleration:** convert to m/s² with gravity included, the same as CMI. The DMP reports acceleration at 8192 counts per g, so `scripts/record.py` uses `raw / 8192 × 9.81`, and its quality check warns if the result looks wrong. The DMP keeps the sensor at its ±2 g setting, so very sharp movements above 2 g (about 20 m/s²) get cut off. That's rare in CMI: 99% of readings are within ±10.5 m/s².
3. **Orientation:** use the MPU6050's built-in motion processor (DMP) to get a quaternion. The i2cdevlib library's `MPU6050_6Axis_MotionApps20` example does this. Because the heading drifts, build the model on features that don't depend on heading:
   - the direction of gravity as the sensor sees it (which way the wrist is tilted),
   - acceleration with gravity removed,
   - how fast the wrist is rotating, worked out from the change in quaternion between samples.

   All three can be computed the same way from CMI data and from our sensor.
4. **Sample rate:** record at 100 Hz with a timestamp on every row. Once the CMI rate is known, downsample our recordings to match.
5. **Axis directions:** our sensor's x/y/z probably point differently from the CMI device's. Record a few CMI gestures, such as "Wave hello" and "Forehead - scratch" while seated. Then find the axis swap or sign flip that makes our readings look most like the CMI ones, and fix that mapping in software.
6. **Recorder CSV columns:** `t_ms, acc_x, acc_y, acc_z, gyro_x_raw, gyro_y_raw, gyro_z_raw, rot_w, rot_x, rot_y, rot_z, label`. Gyro values are kept as raw sensor counts; the model doesn't use them.

## Wiring

| MPU6050 | ESP32 |
|---|---|
| VCC | 3V3 |
| GND | GND |
| SDA | GPIO 21 |
| SCL | GPIO 22 |
| INT | not needed (the sketch checks the sensor for new data instead) |

## Recording data (Phase 2)

**1. Program the ESP32 (once)**

1. Install the [Arduino IDE](https://www.arduino.cc/en/software).
2. Add ESP32 support: *Tools → Board → Boards Manager*, search **esp32**, install **esp32 by Espressif Systems**.
3. Add the sensor library: *Tools → Manage Libraries*, search **MPU6050**, install **MPU6050 by Electronic Cats**.
4. Open `firmware/saha_recorder/saha_recorder.ino`. Pick your board (e.g. *ESP32 Dev Module*) and port under *Tools*, then click **Upload**.
5. Check it: open *Tools → Serial Monitor* at **230400** baud. You should see `# ready`, then lines of numbers. If you see `MPU6050 not found`, check the wiring. Close the Serial Monitor before recording, because only one program can use the port at a time.

**2. Record**

From the project folder, with the virtual environment active:

```
python -m serial.tools.list_ports
python scripts/record.py --port COM3 --label wave_hello --seconds 20
```

Use the port from the first command. The ESP32 restarts and calibrates when the recorder connects, so keep the sensor **flat on the table, chip side up, and still** until you're asked to press Enter. Then put it on your wrist and press Enter.

Recordings go to `data/recordings/`, which Git ignores. After each recording the script prints a quality check:

| Check | Good result |
|---|---|
| sample rate | about 100 Hz |
| gaps | 0, or very few |
| total acceleration | about 9.8 m/s² while still |
| gravity along "up" | about +9.8 m/s², the same as CMI |

**What to record:** a few of each, seated, using CMI gesture names as labels, e.g. `wave_hello`, `text_on_phone`, `forehead_scratch`, `eyebrow_pull_hair` (pretend; don't actually pull hair). Start each recording with your hand resting for a few seconds, then do the gesture, like the CMI recordings.

## Sources

- [Deep Multimodal Wearable Sensor Fusion for Detection of BFRBs (arXiv 2608.09830)](https://arxiv.org/pdf/2608.09830)
- [Rist, CMI competition slides](https://speakerdeck.com/rist/cmi-detect-behavior-with-sensor-data)
- [sugupoko, CMI3 overview](https://speakerdeck.com/sugupoko/oshi-si-genspark-kaggle-cmi3-overview) (lower confidence)

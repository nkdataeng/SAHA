# SAHA: hardware guide

How to build the wearable so the model trained on the CMI dataset also works on its data.

**Parts:** ESP32-WROOM (Freenove), **Adafruit BNO085 breakout** (product 4754) with a STEMMA QT cable with female sockets (product 4397). No vibration motor: alerts are shown on the dashboard.

**Backup:** MPU6050 (GY-521) with jumper wires, in case the BNO085 arrives late or won't work over I2C. Its notes are kept below, marked *MPU6050 backup*.

## What the CMI data looks like

Checked by reading all of `train.csv` (November 1).

- **Size:** 574,945 rows, 8,151 recordings ("sequences"), 81 people. Each recording is a transition movement followed by the gesture itself.
- **Gestures:** 8 BFRB-like (hair pulling, scratching, pinching skin) and 10 ordinary (waving, texting, drinking, scratching your leg, and others). There are 4 body positions: sitting up, leaning forward, lying on your back, lying on your side. All 8 BFRB-like gestures were done in all 4. Ordinary gestures vary: "Text on phone" in all 4; waving, writing in the air and pulling air toward the face in all but leaning forward; drinking, glasses and the tray only sitting up; the 3 knee/leg gestures only leaning forward.
- **Columns to use:** only 7 of the 341 columns are motion data: `acc_x/y/z` and `rot_w/x/y/z`. The other 325 (`thm_*`, `tof_*`) come from heat and distance sensors we don't have, so leave them out.
- **Acceleration (`acc_*`):** in **m/s² with gravity included**. At rest the total is about 9.9. The largest single value is about 46 m/s² (about 4.7 g).
- **Orientation (`rot_*`):** a unit quaternion that turns the sensor's axes into the room's axes, with **Z pointing up**. Rotating the acceleration by it puts gravity at (−0.1, 0.1, 9.6).
  - 3,692 rows have no `rot` values, so the model needs to cope with gaps.
- **Wrist:** the device was worn on the **dominant wrist**. 71 of the 81 people are right-handed.
- **The CMI device used a BNO080/BNO085 IMU** with a magnetometer (compass), according to the Kaggle Data page. Our BNO085 is the same chip family, so its acceleration and orientation should be close to CMI's. (The MPU6050 backup has no compass, so its heading would drift.)
- **Sample rate:** not published anywhere official (checked November 1: the Data and Overview pages, the [Helios Data Visualizer](https://www.kaggle.com/competitions/cmi-detect-behavior-with-sensor-data/discussion/583118) and "Get Started Here!" discussions, and arXiv 2608.09830). Participants asked the organizers, with no public answer. **Working assumption: about 10 Hz**, because the organizers' own visualizer plays the data at 10 frames per second by default, and the rhythm of the waving gestures suggests roughly 10–20 Hz.

## Sensor chip

**BNO085:** the Adafruit board is labelled **BNO085** (or BNO08x). It has a STEMMA QT socket, so no soldering is needed.

*MPU6050 backup:* check the text printed on the chip. It should say **MPU-6050** (often on a small blue board labelled GY-521). An **MPU-3050** has a gyroscope but no accelerometer, so it can't produce the `acc_*` data and won't work.

*Our GY-521 has a look-alike chip* (November 5): it answers at I2C address 0x68 but reports chip ID **0x72** instead of 0x68, so libraries that check the ID (such as Electronic Cats' `testConnection()`) refuse it, and its DMP can't be relied on. The recorder therefore reads only the raw accelerometer and gyro registers, which work on look-alikes too.

**Known issue: BNO085 + ESP32 over I2C.** Adafruit lists the BNO085 as troublesome on the ESP32, because it stretches the I2C clock; newer ESP32 software handles this better. The sketch uses a slow bus (100 kHz), a long timeout, and restarts the sensor reports if the sensor resets. If you still see `BNO085 not found` or frequent `# sensor reset` lines: update the **esp32** board package in the Boards Manager, keep the cable short, and if that fails, switch to the MPU6050 backup.

## Matching the CMI data

1. **Placement:** dominant wrist, on the back of the wrist like a watch face. Strap it on tightly with velcro or tape so it can't wobble. Keep the ESP32 on the table, with the cable slack, and tape the cable to the strap so a pull doesn't tug the connector. Wear it **the same way every time** (chip side up, cable toward the elbow).
2. **Acceleration:** in m/s² with gravity included, the same as CMI. The BNO085's accelerometer report already uses these units, so nothing needs converting.
   - *MPU6050 backup:* the sketch sets the accelerometer to ±8 g (enough for CMI's largest readings, about 4.7 g) and converts to m/s² on the ESP32. Look-alike chips may scale differently, so at startup it measures gravity while the sensor is still and uses that as its scale.
3. **Orientation:** the BNO085's **rotation vector** report gives a quaternion that combines the gyroscope, accelerometer and compass, which is how the Kaggle Data page describes CMI's `rot_*`. The **compass needs calibrating:** after switching on, move the sensor slowly in a figure-of-8 for a few seconds, away from laptops, magnets and metal. Even so, keep building the model on features that don't depend on heading:
   - the direction of gravity as the sensor sees it (which way the wrist is tilted),
   - acceleration with gravity removed,
   - how fast the wrist is rotating, worked out from the change in quaternion between samples.

   All three can be computed the same way from CMI data and from our sensor. They also keep the MPU6050 backup usable, since its heading drifts: it has no compass, and its quaternion comes from a Mahony filter on the ESP32 that combines the raw accelerometer and gyro.
4. **Sample rate:** record at 50 Hz with a timestamp on every row. (100 Hz needed a 230400 serial speed, which garbled about 3 in 4 lines on our ESP32; both sketches now use 115200.) Downsample to 10 Hz first, then also try 15 and 20 Hz, and keep whichever rate the model recognizes best.
5. **Axis directions:** our sensor's x/y/z probably point differently from the CMI device's. Record a few CMI gestures, such as "Wave hello" and "Forehead - scratch" while seated. Then find the axis swap or sign flip that makes our readings look most like the CMI ones, and fix that mapping in software.
6. **Recorder CSV columns:** `t_ms, acc_x, acc_y, acc_z, gyro_x, gyro_y, gyro_z, rot_w, rot_x, rot_y, rot_z, label`, with gyro in rad/s, for both sensors. The model doesn't use the gyro columns yet (CMI has no raw gyro), but they're kept for comparison.

## Wiring

**BNO085**, with the STEMMA QT cable. The small plug clicks into either socket on the sensor board; the female sockets go onto the ESP32's pins.

| Cable wire | ESP32-WROOM |
|---|---|
| Red | 3V3 |
| Black | GND |
| Blue (SDA) | GPIO 21 |
| Yellow (SCL) | GPIO 22 |

Use 3V3, not 5V. If your ESP32 board has a camera, leave it unplugged: on Freenove camera boards it also uses GPIO 21 and 22.

*MPU6050 backup:*

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
3. Add the sensor library: *Tools → Manage Libraries*, search **Adafruit BNO08x**, install it, and say yes when it asks to install the libraries it depends on.
4. Open `firmware/saha_recorder_bno085/saha_recorder_bno085.ino`. Pick **ESP32 Dev Module** and your port under *Tools*, then click **Upload**.
5. Check it: open *Tools → Serial Monitor* at **115200** baud. You should see `# ready`, then lines of numbers that change when you move the sensor. If you see `BNO085 not found`, check the cable and see **Known issue** above. Close the Serial Monitor before recording, because only one program can use the port at a time.

*MPU6050 backup:* no library needed. Upload `firmware/saha_recorder/saha_recorder.ino`, and add `--sensor mpu6050` to the record command below. The Serial Monitor should show the chip ID, the measured acceleration scale (about 4096 counts per g on a genuine chip), `# ready`, then numbers.

**2. Record**

From the project folder, with the virtual environment active:

```
python -m serial.tools.list_ports
python scripts/record.py --port COM3 --label wave_hello --seconds 20
```

Use the port from the first command. The ESP32 restarts when the recorder connects. When you're asked to press Enter, put the sensor on your wrist, move it in a slow figure-of-8 for a few seconds to calibrate the compass, rest your hand, and press Enter.

*MPU6050 backup:* it calibrates on restart instead, so keep it **flat on the table, chip side up, and still** until you're asked to press Enter.

Recordings go to `data/recordings/`, which Git ignores. After each recording the script prints a quality check:

| Check | Good result |
|---|---|
| sample rate | about 50 Hz |
| gaps | 0, or very few |
| total acceleration | about 9.8 m/s² while still |
| gravity along "up" | about +9.8 m/s², the same as CMI |

**What to record:** a few of each, seated, using CMI gesture names as labels, e.g. `wave_hello`, `text_on_phone`, `forehead_scratch`, `eyebrow_pull_hair` (pretend; don't actually pull hair). Start each recording with your hand resting for a few seconds, then do the gesture, like the CMI recordings.

## Personal calibration (November 9)

**Problem:** the model trained on CMI caught **none** of 14 BFRB-like recordings from our wristband (MPU6050 on the back of the right wrist, chip side down, wires toward the elbow). Our sensor's axes point differently from the Helios watch's: during each gesture, gravity pointed almost the opposite way to CMI's.

**Axis mapping:** rotating our axes into CMI's (`TO_CMI` in `saha/personal.py`: CMI x = −our y, CMI y = +our z, CMI z = −our x) brought gravity close to CMI's for every gesture. A second mapping (CMI x = −our x, y = +our z, z = +our y) fits almost as well, and the two halves of our recordings each preferred a different one; both agree on CMI y = our z.

**Results** (26 recordings: 4 hair-pulling/scratching gestures and 3 ordinary ones, 3–4 times each, plus a still one; each recording judged by a model that never saw its round):

| Model | BFRB-like caught | Ordinary with a false alarm |
|---|---|---|
| CMI model, our axes as recorded | 0% | 9% |
| CMI model, axes mapped | 43% | 55% (texting) |
| CMI + our recordings, weighted ×30 to ×300 | 100% | 27–45% (texting) |
| **Our recordings only** (`scripts/train_personal.py`) | **100%** | **0%** |

Texting kept triggering alerts whenever CMI data was included: some of CMI's 81 people held their wrists during BFRBs the way we hold ours while texting. Our own recordings separate the two mainly by wrist tilt.

**To retrain** after recording more: `python scripts/train_personal.py`. It prints the fair test and saves `models/personal_model.joblib` (not committed).

**Limits:** one person, one session, acted gestures. The fair test holds out rounds from the same day, so it doesn't show how the model does on another day or another person. Record a fresh set on a different day to check, and treat each new wearer as needing their own short calibration session.

## Sources

- [Deep Multimodal Wearable Sensor Fusion for Detection of BFRBs (arXiv 2608.09830)](https://arxiv.org/pdf/2608.09830)
- [Rist, CMI competition slides](https://speakerdeck.com/rist/cmi-detect-behavior-with-sensor-data)
- [sugupoko, CMI3 overview](https://speakerdeck.com/sugupoko/oshi-si-genspark-kaggle-cmi3-overview) (lower confidence)

# How SAHA works

A plain-language explanation of SAHA's sensor, its data and its two models, written on November 9 during the T-Minus30 sprint.

SAHA is a wrist-worn prototype that notices BFRB-like hand movements (body-focused repetitive behaviors such as hair pulling and skin picking) to build awareness. It is an awareness tool, not a medical device.

---

## 1. The sensors: accelerometer, gyroscope and quaternion

SAHA's motion sensor (an MPU6050-type chip) has two sensors inside. A third kind of data, the quaternion, is calculated from them.

### Accelerometer: "how is the hand being pushed, and which way is down?"

- Measures **pushes** along three directions, called **x, y and z**, in m/s².
- It always feels **gravity** (about 9.8 m/s² pointing down), even when the hand is still.
- So it mixes two things: **gravity** (which tells you the tilt) and **hand movement** (waves, tugs, jolts).

### Gyroscope: "how fast is the wrist turning?"

- Measures **turning speed** around x, y and z, in degrees (or radians) per second.
- A **speed**, not a position: when the wrist is still, it reads about 0, whichever way the wrist is facing.
- Precise moment to moment, but if you add up its turns over time, small errors pile up and it **drifts**.

### Quaternion: "which way is the wrist facing right now?"

- **Four numbers** (w, x, y, z) that describe any direction and twist in 3D.
- A **position**: when the wrist is still, it stays at the current direction.
- Not measured directly. It's **calculated by combining** the gyroscope (turning) with the accelerometer (which way is down), and on some chips a compass (which way is north).
- Used instead of three angles because angles can get "stuck" in certain positions (gimbal lock); quaternions never do.

**A car comparison:** the gyroscope is how fast you're turning the steering wheel; the quaternion is which way the car is facing; the accelerometer is the push you feel when the car speeds up, brakes or goes over a bump.

### Why keep the accelerometer if the quaternion already uses it?

The quaternion keeps only **which way the wrist is facing**. It uses the accelerometer's gravity part gently to fix the tilt and treats the rest as noise. The **hand movement** part (tugs, jolts, swings) is thrown away. Moving the hand straight up to the forehead without twisting barely changes the quaternion, but the accelerometer shows a clear push. So SAHA uses both: the quaternion for **wrist position**, the accelerometer for **movement**.

---

## 2. How the quaternion is calculated on SAHA's sensor

Code: `firmware/saha_recorder/saha_recorder.ino`. It runs on the ESP32, 50 times a second.

1. **Read raw numbers.** `readRaw()` reads the accelerometer and gyroscope straight from the chip's registers.
2. **Calibrate at start-up (2 seconds, sensor still).**
   - The gyroscope should read 0 when still; whatever it reads instead is its **offset**, subtracted from every later reading.
   - The total acceleration when still must equal gravity, which sets the **scale** for converting raw numbers to m/s².
3. **Start from the current tilt.** Gravity shows which way is down, so the first quaternion matches the sensor's tilt.
4. **Every reading, update in two moves (the Mahony filter, `mahony()`):**
   - **Predict with the gyroscope:** turn the previous direction by (turning speed × 0.02 seconds).
   - **Correct with the accelerometer:** compare where the filter thinks "down" is with where the accelerometer says it is, and nudge the direction slightly toward the accelerometer (setting `Kp`).
   - Rescale the four numbers so they stay a valid direction.
5. **Send** `time, acceleration (3), turning speed (3), quaternion (4)` to the laptop, with a checksum so damaged lines are thrown away.

**Limitation:** the MPU6050 has no compass, so the **heading** (which way you face: north, east…) slowly drifts. SAHA's model only uses tilt and turning speed, so this doesn't matter. The BNO085 (on order) has a compass.

### Why SAHA doesn't use the DMP

Genuine MPU6050 chips contain a small built-in processor, the **DMP** (Digital Motion Processor), that can calculate the quaternion itself. SAHA doesn't use it because:

- **Our chip is a look-alike.** Asked "who are you?", a genuine MPU6050 answers 0x68; ours answers **0x72**.
- The usual library (Electronic Cats MPU6050) checks that answer and **refused to work** with our chip, saying "MPU6050 not found" even though the chip was there.
- A look-alike's DMP can't be relied on, and its workings aren't documented.

Reading the **raw accelerometer and gyroscope** works on genuine and look-alike chips alike, and calculating the quaternion ourselves (Mahony filter) means we know exactly what it does.

---

## 3. From a recording to the model's input

The same steps are used for the research data and for SAHA's own recordings.

1. **Slow down to about 10 readings a second.** SAHA records 50 a second; the research data has about 10 (not published; our best estimate). Every 5th reading is kept.
2. **Rotate the axes** (SAHA's recordings only). SAHA's sensor's x, y, z point differently from the research watch's, so they're rotated to match: CMI x = −our y, CMI y = +our z, CMI z = −our x (`TO_CMI` in `saha/personal.py`).
3. **Cut into 3-second windows.** A window is 30 readings in a row (3 seconds). The next window starts half a second later, so windows overlap and nothing is missed. A 10-second recording gives about 15 windows. On the wrist there's no "start" of a gesture, so SAHA keeps judging the latest 3 seconds.
4. **Measure 9 things at every reading** (`saha/features.py`):

   | Measurement | Means |
   |---|---|
   | tilt x, y, z | which way gravity points: how the wrist is turned |
   | movement x, y, z | acceleration with gravity removed: how the hand is pushed |
   | total movement | how much the hand moves overall |
   | total acceleration | movement plus gravity |
   | turning speed | how fast the wrist twists (from the change in quaternion) |

5. **Summarise each over the window in 4 ways:** mean (average), std (spread: steady or jerky), min (lowest), max (highest).

**9 measurements × 4 summaries = 36 numbers per window.** That's how the model "sees" 3 seconds of movement.

Turning speed comes from the quaternion, not the gyroscope, because the research data has no gyroscope columns and every measurement had to be calculated the same way for both.

---

## 4. The model

Both of SAHA's models are the same kind: a **gradient-boosted tree model** (scikit-learn's `HistGradientBoostingClassifier`, 300 trees).

- A **decision tree** asks a series of yes/no questions about the 36 numbers, such as "is the average turning speed below 0.1?".
- **Gradient boosting** builds 300 small trees one after another; each new tree focuses on the mistakes of the ones before it.
- The result is a **BFRB-like probability** from 0 to 100% for each window.
- **Alert rule:** 2 windows in a row at 50% or above. This filters out one-off blips.

---

## 5. Model 1: the CMI model

File: `models/window_model.joblib` (made in `notebooks/03_sliding_windows.ipynb`).

### The data

The **Child Mind Institute's research dataset** from Kaggle ("CMI 2025 Detect Behavior with Sensor Data Challenge"):

- **81 people** (42 adults, 39 children) wearing the **Helios** research watch on the dominant wrist.
- **18 gestures:** 8 BFRB-like (hair pulling above the ear, hairline, eyebrow, eyelash; forehead scratch; neck scratch; neck and cheek pinching) and 10 ordinary (waving, texting, drinking, glasses on/off, and others), in up to 4 body positions.
- Each recording: move the hand into place, pause, do the gesture.
- The watch has a motion sensor (BNO080/BNO085), 5 heat sensors and 5 distance sensors. **SAHA uses only the 7 motion columns** (`acc_x/y/z`, `rot_w/x/y/z`), because its wristband only has a motion sensor.

### How it was built

1. Every recording was cut into 3-second windows: **77,488 windows**, 27.6% of them BFRB-like.
2. A window was labelled BFRB-like if at least half of it fell in the gesture part of a BFRB-like recording.
3. The 36 numbers were calculated for each window, and the model trained on them.

### How it was tested

**5-fold, split by person:** the 81 people were split into 5 groups of about 16. Each group was tested by a model trained only on the other 4, so every person was tested by a model that had never seen them.

### Results (on the research data)

- Per window: balanced accuracy 0.863, ROC AUC 0.957.
- Per recording, with the alert rule: **90% of BFRB-like gestures caught, 16% of ordinary ones with a false alarm.**
- The hardest ordinary gestures were small hand movements, such as feeling around in a tray (57% false alarms).

---

## 6. Why the CMI model didn't work on SAHA's wristband

When the CMI model was run on SAHA's own recordings, it **caught none of the 14 BFRB-like recordings**.

### The reasons

1. **Different axes.** SAHA's sensor's x, y, z point differently from the research watch's. During each gesture, gravity pointed almost the **opposite** way in SAHA's data compared with CMI's (a distance of 1.65, where 0 is identical and 2 is opposite). The model was effectively seeing "upside-down" data.
2. **A different sensor, worn differently.** A look-alike MPU6050, standing at an angle on its pins on an elastic band, versus the Helios watch's BNO085 with a compass.
3. **Different people.** The model learned how 81 participants held their wrists. One person's habits, such as how they hold a phone, can sit in between.

### What was tried

| Version | BFRB-like caught | Ordinary with a false alarm |
|---|---|---|
| CMI model, SAHA's axes as recorded | 0% | 9% |
| CMI model, axes rotated to CMI's | 43% | 55% (mostly texting) |
| CMI data plus SAHA's recordings in training (weighted ×30 to ×300) | 100% | 27–45% (texting) |
| **SAHA's recordings only (the personal model)** | **100%** | **0%** |

Rotating the axes helped, but **texting kept being mistaken for hair pulling** whenever CMI data was included: some research participants held their wrists during BFRBs the way SAHA's wearer holds the wrist while texting. Trained only on SAHA's own recordings, the model told them apart, mainly by **wrist tilt**.

---

## 7. Model 2: the personal model

File: `models/personal_model.joblib`. Code: `saha/personal.py` and `scripts/train_personal.py`.

### The data

SAHA's own recordings in `data/recordings/` (one person, November 9), each 10 seconds: 3 seconds of rest, then the gesture after the "NOW" prompt.

| BFRB-like | Recordings | Ordinary | Recordings |
|---|---|---|---|
| eyebrow_pull_hair | 4 | text_on_phone | 4 |
| above_ear_pull_hair | 3 | text_on_phone_two_hands | 3 |
| forehead_pull_hairline | 3 | wave_hello | 4 |
| forehead_scratch | 4 | still | 1 |

### How it's built

1. The label comes from the **file name** (e.g. `eyebrow_pull_hair_20261109_132944.csv`).
2. Each recording goes through the steps in section 3: slowed to 10 a second, axes rotated, cut into 3-second windows, 36 numbers each.
3. A window is labelled BFRB-like if it's from a BFRB-like recording and at least half of it comes after "NOW" (3.5 seconds, allowing half a second to start). Rest windows and all windows from ordinary recordings are labelled ordinary.
4. The same kind of model (300 gradient-boosted trees) is trained on these windows. **No CMI data is used.**

### How it was tested (a fair test)

Testing a model on recordings it learned from would only show that it **remembers** them. So each gesture was recorded 3–4 times, in **rounds**, and:

- train on rounds 2, 3, 4 → test on round 1
- train on rounds 1, 3, 4 → test on round 2
- … and so on.

Every recording was judged by a model that **had never seen it**, the same idea as testing the CMI model on people it hadn't seen.

### Results

- **BFRB-like caught: 100%** (14 of 14).
- **Ordinary with a false alarm: 0%** (0 of 12), including texting.

After the test, the model is trained once more on **all** recordings and saved. To retrain after recording more: `python scripts/train_personal.py`.

### What CMI still gave the personal model

- The **evidence** that motion alone can catch most BFRB-like gestures (90% across 81 people).
- The **design**: 3-second windows, the 36 measurements, 10 readings a second.
- The **gesture list** and the **recording style** (rest, then gesture).
- The **axis viewpoint** that SAHA's data is rotated into.

---

## 8. Limits and next steps

**Limits**

- **One person, one day, acted gestures.** The fair test holds out rounds from the same session, so it doesn't show how SAHA does on another day (with the strap slightly moved) or on another person.
- **The axis mapping was worked out from gestures**, which mixes up how the sensor is mounted with how the wearer holds their wrist. A second mapping fit almost as well.
- **A movement isn't a habit.** One quick scratch for an itch is normal. Alerts should depend on **how long and how often** a movement happens, not on single moments.

**Next steps**

1. Record one of each gesture on **another day** and test the personal model on it.
2. Build the **dashboard**: live readings, plus alerts only for long or repeated BFRB-like movement.
3. Test with **3–5 people**, each with a short calibration session.
4. With the **BNO085** (the same chip family as the research watch), work out a proper axis mapping using fixed reference poses, and see whether the CMI model then transfers better.

---

## Glossary

| Term | Meaning |
|---|---|
| BFRB | body-focused repetitive behavior, e.g. hair pulling, skin picking |
| IMU | inertial measurement unit: a motion sensor (accelerometer + gyroscope, sometimes a compass) |
| Quaternion | four numbers describing which way something is facing in 3D |
| Mahony filter | a method that combines gyroscope and accelerometer into a quaternion |
| DMP | the MPU6050's built-in motion processor (not used: our chip is a look-alike) |
| Axis mapping | the translation between two sensors' x, y, z directions |
| Window | a 3-second piece of a recording that the model judges |
| Feature | one of the 36 numbers describing a window |
| Gradient boosting | a model made of many small decision trees, each fixing the previous ones' mistakes |
| Fair test | judging each recording or person with a model that never saw it |
| False alarm | an alert on an ordinary movement |

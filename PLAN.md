# SAHA: T-Minus30 plan

**Sprint:** T-Minus30 by Genesis (AI builder sprint)
**Submission due:** Wednesday, November 18 (submit even if it's not finished)
**Demo Night:** Wednesday, November 25, St. John's Farmers' Market
**Plan written:** Sunday, November 1 (17 days to submission, 24 to Demo Night)

## Goal

SAHA is a wearable that detects BFRB-like hand movements, such as those in trichotillomania, using an **ESP32 + MPU6050** sensor on the wrist.

It has three parts:

1. **Sensor recorder:** read accelerometer and gyroscope data from the wearable and save it to CSV.
2. **ML model:** train a classifier on the CMI research dataset to tell BFRB-like gestures apart from everyday ones, and evaluate it properly on held-out data.
3. **Demo dashboard:** a Streamlit app showing the model's results and the live sensor readings, clearly separated.

### Main decision: use motion data only

The dataset has five kinds of sensor data. The MPU6050 only measures motion, so the model should learn from **`acc_*` and `rot_*` only**. That way, what we train matches what we can build.

Note: the CMI `rot_*` columns are orientation quaternions (w, x, y, z), not raw gyroscope readings. The MPU6050's DMP can output a quaternion too (heading/yaw drifts, since there's no magnetometer). The recorder should save **both** raw gyro and the DMP quaternion, so we can choose later which features to match.

## Phase 1: prove the model works on CMI data (Nov 1 – 9)

- [ ] **Nov 1:** Git set up ✅. Read this plan.
- [ ] **Nov 2:** Install Python and Jupyter. Open `train.csv` and look at the first rows.
- [ ] **Nov 3:** Explore: how many people, which gestures, how many examples of each, how long a gesture lasts.
- [ ] **Nov 4:** Draw charts of the motion data for one BFRB-like gesture next to one ordinary gesture.
- [ ] **Nov 5 (Open Build):** Ask make @ mun or the sprint Slack for help with the ESP32 + MPU6050 if needed.
- [ ] **Nov 6–7:** First simple model: BFRB-like vs. not, motion data only. Write down the score.
- [ ] **Nov 8–9:** Improve the model. Test it on **people it has never seen** (split by `subject`), so the score is honest.

**Done when:** you can explain the data in two sentences and have an honest held-out score.

## Phase 2: prove the wearable records good data (Nov 10 – 13)

- [ ] Wire the MPU6050 to the ESP32 and print accelerometer and gyroscope readings to the laptop.
- [ ] Write the sensor recorder: save readings (with timestamps) to CSV.
- [ ] Check the data: steady sample rate, sensible units, no gaps. Compare a recording with CMI data for the same kind of movement.
- [ ] Record a few labelled sessions: BFRB-like movements and ordinary ones.
- [ ] Commit to Git every time something works.

**Done when:** you have clean CSV recordings from the wrist that look like the CMI motion data.

## Phase 3: connect the two (Nov 14 – 16)

- [ ] Run the trained model on the wearable's recordings, as an **experimental** prediction.
- [ ] Build the Streamlit dashboard:
  - **Model results** on CMI held-out data.
  - **Live sensor readings** from the wearable, with the experimental prediction, clearly separated from the CMI results.
- [ ] Write down how well the model does on your own recordings, and why it might differ from CMI.

**Done when:** the dashboard shows both parts, and a BFRB-like movement on the wearable gets flagged at least some of the time.

## Submission (Nov 17 – 18)

- [ ] Test with 3 to 5 people if possible. Write down what worked and what didn't.
- [ ] Update the README: the problem, how SAHA works, results, limitations.
- [ ] Record a 1–2 minute video of the demo (also your backup if live hardware fails).
- [ ] **Submit by November 18.**

## Demo Night prep (Nov 19 – 25)

- [ ] Polish the demo and fix anything fragile.
- [ ] Prepare a 2-minute pitch: who it's for, what it does, what you learned, what's next.
- [ ] Practice the live demo at an Open Build.
- [ ] Bring: the device, a charged laptop, charging cables, and the backup video.
- [ ] **Demo Night, November 25.**

## Things to check

- **Dataset rules:** check the Kaggle competition's data rules before showing results in public. Kaggle competition data often has limits on how it can be used.
- **Framing:** SAHA is an awareness tool, not a medical device or treatment.
- **Privacy:** if people test it, don't store anything that identifies them.

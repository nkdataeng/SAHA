# SAHA: T-Minus30 plan

**Sprint:** T-Minus30 by Genesis (AI builder sprint)
**Submission due:** Wednesday, November 18 (submit even if it's not finished)
**Demo Night:** Wednesday, November 25, St. John's Farmers' Market
**Plan written:** Sunday, November 1 (17 days to submission, 24 to Demo Night)

## Goal

**A working demo:** a wristband (or a stand-in for one) that notices a BFRB-like hand movement and gives a gentle vibration or on-screen alert, powered by a model trained on real wrist-sensor data.

If there's time, add a small amount of user testing: 3 to 5 people try it and give feedback.

### Main decision: use motion data only

The dataset has five kinds of sensor data. A cheap wristband can only have the motion sensor (accelerometer and rotation). So the model should learn from **`acc_*` and `rot_*` only**. That way, what we train matches what we can build.

## Two tracks

- **Software (must have):** a model that tells BFRB-like gestures apart from ordinary ones, with honest results.
- **Hardware (nice to have):** a board with a motion sensor on the wrist, sending data to the model and vibrating. If parts or time run out, the backup is a recorded demo showing the model working on real data.

## Week 1: understand the data (Nov 1 – 7)

- [ ] **Nov 1:** Git set up ✅. Read this plan.
- [ ] **Nov 2:** Install Python and Jupyter. Open `train.csv` and look at the first rows.
- [ ] **Nov 3:** Explore: how many people, which gestures, how many examples of each, how long a gesture lasts.
- [ ] **Nov 4:** Draw charts of the motion data for one BFRB-like gesture next to one ordinary gesture.
- [ ] **Nov 5 (Open Build):** Ask make @ mun or the sprint Slack about borrowing a board with a motion sensor (e.g. Seeed XIAO nRF52840 Sense or Arduino Nano 33 BLE Sense) and a small vibration motor.
- [ ] **Nov 6–7:** First simple model: BFRB-like vs. not, motion data only. Write down the score.

**Done when:** you can explain the data in two sentences and have a first score.

## Week 2: make it work (Nov 8 – 14)

- [ ] Improve the model. Test it on **people it has never seen** (split by `subject`), so the score is honest.
- [ ] Hardware: get the board reading motion data and printing it to the laptop.
- [ ] Connect the pieces: board → laptop → model → alert (a vibration, a sound, or a message on screen).
- [ ] Commit to Git every time something works.

**Done when:** waving your hand does nothing, and a BFRB-like movement triggers an alert, at least most of the time.

## Submission (Nov 15 – 18)

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

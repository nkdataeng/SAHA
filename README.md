# SAHA

A wrist-worn awareness prototype for body-focused repetitive behaviors (BFRBs), such as hair pulling, skin picking and nail biting.

SAHA is an awareness tool, not a medical device or treatment.

Built for the T-Minus30 sprint by Genesis. See [PLAN.md](PLAN.md) for the plan, [HARDWARE.md](HARDWARE.md) for how to build the wearable, and [docs/HOW_SAHA_WORKS.md](docs/HOW_SAHA_WORKS.md) for a plain-language explanation of the sensor, the data and the models.

## Data

This project uses the Child Mind Institute "Detect Behavior with Sensor Data" dataset from Kaggle. The data is not stored in this repository. Download it from [the competition page](https://www.kaggle.com/competitions/cmi-detect-behavior-with-sensor-data/data) and place it in `data/`.

**Citation:** CMI 2025 Detect Behavior with Sensor Data Challenge

### Data rules

The dataset is licensed CC BY-NC-SA 4.0 under the [competition rules](https://www.kaggle.com/competitions/cmi-detect-behavior-with-sensor-data/rules). In short:

- **Non-commercial use only** (research and education). SAHA must not make money from this data or anything trained on it.
- **Never share the data.** Don't commit it, upload it or give it to anyone. This includes the trained model in `models/`.
- **Never try to identify participants.**
- **Always cite it** as above, including on slides and at demos.
- Before making this repository public, clear notebook outputs that show individual participants' recordings.

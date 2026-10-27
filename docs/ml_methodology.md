# ML methodology: three cardiovascular classifiers

_Generated numbers come from `outputs/tables/clinical_results.json`; re-run `run_pipeline.py` to refresh them._

## 1. Task and data

**Task.** Binary classification: does a patient record belong to the "heart disease present" class (`target = 1`)?

**Dataset.** Doppala, B. P. & Bhattacharyya, D. (2021). *Cardiovascular_Disease_Dataset*, Mendeley Data V1,
doi:10.17632/dzz48mvjht.1. 1,000 patients from one multispecialty hospital in India; 12 predictors, a patient id and
a binary target. 58% of records are positive.

**What the dataset is not.** It is Indian but not Mumbai-specific, has no location field, and comes from a single
hospital. It is never joined to Mumbai wards, and nothing in the app infers ward-level heart-disease prevalence.

**Provenance caveat.** Mendeley and Kaggle were blocked from the build environment, so the CSV was taken from a public
GitHub copy and checked against the published schema (1,000 rows, 14 columns, documented codes). Its SHA-256 is
`db6fdd9250e1717037cc3daa2b38f7e42451fd8e655b802985d28d7fcbf78110`. To confirm, download the original from Mendeley,
save it as `data/raw/clinical/Cardiovascular_Disease_Dataset.csv` and re-run the pipeline.

| Field | Meaning | Treated as |
|---|---|---|
| age | years | numeric, scaled |
| gender | 0 female, 1 male | binary |
| chestpain | 0 typical angina, 1 atypical, 2 non-anginal, 3 asymptomatic | nominal, one-hot |
| restingBP | mm Hg | numeric, scaled |
| serumcholestrol | mg/dl | numeric, scaled (0 = missing) |
| fastingbloodsugar | > 120 mg/dl | binary |
| restingrelectro | 0 normal, 1 ST-T abnormality, 2 LV hypertrophy | nominal, one-hot |
| maxheartrate | bpm | numeric, scaled |
| exerciseangia | exercise-induced angina | binary |
| oldpeak | ST depression | numeric, scaled |
| slope | 1 up, 2 flat, 3 down | nominal, one-hot (0 = missing) |
| noofmajorvessels | 0–3 | count, scaled |
| hr_reserve_pct | engineered: maxheartrate / (220 − age) × 100 | numeric, scaled |

## 2. Cleaning (`src/clinical_data.py`)

1. **Schema check.** The column names and order must match the data dictionary, or the run stops.
2. **Duplicates.** Exact rows, duplicate patient ids and duplicate predictor + target rows: 0 of each. So no patient
   can appear in both the training and the test set; a test asserts this.
3. **Special missing-value markers.**
   * `serumcholestrol = 0` (53 rows) is physiologically impossible, so it is set to missing.
   * `slope = 0` (180 rows) is outside the documented codes 1–3, so it is set to missing.
   * Both markers are almost perfectly tied to the target (cholesterol 0: 100% positive; slope 0: 0% positive). This
     looks like a recording artifact, and it is reported rather than exploited.
4. **Range checks.** Numeric fields are checked against wide plausibility ranges. Nothing else is out of range.
5. **Imputation.** Missing values are imputed inside the model pipeline (median for numeric fields, most frequent for
   coded fields), so the fill values are learned from training folds only.

## 3. Split, preprocessing and tuning (`src/clinical_models.py`, `src/clinical_pipeline.py`)

* **Split.** A stratified 80/20 split (800 / 200) with seed 42. Both sets have a 58% positive rate.
* **One shared pipeline.** Each model is `FunctionTransformer(add_features) → ColumnTransformer(impute + scale
  numeric, impute binary, impute + one-hot nominal) → model`. Every transformation is fitted inside the pipeline. The
  saved `models/clinical_*.joblib` therefore applies exactly the training transformations at prediction time.
* **Tuning.** `GridSearchCV` with 5-fold stratified CV on the **training set only**, scored by ROC-AUC. The test set
  is used once, after tuning.

| Model | Why it was chosen | Grid | Chosen |
|---|---|---|---|
| Logistic Regression | Linear, interpretable baseline (log-odds coefficients) | C ∈ {0.01, 0.1, 1, 10} | C = 10 |
| Random Forest | Non-linear, captures interactions, gives importances | depth ∈ {None, 4, 8}, min leaf ∈ {1, 3, 5}, 300 trees | depth 8, leaf 1 |
| ANN (MLP) | Small feed-forward network for non-linear patterns | hidden ∈ {(16), (32), (32,16)}, alpha ∈ {1e-4 … 0.1} | (32), alpha 0.1 |

The ANN is kept small on purpose: 800 training rows do not support a deep network. Its learning curves (training vs
validation log loss per epoch) come from an inner 640/160 split of the training data, so the test set stays untouched.

## 4. Results on the held-out test set (200 patients)

| Model | Accuracy | Precision | Recall | Specificity | F1 | ROC-AUC | Brier | CV ROC-AUC |
|---|---|---|---|---|---|---|---|---|
| Logistic Regression | 0.890 | 0.898 | 0.914 | 0.857 | 0.906 | 0.968 | 0.070 | 0.974 ± 0.017 |
| Random Forest | **0.955** | **0.957** | **0.966** | **0.941** | **0.961** | **0.992** | **0.040** | 0.992 ± 0.006 |
| ANN (MLP) | 0.935 | 0.948 | 0.940 | 0.929 | 0.944 | 0.986 | 0.047 | 0.983 ± 0.010 |
| Majority-class baseline | 0.580 | | | | | | | |

Confusion matrices (TN / FP / FN / TP): LR 72 / 12 / 10 / 106 · RF 79 / 5 / 4 / 112 · ANN 78 / 6 / 7 / 109.
All three models are right for 174 of the 200 test patients.

**Explanations shown in the Power BI report (Model performance page) and the API (`/api/models`):**
* Logistic Regression coefficients.
* Random Forest impurity importance.
* Permutation importance for all three models: the drop in test ROC-AUC when one input is shuffled.
* Calibration curves.
* ROC curves.
* An actual-versus-predicted table.

## 5. Why the scores are this high, and what that means

The scores are much higher than on typical heart-disease benchmarks. The main reason is that `slope` almost
separates the classes in this file: code 2–3 means nearly always positive, code 1 is 24% positive, and the undocumented
code 0 is always negative. Retraining without `slope` gives ROC-AUC 0.948 (LR), 0.989 (RF) and 0.982 (ANN). The other
fields also carry strong signal, but the result reflects this one hospital's records and coding. It is not evidence of
real-world diagnostic performance.

## 6. Limitations

* There is one hospital and no external validation. Performance on other populations, including Mumbai's, is
  unknown.
* The undocumented codes (slope 0, cholesterol 0) are treated as missing. Their tie to the target suggests a
  data-entry pattern we cannot verify.
* A threshold of 0.5 is used throughout. No cost-sensitive threshold was chosen, because the clinical costs of false
  negatives and false positives are not known here.
* Predictions are **experimental and not clinically validated**. Model agreement is not certainty, because the three
  models learn from the same data.

## 7. The ward clustering (kept, demoted)

The earlier K-Means clustering of the 24 wards is still in the pipeline (`ward_clusters.csv`, cluster names in the Power BI ward data)
as an exploratory description of facility provision (see `docs/model_card.md`). It is **not** one of the three
project models.

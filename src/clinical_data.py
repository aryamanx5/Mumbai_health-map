"""Clinical dataset (Doppala & Bhattacharyya 2021): load, profile and clean, without modifying the raw file.

Source: Mendeley Data, "Cardiovascular_Disease_Dataset", doi:10.17632/dzz48mvjht.1 (1,000 patients from one
multispecialty hospital in India; 12 predictors, binary target). The dataset is Indian but NOT Mumbai-specific and
has no geography, so it is never joined to wards.
"""
import hashlib

import numpy as np
import pandas as pd

from .config import RAW

CLINICAL_RAW = RAW / "clinical" / "Cardiovascular_Disease_Dataset.csv"
SOURCE = dict(
    title="Cardiovascular_Disease_Dataset",
    authors="Bhanu Prakash Doppala; Debnath Bhattacharyya",
    year=2021, publisher="Mendeley Data, V1", doi="10.17632/dzz48mvjht.1",
    url="https://data.mendeley.com/datasets/dzz48mvjht/1",
    mirror_used="https://raw.githubusercontent.com/Tayebbb/cardiovascular-disease-classification/master/"
                "cardiovascular_disease_dataset.csv",
    note="Mendeley and Kaggle were unreachable from the build environment, so the file was taken from a public "
         "GitHub copy and checked against the published schema (1,000 rows, 14 columns, documented codes). "
         "Replace data/raw/clinical/Cardiovascular_Disease_Dataset.csv with the Mendeley download and re-run to "
         "confirm; the SHA-256 is recorded in the quality report.",
)

ID = "patientid"
TARGET = "target"
# Data dictionary from the dataset's Mendeley description: (label, kind, documented codes or a plausibility range
# for numeric fields; numeric ranges are deliberately wide so real extreme values are kept).
DICTIONARY = {
    "age": ("Age (years)", "numeric", (18, 100)),
    "gender": ("Sex (0 = female, 1 = male)", "binary", (0, 1)),
    "chestpain": ("Chest pain type", "nominal", {0: "Typical angina", 1: "Atypical angina",
                                                 2: "Non-anginal pain", 3: "Asymptomatic"}),
    "restingBP": ("Resting blood pressure (mm Hg)", "numeric", (94, 200)),
    "serumcholestrol": ("Serum cholesterol (mg/dl)", "numeric", (80, 700)),
    "fastingbloodsugar": ("Fasting blood sugar > 120 mg/dl", "binary", (0, 1)),
    "restingrelectro": ("Resting ECG", "nominal", {0: "Normal", 1: "ST-T wave abnormality",
                                                   2: "Left ventricular hypertrophy"}),
    "maxheartrate": ("Maximum heart rate achieved (bpm)", "numeric", (71, 202)),
    "exerciseangia": ("Exercise-induced angina", "binary", (0, 1)),
    "oldpeak": ("ST depression induced by exercise (oldpeak)", "numeric", (0, 6.2)),
    "slope": ("Slope of peak exercise ST segment", "nominal", {1: "Upsloping", 2: "Flat", 3: "Downsloping"}),
    "noofmajorvessels": ("Major vessels coloured by fluoroscopy (0-3)", "count", (0, 3)),
}
PREDICTORS = list(DICTIONARY)
NUMERIC = ["age", "restingBP", "serumcholestrol", "maxheartrate", "oldpeak", "noofmajorvessels"]
BINARY = ["gender", "fastingbloodsugar", "exerciseangia"]
NOMINAL = ["chestpain", "restingrelectro", "slope"]
# Physiologically impossible or undocumented codes recoded to missing (never silently dropped).
MISSING_MARKERS = {"serumcholestrol": [0], "slope": [0]}


def sha256(path=CLINICAL_RAW):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_raw(path=CLINICAL_RAW):
    df = pd.read_csv(path)
    expected = [ID] + PREDICTORS + [TARGET]
    if list(df.columns) != expected:
        raise ValueError(f"unexpected columns {list(df.columns)}; expected {expected}")
    return df


def _out_of_range(s, spec):
    if isinstance(spec, dict):
        return ~s.isin(list(spec)) & s.notna()
    lo, hi = spec
    return ((s < lo) | (s > hi)) & s.notna()


def profile(df):
    """Per-column profile: dtype, missing, zeros, distinct values, range and out-of-documented-range counts."""
    rows = []
    for c in df.columns:
        s = df[c]
        spec = DICTIONARY.get(c, (None, None, None))[2]
        rows.append(dict(
            column=c, label=DICTIONARY.get(c, (c,))[0], kind=DICTIONARY.get(c, (None, "id" if c == ID else "target"))[1],
            dtype=str(s.dtype), n=int(s.size), missing=int(s.isna().sum()), zeros=int((s == 0).sum()),
            distinct=int(s.nunique()), min=float(s.min()), max=float(s.max()),
            mean=round(float(s.mean()), 3), std=round(float(s.std()), 3), median=float(s.median()),
            out_of_documented_range=int(_out_of_range(s, spec).sum()) if spec is not None else 0,
        ))
    return pd.DataFrame(rows)


def clean(raw):
    """Returns (clean, log). Missing markers become NaN; imputation happens later, inside the training pipeline."""
    df = raw.copy()
    log = []

    def step(name, n, detail):
        log.append(dict(step=len(log) + 1, action=name, records_affected=int(n), detail=detail))

    step("Validate schema", 0, f"{len(df.columns)} columns match the published data dictionary")
    exact = df.duplicated().sum()
    dup_ids = df[ID].duplicated().sum()
    dup_feat = df.drop(columns=[ID]).duplicated().sum()
    step("Exact duplicate rows", exact, "none removed" if not exact else "removed")
    step("Duplicate patient ids", dup_ids, "patient-level leakage check across train/test")
    step("Duplicate predictor+target rows (ignoring id)", dup_feat,
         "would leak identical records across the split" if dup_feat else "no identical records")
    df = df.drop_duplicates()

    for col, markers in MISSING_MARKERS.items():
        mask = df[col].isin(markers)
        rate = df.loc[mask, TARGET].mean() if mask.any() else np.nan
        step(f"Recode {col} = {markers} to missing", mask.sum(),
             f"outside the documented range; target rate among these rows = {rate:.2f} "
             f"(vs {df[TARGET].mean():.2f} overall), so the code looks like a recording artifact")
        df.loc[mask, col] = np.nan

    for col in PREDICTORS:
        bad = _out_of_range(df[col], DICTIONARY[col][2])
        if bad.any():
            step(f"Out-of-range {col}", bad.sum(), "set to missing")
            df.loc[bad, col] = np.nan

    df = df.drop(columns=[ID])
    step("Drop identifier", 0, f"'{ID}' is not a predictor")
    df[TARGET] = df[TARGET].astype(int)
    step("Binary target", 0, "target: 1 = heart disease present, 0 = absent (as published)")
    return df.reset_index(drop=True), pd.DataFrame(log)


def add_features(df):
    """Engineered feature: share of age-predicted maximum heart rate achieved (max HR / (220 - age))."""
    df = df.copy()
    df["hr_reserve_pct"] = df["maxheartrate"] / (220 - df["age"]) * 100
    return df


ENGINEERED = ["hr_reserve_pct"]

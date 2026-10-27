"""Clinical pipeline tests: cleaning rules on small frames, plus checks on the real saved models and outputs."""
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import roc_auc_score

from src.clinical_data import ID, PREDICTORS, TARGET, add_features, clean, load_raw, profile
from src.clinical_models import MODELS, feature_names, make_pipeline
from src.config import MODELS as MODEL_DIR, PROCESSED, TABLES


def tiny():
    rows = []
    for i in range(40):
        rows.append({ID: 1000 + i, "age": 30 + i, "gender": i % 2, "chestpain": i % 4, "restingBP": 120 + i,
                     "serumcholestrol": 0 if i == 0 else 200 + i, "fastingbloodsugar": i % 2, "restingrelectro": i % 3,
                     "maxheartrate": 150 - i, "exerciseangia": (i // 2) % 2, "oldpeak": (i % 6) * 0.5,
                     "slope": 0 if i == 1 else 1 + i % 3, "noofmajorvessels": i % 4, TARGET: i % 2})
    return pd.DataFrame(rows)


def test_raw_file_schema_and_size():
    raw = load_raw()
    assert raw.shape == (1000, 14)
    assert raw[ID].is_unique
    assert set(raw[TARGET]) == {0, 1}


def test_markers_become_missing_not_zero():
    cleaned, log = clean(tiny())
    assert np.isnan(cleaned.loc[0, "serumcholestrol"])
    assert np.isnan(cleaned.loc[1, "slope"])
    assert ID not in cleaned.columns
    assert cleaned[TARGET].dtype.kind == "i"
    assert (log["action"].str.contains("Recode serumcholestrol")).any()


def test_profile_counts_out_of_range():
    p = profile(tiny()).set_index("column")
    assert p.loc["serumcholestrol", "out_of_documented_range"] == 1
    assert p.loc["slope", "out_of_documented_range"] == 1


def test_engineered_feature():
    df = add_features(pd.DataFrame({"age": [40], "maxheartrate": [180]}))
    assert df["hr_reserve_pct"].iloc[0] == pytest.approx(100.0)


@pytest.mark.parametrize("key", list(MODELS))
def test_pipeline_handles_missing_and_onehot(key):
    cleaned, _ = clean(tiny())
    pipe = make_pipeline(key).fit(cleaned[PREDICTORS], cleaned[TARGET])
    p = pipe.predict_proba(cleaned[PREDICTORS])[:, 1]
    assert np.isfinite(p).all() and ((0 <= p) & (p <= 1)).all()
    names = feature_names(pipe)
    assert "slope_1.0" in names or "slope_1" in names  # nominal fields are one-hot, not ordinal
    assert "slope" not in names


@pytest.fixture(scope="module")
def saved():
    return {k: joblib.load(MODEL_DIR / f"clinical_{k}.joblib") for k in MODELS}


@pytest.fixture(scope="module")
def results():
    return json.loads((TABLES / "clinical_results.json").read_text())


def test_three_models_saved(saved):
    assert set(saved) == {"logistic_regression", "random_forest", "ann"}
    for art in saved.values():
        assert art["predictors"] == PREDICTORS


def test_saved_models_reproduce_reported_test_metrics(saved, results):
    df = pd.read_csv(PROCESSED / "clinical" / "clinical_clean.csv")
    test = df[df["split"] == "test"]
    assert len(test) == results["summary"]["n_test"]
    for k, art in saved.items():
        auc = roc_auc_score(test[TARGET], art["pipeline"].predict_proba(test[PREDICTORS])[:, 1])
        assert auc == pytest.approx(results["models"][k]["test"]["roc_auc"], abs=1e-4)


def test_no_patient_in_both_splits():
    df = pd.read_csv(PROCESSED / "clinical" / "clinical_clean.csv")
    assert not set(df.loc[df.split == "train", "patientid"]) & set(df.loc[df.split == "test", "patientid"])


def test_stratified_split(results):
    s = results["summary"]
    assert abs(s["positive_rate_train"] - s["positive_rate_test"]) < 0.01


def test_confusion_matrix_totals(results):
    for m in results["models"].values():
        assert sum(m["test"]["confusion"].values()) == results["summary"]["n_test"]


def test_models_beat_majority_baseline(results):
    for m in results["models"].values():
        assert m["test"]["accuracy"] > results["summary"]["majority_baseline_accuracy"]

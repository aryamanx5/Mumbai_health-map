"""Loads pipeline outputs and the saved models once. Nothing here retrains anything."""
import json
from functools import lru_cache

import joblib
import pandas as pd

from src.clinical_data import PREDICTORS
from src.config import MODELS, PROCESSED, ROOT, TABLES

MODEL_KEYS = ["logistic_regression", "random_forest", "ann"]
DISCLAIMER = ("Experimental, for education only. These models were trained on one historical dataset of 1,000 "
              "patients from a single hospital in India. They are not clinically validated, are not a screening or "
              "diagnostic tool, and agreement between models does not make a prediction certain. "
              "Consult a qualified doctor for any health concern.")


class NotReady(RuntimeError):
    pass


def _json(path):
    if not path.exists():
        raise NotReady(f"{path.relative_to(ROOT)} is missing. Run run_pipeline.py first.")
    return json.loads(path.read_text())


def _csv(path, **kw):
    if not path.exists():
        raise NotReady(f"{path.relative_to(ROOT)} is missing. Run run_pipeline.py first.")
    return pd.read_csv(path, **kw)


@lru_cache
def models():
    out = {}
    for k in MODEL_KEYS:
        p = MODELS / f"clinical_{k}.joblib"
        if not p.exists():
            raise NotReady(f"models/clinical_{k}.joblib is missing. Run run_pipeline.py first.")
        out[k] = joblib.load(p)
    return out


@lru_cache
def clinical_results():
    return _json(TABLES / "clinical_results.json")


@lru_cache
def clinical_quality():
    return _json(TABLES / "clinical_quality.json")


@lru_cache
def geo_summary():
    return _json(TABLES / "data_summary.json")


@lru_cache
def boundary_summary():
    return _json(TABLES / "boundary_crosscheck.json")


@lru_cache
def wards():
    return _csv(ROOT / "powerbi" / "data" / "dim_ward.csv", dtype={"ward_id": str})


@lru_cache
def facilities():
    return _csv(ROOT / "powerbi" / "data" / "fact_facility.csv", dtype={"ward_id": str})


@lru_cache
def hospital_list():
    return _csv(PROCESSED / "hospital_list_clean.csv", dtype={"ward_id": str})


def table(name):
    return _csv(TABLES / name)


def records(df):
    """DataFrame -> JSON-safe records (NaN becomes null)."""
    return json.loads(df.to_json(orient="records"))


def predict(patient: dict):
    X = pd.DataFrame([{c: patient.get(c) for c in PREDICTORS}]).astype(float)
    res = clinical_results()
    preds = []
    for k, art in models().items():
        p = float(art["pipeline"].predict_proba(X)[0, 1])
        thr = res["summary"]["threshold"]
        preds.append(dict(model=res["models"][k]["short"], label=art["label"], probability=round(p, 4),
                          predicted_class=int(p >= thr),
                          predicted_label="Heart disease indicated" if p >= thr else "No heart disease indicated",
                          test_roc_auc=res["models"][k]["test"]["roc_auc"],
                          test_accuracy=res["models"][k]["test"]["accuracy"]))
    probs = [p["probability"] for p in preds]
    return dict(predictions=preds, models_predicting_disease=sum(p["predicted_class"] for p in preds),
                mean_probability=round(sum(probs) / len(probs), 4), probability_spread=round(max(probs) - min(probs), 4),
                threshold=res["summary"]["threshold"],
                imputed_fields=[c for c in PREDICTORS if patient.get(c) is None], disclaimer=DISCLAIMER)

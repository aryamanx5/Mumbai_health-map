"""Power BI tables for the cardiovascular models, the clinical data and data quality.

Adds to the Mumbai star schema written by export_reporting.py. Everything is read from pipeline outputs, so
re-running run_pipeline.py refreshes the report data. Readable labels replace the dataset's numeric codes.
"""
import json

import pandas as pd

from .config import PROCESSED, ROOT
from .export_reporting import OUT

TABLES = ROOT / "outputs" / "tables"
MODEL_ORDER = ["logistic_regression", "random_forest", "ann"]
MODEL_COLORS = {"logistic_regression": "#3987E5", "random_forest": "#D95926", "ann": "#199E70"}
METRICS = [("accuracy", "Accuracy"), ("precision", "Precision"), ("recall", "Recall"),
           ("specificity", "Specificity"), ("f1", "F1"), ("roc_auc", "ROC-AUC")]
FEATURE_LABELS = {
    "age": "Age", "gender": "Sex", "chestpain": "Chest pain type", "restingBP": "Resting BP",
    "serumcholestrol": "Cholesterol", "fastingbloodsugar": "Fasting blood sugar", "restingrelectro": "Resting ECG",
    "maxheartrate": "Max heart rate", "exerciseangia": "Exercise angina", "oldpeak": "ST depression (oldpeak)",
    "slope": "ST slope", "noofmajorvessels": "Major vessels", "hr_reserve_pct": "Heart-rate reserve %",
}
AGE_BANDS = [(0, 30, "Under 30"), (30, 40, "30-39"), (40, 50, "40-49"), (50, 60, "50-59"), (60, 70, "60-69"),
             (70, 200, "70+")]


def _age_band(age):
    for i, (lo, hi, label) in enumerate(AGE_BANDS):
        if lo <= age < hi:
            return label, i + 1


def clinical_patient(quality):
    codes = {k: v["codes"] for k, v in quality["dictionary"].items() if v["codes"]}
    df = pd.read_csv(PROCESSED / "clinical" / "clinical_clean.csv")
    out = pd.DataFrame({"patientid": df["patientid"], "split": df["split"].str.capitalize(), "age": df["age"]})
    bands = df["age"].map(_age_band)
    out["age_band"] = bands.str[0]
    out["age_band_order"] = bands.str[1]
    out["sex"] = df["gender"].map({0: "Female", 1: "Male"})
    out["chest_pain"] = df["chestpain"].astype(int).astype(str).map(codes["chestpain"])
    out["resting_bp"] = df["restingBP"]
    out["cholesterol"] = df["serumcholestrol"]
    out["cholesterol_recorded"] = df["serumcholestrol"].notna().map({True: "Recorded", False: "Not recorded (code 0)"})
    out["fasting_blood_sugar"] = df["fastingbloodsugar"].map({0: "120 mg/dl or less", 1: "Over 120 mg/dl"})
    out["resting_ecg"] = df["restingrelectro"].astype(int).astype(str).map(codes["restingrelectro"])
    out["max_heart_rate"] = df["maxheartrate"]
    out["exercise_angina"] = df["exerciseangia"].map({0: "No", 1: "Yes"})
    out["st_depression"] = df["oldpeak"]
    out["st_slope"] = df["slope"].map(lambda s: codes["slope"][str(int(s))] if pd.notna(s) else "Not recorded (code 0)")
    out["major_vessels"] = df["noofmajorvessels"].astype(int)
    out["target"] = df["target"].astype(int)
    out["outcome"] = df["target"].map({0: "No heart disease", 1: "Heart disease"})
    return out


def model_tables(res):
    dim, metric, confusion, roc, importance = [], [], [], [], []
    for i, key in enumerate(MODEL_ORDER):
        m = res["models"][key]
        name = m["label"]
        params = ", ".join(f"{k} = {v}" for k, v in m["best_params"].items())
        dim.append(dict(model=name, short=m["short"], sort_order=i + 1, color=MODEL_COLORS[key], why=m["why"],
                        chosen_settings=params))
        for j, (k, label) in enumerate(METRICS):
            metric.append(dict(model=name, set="Test", metric=label, metric_order=j + 1, value=m["test"][k]))
            if k in m["cv"]:
                cv = m["cv"][k]
                metric.append(dict(model=name, set="5-fold CV", metric=label, metric_order=j + 1,
                                   value=cv["mean"] if isinstance(cv, dict) else cv))
        c = m["test"]["confusion"]
        for cell, actual, predicted, order in [("tn", "No heart disease", "No heart disease", 1),
                                               ("fp", "No heart disease", "Heart disease", 2),
                                               ("fn", "Heart disease", "No heart disease", 3),
                                               ("tp", "Heart disease", "Heart disease", 4)]:
            label = {"tn": "True negative", "fp": "False positive", "fn": "False negative", "tp": "True positive"}[cell]
            confusion.append(dict(model=name, cell=label, cell_order=order, actual=actual, predicted=predicted,
                                  patients=c[cell]))
        for p, (fpr, tpr) in enumerate(zip(m["roc"]["fpr"], m["roc"]["tpr"])):
            roc.append(dict(model=name, point=p, fpr=fpr, tpr=tpr))
        for f in m["permutation_importance"]:
            importance.append(dict(model=name, feature=FEATURE_LABELS.get(f["feature"], f["feature"]),
                                   importance=f["mean"], importance_std=f["std"]))
    return (pd.DataFrame(dim), pd.DataFrame(metric), pd.DataFrame(confusion), pd.DataFrame(roc),
            pd.DataFrame(importance))


def test_prediction(res):
    df = pd.read_csv(PROCESSED / "clinical" / "test_predictions.csv")
    names = {res["models"][k]["short"]: res["models"][k]["label"] for k in MODEL_ORDER}
    rows = []
    for short, name in names.items():
        part = pd.DataFrame({"patientid": df["patientid"], "model": name,
                             "actual": df["actual"].map({0: "No heart disease", 1: "Heart disease"}),
                             "probability": df[f"{short}_probability"],
                             "predicted": df[f"{short}_predicted"].map({0: "No heart disease", 1: "Heart disease"})})
        part["correct"] = (df[f"{short}_predicted"] == df["actual"]).map({True: "Correct", False: "Wrong"})
        part["models_predicting_disease"] = df["models_agreeing"]
        rows.append(part)
    return pd.concat(rows, ignore_index=True)


def quality_tables(quality, geo):
    log = pd.DataFrame(quality["cleaning_log"]).rename(columns={"records_affected": "records"})
    log.insert(0, "dataset", "Clinical")
    geo_steps = [
        ("Read the four MCGM facility layers", geo["raw_records_total"], "dispensaries, UPHCs, public hospitals, maternity homes"),
        ("Exclude invalid records", geo["excluded_records"], "none excluded"),
        ("Merge co-located facilities into sites", geo["master_records"] - geo["distinct_sites"],
         f"{geo['master_records']} records become {geo['distinct_sites']} distinct sites"),
        ("Records with no coordinates", geo["coordinate_status"].get("missing", 0), "kept, ward taken from the source"),
        ("Ward assignment needing review", geo["assignment_check"].get("disagree_review", 0)
         + geo["assignment_check"].get("outside_polygons_review", 0), "point-in-polygon check against the source ward"),
        ("Read the MCGM hospitals list", geo["hospital_csv"]["csv_rows"], "ownership types grouped to Public / Private / Trust"),
        ("Hospitals list rows with no bed count", geo.get("hospital_list_beds_missing", 0), "kept, beds left blank"),
    ]
    g = pd.DataFrame([dict(dataset="Mumbai facilities", step=i + 1, action=a, records=n, detail=d)
                      for i, (a, n, d) in enumerate(geo_steps)])
    cleaning = pd.concat([log, g], ignore_index=True)

    stages = [("Raw file", "missing_before"), ("After recoding 0 codes", "missing_after_recode"),
              ("After imputation (in pipeline)", "missing_after_imputation")]
    missing = []
    for order, (stage, key) in enumerate(stages):
        for field, n in quality[key].items():
            missing.append(dict(field=FEATURE_LABELS.get(field, field), stage=stage, stage_order=order + 1, missing=n))
    missing = pd.DataFrame(missing)
    # Only the fields that were ever missing; the other ten are complete at every stage.
    ever = missing.groupby("field")["missing"].transform("max") > 0
    return cleaning, missing[ever]


def hospital_list():
    h = pd.read_csv(PROCESSED / "hospital_list_clean.csv")
    h["beds"] = h["beds"].astype("Int64")
    return h[["csv_row", "ward_id", "hospital_name", "address", "ownership_type", "ownership_class", "beds",
              "match_status"]]


def run():
    res = json.loads((TABLES / "clinical_results.json").read_text())
    quality = json.loads((TABLES / "clinical_quality.json").read_text())
    geo = json.loads((TABLES / "data_summary.json").read_text())
    dim_model, metric, confusion, roc, importance = model_tables(res)
    cleaning, missing = quality_tables(quality, geo)
    tables = dict(clinical_patient=clinical_patient(quality), dim_model=dim_model, model_metric=metric,
                  model_confusion=confusion, model_roc=roc, model_importance=importance,
                  test_prediction=test_prediction(res), cleaning_log=cleaning, missing_values=missing,
                  hospital_list=hospital_list())
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False)
    assert len(tables["clinical_patient"]) == quality["rows"]["clean"]
    assert len(tables["test_prediction"]) == 3 * quality["rows"]["test"]
    assert tables["model_confusion"].groupby("model")["patients"].sum().eq(quality["rows"]["test"]).all()
    return {k: len(v) for k, v in tables.items()}

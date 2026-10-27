"""Clinical stage: profile -> clean -> split -> tune and train LR / RF / ANN -> evaluate -> save artifacts.

Usage:  .venv/bin/python -m src.clinical_pipeline
"""
import json
import time

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.base import clone
from sklearn.calibration import calibration_curve
from sklearn.inspection import permutation_importance
from sklearn.metrics import (accuracy_score, brier_score_loss, confusion_matrix, f1_score, precision_score,
                             recall_score, roc_auc_score, roc_curve)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_validate, train_test_split

from . import plot_style as ps
from .clinical_data import (DICTIONARY, NOMINAL, PREDICTORS, SOURCE, TARGET, clean, load_raw, profile, sha256)
from .clinical_models import (CV_FOLDS, MODELS, SCORING, TEST_SIZE, ann_learning_curves, feature_names,
                              make_pipeline)
from .config import FIGURES, MODELS as MODEL_DIR, PROCESSED, RANDOM_SEED, TABLES

CLIN_PROCESSED = PROCESSED / "clinical"
RESULTS_JSON = TABLES / "clinical_results.json"
QUALITY_JSON = TABLES / "clinical_quality.json"


def _metrics(y, p, thr=0.5):
    yhat = (p >= thr).astype(int)
    tn, fp, fn, tp = confusion_matrix(y, yhat, labels=[0, 1]).ravel()
    return dict(accuracy=accuracy_score(y, yhat), precision=precision_score(y, yhat, zero_division=0),
                recall=recall_score(y, yhat), specificity=tn / (tn + fp) if tn + fp else float("nan"),
                f1=f1_score(y, yhat), roc_auc=roc_auc_score(y, p), brier=brier_score_loss(y, p),
                confusion=dict(tn=int(tn), fp=int(fp), fn=int(fn), tp=int(tp)))


def _r(x, d=4):
    if isinstance(x, dict):
        return {k: _r(v, d) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_r(v, d) for v in x]
    if isinstance(x, (float, np.floating)):
        return None if np.isnan(x) else round(float(x), d)
    if isinstance(x, np.integer):
        return int(x)
    return x


def _distributions(raw, cleaned):
    """Histogram bins for numeric fields (raw vs cleaned) and value counts for coded fields."""
    out = {}
    for c in PREDICTORS:
        kind = DICTIONARY[c][1]
        if kind == "numeric":
            lo, hi = float(raw[c].min()), float(raw[c].max())
            edges = np.linspace(lo, hi, 16)
            out[c] = dict(kind="numeric", edges=edges.round(2).tolist(),
                          raw=np.histogram(raw[c], edges)[0].tolist(),
                          clean=np.histogram(cleaned[c].dropna(), edges)[0].tolist())
        else:
            codes = sorted(set(raw[c].dropna().astype(int)))
            labels = DICTIONARY[c][2] if isinstance(DICTIONARY[c][2], dict) else {}
            out[c] = dict(kind=kind, codes=codes, labels=[labels.get(k, f"code {k}") for k in codes],
                          raw=[int((raw[c] == k).sum()) for k in codes],
                          clean=[int((cleaned[c] == k).sum()) for k in codes],
                          target_rate=[_r(raw.loc[raw[c] == k, TARGET].mean(), 3) for k in codes])
    return out


def _plots(results, curves):
    ps.apply()
    fig, ax = plt.subplots(figsize=(5.5, 5))
    for i, (k, r) in enumerate(results.items()):
        ax.plot(r["roc"]["fpr"], r["roc"]["tpr"], color=ps.SERIES[i], lw=2,
                label=f"{MODELS[k]['short']} (AUC {r['test']['roc_auc']:.3f})")
    ax.plot([0, 1], [0, 1], ls="--", color=ps.NEUTRAL, lw=1)
    ax.set_xlabel("False positive rate")
    ax.set_ylabel("True positive rate")
    ax.set_title("ROC curves, held-out test set")
    ax.legend(loc="lower right")
    fig.savefig(FIGURES / "13_clinical_roc.png")
    plt.close(fig)

    fig, axes = plt.subplots(1, 3, figsize=(11, 3.6))
    for ax, (k, r) in zip(axes, results.items()):
        c = r["test"]["confusion"]
        m = np.array([[c["tn"], c["fp"]], [c["fn"], c["tp"]]])
        ax.imshow(m, cmap="Blues")
        for (i, j), v in np.ndenumerate(m):
            ax.text(j, i, v, ha="center", va="center", fontsize=13, color="white" if v > m.max() / 2 else ps.TEXT)
        ax.set_xticks([0, 1], ["Pred. no", "Pred. yes"])
        ax.set_yticks([0, 1], ["Actual no", "Actual yes"])
        ax.set_title(MODELS[k]["short"])
        ax.grid(False)
    fig.savefig(FIGURES / "14_clinical_confusion.png")
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.plot(curves["epoch"], curves["train_loss"], color=ps.SERIES[0], lw=2, label="training")
    ax.plot(curves["epoch"], curves["val_loss"], color=ps.SERIES[1], lw=2, label="validation")
    ax.set_xlabel("Epoch")
    ax.set_ylabel("Log loss")
    ax.set_title("ANN learning curves (inner split of the training set)")
    ax.legend()
    fig.savefig(FIGURES / "15_clinical_ann_loss.png")
    plt.close(fig)


def run(verbose=True):
    t0 = time.time()
    for d in (CLIN_PROCESSED, TABLES, MODEL_DIR, FIGURES):
        d.mkdir(parents=True, exist_ok=True)

    raw = load_raw()
    raw_profile = profile(raw)
    cleaned, log = clean(raw)
    clean_profile = profile(cleaned)

    X, y = cleaned[PREDICTORS], cleaned[TARGET].to_numpy()
    idx_train, idx_test = train_test_split(np.arange(len(cleaned)), test_size=TEST_SIZE, stratify=y,
                                           random_state=RANDOM_SEED)
    X_train, X_test, y_train, y_test = X.iloc[idx_train], X.iloc[idx_test], y[idx_train], y[idx_test]
    ids = raw.loc[cleaned.index, "patientid"].to_numpy()
    assert not set(ids[idx_train]) & set(ids[idx_test]), "patient id appears in both train and test"
    log = pd.concat([log, pd.DataFrame([dict(
        step=len(log) + 1, action="Stratified train/test split", records_affected=len(cleaned),
        detail=f"{len(idx_train)} train / {len(idx_test)} test, seed {RANDOM_SEED}; 0 patient ids shared. "
               "Imputation, scaling and encoding are fitted on training folds only.")])], ignore_index=True)

    cleaned.assign(split=np.where(np.isin(np.arange(len(cleaned)), idx_train), "train", "test"),
                   patientid=ids).to_csv(CLIN_PROCESSED / "clinical_clean.csv", index=False)

    cv = StratifiedKFold(CV_FOLDS, shuffle=True, random_state=RANDOM_SEED)
    results, fitted = {}, {}
    for key, spec in MODELS.items():
        search = GridSearchCV(make_pipeline(key), spec["grid"], scoring=SCORING, cv=cv, n_jobs=-1, refit=True)
        search.fit(X_train, y_train)
        best = search.best_estimator_
        cvres = cross_validate(clone(best), X_train, y_train, cv=cv, n_jobs=-1,
                               scoring=["accuracy", "precision", "recall", "f1", "roc_auc"])
        p_test = best.predict_proba(X_test)[:, 1]
        fpr, tpr, _ = roc_curve(y_test, p_test)
        frac_pos, mean_pred = calibration_curve(y_test, p_test, n_bins=8, strategy="quantile")
        perm = permutation_importance(best, X_test, y_test, scoring="roc_auc", n_repeats=20,
                                      random_state=RANDOM_SEED, n_jobs=-1)
        results[key] = dict(
            label=spec["label"], short=spec["short"], why=spec["why"],
            best_params={k.replace("model__", ""): (list(v) if isinstance(v, tuple) else v)
                         for k, v in search.best_params_.items()},
            grid_size=len(search.cv_results_["params"]),
            cv={m: dict(mean=cvres[f"test_{m}"].mean(), std=cvres[f"test_{m}"].std())
                for m in ["accuracy", "precision", "recall", "f1", "roc_auc"]},
            test=_metrics(y_test, p_test),
            roc=dict(fpr=fpr.tolist(), tpr=tpr.tolist()),
            calibration=dict(mean_predicted=mean_pred.tolist(), observed=frac_pos.tolist()),
            permutation_importance=sorted([dict(feature=f, mean=m, std=s) for f, m, s in
                                           zip(PREDICTORS, perm.importances_mean, perm.importances_std)],
                                          key=lambda r: -r["mean"]),
        )
        fitted[key] = (best, p_test)
        if verbose:
            print(f"[clinical] {spec['short']}: {search.best_params_} test AUC {results[key]['test']['roc_auc']:.3f}")

    # Model-specific explanations.
    lr = fitted["logistic_regression"][0]
    results["logistic_regression"]["coefficients"] = sorted(
        [dict(feature=f, coef=c) for f, c in zip(feature_names(lr), lr.named_steps["model"].coef_[0])],
        key=lambda r: -abs(r["coef"]))
    rf = fitted["random_forest"][0]
    results["random_forest"]["feature_importance"] = sorted(
        [dict(feature=f, importance=v) for f, v in zip(feature_names(rf), rf.named_steps["model"].feature_importances_)],
        key=lambda r: -r["importance"])
    ann = fitted["ann"][0]
    curves = ann_learning_curves({f"model__{k}": tuple(v) if isinstance(v, list) else v
                                  for k, v in results["ann"]["best_params"].items()}, X_train, y_train)
    results["ann"]["learning_curves"] = curves
    results["ann"]["final_fit"] = dict(n_iter=int(ann.named_steps["model"].n_iter_),
                                       final_training_loss=float(ann.named_steps["model"].loss_),
                                       loss_curve=ann.named_steps["model"].loss_curve_)

    # Sensitivity: the slope field is close to a perfect separator in this file (see quality report).
    sens = []
    for key in MODELS:
        params = {f"model__{k}": tuple(v) if isinstance(v, list) else v for k, v in results[key]["best_params"].items()}
        pipe = make_pipeline(key, drop=("slope",)).set_params(**params)
        Xtr, Xte = X_train.drop(columns="slope"), X_test.drop(columns="slope")
        p = pipe.fit(Xtr, y_train).predict_proba(Xte)[:, 1]
        m = _metrics(y_test, p)
        sens.append(dict(model=MODELS[key]["short"], accuracy=m["accuracy"], f1=m["f1"], roc_auc=m["roc_auc"]))

    preds = X_test.copy()
    preds.insert(0, "patientid", ids[idx_test])
    preds["actual"] = y_test
    for key, (_, p) in fitted.items():
        preds[f"{MODELS[key]['short']}_probability"] = p.round(4)
        preds[f"{MODELS[key]['short']}_predicted"] = (p >= 0.5).astype(int)
    preds["models_agreeing"] = preds[[f"{MODELS[k]['short']}_predicted" for k in MODELS]].sum(axis=1)
    preds.to_csv(CLIN_PROCESSED / "test_predictions.csv", index=False)

    for key, (pipe, _) in fitted.items():
        joblib.dump(dict(pipeline=pipe, key=key, label=MODELS[key]["label"], predictors=PREDICTORS,
                         best_params=results[key]["best_params"], test_roc_auc=results[key]["test"]["roc_auc"],
                         sklearn_version=sklearn.__version__, random_state=RANDOM_SEED),
                    MODEL_DIR / f"clinical_{key}.joblib")

    majority = max(y_test.mean(), 1 - y_test.mean())
    summary = dict(
        source=SOURCE, sha256=sha256(), n_raw=len(raw), n_clean=len(cleaned), n_train=len(idx_train),
        n_test=len(idx_test), positive_rate=float(y.mean()), positive_rate_train=float(y_train.mean()),
        positive_rate_test=float(y_test.mean()), majority_baseline_accuracy=float(majority),
        threshold=0.5, cv_folds=CV_FOLDS, tuning_metric=SCORING, random_state=RANDOM_SEED,
        sklearn_version=sklearn.__version__, test_rows_all_three_agree=int(preds["models_agreeing"].isin([0, 3]).sum()),
        slope_ablation=sens, runtime_s=round(time.time() - t0, 1),
    )
    out = _r(dict(summary=summary, models=results), 4)
    RESULTS_JSON.write_text(json.dumps(out, indent=1))

    quality = _r(dict(
        source=SOURCE, sha256=summary["sha256"],
        rows=dict(raw=len(raw), clean=len(cleaned), train=len(idx_train), test=len(idx_test)),
        missing_before={c: int(raw[c].isna().sum()) for c in PREDICTORS},
        missing_after_recode={c: int(cleaned[c].isna().sum()) for c in PREDICTORS},
        missing_after_imputation={c: 0 for c in PREDICTORS},
        profile_raw=raw_profile.to_dict("records"), profile_clean=clean_profile.to_dict("records"),
        cleaning_log=log.to_dict("records"), distributions=_distributions(raw, cleaned),
        dictionary={c: dict(label=v[0], kind=v[1], codes=v[2] if isinstance(v[2], dict) else None,
                            range=list(v[2]) if not isinstance(v[2], dict) else None) for c, v in DICTIONARY.items()},
        encoding=dict(
            numeric_scaled=["age", "restingBP", "serumcholestrol", "maxheartrate", "oldpeak", "noofmajorvessels",
                            "hr_reserve_pct"],
            binary_passthrough=["gender", "fastingbloodsugar", "exerciseangia"],
            one_hot=NOMINAL, encoded_features=feature_names(lr),
            imputation="median for numeric, most frequent for binary/nominal; fitted on training folds only",
            scaling="StandardScaler (z-score) on numeric fields, fitted on training folds only",
            engineered="hr_reserve_pct = maxheartrate / (220 - age) x 100"),
        class_balance=dict(raw={str(k): int(v) for k, v in raw[TARGET].value_counts().sort_index().items()},
                           train={str(k): int(v) for k, v in pd.Series(y_train).value_counts().sort_index().items()},
                           test={str(k): int(v) for k, v in pd.Series(y_test).value_counts().sort_index().items()}),
    ), 4)
    QUALITY_JSON.write_text(json.dumps(quality, indent=1, default=str))
    raw_profile.to_csv(TABLES / "clinical_profile_raw.csv", index=False)
    clean_profile.to_csv(TABLES / "clinical_profile_clean.csv", index=False)
    log.to_csv(TABLES / "clinical_cleaning_log.csv", index=False)
    pd.DataFrame([dict(model=MODELS[k]["label"], **{m: v for m, v in r["test"].items() if m != "confusion"},
                       **{f"cv_{m}_mean": v["mean"] for m, v in r["cv"].items()})
                  for k, r in results.items()]).round(4).to_csv(TABLES / "clinical_model_metrics.csv", index=False)
    _plots(results, curves)
    if verbose:
        print(f"[clinical] done in {time.time() - t0:.0f}s")
    return out


if __name__ == "__main__":
    o = run()
    print(json.dumps({k: v["test"] for k, v in o["models"].items()}, indent=1))
    print(json.dumps(o["summary"]["slope_ablation"], indent=1))

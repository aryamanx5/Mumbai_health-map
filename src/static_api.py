"""Static copies of the API for hosts without a Python server (GitHub Pages).

Writes dashboard/static-api/:
  overview.json          same payload as GET /api/overview
  test-predictions.json  same payload as GET /api/clinical/test-predictions?limit=1000
  models.json            the three fitted pipelines as plain numbers, so dashboard/model-runtime.js can run
                         them in the browser with the same preprocessing as training

Nothing is retrained: everything is read from the saved models in models/ and the pipeline outputs.
Usage:  .venv/bin/python -m src.static_api      (also run at the end of run_pipeline.py)
"""
import json

import numpy as np

from backend import store
from backend.main import overview, test_predictions
from src.clinical_data import BINARY, ENGINEERED, NOMINAL, NUMERIC, PREDICTORS
from src.clinical_models import feature_names
from src.config import ROOT

OUT = ROOT / "dashboard" / "static-api"


def _floats(a):
    """Exact float64 values (json writes the shortest repr that round-trips)."""
    return [float(x) for x in np.asarray(a, dtype=float).ravel()]


def _prep(pipe):
    """Imputation, scaling and one-hot parameters of the fitted ColumnTransformer, in output-column order."""
    prep = pipe.named_steps["prep"]
    cols = {name: list(c) for name, _, c in prep.transformers_ if name != "remainder"}
    num = prep.named_transformers_["num"]
    nom = prep.named_transformers_["nom"]
    assert cols["num"] == NUMERIC + ENGINEERED and cols["bin"] == BINARY and cols["nom"] == NOMINAL
    out = dict(
        numeric=dict(columns=cols["num"], median=_floats(num.named_steps["impute"].statistics_),
                     mean=_floats(num.named_steps["scale"].mean_), scale=_floats(num.named_steps["scale"].scale_)),
        binary=dict(columns=cols["bin"], mode=_floats(prep.named_transformers_["bin"].statistics_)),
        nominal=dict(columns=cols["nom"], mode=_floats(nom.named_steps["impute"].statistics_),
                     categories=[_floats(c) for c in nom.named_steps["onehot"].categories_]),
        feature_names=feature_names(pipe),
    )
    width = len(out["numeric"]["columns"]) + len(out["binary"]["columns"]) + sum(len(c) for c in out["nominal"]["categories"])
    assert width == len(out["feature_names"]), "exported preprocessing does not match the model's input width"
    return out


def _model(est):
    kind = type(est).__name__
    if kind == "LogisticRegression":
        return dict(type="logistic", coef=_floats(est.coef_[0]), intercept=float(est.intercept_[0]))
    if kind == "MLPClassifier":
        assert est.activation == "relu" and est.out_activation_ == "logistic", "runtime supports relu + logistic only"
        return dict(type="mlp", activation=est.activation,
                    layers=[dict(weights=[_floats(row) for row in W], bias=_floats(b))
                            for W, b in zip(est.coefs_, est.intercepts_)])
    if kind == "RandomForestClassifier":
        assert list(est.classes_) == [0, 1]
        trees = []
        for t in est.estimators_:
            tr = t.tree_
            leaf = tr.children_left == -1
            v = tr.value[:, 0, :]
            p1 = np.where(leaf, v[:, 1] / v.sum(axis=1), 0.0)
            trees.append(dict(left=tr.children_left.tolist(), right=tr.children_right.tolist(),
                              feature=tr.feature.tolist(), threshold=_floats(np.where(leaf, 0.0, tr.threshold)),
                              p1=_floats(p1)))
        return dict(type="forest", trees=trees)
    raise ValueError(f"unsupported model {kind}")


def models_bundle():
    res = store.clinical_results()
    bundle = dict(threshold=res["summary"]["threshold"], disclaimer=store.DISCLAIMER, predictors=PREDICTORS,
                  model_order=store.MODEL_KEYS, models={})
    for key, art in store.models().items():
        pipe = art["pipeline"]
        assert [s for s, _ in pipe.steps] == ["features", "prep", "model"], "unexpected pipeline layout"
        m = res["models"][key]
        bundle["models"][key] = dict(label=art["label"], short=m["short"], test_roc_auc=m["test"]["roc_auc"],
                                     test_accuracy=m["test"]["accuracy"], engineered=["hr_reserve_pct"],
                                     prep=_prep(pipe), model=_model(pipe.named_steps["model"]))
    return bundle


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    files = {"overview.json": overview(), "test-predictions.json": test_predictions(limit=1000),
             "models.json": models_bundle()}
    for name, payload in files.items():
        (OUT / name).write_text(json.dumps(payload, separators=(",", ":"), allow_nan=False))
    return {name: (OUT / name).stat().st_size for name in files}


if __name__ == "__main__":
    print(build())

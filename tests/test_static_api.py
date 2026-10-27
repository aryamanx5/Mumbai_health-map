"""The static API (dashboard/static-api) and the in-browser model runtime used on GitHub Pages.

The parity tests run dashboard/model-runtime.js under Node and compare it with sklearn's predict_proba on the
saved pipelines. They are skipped when Node is not installed.
"""
import json
import shutil
import subprocess

import numpy as np
import pandas as pd
import pytest

from backend import store
from backend.main import overview
from backend.main import test_predictions as api_test_predictions  # aliased so pytest does not collect it
from src.clinical_data import PREDICTORS
from src.config import PROCESSED, ROOT
from src.static_api import OUT, models_bundle

RUNTIME = ROOT / "dashboard" / "model-runtime.js"
NODE = shutil.which("node")


def _load(name):
    return json.loads((OUT / name).read_text())


def test_static_files_match_the_api_and_saved_models():
    assert _load("overview.json") == json.loads(json.dumps(overview()))
    assert _load("test-predictions.json") == json.loads(json.dumps(api_test_predictions(limit=1000)))
    assert _load("models.json") == json.loads(json.dumps(models_bundle())), \
        "static-api/models.json is stale: run `python -m src.static_api`"


def _patients():
    """Every cleaned patient, the same patients with cholesterol unknown, and random in-range inputs."""
    real = pd.read_csv(PROCESSED / "clinical" / "clinical_clean.csv")[PREDICTORS]
    no_chol = real.head(200).assign(serumcholestrol=np.nan)
    rng = np.random.default_rng(7)
    n = 400
    rand = pd.DataFrame(dict(
        age=rng.integers(18, 101, n), gender=rng.integers(0, 2, n), chestpain=rng.integers(0, 4, n),
        restingBP=rng.integers(80, 221, n), serumcholestrol=rng.integers(80, 701, n),
        fastingbloodsugar=rng.integers(0, 2, n), restingrelectro=rng.integers(0, 3, n),
        maxheartrate=rng.integers(60, 221, n), exerciseangia=rng.integers(0, 2, n),
        oldpeak=rng.integers(0, 71, n) / 10, slope=rng.integers(1, 4, n), noofmajorvessels=rng.integers(0, 4, n)))
    return pd.concat([real, no_chol, rand], ignore_index=True).astype(float)


def _run_node(script, payload, tmp_path):
    f = tmp_path / "in.json"
    f.write_text(json.dumps(payload))
    out = subprocess.run([NODE, "-e", script, str(RUNTIME), str(OUT / "models.json"), str(f)],
                         capture_output=True, text=True, check=True, timeout=120)
    return json.loads(out.stdout)


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_browser_probabilities_match_sklearn(tmp_path):
    X = _patients()
    rows = [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in X.to_dict("records")]
    js = _run_node("""
      const rt = require(process.argv[1]), fs = require("fs");
      const b = JSON.parse(fs.readFileSync(process.argv[2])), rows = JSON.parse(fs.readFileSync(process.argv[3]));
      process.stdout.write(JSON.stringify(rows.map((r) => rt.probabilities(b, r))));""", rows, tmp_path)
    for key, art in store.models().items():
        py = art["pipeline"].predict_proba(X)[:, 1]
        got = np.array([r[key] for r in js])
        assert np.abs(got - py).max() < 1e-9, f"{key}: browser and sklearn probabilities differ"
        assert ((got >= 0.5) == (py >= 0.5)).all(), f"{key}: a predicted class differs"


@pytest.mark.skipif(NODE is None, reason="Node.js is not installed")
def test_browser_response_matches_api_response(tmp_path):
    X = _patients().iloc[::25]
    rows = [{k: (None if pd.isna(v) else v) for k, v in r.items()} for r in X.to_dict("records")]
    js = _run_node("""
      const rt = require(process.argv[1]), fs = require("fs");
      const b = JSON.parse(fs.readFileSync(process.argv[2])), rows = JSON.parse(fs.readFileSync(process.argv[3]));
      process.stdout.write(JSON.stringify(rows.map((r) => rt.predict(b, r))));""", rows, tmp_path)
    for row, got in zip(rows, js):
        want = store.predict(row)
        assert got["imputed_fields"] == want["imputed_fields"]
        assert got["models_predicting_disease"] == want["models_predicting_disease"]
        assert got["threshold"] == want["threshold"] and got["disclaimer"] == want["disclaimer"]
        for g, w in zip(got["predictions"], want["predictions"]):
            assert {k: g[k] for k in ("model", "label", "predicted_class", "predicted_label")} == \
                   {k: w[k] for k in ("model", "label", "predicted_class", "predicted_label")}
            assert abs(g["probability"] - w["probability"]) <= 1e-4

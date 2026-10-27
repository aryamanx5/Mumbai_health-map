"""ML workflow tests. Synthetic data is used only for unit behaviour; real-output tests read the exports."""
import json

import joblib
import numpy as np
import pandas as pd
import pytest
from sklearn.metrics import adjusted_rand_score

from src.config import MODELS, PROCESSED, TABLES, WARD_ORDER
from src.model_evaluation import FINAL_K, describe_cluster
from src.model_training import (FEATURE_SETS, PRIMARY, evaluate_k_range, fit_k, make_pipeline, modelling_table,
                                relabel_by, select_k)

FEATS = FEATURE_SETS[PRIMARY]["features"]


def synthetic(n_per=6, seed=0):
    rng = np.random.default_rng(seed)
    centers = np.array([[1, 1.5, 0.1, 0.1], [3, 2, 0.3, 0.3], [1.5, 1.5, 1.5, 0.0]])
    rows = np.vstack([c + rng.normal(0, 0.05, size=(n_per, 4)) for c in centers]).clip(min=0)
    df = pd.DataFrame(rows, columns=FEATS)
    df.insert(0, "ward_id", [f"W{i}" for i in range(len(df))])
    df["population_2011"] = 100_000
    for c in ["dispensary", "uphc", "public_hospital", "maternity_hospital"]:
        df[f"{c}_count"] = 1
    return df


def test_modelling_table_schema_and_excludes_nonfinite():
    df = synthetic()
    df.loc[0, "uphc_per_100k"] = np.nan
    df.loc[1, "dispensary_per_100k"] = np.inf
    X, excluded = modelling_table(df, FEATS)
    assert list(X.columns) == FEATS
    assert excluded == ["W0", "W1"]
    assert all(X.dtypes == float) and np.isfinite(X.to_numpy()).all()


def test_zero_rates_are_valid_inputs():
    df = synthetic()
    df.loc[:5, "public_hospital_per_100k"] = 0.0
    X, excluded = modelling_table(df, FEATS)
    assert not excluded
    f = fit_k(X, 3, log1p=True)
    assert np.isfinite(f["Z"]).all()


def test_preprocessing_standardizes():
    X, _ = modelling_table(synthetic(), FEATS)
    Z = make_pipeline(3, log1p=True)[:-1].fit_transform(X)
    assert Z.shape == X.shape
    np.testing.assert_allclose(Z.mean(axis=0), 0, atol=1e-9)
    np.testing.assert_allclose(Z.std(axis=0), 1, atol=1e-9)


def test_fit_recovers_synthetic_clusters_and_dimensions():
    X, _ = modelling_table(synthetic(), FEATS)
    f = fit_k(X, 3, log1p=False)
    truth = np.repeat([0, 1, 2], 6)
    assert len(f["labels"]) == len(X) and set(f["labels"]) == {0, 1, 2}
    assert adjusted_rand_score(truth, f["labels"]) == 1.0
    assert f["silhouette"] > 0.7


def test_reproducible_with_fixed_seed():
    X, _ = modelling_table(synthetic(), FEATS)
    a, b = fit_k(X, 3, True), fit_k(X, 3, True)
    # Labels must match exactly; inertia can differ in the last bits because OpenMP sums in a varying order.
    assert (a["labels"] == b["labels"]).all() and a["inertia"] == pytest.approx(b["inertia"], rel=1e-9)


def test_invalid_k_raises_and_degenerate_k_flagged():
    X, _ = modelling_table(synthetic(n_per=2), FEATS)  # 6 points
    with pytest.raises(ValueError):
        fit_k(X, len(X), True)
    with pytest.raises(ValueError):
        fit_k(X, 1, True)
    kt, _ = evaluate_k_range(X, True, k_range=range(2, 8))
    assert (kt.loc[kt.k >= 6, "status"].str.startswith("invalid")).all()
    assert (kt.loc[kt.k == 5, "status"].str.startswith("degenerate")).all()


def test_select_k_skips_degenerate():
    kt = pd.DataFrame(dict(k=[2, 3, 4], silhouette=[0.9, 0.5, 0.49], status=["degenerate", "ok", "ok"]))
    assert select_k(kt) == 3


def test_relabel_orders_by_feature():
    X = pd.DataFrame({"f": [5.0, 5.1, 1.0, 1.1]})
    labels, mapping = relabel_by(np.array([0, 0, 1, 1]), X, "f")
    assert labels.tolist() == [2, 2, 1, 1] and mapping == {1: 1, 0: 2}


def test_describe_cluster():
    z = pd.Series({"dispensary_per_100k": 1.2, "uphc_per_100k": -0.8, "public_hospital_per_100k": 0.1})
    assert describe_cluster(z) == "Relatively higher dispensary rates; lower UPHC rates"
    assert describe_cluster(z * 0).startswith("Near")


# ---- tests against the real exported outputs (run `python run_pipeline.py` first) ----

@pytest.fixture(scope="module")
def exported():
    return dict(assign=pd.read_csv(PROCESSED / "ward_clusters.csv"),
                X=pd.read_csv(PROCESSED / "ml_modelling_table.csv").set_index("ward_id"),
                wards=pd.read_csv(PROCESSED / "ward_indicators.csv"),
                model=joblib.load(MODELS / "kmeans_pipeline.joblib"),
                k_table=pd.read_csv(TABLES / "ml_k_evaluation.csv"),
                pbi=pd.read_csv(PROCESSED.parent.parent / "powerbi" / "data" / "dim_ward.csv"))


def test_saved_model_reproduces_exported_assignments(exported):
    m, X, a = exported["model"], exported["X"], exported["assign"].set_index("ward_id")
    assert m["features"] == list(X.columns)
    pred = m["pipeline"].predict(X[m["features"]])
    assert (pred == a.loc[X.index, "kmeans_raw_label"].to_numpy()).all()
    mapped = np.array([m["label_mapping"][int(p)] for p in pred])
    assert (mapped == a.loc[X.index, "cluster_label"].to_numpy()).all()
    assert adjusted_rand_score(pred, a.loc[X.index, "cluster_label"]) == 1.0


def test_exported_clusters_cover_all_wards(exported):
    a = exported["assign"]
    assert sorted(a["ward_id"]) == sorted(WARD_ORDER)
    assert a["cluster_label"].nunique() == FINAL_K
    assert a["cluster_label"].value_counts().min() >= 2


def test_final_k_is_valid_in_evidence_table(exported):
    row = exported["k_table"].set_index("k").loc[FINAL_K]
    assert row["status"] == "ok" and bool(row["converged"])


def test_powerbi_keys_match_ml_output(exported):
    pbi = exported["pbi"].set_index("ward_id")
    a = exported["assign"].set_index("ward_id")
    assert set(pbi.index) == set(a.index) == set(exported["wards"]["ward_id"])
    assert (pbi.loc[a.index, "cluster_label"] == a["cluster_label"]).all()


def test_model_config_matches(exported):
    cfg = json.loads((TABLES / "ml_model_config.json").read_text())
    assert cfg["k"] == FINAL_K and cfg["features"] == exported["model"]["features"]

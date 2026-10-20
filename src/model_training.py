"""Reproducible K-Means experiment on ward-level provision features."""
import warnings

import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.metrics import adjusted_rand_score, silhouette_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import FunctionTransformer, StandardScaler

from .config import RANDOM_SEED

N_INIT = 50
MAX_ITER = 500
K_RANGE = range(2, 7)
MIN_CLUSTER_SIZE = 2  # a K with any singleton cluster is treated as degenerate

# Candidate feature sets. The primary set is chosen in docs/model_card.md on relevance and redundancy grounds
# before looking at cluster quality; the others are sensitivity alternatives.
FEATURE_SETS = {
    "primary_log_category_rates": dict(
        features=["dispensary_per_100k", "uphc_per_100k", "public_hospital_per_100k", "maternity_hospital_per_100k"],
        log1p=True,
        rationale="Four category rates; low mutual correlation; log1p damps the A/E hospital outliers."),
    "raw_category_rates": dict(
        features=["dispensary_per_100k", "uphc_per_100k", "public_hospital_per_100k", "maternity_hospital_per_100k"],
        log1p=False, rationale="Same four rates without the log transform."),
    "primary_vs_secondary_care": dict(
        features=["primary_care_per_100k", "secondary_care_per_100k"], log1p=True,
        rationale="Dispensary+UPHC records vs hospital+maternity records per 100k."),
    "overall_rate_and_density": dict(
        features=["facilities_per_100k", "population_density_per_km2"], log1p=True,
        rationale="Overall site rate plus population density (context, not provision)."),
}
PRIMARY = "primary_log_category_rates"


def add_derived_features(t):
    t = t.copy()
    t["primary_care_per_100k"] = (t["dispensary_count"] + t["uphc_count"]) / t["population_2011"] * 1e5
    t["secondary_care_per_100k"] = (t["public_hospital_count"] + t["maternity_hospital_count"]) / t["population_2011"] * 1e5
    return t


def modelling_table(ward_table, features):
    """Feature matrix keyed by ward_id. Rows with undefined features are excluded and reported, not imputed."""
    t = add_derived_features(ward_table).set_index("ward_id")
    X = t[features].astype(float)
    bad = ~np.isfinite(X).all(axis=1)
    return X[~bad], X.index[bad].tolist()


def make_pipeline(k, log1p, seed=RANDOM_SEED):
    steps = []
    if log1p:
        steps.append(("log1p", FunctionTransformer(np.log1p, feature_names_out="one-to-one")))
    steps += [("scale", StandardScaler()),
              ("kmeans", KMeans(n_clusters=k, n_init=N_INIT, max_iter=MAX_ITER, random_state=seed))]
    return Pipeline(steps)


def fit_k(X, k, log1p, seed=RANDOM_SEED):
    """Fit one configuration, capturing warnings and degenerate output instead of hiding them."""
    if not 2 <= k < len(X):
        raise ValueError(f"k={k} invalid for {len(X)} observations")
    with warnings.catch_warnings(record=True) as w:
        warnings.simplefilter("always")
        pipe = make_pipeline(k, log1p, seed).fit(X)
    labels = pipe.named_steps["kmeans"].labels_
    Z = pipe[:-1].transform(X)
    sizes = np.bincount(labels, minlength=k)
    n_distinct = len(np.unique(Z.round(10), axis=0))
    return dict(
        pipeline=pipe, labels=labels, Z=Z, k=k,
        inertia=float(pipe.named_steps["kmeans"].inertia_),
        silhouette=float(silhouette_score(Z, labels)) if 1 < len(set(labels)) < len(X) else np.nan,
        sizes=sorted(sizes.tolist(), reverse=True), min_size=int(sizes.min()),
        n_iter=int(pipe.named_steps["kmeans"].n_iter_),
        converged=pipe.named_steps["kmeans"].n_iter_ < MAX_ITER,
        warnings="; ".join(str(x.message) for x in w), n_distinct_points=n_distinct,
    )


def evaluate_k_range(X, log1p, k_range=K_RANGE):
    rows, fits = [], {}
    for k in k_range:
        if k >= len(X):
            rows.append(dict(k=k, status="invalid: k >= n_observations"))
            continue
        f = fit_k(X, k, log1p)
        fits[k] = f
        rows.append(dict(k=k, inertia=round(f["inertia"], 4), silhouette=round(f["silhouette"], 4),
                         cluster_sizes=str(f["sizes"]), min_cluster_size=f["min_size"],
                         singleton_clusters=int(sum(s == 1 for s in f["sizes"])), n_iter=f["n_iter"],
                         converged=f["converged"], warnings=f["warnings"] or "",
                         status="degenerate (cluster smaller than %d)" % MIN_CLUSTER_SIZE
                         if f["min_size"] < MIN_CLUSTER_SIZE else "ok"))
    return pd.DataFrame(rows), fits


def select_k(k_table):
    """Highest silhouette among non-degenerate K. Ties (within 0.01) go to the smaller K."""
    ok = k_table[k_table["status"] == "ok"].dropna(subset=["silhouette"])
    if ok.empty:
        raise RuntimeError("no non-degenerate K in range")
    best = ok["silhouette"].max()
    return int(ok[ok["silhouette"] >= best - 0.01]["k"].min())


def relabel_by(labels, X, order_col):
    """Map arbitrary K-Means ids to 1..K ordered by the cluster mean of `order_col` (ascending)."""
    means = pd.Series(X[order_col].to_numpy()).groupby(labels).mean().sort_values()
    mapping = {int(old): new + 1 for new, old in enumerate(means.index)}
    return np.array([mapping[int(l)] for l in labels]), mapping


def seed_stability(X, k, log1p, reference, seeds=range(50)):
    return [adjusted_rand_score(reference, fit_k(X, k, log1p, seed=s)["labels"]) for s in seeds]


def subsample_stability(X, k, log1p, reference, n_rep=200, frac=0.8, seed=RANDOM_SEED):
    rng = np.random.default_rng(seed)
    n = len(X)
    out = []
    for _ in range(n_rep):
        idx = np.sort(rng.choice(n, size=int(round(frac * n)), replace=False))
        f = fit_k(X.iloc[idx], k, log1p)
        out.append(adjusted_rand_score(reference[idx], f["labels"]))
    return out


def noise_stability(X, k, log1p, reference, n_rep=200, scale=0.05, seed=RANDOM_SEED):
    """Multiplicative noise (sd = 5% of each value) on the original-scale features."""
    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_rep):
        Xn = X * (1 + rng.normal(0, scale, size=X.shape))
        out.append(adjusted_rand_score(reference, fit_k(Xn.clip(lower=0), k, log1p)["labels"]))
    return out

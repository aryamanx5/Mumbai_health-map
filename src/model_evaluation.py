"""Run the K-Means experiment end to end: K scan, stability, final fit, profiles, sensitivity, exports."""
import json

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import sklearn
from sklearn.metrics import adjusted_rand_score, silhouette_samples

from . import plot_style as ps
from .config import CATEGORIES, FIGURES, MODELS, PROCESSED, RANDOM_SEED, TABLES
from .model_training import (FEATURE_SETS, K_RANGE, MAX_ITER, MIN_CLUSTER_SIZE, N_INIT, PRIMARY, add_derived_features,
                             evaluate_k_range, fit_k, modelling_table, noise_stability, relabel_by, seed_stability,
                             select_k, subsample_stability)

# Final K is a documented judgement over the evidence table (see docs/model_card.md), not the output of
# a single metric. Selection evidence is regenerated on every run and the choice is re-checked in tests.
FINAL_K = 4
FEATURE_LABELS = {
    "dispensary_per_100k": "Dispensaries per 100k", "uphc_per_100k": "UPHCs per 100k",
    "public_hospital_per_100k": "Public hospitals per 100k", "maternity_hospital_per_100k": "Maternity homes per 100k",
    "primary_care_per_100k": "Dispensary+UPHC records per 100k",
    "secondary_care_per_100k": "Hospital+maternity records per 100k",
    "facilities_per_100k": "Distinct sites per 100k", "population_density_per_km2": "Residents per km2",
}


SHORT = {"dispensary_per_100k": "dispensary", "uphc_per_100k": "UPHC", "public_hospital_per_100k": "public-hospital",
         "maternity_hospital_per_100k": "maternity-home", "primary_care_per_100k": "primary-care",
         "secondary_care_per_100k": "hospital/maternity", "facilities_per_100k": "overall site",
         "population_density_per_km2": "density"}


def describe_cluster(z_means, threshold=0.5):
    """Plain-language descriptor from standardized cluster means (relative to the 24 wards).

    Lists features whose cluster mean is at least `threshold` SD from the ward mean, strongest first.
    """
    hi, lo = [], []
    for f, z in z_means.sort_values(key=abs, ascending=False).items():
        if z >= threshold:
            hi.append(SHORT[f])
        elif z <= -threshold:
            lo.append(SHORT[f])
    parts = ([f"higher {' & '.join(hi)} rates"] if hi else []) + ([f"lower {' & '.join(lo)} rates"] if lo else [])
    return "Relatively " + "; ".join(parts) if parts else "Near the ward average on all features"


def _plot_k_diagnostics(k_table, name):
    ok = k_table.dropna(subset=["silhouette"])
    fig, axes = plt.subplots(1, 2, figsize=(10, 3.8))
    axes[0].plot(ok["k"], ok["inertia"], marker="o", color=ps.SERIES[0], lw=2, ms=8)
    axes[0].set_title("Elbow: within-cluster sum of squares")
    axes[0].set_xlabel("K")
    axes[0].set_ylabel("Inertia (standardized units)")
    axes[1].plot(ok["k"], ok["silhouette"], marker="o", color=ps.SERIES[0], lw=2, ms=8)
    deg = ok[ok["status"] != "ok"]
    axes[1].scatter(deg["k"], deg["silhouette"], marker="x", s=80, color=ps.TEXT, zorder=4, label="degenerate (singleton)")
    axes[1].axvline(FINAL_K, color=ps.TEXT_2, ls="--", lw=1)
    axes[1].text(FINAL_K, axes[1].get_ylim()[1], f" chosen K={FINAL_K}", va="top", fontsize=8, color=ps.TEXT_2)
    axes[1].set_title("Mean silhouette score")
    axes[1].set_xlabel("K")
    if len(deg):
        axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_xticks(list(ok["k"]))
    ps.note(fig, "Primary feature set: log1p of four category rates per 100,000 residents, standardized. "
                 "24 wards; fixed seed; 50 initializations per fit.")
    fig.savefig(FIGURES / name)
    plt.close(fig)


def _plot_profiles(profile_z, names, name):
    feats = list(profile_z.columns)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    width = 0.8 / len(profile_z)
    x = np.arange(len(feats))
    for i, (c, row) in enumerate(profile_z.iterrows()):
        ax.bar(x + i * width - 0.4 + width / 2, row.values, width=width * 0.92, color=ps.SERIES[i],
               label=f"Cluster {c} ({names[c]['n']} wards)")
    ax.axhline(0, color=ps.TEXT_2, lw=1)
    ax.set_xticks(x, [FEATURE_LABELS[f].replace(" per ", "\nper ") for f in feats], fontsize=9)
    ax.set_ylabel("Cluster mean, SD from ward mean")
    ax.set_title("Cluster profiles (original-scale rates, standardized for comparison)")
    ax.legend(fontsize=8, ncols=2)
    ax.grid(axis="x", visible=False)
    ps.note(fig, "Bars compare each cluster's mean rate with the 24-ward mean. Within-dataset comparison only.")
    fig.savefig(FIGURES / name)
    plt.close(fig)


def _plot_cluster_map(wards, assign, name):
    w = wards.merge(assign, on="ward_id")
    fig, ax = plt.subplots(figsize=(7, 9.5))
    hatches = ["", "..", "//", "xx", "\\\\", "++"]
    for i, c in enumerate(sorted(w["cluster_label"].unique())):
        d = w[w["cluster_label"] == c]
        d.plot(ax=ax, color=ps.SERIES[i], edgecolor="white", linewidth=0.8, hatch=hatches[i],
               label=f"Cluster {c}")
    for r in w.itertuples():
        p = r.geometry.representative_point()
        ax.text(p.x, p.y, r.ward_id, fontsize=7.5, ha="center", va="center", weight="bold", color=ps.TEXT,
                bbox=dict(boxstyle="round,pad=0.15", fc=ps.SURFACE, ec="none", alpha=0.8))
    handles = [plt.Rectangle((0, 0), 1, 1, color=ps.SERIES[i], hatch=hatches[i]) for i in range(w.cluster_label.nunique())]
    labels = [f"Cluster {c}: {w[w.cluster_label == c].cluster_name.iloc[0]}" for c in sorted(w.cluster_label.unique())]
    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(0, 0.02), fontsize=8, frameon=False)
    ax.set_axis_off()
    ax.set_title(f"K-Means clusters (K={FINAL_K}) of wards by provision profile")
    ps.note(fig, "Exploratory unsupervised grouping of 24 wards. Clusters describe similarity of listed-facility "
                 "rates, not adequacy of access.")
    fig.savefig(FIGURES / name)
    plt.close(fig)


def run(ward_table, wards):
    ps.apply()
    for d in (FIGURES, TABLES, MODELS):
        d.mkdir(parents=True, exist_ok=True)
    spec = FEATURE_SETS[PRIMARY]
    feats, log1p = spec["features"], spec["log1p"]
    X, excluded = modelling_table(ward_table, feats)
    assert not excluded, f"wards with undefined features: {excluded}"

    # ---- K scan with stability for every candidate ----
    k_table, fits = evaluate_k_range(X, log1p)
    stab_rows = []
    for k, f in fits.items():
        seed_ari = seed_stability(X, k, log1p, f["labels"], seeds=range(30))
        sub_ari = subsample_stability(X, k, log1p, f["labels"], n_rep=100)
        noise_ari = noise_stability(X, k, log1p, f["labels"], n_rep=100)
        stab_rows.append(dict(k=k, seed_ari_min=round(min(seed_ari), 3), subsample80_ari_mean=round(np.mean(sub_ari), 3),
                              subsample80_ari_p10=round(np.percentile(sub_ari, 10), 3),
                              noise5pct_ari_mean=round(np.mean(noise_ari), 3)))
    k_table = k_table.merge(pd.DataFrame(stab_rows), on="k", how="left")
    k_table["max_silhouette_rule_choice"] = k_table["k"] == select_k(k_table)
    k_table["final_choice"] = k_table["k"] == FINAL_K
    k_table.to_csv(TABLES / "ml_k_evaluation.csv", index=False)
    _plot_k_diagnostics(k_table, "10_ml_elbow_silhouette.png")
    assert k_table.set_index("k").loc[FINAL_K, "status"] == "ok", "chosen K is degenerate"

    # ---- final model ----
    final = fits[FINAL_K]
    pipe = final["pipeline"]
    labels, mapping = relabel_by(final["labels"], X.assign(_o=ward_table.set_index("ward_id").loc[X.index, "facilities_per_100k"]), "_o")
    k2_labels, _ = relabel_by(fits[2]["labels"], X.assign(_o=ward_table.set_index("ward_id").loc[X.index, "facilities_per_100k"]), "_o")
    sil = silhouette_samples(final["Z"], final["labels"])

    zX = (X - X.mean()) / X.std()
    profile_z = zX.groupby(labels).mean()
    names = {c: dict(n=int((labels == c).sum()), name=describe_cluster(profile_z.loc[c])) for c in profile_z.index}

    assign = pd.DataFrame({
        "ward_id": X.index, "cluster_label": labels, "kmeans_raw_label": final["labels"],
        "cluster_name": [names[c]["name"] for c in labels], "silhouette_sample": sil.round(4),
        "cluster_k2_label": k2_labels,
    })
    joblib.dump(dict(pipeline=pipe, features=feats, log1p=log1p, label_mapping=mapping, ward_ids=list(X.index)),
                MODELS / "kmeans_pipeline.joblib")

    # ---- profiles on the original scale ----
    t = add_derived_features(ward_table).set_index("ward_id").loc[X.index]
    prof_cols = feats + ["facilities_per_100k", "population_per_facility", "population_2011",
                         "population_density_per_km2", "total_distinct_public_facilities"] + \
                [f"{c}_count" for c in CATEGORIES]
    g = t[prof_cols].groupby(labels)
    prof = pd.concat([g.mean().add_suffix("_mean"), g.median().add_suffix("_median")], axis=1).round(3)
    prof.insert(0, "n_wards", g.size())
    prof.insert(1, "share_of_wards_pct", (g.size() / len(X) * 100).round(1))
    prof.insert(2, "wards", [", ".join(X.index[labels == c]) for c in prof.index])
    prof.insert(3, "cluster_name", [names[c]["name"] for c in prof.index])
    prof.insert(4, "mean_silhouette", pd.Series(sil).groupby(labels).mean().round(3).values)
    prof.insert(5, "population_total", g["population_2011"].sum().values)
    prof.index.name = "cluster_label"
    prof.reset_index().to_csv(TABLES / "ml_cluster_profiles.csv", index=False)
    _plot_profiles(profile_z, names, "11_ml_cluster_profiles.png")
    _plot_cluster_map(wards, assign, "12_ml_cluster_map.png")

    # ---- centroids back on the original scale ----
    cents = pipe.named_steps["scale"].inverse_transform(pipe.named_steps["kmeans"].cluster_centers_)
    if log1p:
        cents = np.expm1(cents)
    cent = pd.DataFrame(cents, columns=feats).round(4)
    cent.insert(0, "cluster_label", [mapping[i] for i in range(FINAL_K)])
    cent.sort_values("cluster_label").to_csv(TABLES / "ml_centroids_original_scale.csv", index=False)

    # ---- sensitivity to feature-set alternatives ----
    sens = []
    for name, fs in FEATURE_SETS.items():
        Xa, _ = modelling_table(ward_table, fs["features"])
        kt, fa = evaluate_k_range(Xa, fs["log1p"])
        own_k = select_k(kt)
        same = fa[FINAL_K]["labels"] if FINAL_K in fa else None
        sens.append(dict(feature_set=name, features=", ".join(fs["features"]), log1p=fs["log1p"],
                         rationale=fs["rationale"], max_silhouette_k=own_k,
                         silhouette_at_final_k=round(fa[FINAL_K]["silhouette"], 3),
                         sizes_at_final_k=str(fa[FINAL_K]["sizes"]),
                         ari_vs_final_at_final_k=round(adjusted_rand_score(final["labels"], same), 3),
                         ari_vs_final_k2=round(adjusted_rand_score(fits[2]["labels"], fa[2]["labels"]), 3)))
    sens = pd.DataFrame(sens)
    sens.to_csv(TABLES / "ml_feature_set_sensitivity.csv", index=False)

    # ---- outputs ----
    feat_dict = pd.DataFrame([dict(feature=f, label=FEATURE_LABELS[f], transform="log1p then z-score" if log1p else "z-score",
                                   order=i + 1, missing_in_modelling_table=int(X[f].isna().sum()),
                                   min=round(X[f].min(), 4), max=round(X[f].max(), 4)) for i, f in enumerate(feats)])
    feat_dict.to_csv(TABLES / "ml_feature_dictionary.csv", index=False)
    X.reset_index().to_csv(PROCESSED / "ml_modelling_table.csv", index=False)
    assign.to_csv(PROCESSED / "ward_clusters.csv", index=False)

    final_stab = k_table.set_index("k").loc[FINAL_K]
    config = dict(feature_set=PRIMARY, features=feats, log1p=log1p, scaler="StandardScaler",
                  algorithm="KMeans (lloyd)", k=FINAL_K, n_init=N_INIT, max_iter=MAX_ITER, random_state=RANDOM_SEED,
                  min_cluster_size_rule=MIN_CLUSTER_SIZE, k_range=list(K_RANGE), n_observations=len(X),
                  sklearn_version=sklearn.__version__, label_order="cluster 1 = lowest mean distinct sites per 100k",
                  final_silhouette=round(final["silhouette"], 4), final_inertia=round(final["inertia"], 4),
                  final_sizes=final["sizes"], converged=bool(final["converged"]),
                  stability=dict(seed_ari_min=final_stab["seed_ari_min"],
                                 subsample80_ari_mean=final_stab["subsample80_ari_mean"],
                                 subsample80_ari_p10=final_stab["subsample80_ari_p10"],
                                 noise5pct_ari_mean=final_stab["noise5pct_ari_mean"]))
    (TABLES / "ml_model_config.json").write_text(json.dumps(config, indent=2, default=float))
    return dict(k_table=k_table, assign=assign, profiles=prof, sensitivity=sens, config=config, X=X)


if __name__ == "__main__":
    import geopandas as gpd
    from .config import PROCESSED as P
    out = run(pd.read_csv(P / "ward_indicators.csv"), gpd.read_file(P / "ward_boundaries.geojson"))
    pd.set_option("display.width", 250)
    print(out["k_table"].drop(columns=["warnings"]).to_string(index=False))
    print(out["profiles"].iloc[:, :12].to_string())
    print(out["sensitivity"].drop(columns=["rationale", "features"]).to_string(index=False))
    print(json.dumps(out["config"], indent=1, default=float))

"""Power BI import-ready tables (star schema keyed on ward_id / site_id / cluster_label)."""
import pandas as pd

from .config import CATEGORIES, POWERBI
from .plot_style import CATEGORY_LABELS

OUT = POWERBI / "data"


def run(master, sites, ward_table, assign, profiles, k_table):
    OUT.mkdir(parents=True, exist_ok=True)
    a = assign.set_index("ward_id")

    dim_ward = ward_table.copy()
    dim_ward["cluster_label"] = dim_ward["ward_id"].map(a["cluster_label"])
    dim_ward["cluster_name"] = dim_ward["ward_id"].map(a["cluster_name"])
    dim_ward["cluster_k2_label"] = dim_ward["ward_id"].map(a["cluster_k2_label"])
    dim_ward["silhouette_sample"] = dim_ward["ward_id"].map(a["silhouette_sample"])
    dim_ward["rank_sites_per_100k_low_to_high"] = dim_ward["facilities_per_100k"].rank(method="min").astype(int)
    dim_ward = dim_ward.drop(columns=["geometry_repaired", "source_ward_name"], errors="ignore")
    dim_ward = dim_ward.round(4)

    fact_facility = master[["facility_id", "site_id", "ward_id", "category", "facility_name", "address",
                            "source_subtype", "longitude", "latitude", "coordinate_decimals", "coordinate_status",
                            "assignment_check", "source_file", "source_record_id"]].copy()
    fact_facility["category_label"] = fact_facility["category"].map(CATEGORY_LABELS)
    fact_facility["coordinates_approximate"] = fact_facility["coordinate_decimals"].fillna(0) <= 2

    dim_site = sites.copy()
    dim_site["category_labels"] = dim_site["categories"].map(
        lambda s: "; ".join(CATEGORY_LABELS[c] for c in s.split(";")))

    dim_category = pd.DataFrame([dict(category=c, category_label=CATEGORY_LABELS[c], sort_order=i + 1)
                                 for i, c in enumerate(CATEGORIES)])

    # Long-format ward x category rates for slicer-driven visuals.
    rows = []
    for r in ward_table.itertuples():
        for c in CATEGORIES:
            rows.append(dict(ward_id=r.ward_id, category=c, facility_records=getattr(r, f"{c}_count"),
                             per_100k=round(getattr(r, f"{c}_per_100k"), 4),
                             share_of_ward_sites_pct=round(getattr(r, f"{c}_share_pct"), 4)))
    fact_ward_category = pd.DataFrame(rows)

    dim_cluster = profiles.reset_index()[["cluster_label", "cluster_name", "n_wards", "share_of_wards_pct", "wards",
                                          "mean_silhouette", "population_total"] +
                                         [c for c in profiles.columns if c.endswith("_mean")]].round(4)

    tables = dict(dim_ward=dim_ward, fact_facility=fact_facility, dim_site=dim_site, dim_category=dim_category,
                  fact_ward_category=fact_ward_category, dim_cluster=dim_cluster,
                  ml_k_evaluation=k_table.drop(columns=["warnings"]))
    for name, df in tables.items():
        df.to_csv(OUT / f"{name}.csv", index=False)

    # Reconciliation that Power BI KPIs must reproduce.
    kpis = dict(
        total_distinct_sites=int(dim_site.shape[0]),
        total_facility_records=int(fact_facility.shape[0]),
        population_2011=int(dim_ward["population_2011"].sum()),
        sites_per_100k=round(dim_site.shape[0] / dim_ward["population_2011"].sum() * 1e5, 4),
        records_by_category=fact_facility["category"].value_counts().to_dict(),
        wards=int(dim_ward.shape[0]), clusters=int(dim_cluster.shape[0]),
    )
    assert kpis["total_distinct_sites"] == dim_ward["total_distinct_public_facilities"].sum()
    assert fact_ward_category["facility_records"].sum() == kpis["total_facility_records"]
    assert set(fact_facility["ward_id"]) <= set(dim_ward["ward_id"])
    assert dim_ward["cluster_label"].notna().all()
    pd.Series(kpis).to_json(OUT / "expected_kpis.json", indent=2)
    return kpis

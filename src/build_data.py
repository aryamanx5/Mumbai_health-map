"""Stage 1-2: cleaned facility master, ward table, indicators, and data-quality outputs."""
import json

import pandas as pd

from .config import CATEGORIES, INTERIM, PROCESSED, ROOT, TABLES, WARD_ORDER
from .data_ingestion import file_inventory
from .data_integration import build_facility_master, clean_hospital_list, reconcile_hospital_list
from .geospatial_processing import load_ward_polygons, validate_assignments
from .indicators import compute_indicators, ward_counts
from .population import build_population_table
from .preprocessing import ward_display_name


def run():
    for d in (INTERIM, PROCESSED, TABLES):
        d.mkdir(parents=True, exist_ok=True)

    inventory = file_inventory()
    inventory.to_csv(TABLES / "raw_file_inventory.csv", index=False)

    master, log = build_facility_master()
    wards = load_ward_polygons()
    checks = validate_assignments(master, wards)
    master = master.merge(checks, on="facility_id", how="left")
    master["ward_name"] = master["ward_id"].map(ward_display_name)

    # Physical-site table: one row per distinct site, with its service categories.
    sites = (master.sort_values("facility_id").groupby("site_id")
             .agg(ward_id=("ward_id", "first"), ward_ids_n=("ward_id", "nunique"),
                  site_name=("facility_name", "first"),
                  categories=("category", lambda s: ";".join(sorted(set(s)))),
                  n_records=("facility_id", "count"),
                  longitude=("longitude", "mean"), latitude=("latitude", "mean"))
             .reset_index())
    assert (sites["ward_ids_n"] == 1).all(), "a site spans more than one ward"
    for c in CATEGORIES:
        sites[f"is_{c}"] = sites["categories"].str.split(";").map(lambda cs, c=c: c in cs)
    sites = sites.drop(columns="ward_ids_n")

    pop, pop_checks = build_population_table()
    ward_master = wards.drop(columns="geometry").merge(pop, on="ward_id", how="left")
    ward_master["ward_name"] = ward_master["ward_id"].map(ward_display_name)
    ward_master["ward_order"] = ward_master["ward_id"].map(WARD_ORDER.index) + 1
    ward_master = ward_master.sort_values("ward_order").reset_index(drop=True)
    ward_master["population_density_per_km2"] = ward_master["population_2011"] / ward_master["area_km2"]

    counts = ward_counts(master, ward_master["ward_id"].tolist())
    ward_table = compute_indicators(ward_master.merge(counts, on="ward_id", how="left"))

    rec, kml_only, csv_summary = reconcile_hospital_list(master)

    # ---- reconciliation checks (fail loudly) ----
    assert len(ward_table) == 24 and set(ward_table["ward_id"]) == set(WARD_ORDER)
    assert ward_table["total_distinct_public_facilities"].sum() == master["site_id"].nunique() == len(sites)
    assert ward_table["total_facility_records"].sum() == len(master)
    for c in CATEGORIES:
        assert ward_table[f"{c}_count"].sum() == (master["category"] == c).sum() == sites[f"is_{c}"].sum()
    assert abs(ward_table["population_share_pct"].sum() - 100) < 1e-9
    assert abs(ward_table["facility_share_pct"].sum() - 100) < 1e-9

    # ---- write outputs ----
    master.to_csv(PROCESSED / "facility_master.csv", index=False)
    sites.to_csv(PROCESSED / "facility_sites.csv", index=False)
    ward_table.to_csv(PROCESSED / "ward_indicators.csv", index=False)
    wards[["ward_id", "geometry"]].to_file(PROCESSED / "ward_boundaries.geojson", driver="GeoJSON")
    pop.to_csv(INTERIM / "ward_population_2011.csv", index=False)
    pop_checks.to_csv(TABLES / "population_checks.csv", index=False)
    log["ward_map"].to_csv(TABLES / "ward_value_mapping.csv", index=False)
    log["pairs"].to_csv(TABLES / "colocation_candidate_pairs.csv", index=False)
    log["exclusions"].to_csv(TABLES / "exclusion_log.csv", index=False)
    checks.merge(master[["facility_id", "facility_name", "category", "ward_id", "coordinate_decimals"]],
                 on="facility_id").query("assignment_check != 'agree'").to_csv(
        TABLES / "ward_assignment_review.csv", index=False)
    rec.to_csv(TABLES / "hospital_list_reconciliation.csv", index=False)
    hospital_list = clean_hospital_list(rec)
    hospital_list.to_csv(PROCESSED / "hospital_list_clean.csv", index=False)
    kml_only.to_csv(TABLES / "kml_hospitals_not_in_csv.csv", index=False)

    summary = dict(
        raw_records=log["raw_counts"], raw_records_total=sum(log["raw_counts"].values()),
        excluded_records=len(log["exclusions"]), master_records=len(master),
        distinct_sites=len(sites), multi_category_sites=int((sites["n_records"] > 1).sum()),
        category_records=master["category"].value_counts().to_dict(),
        colocation_pairs=log["pairs"]["decision"].value_counts().to_dict(),
        colocation_matches_by_pair=log["pairs"].query("decision=='match'")
            .groupby(["category_a", "category_b"]).size().rename("n").reset_index().to_dict("records"),
        coordinate_status=master["coordinate_status"].value_counts().to_dict(),
        coordinate_decimals=master["coordinate_decimals"].value_counts(dropna=False).sort_index()
            .rename(index=str).to_dict(),
        assignment_check=master["assignment_check"].value_counts().to_dict(),
        ward_polygon_problems=wards.attrs["problems"], ward_polygons_repaired=int(wards["geometry_repaired"].sum()),
        total_area_km2=round(float(wards["area_km2"].sum()), 2),
        population_total_2011=int(pop["population_2011"].sum()),
        population_checks_passed=bool(pop_checks["passed"].all()),
        hospital_csv=csv_summary, hospital_csv_reconciliation=rec["status"].value_counts().to_dict(),
        kml_hospital_records_not_in_csv=len(kml_only),
        hospital_list_ownership=hospital_list["ownership_class"].value_counts().to_dict(),
        hospital_list_beds_missing=int(hospital_list["beds"].isna().sum()),
        hospital_list_unmapped_wards=int(hospital_list["ward_id"].isna().sum()),
    )
    (TABLES / "data_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    return dict(master=master, sites=sites, ward_table=ward_table, wards=wards, log=log,
                summary=summary, rec=rec, pop_checks=pop_checks, inventory=inventory)


if __name__ == "__main__":
    out = run()
    print(json.dumps(out["summary"], indent=2, default=str))

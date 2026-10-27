"""Cross-check the OpenCity ward polygons against an independent copy (BMC_admin_wards.geojson).

Source of the second layer: github.com/sanjanakrishnan/mumbai_spatial_data (24 BMC administrative wards, not the
227 electoral wards). The OpenCity layer stays the primary geometry; this stage only measures agreement.
"""
import json

import geopandas as gpd
import pandas as pd

from .config import PROCESSED, PROJECTED_CRS, RAW, TABLES, WARD_ORDER
from .preprocessing import standardize_ward

BMC_GEOJSON = RAW / "boundaries" / "BMC_admin_wards.geojson"
SOURCE_URL = "https://github.com/sanjanakrishnan/mumbai_spatial_data/blob/master/BMC_admin_wards.geojson"


def run(master=None):
    primary = gpd.read_file(PROCESSED / "ward_boundaries.geojson").to_crs(PROJECTED_CRS).set_index("ward_id")
    other = gpd.read_file(BMC_GEOJSON)
    other["ward_id"] = other["name"].map(standardize_ward)
    problems = []
    if other["ward_id"].isna().any() or set(other["ward_id"]) != set(WARD_ORDER):
        problems.append("BMC layer does not resolve to the 24 administrative wards")
    other = other.to_crs(PROJECTED_CRS).set_index("ward_id")
    other["geometry"] = other.geometry.buffer(0)

    rows = []
    for w in WARD_ORDER:
        a, b = primary.geometry[w], other.geometry[w]
        inter = a.intersection(b).area
        rows.append(dict(ward_id=w, area_opencity_km2=a.area / 1e6, area_bmc_layer_km2=b.area / 1e6,
                         iou=inter / a.union(b).area, share_of_opencity_covered=inter / a.area))
    table = pd.DataFrame(rows).round(4)

    agree = None
    if master is None and (PROCESSED / "facility_master.csv").exists():
        master = pd.read_csv(PROCESSED / "facility_master.csv")
    if master is not None:
        pts = master[master["coordinate_status"] == "valid"]
        g = gpd.GeoDataFrame(pts[["facility_id", "ward_id"]],
                             geometry=gpd.points_from_xy(pts.longitude, pts.latitude), crs="EPSG:4326")
        j = gpd.sjoin(g.to_crs(PROJECTED_CRS), other.reset_index()[["ward_id", "geometry"]].rename(
            columns={"ward_id": "bmc_ward"}), how="left", predicate="within")
        j = j[~j.index.duplicated()]
        agree = dict(points=len(j), same_as_source_ward=int((j["bmc_ward"] == j["ward_id"]).sum()),
                     outside_bmc_layer=int(j["bmc_ward"].isna().sum()))

    summary = dict(source=SOURCE_URL, wards=len(other), problems=problems,
                   median_iou=float(table["iou"].median()), min_iou=float(table["iou"].min()),
                   min_iou_ward=table.loc[table["iou"].idxmin(), "ward_id"],
                   total_area_opencity_km2=round(float(table["area_opencity_km2"].sum()), 2),
                   total_area_bmc_layer_km2=round(float(table["area_bmc_layer_km2"].sum()), 2),
                   facility_points=agree)
    table.to_csv(TABLES / "boundary_crosscheck.csv", index=False)
    (TABLES / "boundary_crosscheck.json").write_text(json.dumps(summary, indent=2))
    return summary, table


if __name__ == "__main__":
    s, t = run()
    print(json.dumps(s, indent=2))
    print(t.to_string(index=False))

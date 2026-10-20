"""Ward polygons and spatial validation of source ward assignments."""
import geopandas as gpd
import pandas as pd

from .config import PROJECTED_CRS, RAW, WARD_ORDER
from .data_ingestion import read_kml_polygons
from .preprocessing import rounding_error_m, standardize_ward


def load_ward_polygons(path=RAW / "mumbai_wards.kml"):
    df = read_kml_polygons(path)
    df["ward_id"] = df["source_ward_name"].map(standardize_ward)
    gdf = gpd.GeoDataFrame(df, geometry="geometry", crs="EPSG:4326")
    problems = []
    if gdf["ward_id"].isna().any():
        problems.append(f"unmapped polygon names: {gdf.loc[gdf.ward_id.isna(), 'source_ward_name'].tolist()}")
    if gdf["ward_id"].duplicated().any():
        problems.append("duplicate ward polygons")
    if set(gdf["ward_id"]) != set(WARD_ORDER):
        problems.append(f"polygon wards differ from the 24-ward list: {set(WARD_ORDER) ^ set(gdf['ward_id'])}")
    invalid = ~gdf.geometry.is_valid
    if invalid.any():
        gdf.loc[invalid, "geometry"] = gdf.loc[invalid, "geometry"].buffer(0)
    gdf["geometry_repaired"] = invalid
    gdf["area_km2"] = gdf.to_crs(PROJECTED_CRS).area / 1e6
    gdf.attrs["problems"] = problems
    return gdf[["ward_id", "source_ward_name", "area_km2", "geometry_repaired", "geometry"]]


def validate_assignments(facilities, wards):
    """Compare each facility's source ward with the polygon its point falls in.

    Returns per-record: spatial_ward_id, distance_to_source_ward_m, assignment_check.
    The source ward stays authoritative; this only flags records for review.
    """
    has_xy = facilities["coordinate_status"] == "valid"
    pts = gpd.GeoDataFrame(
        facilities.loc[has_xy, ["facility_id"]],
        geometry=gpd.points_from_xy(facilities.loc[has_xy, "longitude"], facilities.loc[has_xy, "latitude"]),
        crs="EPSG:4326",
    )
    joined = gpd.sjoin(pts, wards[["ward_id", "geometry"]], how="left", predicate="within")
    joined = joined[~joined.index.duplicated()]  # a point on a shared edge can hit two polygons
    out = facilities[["facility_id", "ward_id", "coordinate_decimals"]].copy()
    out["spatial_ward_id"] = joined["ward_id"].reindex(out.index)

    pts_m = pts.to_crs(PROJECTED_CRS)
    wards_m = wards.set_index("ward_id").to_crs(PROJECTED_CRS).geometry
    dist = pd.Series(index=out.index, dtype=float)
    for idx, geom in pts_m.geometry.items():
        src = out.at[idx, "ward_id"]
        if src in wards_m.index:
            dist[idx] = geom.distance(wards_m[src])
    out["distance_to_source_ward_m"] = dist.round(1)

    def classify(r):
        if pd.isna(r.coordinate_decimals) or r.name not in pts.index:
            return "no_valid_coordinates"
        near = r.distance_to_source_ward_m <= rounding_error_m(int(r.coordinate_decimals))
        if pd.isna(r.spatial_ward_id):
            return "outside_polygons_within_rounding" if near else "outside_polygons_review"
        if r.spatial_ward_id == r.ward_id:
            return "agree"
        return "disagree_within_coordinate_rounding" if near else "disagree_review"

    out["assignment_check"] = out.apply(classify, axis=1)
    return out[["facility_id", "spatial_ward_id", "distance_to_source_ward_m", "assignment_check"]]

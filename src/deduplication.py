"""Within-layer duplicate detection and cross-layer co-location into physical sites."""
import itertools
import math

import pandas as pd

from .config import COLOCATION_BASE_TOLERANCE_M
from .preprocessing import rounding_error_m


def haversine_m(lon1, lat1, lon2, lat2):
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def match_tolerance_m(dec_a, dec_b):
    return COLOCATION_BASE_TOLERANCE_M + rounding_error_m(int(dec_a)) + rounding_error_m(int(dec_b))


def candidate_pairs(df):
    """All record pairs that share a ward and an identical, non-empty name stem.

    Each pair gets a distance and a decision. A pair is a match only when the
    coordinates are also within tolerance; name + ward alone is not enough.
    """
    rows = []
    for (_, _), grp in df[df["name_stem"] != ""].groupby(["ward_id", "name_stem"]):
        for a, b in itertools.combinations(grp.itertuples(), 2):
            if pd.isna(a.longitude) or pd.isna(b.longitude):
                dist, tol, decision = None, None, "no_match_missing_coordinates"
            else:
                dist = haversine_m(a.longitude, a.latitude, b.longitude, b.latitude)
                tol = match_tolerance_m(a.coordinate_decimals, b.coordinate_decimals)
                decision = "match" if dist <= tol else "no_match_too_far"
            rows.append(dict(facility_id_a=a.facility_id, category_a=a.category, name_a=a.facility_name,
                             facility_id_b=b.facility_id, category_b=b.category, name_b=b.facility_name,
                             ward_id=a.ward_id, name_stem=a.name_stem,
                             distance_m=None if dist is None else round(dist, 1),
                             tolerance_m=None if tol is None else round(tol, 1), decision=decision))
    return pd.DataFrame(rows, columns=["facility_id_a", "category_a", "name_a", "facility_id_b", "category_b",
                                       "name_b", "ward_id", "name_stem", "distance_m", "tolerance_m", "decision"])


def exact_duplicates(df, cols):
    return df[df.duplicated(subset=cols, keep="first")]


def assign_sites(df, pairs):
    """Union-find over matched pairs. Same-category matches are within-layer duplicates;
    cross-category matches are one physical site offering several services."""
    parent = {f: f for f in df["facility_id"]}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for p in pairs[pairs["decision"] == "match"].itertuples():
        ra, rb = find(p.facility_id_a), find(p.facility_id_b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)
    roots = df["facility_id"].map(find)
    order = {r: i + 1 for i, r in enumerate(pd.unique(roots))}
    return roots.map(lambda r: f"SITE-{order[r]:04d}")

"""Standardization helpers: ward codes, names, coordinates."""
import math
import re

import numpy as np
import pandas as pd

from .config import MUMBAI_BBOX, SUFFIX_NAMES, WARD_ORDER

CANONICAL_WARDS = set(WARD_ORDER)


def standardize_ward(value):
    """Map a source ward value (e.g. 'GS', 'G/S', ' k/e ') to a canonical ward id, or None.

    Equivalence is purely structural: a one-letter ward plus a direction suffix with the
    slash removed. Anything that does not resolve to one of the 24 canonical ids returns None.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    v = re.sub(r"\s+", "", str(value)).upper().replace("\\", "/")
    if v in CANONICAL_WARDS:
        return v
    if len(v) == 2 and f"{v[0]}/{v[1]}" in CANONICAL_WARDS:
        return f"{v[0]}/{v[1]}"
    return None


def ward_display_name(ward_id):
    if "/" in ward_id:
        letter, suffix = ward_id.split("/")
        return f"{letter} {SUFFIX_NAMES[suffix]}"
    return ward_id


def clean_text(s):
    if s is None or (isinstance(s, float) and math.isnan(s)):
        return None
    s = str(s).replace("\xa0", " ")
    s = re.sub(r"\s+", " ", s).strip()
    return s or None


TYPE_WORDS = {
    "dispensary", "dispensaries", "disp", "uphc", "municipal", "mun", "health", "post", "centre", "center",
    "hospital", "hosp", "hospitals", "maternity", "mat", "home", "general", "gen", "bmc", "mcgm", "the",
    "and", "of", "urban", "primary", "nursing",
}


def name_stem(name):
    """Lower-case name with punctuation and facility-type words removed (for matching only)."""
    if not name:
        return ""
    tokens = re.sub(r"[^a-z0-9 ]", " ", name.lower().replace("&", " and ")).split()
    return " ".join(t for t in tokens if t not in TYPE_WORDS)


def coordinate_decimals(x, max_decimals=8):
    """Smallest number of decimals that reproduces x (float artifacts like 72.8199999 -> 2)."""
    for d in range(max_decimals + 1):
        if abs(x - round(x, d)) < 1e-9:
            return d
    return max_decimals


def rounding_error_m(decimals, lat_deg=19.07):
    """Worst-case distance error (metres) from rounding both lon and lat to `decimals`."""
    half = 0.5 * 10 ** (-decimals)
    dy = half * 111_320
    dx = half * 111_320 * math.cos(math.radians(lat_deg))
    return math.hypot(dx, dy)


def parse_point(raw):
    """'lon,lat[,alt]' -> (lon, lat) floats, or (nan, nan) if missing/malformed."""
    if not isinstance(raw, str) or not raw.strip():
        return np.nan, np.nan
    try:
        parts = raw.split(",")
        return float(parts[0]), float(parts[1])
    except (ValueError, IndexError):
        return np.nan, np.nan


def coordinate_status(lon, lat):
    if pd.isna(lon) or pd.isna(lat):
        return "missing"
    b = MUMBAI_BBOX
    if not (b["lon_min"] <= lon <= b["lon_max"] and b["lat_min"] <= lat <= b["lat_max"]):
        return "outside_study_bbox"
    return "valid"

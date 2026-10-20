import numpy as np
import pandas as pd
import pytest

from src.deduplication import assign_sites, candidate_pairs
from src.preprocessing import (coordinate_decimals, coordinate_status, name_stem, parse_point,
                               rounding_error_m, standardize_ward)


@pytest.mark.parametrize("raw,expected", [
    ("GS", "G/S"), ("G/S", "G/S"), (" k/e ", "K/E"), ("RC", "R/C"), ("A", "A"), ("T", "T"),
    ("XYZ", None), ("G/X", None), ("", None), (None, None), (np.nan, None),
])
def test_standardize_ward(raw, expected):
    assert standardize_ward(raw) == expected


def test_name_stem_removes_type_words():
    assert name_stem("Colaba Dispensary") == name_stem("Colaba UPHC") == "colaba"
    assert name_stem("R. S. Nimkar Disp") == name_stem("R S Nimkar UPHC")
    assert name_stem("Naigaon Maternity Home") == "naigaon"


def test_coordinate_decimals_ignores_float_artifacts():
    assert coordinate_decimals(72.81999999999999) == 2
    assert coordinate_decimals(72.8336) == 4
    assert coordinate_decimals(19.0) == 0


def test_rounding_error_monotone():
    assert rounding_error_m(2) > rounding_error_m(4) > 0
    assert 700 < rounding_error_m(2) < 800


def test_parse_point_and_status():
    assert parse_point("72.83,18.92,0") == (72.83, 18.92)
    assert all(np.isnan(v) for v in parse_point(None))
    assert all(np.isnan(v) for v in parse_point(float("nan")))
    assert all(np.isnan(v) for v in parse_point("abc"))
    assert coordinate_status(72.83, 18.92) == "valid"
    assert coordinate_status(0.0, 0.0) == "outside_study_bbox"
    assert coordinate_status(np.nan, 18.9) == "missing"


def _records():
    return pd.DataFrame({
        "facility_id": ["DISP-1", "UPHC-1", "DISP-2", "DISP-3", "UPHC-3", "MAT-1"],
        "category": ["dispensary", "uphc", "dispensary", "dispensary", "uphc", "maternity_hospital"],
        "facility_name": ["Kajupada Dispensary", "Kajupada UPHC", "Kajupada Dispensary",
                          "Far Dispensary", "Far UPHC", "Kajupada Maternity Home"],
        "ward_id": ["L", "L", "R/C", "S", "S", "L"],
        "longitude": [72.89, 72.89, 72.87, 72.90, 72.99, np.nan],
        "latitude": [19.09, 19.09, 19.23, 19.10, 19.20, np.nan],
        "coordinate_decimals": [2, 2, 2, 4, 4, pd.NA],
    })


def test_colocation_requires_ward_name_and_distance():
    df = _records()
    df["name_stem"] = df["facility_name"].map(name_stem)
    pairs = candidate_pairs(df)
    decisions = {(p.facility_id_a, p.facility_id_b): p.decision for p in pairs.itertuples()}
    assert decisions[("DISP-1", "UPHC-1")] == "match"
    # same name in a different ward is never even a candidate
    assert not any("DISP-2" in k for k in decisions)
    assert decisions[("DISP-3", "UPHC-3")] == "no_match_too_far"
    assert decisions[("DISP-1", "MAT-1")] == "no_match_missing_coordinates"
    sites = assign_sites(df, pairs)
    assert sites[0] == sites[1]
    assert sites.nunique() == 5

import numpy as np
import pandas as pd
import pytest

from src.indicators import compute_indicators, per_100k, population_per_facility, share_pct, ward_counts


def test_per_100k_known_values():
    out = per_100k([5, 0, 3], [250_000, 100_000, 300_000])
    assert out.tolist() == pytest.approx([2.0, 0.0, 1.0])


def test_per_100k_invalid_population_is_undefined_not_zero():
    out = per_100k([5, 5, 5], [np.nan, 0, -10])
    assert out.isna().all()


def test_population_per_facility_zero_facilities_undefined():
    out = population_per_facility([100_000, 100_000], [0, 4])
    assert np.isnan(out[0]) and out[1] == 25_000


def test_share_pct_sums_to_100_and_handles_zero_total():
    assert share_pct([1, 1, 2]).tolist() == pytest.approx([25, 25, 50])
    assert share_pct([0, 0]).isna().all()


def _toy_master():
    # Ward X: one site holding a dispensary and a UPHC (multi-category), plus a hospital.
    # Ward Y: one dispensary. Ward Z: no facilities.
    return pd.DataFrame({
        "facility_id": ["D1", "U1", "H1", "D2"],
        "site_id": ["S1", "S1", "S2", "S3"],
        "ward_id": ["X", "X", "X", "Y"],
        "category": ["dispensary", "uphc", "public_hospital", "dispensary"],
    })


def test_ward_counts_keeps_zero_wards_and_counts_distinct_sites():
    c = ward_counts(_toy_master(), ["X", "Y", "Z"]).set_index("ward_id")
    assert c.loc["Z"].sum() == 0
    assert c.loc["X", "total_distinct_public_facilities"] == 2  # S1 counted once
    assert c.loc["X", "total_facility_records"] == 3
    assert c.loc["X", "dispensary_count"] == 1 and c.loc["X", "uphc_count"] == 1
    assert c.loc["X", "maternity_hospital_count"] == 0


def test_compute_indicators_end_to_end_independent_calculation():
    c = ward_counts(_toy_master(), ["X", "Y", "Z"])
    c["population_2011"] = [200_000, 100_000, 100_000]
    t = compute_indicators(c).set_index("ward_id")
    assert t.loc["X", "facilities_per_100k"] == pytest.approx(1.0)
    assert t.loc["Y", "population_per_facility"] == pytest.approx(100_000)
    assert np.isnan(t.loc["Z", "population_per_facility"])
    assert t.loc["Z", "facilities_per_100k"] == 0
    # 2 of 3 sites in X; 50% of population in X
    assert t.loc["X", "facility_share_pct"] == pytest.approx(200 / 3)
    assert t.loc["X", "population_facility_share_gap"] == pytest.approx(50 - 200 / 3)
    # multi-category: category shares in X sum to more than 100%
    shares = t.loc["X", ["dispensary_share_pct", "uphc_share_pct", "public_hospital_share_pct",
                         "maternity_hospital_share_pct"]].sum()
    assert shares == pytest.approx(150)
    assert np.isnan(t.loc["Z", "dispensary_share_pct"])


def test_missing_population_propagates_as_undefined():
    c = ward_counts(_toy_master(), ["X", "Y"])
    c["population_2011"] = [np.nan, 100_000]
    t = compute_indicators(c).set_index("ward_id")
    assert np.isnan(t.loc["X", "facilities_per_100k"])
    assert t.loc["Y", "facilities_per_100k"] == pytest.approx(1.0)

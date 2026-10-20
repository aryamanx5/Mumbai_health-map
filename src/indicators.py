"""Ward-level indicators. Undefined values are NaN, never zero-filled."""
import numpy as np
import pandas as pd

from .config import CATEGORIES


def per_100k(count, population):
    count = pd.Series(count, dtype=float)
    population = pd.Series(population, dtype=float)
    valid = population.notna() & (population > 0) & count.notna()
    return pd.Series(np.where(valid, count / population.where(valid) * 100_000, np.nan), index=count.index)


def population_per_facility(population, facilities):
    population = pd.Series(population, dtype=float)
    facilities = pd.Series(facilities, dtype=float)
    valid = population.notna() & (population > 0) & (facilities > 0)
    return pd.Series(np.where(valid, population / facilities.where(valid), np.nan), index=population.index)


def share_pct(part):
    part = pd.Series(part, dtype=float)
    total = part.sum(skipna=True)
    if not total or np.isnan(total):
        return pd.Series(np.nan, index=part.index)
    return part / total * 100


def ward_counts(master, wards):
    """Facility counts per ward from the master table, driven by the ward list (zeros kept)."""
    cat = (master.groupby(["ward_id", "category"])["facility_id"].nunique()
           .unstack(fill_value=0).reindex(columns=CATEGORIES, fill_value=0))
    cat.columns = [f"{c}_count" for c in cat.columns]
    sites = master.groupby("ward_id")["site_id"].nunique().rename("total_distinct_public_facilities")
    units = master.groupby("ward_id")["facility_id"].nunique().rename("total_facility_records")
    out = pd.DataFrame({"ward_id": wards}).set_index("ward_id").join([cat, sites, units])
    return out.fillna(0).astype(int).reset_index()


def compute_indicators(ward_table):
    t = ward_table.copy()
    pop = t["population_2011"]
    total = t["total_distinct_public_facilities"]
    t["facilities_per_100k"] = per_100k(total, pop)
    t["population_per_facility"] = population_per_facility(pop, total)
    for c in CATEGORIES:
        t[f"{c}_per_100k"] = per_100k(t[f"{c}_count"], pop)
        t[f"{c}_share_pct"] = np.where(total > 0, t[f"{c}_count"] / total.where(total > 0) * 100, np.nan)
    t["population_share_pct"] = share_pct(pop)
    t["facility_share_pct"] = share_pct(total)
    t["population_facility_share_gap"] = t["population_share_pct"] - t["facility_share_pct"]
    return t

"""Aggregate 2011 Census population from census wards to the 24 BMC wards, with cross-checks."""
import pandas as pd

from .config import RAW, WARD_ORDER
from .preprocessing import standardize_ward


def load_census_wards(path=RAW / "mumbai_census_2011_wards.csv"):
    c = pd.read_csv(path, dtype={"Ward Code": str})
    c["census_ward_code"] = c["Ward Code"].str.zfill(4)
    c["ward_id"] = c["Ward Name"].map(standardize_ward)
    return c


def load_pca(paths=(RAW / "mumbai_city_pca_2011.csv", RAW / "mumbai_suburban_pca_2011.csv")):
    frames = [pd.read_csv(p, dtype=str, encoding="utf-8-sig") for p in paths]
    pca = pd.concat(frames, ignore_index=True)
    town_totals = pca[(pca["Level"] == "TOWN") & (pca["TRU"] == "Urban")]["TOT_P"].astype(int).sum()
    w = pca[(pca["Level"] == "WARD") & (pca["TRU"] == "Urban")].copy()
    w["census_ward_code"] = w["Ward"].str.zfill(4)
    w["TOT_P"] = w["TOT_P"].astype(int)
    return w[["census_ward_code", "TOT_P", "District"]], town_totals


def build_population_table():
    """Returns (ward population table, list of check results)."""
    c = load_census_wards()
    pca, town_total = load_pca()
    checks = []

    def check(name, ok, detail=""):
        checks.append(dict(check=name, passed=bool(ok), detail=detail))

    check("all census ward names map to a BMC ward", c["ward_id"].notna().all(),
          str(c.loc[c.ward_id.isna(), "Ward Name"].tolist()))
    check("census ward codes unique", not c["census_ward_code"].duplicated().any())
    # The first two digits of the census ward code follow the BMC ward sequence (01=A ... 24=T).
    prefix_map = c.groupby(c["census_ward_code"].str[:2])["ward_id"].agg(lambda s: sorted(set(s)))
    expected = {f"{i + 1:02d}": [w] for i, w in enumerate(WARD_ORDER)}
    check("ward-code prefix agrees with ward name for every row", prefix_map.to_dict() == expected,
          "" if prefix_map.to_dict() == expected else str(prefix_map.to_dict()))
    merged = c.merge(pca, on="census_ward_code", how="outer", indicator=True)
    check("every census ward found in Primary Census Abstract", (merged["_merge"] == "both").all(),
          merged["_merge"].value_counts().to_dict().__str__())
    both = merged[merged["_merge"] == "both"]
    mism = both[both["Total Population"] != both["TOT_P"]]
    check("ward populations equal PCA TOT_P", mism.empty, f"{len(mism)} mismatches")
    total = int(c["Total Population"].sum())
    check("total equals sum of the two district TOWN totals (Greater Mumbai)", total == town_total,
          f"{total} vs {town_total}")

    pop = (c.groupby("ward_id")
           .agg(population_2011=("Total Population", "sum"),
                census_wards=("census_ward_code", "count"),
                census_district=("District Name", "first"))
           .reindex(WARD_ORDER).reset_index())
    check("24 wards with positive population", len(pop) == 24 and (pop["population_2011"] > 0).all())
    return pop, pd.DataFrame(checks)

"""EDA tables and figures from the validated ward and facility tables."""
import json

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, TwoSlopeNorm

from . import plot_style as ps
from .config import CATEGORIES, FIGURES, TABLES

SOURCE_NOTE = ("Sources: OpenCity / MCGM facility KMLs (Nov 2025); Census of India 2011 ward population. "
               "Counts are listed public facilities, not capacity or access.")


def _save(fig, name):
    FIGURES.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES / name)
    plt.close(fig)
    return name


def category_totals(master, sites):
    rows = [dict(category=ps.CATEGORY_LABELS[c], facility_records=int((master.category == c).sum()),
                 sites_offering=int(sites[f"is_{c}"].sum())) for c in CATEGORIES]
    df = pd.DataFrame(rows)
    fig, ax = plt.subplots(figsize=(7, 3.2))
    ax.barh(df["category"][::-1], df["facility_records"][::-1], color=ps.SERIES[0], height=0.55)
    for y, v in enumerate(df["facility_records"][::-1]):
        ax.text(v + 2, y, str(v), va="center", color=ps.TEXT_2, fontsize=9)
    ax.set_xlabel("Listed facility records")
    ax.set_title(f"Listed public facilities by category ({len(sites)} distinct sites, {len(master)} records)")
    ax.grid(axis="y", visible=False)
    multi = int((sites["n_records"] > 1).sum())
    ps.note(fig, f"{multi} sites hold more than one category (mostly a dispensary and a UPHC at the same site), "
                 "so category records sum to more than distinct sites.")
    return df, _save(fig, "01_category_totals.png")


def ranked_bar(t, col, title, xlabel, name, fmt="{:.2f}", ref=None, ref_label=None):
    d = t.sort_values(col, ascending=True)
    fig, ax = plt.subplots(figsize=(7.5, 7))
    ax.barh(d["ward_id"], d[col], color=ps.SERIES[0], height=0.62)
    for y, v in enumerate(d[col]):
        ax.text(v, y, " " + fmt.format(v), va="center", fontsize=8, color=ps.TEXT_2)
    if ref is not None:
        ax.axvline(ref, color=ps.TEXT_2, lw=1, ls="--")
        ax.text(ref, len(d) - 0.3, f" {ref_label}", fontsize=8, color=ps.TEXT_2, va="bottom")
    ax.set_title(title)
    ax.set_xlabel(xlabel)
    ax.grid(axis="y", visible=False)
    ps.note(fig, SOURCE_NOTE)
    return _save(fig, name)


def category_mix(t):
    d = t.sort_values("total_distinct_public_facilities")
    fig, ax = plt.subplots(figsize=(8, 7))
    left = np.zeros(len(d))
    for i, c in enumerate(CATEGORIES):
        v = d[f"{c}_count"].to_numpy()
        ax.barh(d["ward_id"], v, left=left, color=ps.SERIES[i], height=0.62, label=ps.CATEGORY_LABELS[c],
                edgecolor=ps.SURFACE, linewidth=1)
        left += v
    ax.legend(loc="lower right", ncols=2)
    ax.set_title("Facility records by category and ward")
    ax.set_xlabel("Facility records (a co-located site counts once per category)")
    ax.grid(axis="y", visible=False)
    ps.note(fig, SOURCE_NOTE)
    return _save(fig, "05_category_mix_by_ward.png")


def rate_heatmap(t):
    cols = [f"{c}_per_100k" for c in CATEGORIES]
    d = t.set_index("ward_id")[cols]
    z = (d - d.mean()) / d.std()
    # Red = below the ward mean (relatively fewer facilities), matching the share-gap chart's polarity.
    cmap = LinearSegmentedColormap.from_list("div", ps.DIVERGING[::-1])
    fig, ax = plt.subplots(figsize=(6.5, 8))
    lim = float(np.nanmax(np.abs(z.to_numpy())))
    im = ax.imshow(z.to_numpy(), cmap=cmap, norm=TwoSlopeNorm(0, -lim, lim), aspect="auto")
    for (i, j), v in np.ndenumerate(d.to_numpy()):
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7.5, color=ps.TEXT)
    ax.set_xticks(range(len(cols)), [ps.CATEGORY_LABELS[c] for c in CATEGORIES], rotation=20, ha="right")
    ax.set_yticks(range(len(d)), d.index)
    ax.grid(False)
    ax.set_title("Facilities per 100,000 residents by category")
    cb = fig.colorbar(im, ax=ax, shrink=0.6)
    cb.set_label("SD from ward mean (red = below, blue = above)")
    ps.note(fig, "Cell text shows the rate; colour shows how far it sits from the 24-ward mean for that category.")
    return _save(fig, "06_rate_heatmap.png")


def scatter_population(t):
    fig, ax = plt.subplots(figsize=(7.5, 5.5))
    x, y = t["population_2011"] / 1e5, t["total_distinct_public_facilities"]
    ax.scatter(x, y, s=46, color=ps.SERIES[0], edgecolor=ps.SURFACE, linewidth=1.5, zorder=3)
    rate = y.sum() / (t["population_2011"].sum() / 1e5)
    xs = np.linspace(0, x.max() * 1.05, 10)
    ax.plot(xs, xs * rate, color=ps.TEXT_2, lw=1, ls="--")
    ax.text(xs[-1], xs[-1] * rate, f" city-wide rate\n {rate:.2f} per 100k", fontsize=8, color=ps.TEXT_2, va="center")
    for r in t.itertuples():
        ax.annotate(r.ward_id, (r.population_2011 / 1e5, r.total_distinct_public_facilities), xytext=(4, 3),
                    textcoords="offset points", fontsize=8, color=ps.TEXT_2)
    ax.set_xlabel("Population, Census 2011 (lakh = 100,000)")
    ax.set_ylabel("Distinct public facility sites")
    ax.set_title("Population vs. listed public facility sites, by ward")
    ps.note(fig, "Points below the dashed line have fewer sites than the city-wide rate would imply. " + SOURCE_NOTE)
    return _save(fig, "07_population_vs_facilities.png")


def share_gap(t):
    d = t.sort_values("population_facility_share_gap")
    fig, ax = plt.subplots(figsize=(7.5, 7))
    colors = [ps.DIVERGING[2] if v > 0 else ps.DIVERGING[0] for v in d["population_facility_share_gap"]]
    ax.barh(d["ward_id"], d["population_facility_share_gap"], color=colors, height=0.62)
    for yy, v in enumerate(d["population_facility_share_gap"]):
        ax.text(v, yy, f" {v:+.2f} " if v > 0 else f" {v:+.2f} ", va="center",
                ha="left" if v > 0 else "right", fontsize=8, color=ps.TEXT_2)
    ax.axvline(0, color=ps.TEXT_2, lw=1)
    ax.set_xlabel("Population share minus facility-site share (percentage points)")
    ax.set_title("Population share vs. facility share")
    ax.grid(axis="y", visible=False)
    ps.note(fig, "Red (positive): the ward's share of population exceeds its share of listed sites. "
                 "Blue (negative): the reverse. A distribution indicator, not a measure of access.")
    return _save(fig, "08_population_facility_share_gap.png")


def facility_map(master, wards, t):
    fig, ax = plt.subplots(figsize=(7.5, 10))
    w = wards.merge(t[["ward_id", "facilities_per_100k"]], on="ward_id")
    cmap = LinearSegmentedColormap.from_list("seq", ps.SEQ[:5])
    w.plot(column="facilities_per_100k", cmap=cmap, ax=ax, edgecolor="white", linewidth=0.8, legend=True,
           legend_kwds=dict(label="Distinct sites per 100,000 residents", shrink=0.5))
    for r in w.itertuples():
        p = r.geometry.representative_point()
        ax.text(p.x, p.y, r.ward_id, fontsize=7, ha="center", va="center", color=ps.TEXT, weight="bold")
    pts = master[master["coordinate_status"] == "valid"]
    for i, c in enumerate(CATEGORIES):
        d = pts[pts.category == c]
        ax.scatter(d.longitude, d.latitude, s=12 if i < 2 else 26, marker=ps.MARKERS[i], color=ps.SERIES[i],
                   edgecolor=ps.TEXT if i >= 2 else ps.SURFACE, linewidth=0.5, label=f"{ps.CATEGORY_LABELS[c]} ({len(d)})",
                   zorder=3 + i)
    ax.legend(loc="lower left", fontsize=8, frameon=True, facecolor=ps.SURFACE)
    ax.set_axis_off()
    ax.set_title("Listed public facilities over ward polygons")
    coarse = (pts["coordinate_decimals"] <= 2).mean() * 100
    missing = int((master["coordinate_status"] != "valid").sum())
    ps.note(fig, f"Ward polygons: OpenCity Mumbai Wards Map. {coarse:.0f}% of facility coordinates have 2 or fewer "
                 f"decimals (~1 km), so points are approximate. {missing} record(s) without coordinates not shown.")
    return _save(fig, "09_facility_map.png")


def outliers(t, cols):
    rows = []
    for c in cols:
        q1, q3 = t[c].quantile([0.25, 0.75])
        iqr = q3 - q1
        for r in t.itertuples():
            v = getattr(r, c)
            if v > q3 + 1.5 * iqr or v < q1 - 1.5 * iqr:
                rows.append(dict(metric=c, ward_id=r.ward_id, value=round(v, 3), q1=round(q1, 3), q3=round(q3, 3),
                                 direction="high" if v > q3 else "low"))
    return pd.DataFrame(rows)


def run(master, sites, t, wards):
    ps.apply()
    figs = {}
    cat_df, figs["category_totals"] = category_totals(master, sites)
    city_rate = t.total_distinct_public_facilities.sum() / t.population_2011.sum() * 1e5
    figs["counts"] = ranked_bar(t, "total_distinct_public_facilities", "Distinct public facility sites by ward",
                                "Distinct sites", "02_sites_by_ward.png", fmt="{:.0f}")
    figs["per_100k"] = ranked_bar(t, "facilities_per_100k", "Distinct sites per 100,000 residents",
                                  "Sites per 100,000 residents (Census 2011)", "03_sites_per_100k.png",
                                  ref=city_rate, ref_label=f"city-wide {city_rate:.2f}")
    figs["pop_per_facility"] = ranked_bar(t, "population_per_facility", "Residents per distinct facility site",
                                          "Residents per site (Census 2011)", "04_population_per_site.png",
                                          fmt="{:,.0f}", ref=1e5 / city_rate, ref_label="city-wide")
    figs["mix"] = category_mix(t)
    figs["heatmap"] = rate_heatmap(t)
    figs["scatter"] = scatter_population(t)
    figs["gap"] = share_gap(t)
    figs["map"] = facility_map(master, wards, t)

    rate_cols = ["facilities_per_100k", "population_per_facility", "population_facility_share_gap"] + \
                [f"{c}_per_100k" for c in CATEGORIES]
    out = outliers(t, rate_cols)
    out.to_csv(TABLES / "eda_iqr_outliers.csv", index=False)
    cat_df.to_csv(TABLES / "eda_category_totals.csv", index=False)
    t[["ward_id"] + rate_cols].describe().round(3).to_csv(TABLES / "eda_indicator_summary.csv")
    rk = t[["ward_id", "population_2011", "total_distinct_public_facilities", "facilities_per_100k",
            "population_per_facility", "population_facility_share_gap"]].copy()
    rk["rank_sites_per_100k_low_to_high"] = rk["facilities_per_100k"].rank(method="min").astype(int)
    rk.sort_values("facilities_per_100k").to_csv(TABLES / "eda_ward_ranking.csv", index=False)
    corr = t[[f"{c}_per_100k" for c in CATEGORIES] + ["facilities_per_100k", "population_2011",
                                                       "population_density_per_km2"]].corr(method="spearman")
    corr.round(3).to_csv(TABLES / "eda_spearman_correlations.csv")
    stats = dict(city_rate_per_100k=round(city_rate, 3),
                 pearson_population_vs_sites=round(float(t.population_2011.corr(t.total_distinct_public_facilities)), 3),
                 spearman_population_vs_rate=round(float(corr.loc["population_2011", "facilities_per_100k"]), 3),
                 wards_positive_gap=int((t.population_facility_share_gap > 0).sum()),
                 rate_min_max_ratio=round(float(t.facilities_per_100k.max() / t.facilities_per_100k.min()), 2),
                 figures=figs)
    (TABLES / "eda_stats.json").write_text(json.dumps(stats, indent=2))
    return stats, out

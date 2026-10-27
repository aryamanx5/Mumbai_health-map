"""Build the cleaned facility master table and reconcile with the hospitals list."""
import pandas as pd

from .config import FACILITY_LAYERS, RAW, ROOT
from .data_ingestion import read_hospitals_csv, read_kml_points
from .deduplication import assign_sites, candidate_pairs, exact_duplicates
from .preprocessing import (clean_text, coordinate_decimals, coordinate_status, name_stem, parse_point,
                            standardize_ward)

MASTER_COLUMNS = [
    "facility_id", "site_id", "category", "facility_name", "address", "source_subtype", "owner_dept",
    "source_ward_value", "ward_id", "longitude", "latitude", "coordinate_decimals", "coordinate_status",
    "source_file", "source_record_id", "name_stem",
]


def load_layer(category, spec):
    raw = read_kml_points(RAW / spec["file"])
    df = pd.DataFrame({
        "category": category,
        "source_file": spec["file"],
        "source_record_id": raw[spec["id"]].astype(int),
        "facility_name": raw[spec["name"]].map(clean_text),
        "address": raw[spec["address"]].map(clean_text),
        "source_subtype": raw[spec["subtype"]].map(clean_text) if spec["subtype"] else None,
        "owner_dept": raw[spec["owner"]].map(clean_text),
        "source_ward_value": raw[spec["ward"]],
        "_raw_coordinates": raw["_raw_coordinates"],
    })
    df["facility_id"] = [f"{spec['prefix']}-{i:03d}" for i in df["source_record_id"]]
    return df


def build_facility_master():
    """Returns (master, log) where log holds the intermediate tables used by reports."""
    layers = {c: load_layer(c, s) for c, s in FACILITY_LAYERS.items()}
    raw_counts = {c: len(d) for c, d in layers.items()}
    df = pd.concat(layers.values(), ignore_index=True)

    assert not df["facility_id"].duplicated().any(), "source record ids are not unique within a layer"

    df["ward_id"] = df["source_ward_value"].map(standardize_ward)
    ward_map = (df.groupby(["source_ward_value", "ward_id"], dropna=False).size()
                .rename("records").reset_index().sort_values(["ward_id", "source_ward_value"]))

    xy = df["_raw_coordinates"].map(parse_point)
    df["longitude"] = [p[0] for p in xy]
    df["latitude"] = [p[1] for p in xy]
    df["coordinate_status"] = [coordinate_status(x, y) for x, y in zip(df.longitude, df.latitude)]
    valid = df["coordinate_status"] == "valid"
    df["coordinate_decimals"] = pd.Series(pd.NA, index=df.index, dtype="Int64")
    df.loc[valid, "coordinate_decimals"] = [
        max(coordinate_decimals(x), coordinate_decimals(y)) for x, y in zip(df.loc[valid, "longitude"], df.loc[valid, "latitude"])
    ]
    df.loc[~valid, ["longitude", "latitude"]] = float("nan")

    df["name_stem"] = df["facility_name"].map(name_stem)
    exact = exact_duplicates(df, ["category", "facility_name", "address", "ward_id", "_raw_coordinates"])
    pairs = candidate_pairs(df)
    df["site_id"] = assign_sites(df, pairs)

    # Within-layer duplicates (same category, same site) collapse to one record.
    within = df[df.duplicated(subset=["site_id", "category"], keep="first")]
    exclusions = pd.concat([
        exact.assign(reason="exact duplicate record"),
        within[~within["facility_id"].isin(exact["facility_id"])].assign(reason="within-layer probable duplicate"),
        df[df["ward_id"].isna()].assign(reason="ward value could not be standardized"),
    ], ignore_index=True)
    master = df[~df["facility_id"].isin(exclusions["facility_id"])].copy()

    log = dict(raw_counts=raw_counts, ward_map=ward_map, pairs=pairs, exclusions=exclusions,
               all_records=df)
    return master[MASTER_COLUMNS].reset_index(drop=True), log


MANUAL_MATCHES = ROOT / "data" / "reference" / "hospital_list_manual_matches.csv"

PUBLIC_TYPES = {"Municipal": "Municipal (BMC)", "BMC": "Municipal (BMC)", "Government": "Government",
                "Govt": "Government", "Defence": "Government (Defence)"}


def _tokens(name):
    return set(name_stem(name).split()) - {"dr", "shri", "smt", "seth"}


def reconcile_hospital_list(master):
    """Match public rows of the ward-wise hospitals CSV to KML hospital/maternity records.

    Used for reconciliation only: the CSV has no coordinates or record ids, so it does not add
    facilities to the counts. Scores are token overlap on name stems within the same ward.
    """
    h = read_hospitals_csv()
    h.columns = ["csv_ward", "csv_type", "csv_name", "csv_address", "csv_beds", "csv_contact"]
    for c in h.columns:
        h[c] = h[c].map(clean_text)
    h["csv_row"] = h.index + 2  # spreadsheet row number incl. header
    h["ward_id"] = h["csv_ward"].map(standardize_ward)
    h["ownership_csv"] = h["csv_type"].map(lambda t: PUBLIC_TYPES.get(t, t))
    pub = h[h["csv_type"].isin(PUBLIC_TYPES)].copy()

    kml = master[master["category"].isin(["public_hospital", "maternity_hospital"])]
    rows = []
    for r in pub.itertuples():
        cand = kml[kml["ward_id"] == r.ward_id]
        # Prefer the layer implied by the CSV name; fall back to both layers.
        hint = "maternity_hospital" if "maternity" in r.csv_name.lower() else "public_hospital"
        if (cand["category"] == hint).any():
            cand = cand[cand["category"] == hint]
        best, score = None, 0.0
        a = _tokens(r.csv_name)
        for k in cand.itertuples():
            b = _tokens(k.facility_name)
            if a and b:
                s = len(a & b) / min(len(a), len(b))
                if s > score:
                    best, score = k, s
        rows.append(dict(csv_row=r.csv_row, ward_id=r.ward_id, csv_name=r.csv_name, ownership_csv=r.ownership_csv,
                         csv_beds=r.csv_beds, matched_facility_id=best.facility_id if best is not None and score >= 0.5 else None,
                         matched_name=best.facility_name if best is not None and score >= 0.5 else None,
                         match_score=round(score, 2),
                         status="matched_in_kml" if score >= 0.5 else "not_found_in_kml_layers"))
    rec = pd.DataFrame(rows)
    rec["match_method"] = rec["status"].map({"matched_in_kml": "automatic_name_tokens"})

    # Documented manual review overrides (data/reference/hospital_list_manual_matches.csv).
    manual = pd.read_csv(MANUAL_MATCHES, dtype={"csv_row": int})
    names = master.set_index("facility_id")["facility_name"]
    for m in manual.itertuples():
        i = rec.index[rec["csv_row"] == m.csv_row]
        assert len(i) == 1 and rec.loc[i[0], "csv_name"] == m.csv_name, f"manual match row {m.csv_row} is stale"
        rec.loc[i, ["matched_facility_id", "matched_name", "status", "match_method", "match_score"]] = [
            m.facility_id, names[m.facility_id],
            "matched_in_kml_ward_conflict" if m.decision == "match_ward_conflict" else "matched_in_kml",
            f"manual_review_{m.confidence}_confidence", None]
    matched_ids = set(rec["matched_facility_id"].dropna())
    kml_only = kml[~kml["facility_id"].isin(matched_ids)][["facility_id", "category", "facility_name", "ward_id"]]
    summary = dict(csv_rows=len(h), csv_type_counts=h["csv_type"].value_counts().to_dict(),
                   csv_public_rows=len(pub), csv_wards=sorted(h["ward_id"].dropna().unique()),
                   csv_unmapped_wards=h.loc[h.ward_id.isna(), "csv_ward"].unique().tolist())
    return rec, kml_only, summary


OWNERSHIP_CLASS = {"Municipal": "Public", "BMC": "Public", "Government": "Public", "Govt": "Public",
                   "Defence": "Public", "Private": "Private", "Trust": "Trust"}


def clean_hospital_list(rec):
    """All 288 rows of the hospitals CSV, cleaned for display: ward, ownership class, beds (NaN when blank).

    Ownership comes only from the CSV's own type column. Public rows carry the KML facility they were matched to
    (from reconcile_hospital_list); private and trust rows have no coordinates, so they are listed, never mapped.
    """
    h = read_hospitals_csv()
    h.columns = ["csv_ward", "csv_type", "csv_name", "csv_address", "csv_beds", "csv_contact"]
    for c in h.columns:
        h[c] = h[c].map(clean_text)
    out = pd.DataFrame({
        "csv_row": h.index + 2, "ward_id": h["csv_ward"].map(standardize_ward), "source_ward_value": h["csv_ward"],
        "hospital_name": h["csv_name"], "address": h["csv_address"], "source_type": h["csv_type"],
        "ownership_type": h["csv_type"].map(lambda t: PUBLIC_TYPES.get(t, t)),
        "ownership_class": h["csv_type"].map(OWNERSHIP_CLASS).fillna("Unknown"),
        "beds": pd.to_numeric(h["csv_beds"], errors="coerce").astype("Int64"),
    })
    m = rec.set_index("csv_row")
    out["matched_facility_id"] = out["csv_row"].map(m["matched_facility_id"])
    out["match_status"] = out["csv_row"].map(m["status"]).fillna("not_applicable_private_or_trust")
    return out

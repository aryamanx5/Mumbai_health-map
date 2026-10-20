# Methodology

## Pipeline
`run_pipeline.py` runs these stages in order. Each stage asserts its own reconciliation checks and fails loudly.

1. **Ingestion** (`data_ingestion.py`). KML placemarks are parsed with ElementTree, keeping every ExtendedData field
   and the raw coordinate string. The hospitals CSV is read as cp1252, because it is not UTF-8. A file inventory with
   SHA-256 hashes is recorded.
2. **Standardization** (`preprocessing.py`).
   * Text is cleaned of whitespace and non-breaking spaces.
   * Ward values are mapped to 24 canonical ids by a structural rule (`GS` → `G/S`). Anything that does not
     resolve returns `None` and is logged.
   * Coordinates are parsed and checked against a Mumbai bounding box.
   * Precision is the number of decimals needed to reproduce the value, which removes float artifacts.
3. **Co-location / deduplication** (`deduplication.py`).
   * Candidate pairs share a ward and an identical name stem; facility-type words are removed before comparing names.
   * A pair matches only if the haversine distance is ≤ 300 m plus the rounding error of both points.
   * Union-find over the matches produces `site_id`. Same-category matches would be within-layer duplicates; none
     occurred. Cross-category matches are one physical site with several services.
4. **Geospatial checks** (`geospatial_processing.py`).
   * Ward polygons are loaded and their validity checked.
   * Area is computed in EPSG:32643 (UTM 43N).
   * A point-in-polygon join and the distance to the source-ward polygon classify each record as agree / within
     rounding / review. The source ward is never overwritten.
5. **Population** (`population.py`).
   * 97 Census 2011 wards are summed to the 24 BMC wards.
   * Six checks: every name maps; codes are unique; the code prefix (01 = A … 24 = T) agrees with the name; every
     ward is found in the Primary Census Abstract; populations equal PCA TOT_P; the total equals the district
     totals.
6. **Integration and indicators** (`build_data.py`, `indicators.py`). The ward table is driven by the 24-ward
   master list, so zero-count wards are kept. Formulas are in the final report, Section 6. Undefined values are NaN.
7. **EDA** (`exploratory_analysis.py`). Nine figures plus ranking, correlation and IQR-outlier tables.
8. **K-Means** (`model_training.py`, `model_evaluation.py`). See `model_card.md`.
9. **Exports** (`export_reporting.py`). A star-schema CSV set for Power BI plus the expected KPIs.
10. **Reports** (`build_report.py`). Every number in the reports is filled in from the outputs.

## Key decisions and why

| Decision | Reason |
|---|---|
| Source `Ward` field is authoritative | It is the strongest evidence (PRD priority 1). Coordinates are mostly rounded to ~1 km, so a spatial join would misassign boundary facilities. |
| Census 2011 population | No 2023 ward population was supplied. Census 2011 is the only official ward-level source found. The user approved it. |
| Hospitals CSV used for reconciliation only | It has no coordinates or ids, is 82% private, and has no rows for ward C. |
| Manual match file for 9 CSV rows | Initials and abbreviations (J.J., G.T., KEM, GTB) defeat token matching. Each decision carries its rationale and a confidence level. |
| Total = distinct sites | The PRD asks for distinct physical facilities. Category counts are kept separately; they sum to 456 records. |
| K = 4 by documented judgement | The max-silhouette K = 2 only isolates two outliers and is unstable under subsampling. See the model card. |

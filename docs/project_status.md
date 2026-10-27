# Project status

_Last updated: 2026-10-20_

## Done and verified
| Stage | Evidence |
|---|---|
| Data acquisition | 9 raw files in `data/raw/` from OpenCity, with SHA-256 hashes in `outputs/tables/raw_file_inventory.csv` |
| Inventory and data quality | `docs/data_quality_report.md` (generated) |
| Facility master | 456 records → 402 distinct sites; 0 exclusions; all 24 wards covered; totals reconcile (assertions in `build_data.py`) |
| Ward assignment | Source ward authoritative; 387 agree with polygons, 44 within rounding, 24 flagged for review, 1 with no coordinates |
| Population | Census 2011, 24 wards, total 12,442,373; all 7 population checks pass |
| Indicators | `data/processed/ward_indicators.csv`; formula and edge-case tests pass |
| EDA | 9 figures + tables in `outputs/` |
| K-Means | K scan 2–6 with stability; final K = 4; saved pipeline reproduces the exports (tested) |
| Power BI exports | `powerbi/data/*.csv`, `measures.dax`, `powerbi_spec.md`, `expected_kpis.json` |
| Landing page | `index.html` + `landing/` at http://localhost:8050/; the live ward sentence was tested in a browser; design lint and inspector pass at 1440, 768 and 390 px |
| Web dashboard | `dashboard/` at http://localhost:8050/dashboard/; graphite/orange theme; all three pages, filters, ward deep links and the drill-down panel checked in a browser |
| Report | `outputs/reports/final_report.pdf` (12 pages, numbers generated from outputs) |
| Tests | `pytest`: 68 passed (37 original, 25 for the clinical models and API, 6 for the Power BI project) |
| Cardiovascular models | LR / RF / ANN on the Doppala & Bhattacharyya (2021) Indian dataset; test ROC-AUC 0.968 / 0.992 / 0.986; see `docs/ml_methodology.md` |
| FastAPI backend | `backend/`; serves the site, `/api/*` and Swagger at `/api/docs` |
| Dashboard | Overview (KPIs, model cards, ward lookup), Heart risk predictor, Power BI dashboard (embedded report). Charts and the map moved to Power BI |
| Power BI report | `powerbi/MumbaiHealth.pbip`: 5 pages, 101 visuals, own navy/heart-red/teal theme, 15 tables, 35 measures. Passes Microsoft's TMDL parser and PBIR schemas; not yet opened in Desktop |
| Boundary cross-check | OpenCity wards vs `BMC_admin_wards.geojson`: median IoU 0.986 |

## Blockers and gaps
* **Clinical CSV provenance.** Mendeley and Kaggle were blocked during the build, so a public GitHub copy was used. Replace it with the Mendeley download and re-run to confirm.
* **Power BI not yet opened in Desktop or published.** The project is generated and validated, but Power BI Desktop
  runs only on Windows. Publishing needs the user's Power BI account; see `powerbi/POWERBI_GUIDE.md`.
* **2023 population not available.** Census 2011 is used instead; drop a newer table into `src/population.py` to
  update everything.
* 24 ward-assignment records and 9 manual hospital-list matches would benefit from a human review against ground
  truth.

## Next action
Open `powerbi/MumbaiHealth.pbip` in Power BI Desktop, refresh and check the Home page numbers. Then publish it, and paste the
embed link into `dashboard/powerbi-config.js` (`powerbi/POWERBI_GUIDE.md`).

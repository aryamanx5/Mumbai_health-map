# Project status

_Last updated: 2026-10-19_

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
| Tests | `pytest`: 37 passed |

## Blockers and gaps
* **Power BI PBIX not built.** Power BI Desktop is not available on macOS. The spec, DAX and acceptance checks are
  ready, so the build must be done on Windows.
* **2023 population not available.** Census 2011 is used instead; drop a newer table into `src/population.py` to
  update everything.
* 24 ward-assignment records and 9 manual hospital-list matches would benefit from a human review against ground
  truth.

## Next action
Build the three-page report in Power BI Desktop on Windows, following `powerbi/powerbi_spec.md`, and run its
acceptance checks.

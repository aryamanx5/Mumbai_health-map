# Migration report: from ward clustering to cardiovascular prediction plus Mumbai infrastructure

The existing project (Python pipeline, static landing page and Chart.js/Leaflet dashboard) was **extended, not
rebuilt**. The graphite and orange design, the navigation and every existing page keep working as before.

## Files preserved (unchanged)
* `src/`: `config.py`, `data_ingestion.py`, `preprocessing.py`, `deduplication.py`, `geospatial_processing.py`,
  `population.py`, `indicators.py`, `exploratory_analysis.py`, `model_training.py`, `model_evaluation.py`,
  `export_reporting.py`, `plot_style.py`, `build_report.py`
* All raw Mumbai inputs in `data/raw/`, plus `data/reference/`, `powerbi/` and the existing tests
  (`tests/test_preprocessing.py`, `tests/test_indicators.py`, `tests/test_model.py`)
* `landing/` assets, script and styles; `docs/model_card.md`, `methodology.md`, `data_dictionary.md`,
  `data_quality_report.md`

## Files modified
| File | Change |
|---|---|
| `run_pipeline.py` | Adds the boundary cross-check and the clinical stage after the existing stages |
| `src/data_integration.py` | New `clean_hospital_list()`: all 288 hospitals CSV rows with ownership and beds (missing beds stay missing) |
| `src/build_data.py` | Writes `data/processed/hospital_list_clean.csv` and adds its counts to `data_summary.json` |
| `dashboard/index.html` | Four new tabs and pages; the overview gains a three-model strip; adds an API docs link and the clinical source in the footer |
| `dashboard/app.js` | Page list extended; calls `initExtra()`; the ward drawer adds the ward's hospitals-list rows |
| `dashboard/style.css` | Styles for the new pages in the same theme |
| `index.html` | Links to the predictor, model comparison and API docs; clinical data credit |
| `requirements.txt`, `README.md`, `.claude/launch.json` | FastAPI and uvicorn; new run instructions |
| `tests/test_model.py` | One flaky assertion fixed: K-Means inertia is compared with a 1e-9 tolerance, because multithreaded summation made exact float equality fail intermittently (labels are still compared exactly) |

## Files replaced
None. The K-Means ward clustering was **demoted**, not deleted. Its tab is now *Ward clusters* and is labelled as
exploratory and "not one of the three project models".

## New components
| Path | Purpose |
|---|---|
| `data/raw/clinical/Cardiovascular_Disease_Dataset.csv` | Doppala & Bhattacharyya (2021) Indian dataset (see the provenance note) |
| `data/raw/boundaries/BMC_admin_wards.geojson` | Independent ward boundary layer used for cross-checking |
| `src/clinical_data.py` | Loading, profiling, cleaning and the data dictionary |
| `src/clinical_models.py` | Shared preprocessing pipeline and the LR / RF / ANN definitions and grids |
| `src/clinical_pipeline.py` | Split, CV tuning, evaluation, explanations, artifacts and figures 13–15 |
| `src/boundary_check.py` | IoU of the OpenCity wards vs `BMC_admin_wards.geojson`, plus facility point agreement |
| `backend/` | FastAPI app: `/api/*`, the `/predict` HTML form, Swagger at `/api/docs`, and serving of the existing site |
| `dashboard/clinical.js` | Heart risk predictor, model comparison, hospital map and data cleaning pages |
| `models/clinical_{logistic_regression,random_forest,ann}.joblib` | Saved fitted pipelines |
| `tests/test_clinical.py`, `tests/test_api.py` | 25 new tests |
| `docs/ml_methodology.md`, `docs/migration_report.md` | Documentation |
| `start_windows.bat` | One-click setup and run on Windows |

## Power BI move (second round)

* **Charts and the map moved to Power BI.**
  * New: `src/powerbi_data.py`, which writes 10 report tables, and `src/powerbi_project.py`, which generates
    `powerbi/MumbaiHealth.pbip`. That is a TMDL model and a PBIR report with five pages. The page structure follows the reference group's
    sample report; the theme is the project's own (navy frame, heart red for cardiovascular risk, teal for Mumbai access).
  * New: `tests/test_powerbi.py` and `powerbi/POWERBI_GUIDE.md`.
* **Web dashboard trimmed.**
  * Removed the Model comparison, Hospital map, Ward analysis, Data cleaning and Ward clusters tabs, along with Chart.js and
    Leaflet.
  * Kept the Overview (KPIs, model cards, observations, and a new ward lookup for the ward panel) and the Heart risk
    predictor.
  * Added a Power BI dashboard tab, plus a header button that embeds the published report. The link is set in
    `dashboard/powerbi-config.js`.
* **Landing page.** Links that pointed at the removed tabs now go to the Power BI tab or the ward lookup.
* **API unchanged.** `/api/models`, `/api/data-quality` and the rest still return everything the removed pages used.

## Remaining limitations
* The clinical CSV came from a GitHub mirror, because Mendeley and Kaggle were blocked in the build environment.
  Replace it with the Mendeley download to confirm the file (the SHA-256 is in `ml_methodology.md`).
* There is no 2023/2024 ward population file in the ZIP, so Census 2011 is still used. Drop a newer table into
  `src/population.py` to update every rate.
* The BMC Civic Diary PDF and NFHS-5 were not reachable, so they were not used. No district rates are spread across
  wards.
* The hospitals CSV has no coordinates. Private and trust hospitals are listed per ward, not mapped.
* The dashboard loads Chart.js, Leaflet, PapaParse and map tiles from CDNs, so it needs internet access.
* The Power BI `.pbix` is still not built (as before). The spec and CSVs are in `powerbi/`.

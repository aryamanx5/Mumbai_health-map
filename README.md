# Healthcare facility provision across Mumbai's 24 wards

An end-to-end academic analytics project covering the distribution of listed public health facilities
(dispensaries, UPHCs, public hospitals, maternity homes) across Greater Mumbai's 24 BMC wards. It includes
population-normalized indicators, EDA, an evaluated K-Means clustering, and Power BI-ready exports.

**Start here:** [final report (PDF)](outputs/reports/final_report.pdf) · [project status](docs/project_status.md) ·
[data quality](docs/data_quality_report.md) · [model card](docs/model_card.md) · [Power BI spec](powerbi/powerbi_spec.md)

## Setup and run

Requires Python 3.11+ (built with 3.14). The PDF step needs Google Chrome.

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python run_pipeline.py        # data → indicators → EDA → K-Means → Power BI CSVs (~40 s)
.venv/bin/python -m pytest -q           # 37 tests (unit + checks on the real exported outputs)
.venv/bin/python -m src.build_report    # docs/data_quality_report.md + outputs/reports/final_report.{md,html,pdf}
```

### Interactive dashboard (localhost)

After `run_pipeline.py`, serve the project root and open the dashboard:

```bash
.venv/bin/python -m http.server 8050 --bind 127.0.0.1
```

Then open <http://localhost:8050/>, the **landing page**. It explains the study, and its headline is live: pick any ward
and the sentence rewrites itself with that ward's sites, population and rate. From there, <http://localhost:8050/dashboard/>
is the **dashboard**: three pages that mirror the Power BI spec (Overview, Ward analysis, ML clusters) and a ward detail
panel that opens when you click any ward, bar or table row. `dashboard/#ward=R/S` opens a ward directly. It reads
`powerbi/data/*.csv` and `data/processed/ward_boundaries.geojson`, so re-running the pipeline and refreshing the
page updates it. It needs internet access for the chart and map libraries and the map tiles.

Raw inputs are already in `data/raw/` (downloaded from OpenCity on 2026-10-19; see the data quality report for
sources and SHA-256 hashes). The pipeline never modifies them.

## Layout

```
data/raw/            untouched inputs (4 facility KMLs, hospitals CSV, ward polygons KML, 3 census CSVs)
data/reference/      documented manual reconciliation decisions
data/interim/        ward population aggregated from census wards
data/processed/      facility_master, facility_sites, ward_indicators, ward_clusters, ml_modelling_table, ward_boundaries.geojson
src/                 pipeline modules (config, ingestion, preprocessing, deduplication, geospatial, population,
                     integration, indicators, EDA, model training/evaluation, Power BI export, report builder)
tests/               pytest suite
models/              fitted K-Means pipeline (joblib)
outputs/figures/     12 PNG figures
outputs/tables/      quality, reconciliation, EDA and ML tables
outputs/reports/     final report (md/html/pdf)
powerbi/             import-ready CSVs, DAX measures, report spec
index.html, landing/  landing page (style.css, app.js, assets/ with credited photos, footage and dashboard screenshots)
dashboard/           local web dashboard (index.html, app.js, style.css)
docs/                methodology, data dictionary, data quality, model card, status, viva notes
```

## Key caveats

* Population is **Census 2011**, because no 2023 ward table was available. Facilities date from about 2025.
* Counts cover the MCGM facility layers only. 18 public hospitals in the hospitals CSV are missing from those layers.
* Most coordinates are rounded to about 1 km.
* K-Means is exploratory: 24 observations, and the clusters depend on the feature set.
* No Power BI PBIX was built, because Power BI Desktop is unavailable on macOS. The local web dashboard covers the
  same three pages; `powerbi/powerbi_spec.md` has the Power BI build instructions.

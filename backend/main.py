"""FastAPI app: the /api endpoints plus the existing static site (landing page, dashboard, outputs).

Run from the project root:
    .venv/bin/uvicorn backend.main:app --port 8050            (Windows: .venv\\Scripts\\uvicorn backend.main:app --port 8050)
Then open http://localhost:8050/ (site), http://localhost:8050/dashboard/ and http://localhost:8050/api/docs (Swagger).
"""
import html
from typing import Optional

from fastapi import FastAPI, Form, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from src.config import ROOT

from . import store
from .schemas import Health, PatientInput, PredictionResponse

TAGS = [
    {"name": "Cardiovascular models", "description": "Logistic Regression, Random Forest and ANN trained on the "
                                                    "Doppala & Bhattacharyya (2021) Indian dataset."},
    {"name": "Mumbai infrastructure", "description": "Listed public facilities, wards and the hospitals list."},
    {"name": "Data quality", "description": "Cleaning and preprocessing audit for both pipelines."},
    {"name": "Metadata & KPIs", "description": "Health check and headline numbers."},
]
app = FastAPI(title="Mumbai Healthcare & Cardiovascular Risk API", version="2.0.0", openapi_tags=TAGS,
              docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json",
              description="Serves pipeline outputs and the three saved classifiers. Models are loaded from "
                          "`models/`, never retrained per request. Predictions are experimental and not clinically "
                          "validated.")


@app.exception_handler(store.NotReady)
def not_ready(_req: Request, exc: store.NotReady):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


# ---------------- metadata ----------------
@app.get("/api/health", response_model=Health, tags=["Metadata & KPIs"])
def health():
    try:
        loaded = list(store.models())
        store.clinical_results()
        store.wards()
        ready = True
    except store.NotReady:
        loaded, ready = [], False
    return Health(status="ok" if ready else "pipeline outputs missing", models_loaded=loaded, data_ready=ready)


@app.get("/api/overview", tags=["Metadata & KPIs"])
def overview():
    """Headline numbers for both modules, all read from pipeline outputs."""
    res, geo, w = store.clinical_results(), store.geo_summary(), store.wards()
    s = res["summary"]
    return dict(
        clinical=dict(records=s["n_clean"], train=s["n_train"], test=s["n_test"], positive_rate=s["positive_rate"],
                      source=s["source"]["title"], citation=f"{s['source']['authors']} ({s['source']['year']})",
                      majority_baseline_accuracy=s["majority_baseline_accuracy"]),
        models=[dict(key=k, label=m["label"], short=m["short"], **{x: m["test"][x] for x in
                     ["accuracy", "precision", "recall", "f1", "roc_auc"]}) for k, m in res["models"].items()],
        infrastructure=dict(wards=int(len(w)), facility_records=geo["master_records"], distinct_sites=geo["distinct_sites"],
                            population_2011=int(w["population_2011"].sum()),
                            sites_per_100k=round(geo["distinct_sites"] / w["population_2011"].sum() * 1e5, 3),
                            records_by_category=geo["category_records"],
                            hospital_list_rows=geo["hospital_csv"]["csv_rows"],
                            hospital_list_ownership=geo.get("hospital_list_ownership")),
    )


# ---------------- cardiovascular models ----------------
@app.post("/api/predict", response_model=PredictionResponse, tags=["Cardiovascular models"])
def predict(patient: PatientInput):
    """Run all three saved pipelines on one patient. The same preprocessing as training is applied."""
    return store.predict(patient.model_dump())


@app.get("/api/models", tags=["Cardiovascular models"])
def models_comparison():
    """Test-set metrics, CV metrics, ROC/calibration points, coefficients, importances and ANN curves."""
    return store.clinical_results()


@app.get("/api/models/{key}", tags=["Cardiovascular models"])
def model_detail(key: str):
    res = store.clinical_results()["models"]
    if key not in res:
        raise HTTPException(404, f"unknown model '{key}'; use one of {list(res)}")
    return res[key]


@app.get("/api/clinical/test-predictions", tags=["Cardiovascular models"])
def test_predictions(limit: int = Query(200, ge=1, le=1000)):
    """Actual versus predicted for the held-out test patients."""
    from src.config import PROCESSED
    return store.records(store._csv(PROCESSED / "clinical" / "test_predictions.csv").head(limit))


@app.get("/api/clinical/dictionary", tags=["Cardiovascular models"])
def dictionary():
    return store.clinical_quality()["dictionary"]


# ---------------- Mumbai infrastructure ----------------
@app.get("/api/wards", tags=["Mumbai infrastructure"])
def wards():
    return store.records(store.wards())


@app.get("/api/wards/{ward_id:path}", tags=["Mumbai infrastructure"])
def ward(ward_id: str):
    w = store.wards()
    row = w[w["ward_id"].str.upper() == ward_id.upper()]
    if row.empty:
        raise HTTPException(404, f"unknown ward '{ward_id}'")
    wid = row.iloc[0]["ward_id"]
    f, h = store.facilities(), store.hospital_list()
    return dict(ward=store.records(row)[0], facilities=store.records(f[f["ward_id"] == wid]),
                hospital_list=store.records(h[h["ward_id"] == wid]))


@app.get("/api/facilities", tags=["Mumbai infrastructure"])
def facilities(category: Optional[str] = None, ward: Optional[str] = None, q: Optional[str] = None):
    f = store.facilities()
    if category:
        f = f[f["category"] == category]
    if ward:
        f = f[f["ward_id"] == ward]
    if q:
        f = f[f["facility_name"].str.contains(q, case=False, na=False, regex=False)]
    return store.records(f)


@app.get("/api/hospital-list", tags=["Mumbai infrastructure"])
def hospital_list(ward: Optional[str] = None, ownership: Optional[str] = None):
    """The 288-row hospitals CSV, cleaned. It has no coordinates, so it is listed rather than mapped."""
    h = store.hospital_list()
    if ward:
        h = h[h["ward_id"] == ward]
    if ownership:
        h = h[h["ownership_class"].str.lower() == ownership.lower()]
    return store.records(h)


# ---------------- data quality ----------------
@app.get("/api/data-quality", tags=["Data quality"])
def data_quality():
    """Before/after audit for the clinical and the geographic pipelines."""
    return dict(
        clinical=store.clinical_quality(),
        geographic=dict(summary=store.geo_summary(), boundaries=store.boundary_summary(),
                        boundary_table=store.records(store.table("boundary_crosscheck.csv")),
                        ward_value_mapping=store.records(store.table("ward_value_mapping.csv")),
                        colocation_pairs=store.records(store.table("colocation_candidate_pairs.csv")),
                        assignment_review=store.records(store.table("ward_assignment_review.csv")),
                        population_checks=store.records(store.table("population_checks.csv"))),
    )


# ---------------- server-rendered form (no JavaScript needed) ----------------
@app.post("/predict", response_class=HTMLResponse, include_in_schema=True, tags=["Cardiovascular models"])
def predict_form(age: int = Form(...), gender: int = Form(...), chestpain: int = Form(...),
                 restingBP: float = Form(...), serumcholestrol: Optional[str] = Form(None),
                 fastingbloodsugar: int = Form(...), restingrelectro: int = Form(...), maxheartrate: float = Form(...),
                 exerciseangia: int = Form(...), oldpeak: float = Form(...), slope: int = Form(...),
                 noofmajorvessels: int = Form(...)):
    """Same prediction as /api/predict, submitted as an HTML form and returned as a result page."""
    chol = float(serumcholestrol) if serumcholestrol not in (None, "") else None
    try:
        p = PatientInput(age=age, gender=gender, chestpain=chestpain, restingBP=restingBP, serumcholestrol=chol,
                         fastingbloodsugar=fastingbloodsugar, restingrelectro=restingrelectro,
                         maxheartrate=maxheartrate, exerciseangia=exerciseangia, oldpeak=oldpeak, slope=slope,
                         noofmajorvessels=noofmajorvessels)
    except Exception as e:  # validation error -> readable page
        return HTMLResponse(_page("Check the inputs", f"<pre>{html.escape(str(e))}</pre>"), status_code=422)
    r = store.predict(p.model_dump())
    rows = "".join(
        f"<div class='row'><div class='name'>{html.escape(x['label'])}</div><div class='bar'><i style='width:{x['probability'] * 100:.1f}%'></i></div>"
        f"<div class='pct'>{x['probability'] * 100:.1f}%</div><div class='cls'>{html.escape(x['predicted_label'])}</div></div>"
        for x in r["predictions"])
    body = (f"<p class='lead'>{r['models_predicting_disease']} of 3 models indicate heart disease at the "
            f"{r['threshold']:.0%} threshold. Mean probability {r['mean_probability'] * 100:.1f}%, spread "
            f"{r['probability_spread'] * 100:.1f} points.</p>{rows}"
            + (f"<p class='hint'>Imputed (training median): {', '.join(r['imputed_fields'])}</p>" if r["imputed_fields"] else "")
            + f"<p class='disc'>{html.escape(r['disclaimer'])}</p>")
    return HTMLResponse(_page("Cardiovascular model result", body))


def _page(title, body):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<style>body{{margin:0;background:#18191b;color:#eff0f1;font:16px/1.5 Barlow,Segoe UI,sans-serif}}.bar0{{height:6px;background:#ff4a1f}}
main{{max-width:760px;margin:40px auto;padding:24px 28px;background:#222427;border-radius:6px}}h1{{font:700 40px/1 'Barlow Condensed',sans-serif;text-transform:uppercase;margin:0 0 12px}}
.row{{display:grid;grid-template-columns:200px 1fr 70px;gap:4px 14px;align-items:center;margin:14px 0}}.name{{font-weight:600}}.bar{{height:12px;background:#2b2e32;border-radius:6px;overflow:hidden}}
.bar i{{display:block;height:100%;background:#ff4a1f}}.pct{{font:700 24px 'Barlow Condensed';text-align:right}}.cls{{grid-column:2/4;color:#a3a5aa;font-size:14px}}
.hint,.disc{{color:#a3a5aa;font-size:14px}}.disc{{border-left:4px solid #ff4a1f;padding-left:12px;margin-top:22px}}a{{color:#ff4a1f}}pre{{white-space:pre-wrap}}</style></head>
<body><div class="bar0"></div><main><h1>{html.escape(title)}</h1>{body}<p><a href="/dashboard/#predict">← Back to the predictor</a></p></main></body></html>"""


# ---------------- static site (existing frontend, unchanged paths) ----------------
@app.get("/", include_in_schema=False)
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/README.md", include_in_schema=False)
def readme():
    return FileResponse(ROOT / "README.md", media_type="text/plain; charset=utf-8")


for _path in ["landing", "dashboard", "powerbi", "outputs", "docs"]:
    app.mount(f"/{_path}", StaticFiles(directory=ROOT / _path, html=True), name=_path)
app.mount("/data/processed", StaticFiles(directory=ROOT / "data" / "processed"), name="processed")

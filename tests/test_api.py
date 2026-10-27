"""FastAPI endpoint tests (in-process, against the real saved outputs)."""
import pytest
from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
PATIENT = {"age": 54, "gender": 1, "chestpain": 2, "restingBP": 150, "serumcholestrol": 290, "fastingbloodsugar": 0,
           "restingrelectro": 1, "maxheartrate": 140, "exerciseangia": 1, "oldpeak": 2.4, "slope": 2,
           "noofmajorvessels": 1}


def test_health():
    r = client.get("/api/health").json()
    assert r["data_ready"] and len(r["models_loaded"]) == 3


def test_predict_returns_three_models():
    r = client.post("/api/predict", json=PATIENT)
    assert r.status_code == 200
    j = r.json()
    assert [p["model"] for p in j["predictions"]] == ["LR", "RF", "ANN"]
    assert all(0 <= p["probability"] <= 1 for p in j["predictions"])
    assert "not clinically validated" in j["disclaimer"]


def test_predict_unknown_cholesterol_is_imputed():
    j = client.post("/api/predict", json={**PATIENT, "serumcholestrol": None}).json()
    assert j["imputed_fields"] == ["serumcholestrol"]


@pytest.mark.parametrize("field,value", [("age", 5), ("slope", 0), ("restingBP", 400), ("gender", 2)])
def test_predict_rejects_invalid(field, value):
    assert client.post("/api/predict", json={**PATIENT, field: value}).status_code == 422


def test_overview_and_models():
    o = client.get("/api/overview").json()
    assert o["clinical"]["records"] == 1000 and o["infrastructure"]["wards"] == 24
    m = client.get("/api/models").json()
    assert set(m["models"]) == {"logistic_regression", "random_forest", "ann"}
    assert client.get("/api/models/nope").status_code == 404


def test_wards_and_facilities():
    w = client.get("/api/wards").json()
    assert len(w) == 24
    d = client.get("/api/wards/R/S").json()
    assert d["ward"]["ward_id"] == "R/S" and all(f["ward_id"] == "R/S" for f in d["facilities"])
    f = client.get("/api/facilities", params={"category": "public_hospital"}).json()
    assert len(f) == 31
    assert client.get("/api/wards/ZZ").status_code == 404


def test_hospital_list_keeps_missing_beds():
    h = client.get("/api/hospital-list").json()
    assert len(h) == 288
    assert sum(r["beds"] is None for r in h) == 2


def test_data_quality_and_static_site():
    q = client.get("/api/data-quality").json()
    assert q["clinical"]["rows"]["raw"] == 1000 and q["geographic"]["boundaries"]["wards"] == 24
    for path in ["/", "/dashboard/", "/api/docs", "/powerbi/data/dim_ward.csv"]:
        assert client.get(path).status_code == 200


def test_server_form_predict():
    form = {k: str(v) for k, v in PATIENT.items()}
    r = client.post("/predict", data=form)
    assert r.status_code == 200 and "of 3 models" in r.text

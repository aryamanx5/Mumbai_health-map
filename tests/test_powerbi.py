"""Power BI project: report tables, and every field the report uses exists in the semantic model."""
import json
import re

import pandas as pd
import pytest

from src import powerbi_project as pp
from src.export_reporting import OUT as DATA

DEF = pp.RP / "definition"


@pytest.fixture(scope="module")
def model():
    """Column and measure names per table, parsed from the TMDL files."""
    out = {}
    for f in (pp.SM / "definition" / "tables").glob("*.tmdl"):
        text = f.read_text()
        name = re.search(r"^table (\S+)", text, re.M).group(1)
        names = re.findall(r"^\t(?:column|measure) ('(?:[^']|'')+'|[^\s=]+)", text, re.M)
        out[name] = {n.strip("'").replace("''", "'") for n in names}
    return out


def visuals():
    return [json.loads(p.read_text()) for p in DEF.glob("pages/*/visuals/*/visual.json")]


def fields(obj):
    """Every (Entity, Property) pair referenced anywhere in a visual."""
    if isinstance(obj, dict):
        if "Expression" in obj and "Property" in obj and "SourceRef" in obj["Expression"]:
            yield obj["Expression"]["SourceRef"]["Entity"], obj["Property"]
        for v in obj.values():
            yield from fields(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from fields(v)


def test_report_tables_reconcile():
    pat = pd.read_csv(DATA / "clinical_patient.csv")
    assert len(pat) == 1000 and pat["patientid"].is_unique
    assert pat.loc[pat["split"] == "Test", "target"].mean() == pytest.approx(0.58)
    cm = pd.read_csv(DATA / "model_confusion.csv")
    assert (cm.groupby("model")["patients"].sum() == 200).all()
    met = pd.read_csv(DATA / "model_metric.csv")
    rf = met[(met["model"] == "Random Forest") & (met["set"] == "Test") & (met["metric"] == "ROC-AUC")]["value"]
    assert rf.iloc[0] == pytest.approx(0.992, abs=1e-3)
    preds = pd.read_csv(DATA / "test_prediction.csv")
    assert (preds[preds["correct"] == "Correct"].groupby("patientid").size() == 3).sum() == 174


def test_every_report_field_exists_in_model(model):
    missing = {(t, p) for v in visuals() for t, p in fields(v) if p not in model.get(t, set())}
    assert not missing


def test_measures_only_reference_existing_measures(model):
    measures = {m for _, m, _, _ in pp.MEASURES}
    for _, name, dax, _ in pp.MEASURES:
        refs = set(re.findall(r"(?<![\w\]])\[([^\]]+)\]", dax))
        assert refs <= measures, (name, refs - measures)
        for table, column in re.findall(r"(\w+)\[([^\]]+)\]", dax):
            assert column in model[table], (name, table, column)


def test_pages_and_navigation():
    order = json.loads((DEF / "pages" / "pages.json").read_text())["pageOrder"]
    assert 3 <= len(order) <= 5
    assert sorted(order) == sorted(p.name for p in DEF.joinpath("pages").iterdir() if p.is_dir())
    targets = set()
    for v in visuals():
        for link in v["visual"].get("visualContainerObjects", {}).get("visualLink", []):
            targets.add(link["properties"]["navigationSection"]["expr"]["Literal"]["Value"].strip("'"))
    assert targets == set(order)


def test_project_files_point_at_each_other():
    pbip = json.loads((pp.POWERBI / f"{pp.NAME}.pbip").read_text())
    assert pbip["artifacts"][0]["report"]["path"] == f"{pp.NAME}.Report"
    pbir = json.loads((pp.RP / "definition.pbir").read_text())
    assert pbir["datasetReference"]["byPath"]["path"] == f"../{pp.NAME}.SemanticModel"
    report = json.loads((DEF / "report.json").read_text())
    for pkg in report["resourcePackages"]:
        for item in pkg["items"]:
            assert (pp.RP / "StaticResources" / pkg["name"] / item["path"]).exists()


def test_data_folder_parameter_points_at_csvs():
    expr = (pp.SM / "definition" / "expressions.tmdl").read_text()
    folder = re.search(r'DataFolder = "([^"]+)"', expr).group(1)
    for t in pp.TABLES:
        assert (DATA / f"{t}.csv").exists()
    assert folder.endswith(("/", "\\"))

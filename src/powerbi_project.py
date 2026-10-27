"""Generate the Power BI report as a Power BI Project (PBIP): a TMDL semantic model plus a PBIR report.

Open powerbi/MumbaiHealth.pbip in Power BI Desktop (Windows), refresh, then publish. The report reads the CSVs in
powerbi/data/ through the DataFolder parameter, which this module sets to the absolute path on this machine.

    python -m src.powerbi_project                  write the project if it does not exist, else update DataFolder
    python -m src.powerbi_project --rebuild        rewrite the whole project (overwrites edits made in Desktop)
    python -m src.powerbi_project --set-data-folder  only point DataFolder at this machine's powerbi/data/
"""
import argparse
import json
import shutil
import uuid
from pathlib import Path

import pandas as pd

from .config import POWERBI
from .export_reporting import OUT as DATA

NAME = "MumbaiHealth"
SM = POWERBI / f"{NAME}.SemanticModel"
RP = POWERBI / f"{NAME}.Report"
BASE_THEME = "CY24SU06"
THEME = "MumbaiHealthTheme"
SCHEMA = "https://developer.microsoft.com/json-schemas/fabric"

# Theme: a clinical navy frame, heart red for the cardiovascular module and teal for Mumbai's health facilities.
NAVY, NAVY_2, HEART, TEAL, MIST = "#0B2545", "#16365C", "#C8102E", "#0E7C86", "#EEF3F7"
INK, MUTED, LINE, SKY = "#1B2A3A", "#5F6B7A", "#D5DEE7", "#9FB7CF"
OUTCOME_COLORS = {"Heart disease": HEART, "No heart disease": SKY}
MODEL_COLORS = {"Logistic Regression": SKY, "Random Forest": HEART, "Artificial Neural Network (MLP)": NAVY}
CATEGORY_COLORS = {"Dispensary": TEAL, "UPHC": "#4DB6AC", "Public hospital": NAVY, "Maternity home": "#E0A030"}
MODULE = {"home": ("OVERVIEW", NAVY), "models": ("MODULE 1 · CARDIOVASCULAR RISK", HEART),
          "patients": ("MODULE 1 · CARDIOVASCULAR RISK", HEART), "mumbai": ("MODULE 2 · MUMBAI HEALTHCARE ACCESS", TEAL),
          "insights": ("SUMMARY", NAVY)}

# ---------------------------------------------------------------- semantic model ------------------------------------
TABLES = ["dim_ward", "dim_category", "dim_site", "fact_facility", "fact_ward_category", "hospital_list",
          "clinical_patient", "dim_model", "model_metric", "model_confusion", "model_roc", "model_importance",
          "test_prediction", "cleaning_log", "missing_values"]

SORT_BY = {("dim_ward", "ward_name"): "ward_order", ("dim_category", "category_label"): "sort_order",
           ("clinical_patient", "age_band"): "age_band_order", ("dim_model", "model"): "sort_order",
           ("model_metric", "metric"): "metric_order", ("model_confusion", "cell"): "cell_order",
           ("missing_values", "stage"): "stage_order"}
DATA_CATEGORY = {"latitude": "Latitude", "longitude": "Longitude"}
HIDDEN = {"ward_order", "sort_order", "age_band_order", "metric_order", "cell_order", "stage_order"}

RELATIONSHIPS = [
    ("fact_facility", "ward_id", "dim_ward", "ward_id"),
    ("fact_ward_category", "ward_id", "dim_ward", "ward_id"),
    ("hospital_list", "ward_id", "dim_ward", "ward_id"),
    ("fact_facility", "category", "dim_category", "category"),
    ("fact_ward_category", "category", "dim_category", "category"),
    ("fact_facility", "site_id", "dim_site", "site_id"),
    ("model_metric", "model", "dim_model", "model"),
    ("model_confusion", "model", "dim_model", "model"),
    ("model_roc", "model", "dim_model", "model"),
    ("model_importance", "model", "dim_model", "model"),
    ("test_prediction", "model", "dim_model", "model"),
]

# (table, name, DAX, format string)
MEASURES = [
    # Mumbai facilities (from powerbi/measures.dax)
    ("fact_facility", "Total Distinct Sites", "DISTINCTCOUNT ( fact_facility[site_id] )", "#,0"),
    ("fact_facility", "Facility Records", "COUNTROWS ( fact_facility )", "#,0"),
    ("dim_ward", "Population 2011", "SUM ( dim_ward[population_2011] )", "#,0"),
    ("dim_ward", "Sites per 100k", "DIVIDE ( [Total Distinct Sites], [Population 2011] ) * 100000", "0.00"),
    ("dim_ward", "City-wide Sites per 100k", "CALCULATE ( [Sites per 100k], ALL ( dim_ward ) )", "0.00"),
    ("dim_ward", "Population Share %",
     "DIVIDE ( [Population 2011], CALCULATE ( [Population 2011], ALL ( dim_ward ) ) ) * 100", "0.00"),
    ("dim_ward", "Facility Share %",
     "DIVIDE ( [Total Distinct Sites], CALCULATE ( [Total Distinct Sites], ALL ( dim_ward ) ) ) * 100", "0.00"),
    ("dim_ward", "Share Gap (pp)", "[Population Share %] - [Facility Share %]", "+0.00;-0.00;0.00"),
    ("hospital_list", "Hospitals Listed", "COUNTROWS ( hospital_list )", "#,0"),
    ("hospital_list", "Beds Listed", "SUM ( hospital_list[beds] )", "#,0"),
    ("hospital_list", "Public Hospitals Listed",
     "CALCULATE ( COUNTROWS ( hospital_list ), hospital_list[ownership_class] = \"Public\" )", "#,0"),
    # Clinical data
    ("clinical_patient", "Patients", "COUNTROWS ( clinical_patient )", "#,0"),
    ("clinical_patient", "Heart Disease Patients",
     "CALCULATE ( COUNTROWS ( clinical_patient ), clinical_patient[target] = 1 )", "#,0"),
    ("clinical_patient", "Heart Disease Rate", "DIVIDE ( [Heart Disease Patients], [Patients] )", "0.0%"),
    ("clinical_patient", "Average Age", "AVERAGE ( clinical_patient[age] )", "0.0"),
    ("clinical_patient", "Average Max Heart Rate", "AVERAGE ( clinical_patient[max_heart_rate] )", "0"),
    ("clinical_patient", "Average Cholesterol", "AVERAGE ( clinical_patient[cholesterol] )", "0"),
    ("clinical_patient", "Cholesterol Not Recorded",
     "CALCULATE ( COUNTROWS ( clinical_patient ), ISBLANK ( clinical_patient[cholesterol] ) )", "#,0"),
    ("clinical_patient", "Male Share",
     "DIVIDE ( CALCULATE ( COUNTROWS ( clinical_patient ), clinical_patient[sex] = \"Male\" ), [Patients] )", "0.0%"),
    ("clinical_patient", "Majority Baseline Accuracy",
     "DIVIDE ( CALCULATE ( COUNTROWS ( clinical_patient ), clinical_patient[split] = \"Test\", "
     "clinical_patient[target] = 1 ), CALCULATE ( COUNTROWS ( clinical_patient ), clinical_patient[split] = \"Test\" ) )",
     "0.000"),
    # Models
    ("model_metric", "Test Metric", "CALCULATE ( AVERAGE ( model_metric[value] ), model_metric[set] = \"Test\" )",
     "0.000"),
    ("model_metric", "CV Metric", "CALCULATE ( AVERAGE ( model_metric[value] ), model_metric[set] = \"5-fold CV\" )",
     "0.000"),
    ("model_metric", "Test Accuracy", "CALCULATE ( [Test Metric], model_metric[metric] = \"Accuracy\" )", "0.0%"),
    ("model_metric", "Test ROC-AUC", "CALCULATE ( [Test Metric], model_metric[metric] = \"ROC-AUC\" )", "0.000"),
    ("model_metric", "Test F1", "CALCULATE ( [Test Metric], model_metric[metric] = \"F1\" )", "0.000"),
    ("model_metric", "Test Recall", "CALCULATE ( [Test Metric], model_metric[metric] = \"Recall\" )", "0.0%"),
    ("model_metric", "Best Test ROC-AUC",
     "CALCULATE ( MAX ( model_metric[value] ), model_metric[set] = \"Test\", model_metric[metric] = \"ROC-AUC\" )",
     "0.000"),
    ("model_metric", "Best Model",
     "\nVAR scores = FILTER ( ALL ( model_metric ), model_metric[set] = \"Test\" && model_metric[metric] = \"ROC-AUC\" )"
     "\nVAR top = MAXX ( scores, model_metric[value] )"
     "\nRETURN MAXX ( FILTER ( scores, model_metric[value] = top ), model_metric[model] )", None),
    ("model_confusion", "Confusion Patients", "SUM ( model_confusion[patients] )", "#,0"),
    ("model_roc", "True Positive Rate", "MAX ( model_roc[tpr] )", "0.00"),
    ("model_importance", "Permutation Importance", "AVERAGE ( model_importance[importance] )", "0.000"),
    ("test_prediction", "Test Predictions", "COUNTROWS ( test_prediction )", "#,0"),
    ("test_prediction", "Correct Share",
     "DIVIDE ( CALCULATE ( COUNTROWS ( test_prediction ), test_prediction[correct] = \"Correct\" ), "
     "COUNTROWS ( test_prediction ) )", "0.0%"),
    ("test_prediction", "Patients All Models Right",
     "\nCALCULATE ("
     "\n    COUNTROWS ("
     "\n        FILTER ("
     "\n            VALUES ( test_prediction[patientid] ),"
     "\n            CALCULATE ( COUNTROWS ( test_prediction ), test_prediction[correct] = \"Correct\" ) = 3"
     "\n        )"
     "\n    ),"
     "\n    REMOVEFILTERS ( dim_model )"
     "\n)", "#,0"),
    ("missing_values", "Missing Values", "SUM ( missing_values[missing] )", "#,0"),
]


def _tag(*parts):
    return str(uuid.uuid5(uuid.NAMESPACE_URL, "mumbaihealth/" + "/".join(parts)))


def _q(name):
    """TMDL object name, quoted when it is not a plain identifier."""
    return name if name.replace("_", "").isalnum() and not name[0].isdigit() else "'" + name.replace("'", "''") + "'"


def _types(df):
    out = {}
    for c, t in df.dtypes.items():
        if pd.api.types.is_bool_dtype(t):
            out[c] = ("boolean", "type logical")
        elif pd.api.types.is_integer_dtype(t):
            out[c] = ("int64", "Int64.Type")
        elif pd.api.types.is_float_dtype(t):
            out[c] = ("double", "type number")
        else:
            out[c] = ("string", "type text")
    return out


def _table_tmdl(name):
    df = pd.read_csv(DATA / f"{name}.csv")
    types = _types(df)
    lines = [f"table {name}", f"\tlineageTag: {_tag(name)}", ""]
    for table, mname, dax, fmt in MEASURES:
        if table != name:
            continue
        if dax.startswith("\n"):
            lines.append(f"\tmeasure {_q(mname)} =")
            lines += ["\t\t\t" + x for x in dax.strip("\n").split("\n")]
        else:
            lines.append(f"\tmeasure {_q(mname)} = {dax}")
        if fmt:
            lines.append(f"\t\tformatString: {fmt}")
        lines += [f"\t\tlineageTag: {_tag(name, 'm', mname)}", ""]
    for col, (dtype, _) in types.items():
        lines += [f"\tcolumn {_q(col)}", f"\t\tdataType: {dtype}"]
        if col in HIDDEN:
            lines.append("\t\tisHidden")
        if col in DATA_CATEGORY:
            lines.append(f"\t\tdataCategory: {DATA_CATEGORY[col]}")
        lines += [f"\t\tlineageTag: {_tag(name, 'c', col)}", "\t\tsummarizeBy: none", f"\t\tsourceColumn: {col}"]
        if (name, col) in SORT_BY:
            lines.append(f"\t\tsortByColumn: {SORT_BY[(name, col)]}")
        lines += ["", "\t\tannotation SummarizationSetBy = Automatic", ""]
    typed = ", ".join(f'{{"{c}", {m}}}' for c, (_, m) in types.items())
    m = [
        "let",
        f'    Source = Csv.Document(File.Contents(DataFolder & "{name}.csv"), [Delimiter = ",", Encoding = 65001, '
        "QuoteStyle = QuoteStyle.Csv]),",
        "    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),",
        f'    Typed = Table.TransformColumnTypes(Promoted, {{{typed}}}, "en-US")',
        "in",
        "    Typed",
    ]
    lines += [f"\tpartition {name} = m", "\t\tmode: import", "\t\tsource ="] + ["\t\t\t\t" + x for x in m]
    lines += ["", "\tannotation PBI_ResultType = Table", ""]
    return "\n".join(lines)


def data_folder_expression(folder):
    folder = str(folder).rstrip("\\/") + ("\\" if "\\" in str(folder) or ":" in str(folder)[:3] else "/")
    return "\n".join([
        f'expression DataFolder = "{folder}" meta [IsParameterQuery = true, Type = "Text", '
        "IsParameterQueryRequired = true]",
        f"\tlineageTag: {_tag('DataFolder')}",
        "",
        "\tannotation PBI_ResultType = Text",
        "",
    ])


def write_semantic_model(folder):
    d = SM / "definition"
    (d / "tables").mkdir(parents=True, exist_ok=True)
    _json(SM / "definition.pbism", {
        "$schema": f"{SCHEMA}/item/semanticModel/definitionProperties/1.0.0/schema.json",
        "version": "4.2", "settings": {}})
    (d / "database.tmdl").write_text("database\n\tcompatibilityLevel: 1567\n\n")
    order = json.dumps(["DataFolder"] + TABLES)
    (d / "model.tmdl").write_text("\n".join([
        "model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3",
        "\tsourceQueryCulture: en-US", "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull",
        "", "annotation __PBI_TimeIntelligenceEnabled = 0", "", f"annotation PBI_QueryOrder = {order}", "",
        *[f"ref table {t}" for t in TABLES], ""]))
    (d / "expressions.tmdl").write_text(data_folder_expression(folder))
    for t in TABLES:
        (d / "tables" / f"{t}.tmdl").write_text(_table_tmdl(t))
    rel = []
    for ft, fc, tt, tc in RELATIONSHIPS:
        rel += [f"relationship {_tag('rel', ft, fc, tt)}", f"\tfromColumn: {ft}.{fc}", f"\ttoColumn: {tt}.{tc}", ""]
    (d / "relationships.tmdl").write_text("\n".join(rel))


# ---------------------------------------------------------------- report helpers ------------------------------------
def _lit(v):
    if isinstance(v, bool):
        s = "true" if v else "false"
    elif isinstance(v, int):
        s = f"{v}L"
    elif isinstance(v, float):
        s = f"{v:g}D"
    else:
        s = "'" + str(v).replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": s}}}


def _num(v):
    return {"expr": {"Literal": {"Value": f"{v:g}D"}}}


def _color(hex_):
    return {"solid": {"color": {"expr": {"Literal": {"Value": f"'{hex_}'"}}}}}


def _props(**kw):
    return {"properties": kw}


def col(table, column):
    return {"Column": {"Expression": {"SourceRef": {"Entity": table}}, "Property": column}}


def meas(table, measure):
    return {"Measure": {"Expression": {"SourceRef": {"Entity": table}}, "Property": measure}}


def avg(table, column):
    return {"Aggregation": {"Expression": col(table, column), "Function": 1}}


def _proj(field, active=False):
    if "Aggregation" in field:
        c = field["Aggregation"]["Expression"]["Column"]
        ref, native = f"Avg({c['Expression']['SourceRef']['Entity']}.{c['Property']})", f"Average of {c['Property']}"
    else:
        f = field.get("Column") or field.get("Measure")
        ref, native = f"{f['Expression']['SourceRef']['Entity']}.{f['Property']}", f["Property"]
    p = {"field": field, "queryRef": ref, "nativeQueryRef": native}
    if active:
        p["active"] = True
    return p


class Page:
    def __init__(self, name, title, order):
        self.name, self.title, self.order = name, title, order
        self.eyebrow, self.accent = MODULE[name]
        self.visuals, self.objects = [], {}
        self._z = 0

    def add(self, vtype, x, y, w, h, roles=None, objects=None, vc=None, title=None, sort=None, extra=None):
        self._z += 1
        vid = f"{self.name}_{self._z:02d}"
        visual = {"visualType": vtype}
        if roles:
            qs = {}
            for role, fields in roles.items():
                qs[role] = {"projections": [_proj(f, active=(role in ("Category", "Rows", "Values") and vtype == "slicer"))
                                            for f in fields]}
            visual["query"] = {"queryState": qs}
            if sort:
                visual["query"]["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}],
                                                     "isDefaultSort": True}
        if objects:
            visual["objects"] = objects
        vco = dict(vc or {})
        if title is not None:
            vco["title"] = [_props(show=_lit(True), text=_lit(title))]
        if vco:
            visual["visualContainerObjects"] = vco
        visual["drillFilterOtherVisuals"] = True
        if extra:
            visual.update(extra)
        self.visuals.append({
            "$schema": f"{SCHEMA}/item/report/definition/visualContainer/1.1.0/schema.json",
            "name": vid,
            "position": {"x": x, "y": y, "z": self._z * 100, "height": h, "width": w, "tabOrder": self._z * 100},
            "visual": visual})
        return vid


def _text(paragraphs):
    """paragraphs: list of (runs, align) where runs are (text, style dict)."""
    out = []
    for runs, align in paragraphs:
        p = {"textRuns": [{"value": t, "textStyle": s} for t, s in runs]}
        if align:
            p["horizontalTextAlignment"] = align
        out.append(p)
    return {"general": [_props(paragraphs=out)]}


def _no_chrome(bg=None):
    vc = {"border": [_props(show=_lit(False))], "dropShadow": [_props(show=_lit(False))],
          "title": [_props(show=_lit(False))]}
    vc["background"] = [_props(show=_lit(bg is not None), **({"color": _color(bg), "transparency": _num(0)}
                                                              if bg else {}))]
    return vc


def textbox(page, x, y, w, h, paragraphs, bg=None):
    return page.add("textbox", x, y, w, h, objects=_text(paragraphs), vc=_no_chrome(bg))


def card(page, x, y, w, h, field, label, color=None):
    return page.add("card", x, y, w, h, roles={"Values": [field]}, objects={
        "labels": [_props(color=_color(color or page.accent), fontSize=_num(24), bold=_lit(True))],
        "categoryLabels": [_props(show=_lit(False))]},
        vc={"title": [_props(show=_lit(True), text=_lit(label), fontColor=_color(MUTED), fontSize=_num(10),
                             alignment=_lit("center"))]})


def slicer(page, x, y, w, h, field, title, tiles=True):
    return page.add("slicer", x, y, w, h, roles={"Values": [field]}, objects={
        "data": [_props(mode=_lit("Basic" if tiles else "Dropdown"))],
        "general": [_props(orientation=_num(1 if tiles else 0))],
        "header": [_props(show=_lit(True), fontColor=_color(page.accent), textSize=_num(10), text=_lit(title))],
        "items": [_props(fontColor=_color(INK), background=_color("#FFFFFF"), textSize=_num(10))]})


def _point_colors(field, colors):
    """dataPoint fills keyed on the values of one column (a legend or category field)."""
    return [{"properties": {"fill": _color(c)},
             "selector": {"data": [{"scopeId": {"Comparison": {"ComparisonKind": 0, "Left": field,
                                                               "Right": {"Literal": {"Value": _lit(v)["expr"]["Literal"]["Value"]}}}}}]}}
            for v, c in colors.items()]


def chart(page, vtype, x, y, w, h, title, category, values, series=None, sort=None, labels=True, extra_objects=None,
          colors=None, fill=None, measure_colors=None):
    """colors: {value: hex} for the series field (or the category field of a donut); measure_colors: one hex per
    measure in values; otherwise one fill, the page accent by default."""
    roles = {"Category": category, "Y": values}
    if series:
        roles["Series"] = series
    objects = {"labels": [_props(show=_lit(labels), fontSize=_num(9))],
               "legend": [_props(show=_lit(bool(series)), position=_lit("Top"), fontSize=_num(9))],
               "valueAxis": [_props(gridlineShow=_lit(False), showAxisTitle=_lit(False))],
               "categoryAxis": [_props(showAxisTitle=_lit(False), fontSize=_num(9))]}
    if vtype in ("donutChart", "pieChart"):
        objects = {"labels": [_props(show=_lit(True), labelStyle=_lit("Category, percent of total"),
                                     fontSize=_num(9))],
                   "legend": [_props(show=_lit(False))]}
    if colors:
        objects["dataPoint"] = _point_colors((series or category)[0], colors)
    elif measure_colors:
        objects["dataPoint"] = [{"properties": {"fill": _color(c)}, "selector": {"metadata": _proj(f)["queryRef"]}}
                                for f, c in zip(values, measure_colors)]
    elif not series and vtype not in ("donutChart", "pieChart"):
        objects["dataPoint"] = [_props(fill=_color(fill or page.accent))]
    objects.update(extra_objects or {})
    return page.add(vtype, x, y, w, h, roles=roles, objects=objects, title=title, sort=sort)


def table(page, vtype, x, y, w, h, title, roles):
    return page.add(vtype, x, y, w, h, roles=roles, title=title, objects={
        "columnHeaders": [_props(fontColor=_color("#FFFFFF"), backColor=_color(page.accent), fontSize=_num(10),
                                 bold=_lit(True))],
        "values": [_props(fontSize=_num(9))],
        "grid": [_props(gridVertical=_lit(False), rowPadding=_num(3))]})


# ---------------------------------------------------------------- report pages --------------------------------------
PAGES = [("home", "Home"), ("models", "Model performance"), ("patients", "Patient data"),
         ("mumbai", "Mumbai facilities"), ("insights", "Insights")]
X0, W = 150, 1115  # content area right of the navigation rail


def nav_and_header(page, subtitle):
    """Navy navigation rail and header band, with a thin accent line in the page's module colour."""
    textbox(page, 0, 0, 140, 720, [([("", {})], None)], bg=NAVY)
    textbox(page, 10, 18, 120, 84, [([("\u2665", {"fontSize": "26pt", "fontWeight": "bold", "color": HEART})], "center"),
                                    ([("MUMBAI HEALTH", {"fontSize": "10pt", "fontWeight": "bold", "color": "#FFFFFF"})],
                                     "center"),
                                    ([("heart risk · city care", {"fontSize": "8pt", "color": SKY})], "center")])
    for i, (pid, label) in enumerate(PAGES):
        active = pid == page.name
        page.add("actionButton", 14, 124 + i * 58, 112, 44, objects={
            "icon": [_props(show=_lit(False))],
            "text": [_props(show=_lit(True)),
                     {"properties": {"text": _lit(label), "fontColor": _color("#FFFFFF" if active else "#DCE6F0"),
                                     "fontSize": _num(10), "horizontalAlignment": _lit("center")},
                      "selector": {"id": "default"}}],
            "fill": [_props(show=_lit(True)),
                     {"properties": {"fillColor": _color((MODULE[pid][1] if MODULE[pid][1] != NAVY else "#3A6EA5")
                                                         if active else NAVY_2),
                                     "transparency": _num(0)},
                      "selector": {"id": "default"}}],
            "outline": [_props(show=_lit(False))],
            "shape": [_props(roundEdge=_num(8))]},
            vc={"visualLink": [_props(show=_lit(True), type=_lit("PageNavigation"),
                                      navigationSection=_lit(pid))],
                "title": [_props(show=_lit(False))], "border": [_props(show=_lit(False))],
                "dropShadow": [_props(show=_lit(False))], "background": [_props(show=_lit(False))]})
    textbox(page, 10, 640, 120, 66, [([("Models are experimental, not clinical advice. Clinical data: India, not Mumbai.",
                                        {"fontSize": "7pt", "color": SKY})], "center")], bg=NAVY)
    textbox(page, X0, 10, W, 62, [
        ([(page.eyebrow, {"fontSize": "8pt", "fontWeight": "bold", "color": SKY})], None),
        ([(page.title, {"fontSize": "18pt", "fontWeight": "bold", "color": "#FFFFFF"})], None)], bg=NAVY)
    textbox(page, X0 + 420, 14, W - 432, 54, [([(subtitle, {"fontSize": "9pt", "color": "#DCE6F0"})], None)],
            bg=NAVY)
    textbox(page, X0, 72, W, 4, [([("", {})], None)], bg=page.accent if page.accent != NAVY else "#3A6EA5")


def build_pages(facts):
    pages = []
    P, M, CP, F, WD, HL = "clinical_patient", "model_metric", "clinical_patient", "fact_facility", "dim_ward", \
        "hospital_list"

    # 1. Home -------------------------------------------------------------------------------------------------------
    p = Page("home", "Home", 1)
    nav_and_header(p, "Two modules in one report: three heart-disease classifiers trained on an Indian clinical "
                      "dataset (Doppala & Bhattacharyya, 2021), and public health facilities across Mumbai's 24 BMC "
                      "wards. The clinical data is not Mumbai-specific, so the two are never joined.")
    kpis = [(meas(P, "Patients"), "Patients in clinical data"), (meas(P, "Heart Disease Rate"), "Heart-disease rate"),
            (meas(M, "Best Test ROC-AUC"), "Best test ROC-AUC"), (meas(F, "Total Distinct Sites"), "Public health sites"),
            (meas(WD, "Population 2011"), "Population (Census 2011)"), (meas(WD, "Sites per 100k"), "Sites per 100k people")]
    cw = (W - 5 * 12) / 6
    for i, (f, label) in enumerate(kpis):  # cardiovascular cards in heart red, Mumbai cards in teal
        card(p, X0 + i * (cw + 12), 88, cw, 96, f, label, color=HEART if i < 3 else TEAL)
    third = (W - 24) / 3
    chart(p, "clusteredColumnChart", X0, 196, third, 300, "Test accuracy by model",
          [col("dim_model", "model")], [meas(M, "Test Accuracy")], fill=HEART)
    chart(p, "columnChart", X0 + third + 12, 196, third, 300, "Patients by age band and outcome",
          [col(CP, "age_band")], [meas(P, "Patients")], series=[col(CP, "outcome")], labels=False,
          colors=OUTCOME_COLORS)
    chart(p, "donutChart", X0 + 2 * (third + 12), 196, third, 300, "Facility records by category",
          [col("dim_category", "category_label")], [meas(F, "Facility Records")], colors=CATEGORY_COLORS)
    textbox(p, X0, 508, W, 196, [
        ([("Highlights", {"fontSize": "13pt", "fontWeight": "bold", "color": NAVY})], None),
        *[([("•  " + t, {"fontSize": "10pt", "color": INK})], None) for t in facts["home"]]], bg="#FFFFFF")
    pages.append(p)

    # 2. Model performance ------------------------------------------------------------------------------------------
    p = Page("models", "Model performance", 2)
    nav_and_header(p, "Logistic Regression, Random Forest and an ANN (MLP), tuned with 5-fold stratified "
                      "cross-validation on 800 patients and tested once on 200 held-out patients. Pick a model "
                      "to filter the page.")
    slicer(p, X0, 84, 420, 74, col("dim_model", "model"), "Model")
    k = [(meas(M, "Best Model"), "Best model (ROC-AUC)"), (meas(P, "Majority Baseline Accuracy"),
                                                           "Majority-class baseline accuracy"),
         (meas("test_prediction", "Patients All Models Right"), "Test patients all 3 models got right")]
    for i, (f, label) in enumerate(k):
        card(p, X0 + 432 + i * 232, 84, 220, 74, f, label)
    half = (W - 12) / 2
    table(p, "pivotTable", X0, 170, half, 170, "Test-set metrics", {
        "Rows": [col("dim_model", "model")], "Columns": [col(M, "metric")], "Values": [meas(M, "Test Metric")]})
    table(p, "pivotTable", X0 + half + 12, 170, half, 170, "Confusion matrix (200 test patients)", {
        "Rows": [col("model_confusion", "cell")], "Columns": [col("dim_model", "model")],
        "Values": [meas("model_confusion", "Confusion Patients")]})
    third = (W - 24) / 3
    chart(p, "lineChart", X0, 352, third, 352, "ROC curve (test set)", [col("model_roc", "fpr")],
          [meas("model_roc", "True Positive Rate")], series=[col("dim_model", "model")], labels=False,
          colors=MODEL_COLORS,
          extra_objects={"categoryAxis": [_props(axisType=_lit("Scalar"), showAxisTitle=_lit(True),
                                                 titleText=_lit("False positive rate"), fontSize=_num(9))]})
    chart(p, "clusteredColumnChart", X0 + third + 12, 352, third, 352, "Test vs 5-fold CV ROC-AUC",
          [col("dim_model", "model")], [meas(M, "Test ROC-AUC"), meas(M, "CV Metric")], labels=True,
          measure_colors=[HEART, SKY], extra_objects={"legend": [_props(show=_lit(True), position=_lit("Top"))]})
    chart(p, "clusteredBarChart", X0 + 2 * (third + 12), 352, third, 352,
          "Permutation importance (drop in ROC-AUC)", [col("model_importance", "feature")],
          [meas("model_importance", "Permutation Importance")], labels=False,
          sort=(meas("model_importance", "Permutation Importance"), "Descending"))
    pages.append(p)

    # 3. Patient data -----------------------------------------------------------------------------------------------
    p = Page("patients", "Patient data", 3)
    nav_and_header(p, "1,000 patients from one hospital in India (Doppala & Bhattacharyya, 2021). Use the slicers "
                      "to compare groups. Cholesterol 0 and slope 0 are treated as not recorded.")
    slicer(p, X0, 84, 260, 74, col(CP, "sex"), "Sex")
    slicer(p, X0 + 272, 84, 330, 74, col(CP, "outcome"), "Outcome")
    k = [(meas(P, "Patients"), "Patients"), (meas(P, "Heart Disease Rate"), "Heart-disease rate"),
         (meas(P, "Average Age"), "Average age"), (meas(P, "Cholesterol Not Recorded"), "Cholesterol not recorded")]
    kw = (W - 614 - 36) / 4
    for i, (f, label) in enumerate(k):
        card(p, X0 + 614 + i * (kw + 12), 84, kw, 74, f, label)
    half = (W - 12) / 2
    chart(p, "columnChart", X0, 170, half, 260, "Patients by age band and outcome", [col(CP, "age_band")],
          [meas(P, "Patients")], series=[col(CP, "outcome")], labels=False, colors=OUTCOME_COLORS)
    chart(p, "clusteredBarChart", X0 + half + 12, 170, half, 260, "Heart-disease rate by chest pain type",
          [col(CP, "chest_pain")], [meas(P, "Heart Disease Rate")],
          sort=(meas(P, "Heart Disease Rate"), "Descending"))
    third = (W - 24) / 3
    chart(p, "donutChart", X0, 442, third, 262, "Patients by sex", [col(CP, "sex")], [meas(P, "Patients")],
          colors={"Male": NAVY, "Female": SKY})
    chart(p, "clusteredBarChart", X0 + third + 12, 442, third, 262, "Heart-disease rate by ST slope",
          [col(CP, "st_slope")], [meas(P, "Heart Disease Rate")], sort=(meas(P, "Heart Disease Rate"), "Descending"))
    chart(p, "clusteredColumnChart", X0 + 2 * (third + 12), 442, third, 262,
          "Heart-disease rate by major vessels (0-3)", [col(CP, "major_vessels")], [meas(P, "Heart Disease Rate")])
    pages.append(p)

    # 4. Mumbai facilities ------------------------------------------------------------------------------------------
    p = Page("mumbai", "Mumbai facilities", 4)
    nav_and_header(p, "Listed MCGM dispensaries, UPHCs, public hospitals and maternity homes (about 2025) against "
                      "Census 2011 ward population. Most coordinates are rounded to about 1 km.")
    slicer(p, X0, 84, 470, 74, col("dim_category", "category_label"), "Facility type")
    slicer(p, X0 + 482, 84, 150, 74, col(WD, "ward_name"), "Ward", tiles=False)
    k = [(meas(F, "Total Distinct Sites"), "Sites"), (meas(WD, "Sites per 100k"), "Sites per 100k"),
         (meas(HL, "Hospitals Listed"), "Hospitals list rows"), (meas(HL, "Beds Listed"), "Beds listed")]
    kw = (W - 644 - 36) / 4
    for i, (f, label) in enumerate(k):
        card(p, X0 + 644 + i * (kw + 12), 84, kw, 74, f, label)
    p.add("map", X0, 170, 420, 534, roles={
        "Category": [col(F, "facility_id")], "Series": [col("dim_category", "category_label")],
        "Y": [avg(F, "latitude")], "X": [avg(F, "longitude")], "Tooltips": [col(F, "facility_name")]},
        objects={"legend": [_props(show=_lit(True), position=_lit("Top"))],
                 "dataPoint": [_props(bubbleSize=_num(-6)),
                               *_point_colors(col("dim_category", "category_label"), CATEGORY_COLORS)]},
        title="Facility locations (coordinates rounded)")
    rest = W - 432
    half = (rest - 12) / 2
    chart(p, "clusteredBarChart", X0 + 432, 170, half, 534, "Sites per 100k people by ward",
          [col(WD, "ward_name")], [meas(WD, "Sites per 100k")], sort=(meas(WD, "Sites per 100k"), "Descending"))
    chart(p, "donutChart", X0 + 432 + half + 12, 170, half, 220, "Facility records by category",
          [col("dim_category", "category_label")], [meas(F, "Facility Records")], colors=CATEGORY_COLORS)
    chart(p, "clusteredBarChart", X0 + 432 + half + 12, 402, half, 302, "Hospitals list beds by ownership",
          [col(HL, "ownership_class")], [meas(HL, "Beds Listed")], sort=(meas(HL, "Beds Listed"), "Descending"))
    pages.append(p)

    # 5. Insights ---------------------------------------------------------------------------------------------------
    p = Page("insights", "Insights", 5)
    nav_and_header(p, "What the five pages add up to, written from the same data the charts use, plus the data "
                      "cleaning record and the caveats that limit how far the results can be taken.")
    boxes = [("Models", HEART, facts["models"]), ("Patient data", HEART, facts["patients"]),
             ("Mumbai facilities", TEAL, facts["mumbai"]), ("Data cleaning and caveats", NAVY, facts["quality"])]
    half = (W - 12) / 2
    for i, (head, color, items) in enumerate(boxes):
        x, y = X0 + (i % 2) * (half + 12), 88 + (i // 2) * 212
        textbox(p, x, y, half, 200, [([(head, {"fontSize": "13pt", "fontWeight": "bold", "color": color})], None),
                                     *[([(f"{n + 1}. {t}", {"fontSize": "10pt", "color": INK})], None)
                                       for n, t in enumerate(items)]], bg="#FFFFFF")
    table(p, "tableEx", X0, 512, half + 180, 192, "Cleaning log", {
        "Values": [col("cleaning_log", "dataset"), col("cleaning_log", "action"), col("cleaning_log", "records")]})
    chart(p, "clusteredColumnChart", X0 + half + 192, 512, W - half - 192, 192, "Missing values by stage",
          [col("missing_values", "field")], [meas("missing_values", "Missing Values")],
          series=[col("missing_values", "stage")],
          colors={"Raw file": SKY, "After recoding 0 codes": HEART, "After imputation (in pipeline)": TEAL})
    pages.append(p)
    return pages


def facts():
    """Numbers for the text boxes, read from the same CSVs the report loads."""
    met = pd.read_csv(DATA / "model_metric.csv")
    t = met[met["set"] == "Test"].pivot(index="model", columns="metric", values="value")
    best = t["ROC-AUC"].idxmax()
    pat = pd.read_csv(DATA / "clinical_patient.csv")
    rate = pat["target"].mean()
    cp = pat.groupby("chest_pain")["target"].mean().sort_values()
    sl = pat.groupby("st_slope")["target"].mean()
    ward = pd.read_csv(DATA / "dim_ward.csv")
    hi, lo = ward.loc[ward["facilities_per_100k"].idxmax()], ward.loc[ward["facilities_per_100k"].idxmin()]
    sites = pd.read_csv(DATA / "dim_site.csv")
    fac = pd.read_csv(DATA / "fact_facility.csv")
    pop = ward["population_2011"].sum()
    hl = pd.read_csv(DATA / "hospital_list.csv")
    beds = hl.groupby("ownership_class")["beds"].sum()
    preds = pd.read_csv(DATA / "test_prediction.csv")
    allright = int((preds[preds["correct"] == "Correct"].groupby("patientid").size() == 3).sum())
    log = pd.read_csv(DATA / "cleaning_log.csv")
    chol = int(log.loc[log["action"].str.contains("serumcholestrol"), "records"].iloc[0])
    slope0 = int(log.loc[log["action"].str.contains("slope"), "records"].iloc[0])
    return {
        "home": [
            f"{best} scores best on the 200 held-out patients: ROC-AUC {t.loc[best, 'ROC-AUC']:.3f}, accuracy "
            f"{t.loc[best, 'Accuracy']:.1%}. A majority-class guess scores {pat[pat['split'] == 'Test']['target'].mean():.1%}.",
            f"{rate:.0%} of the {len(pat):,} patients have heart disease. The data is Indian but not from Mumbai.",
            f"Mumbai has {len(sites)} listed public health sites for {pop:,} people (Census 2011): "
            f"{len(sites) / pop * 1e5:.2f} per 100,000. Ward {hi['ward_id']} has the most per person, "
            f"{lo['ward_id']} the fewest.",
        ],
        "models": [
            f"{best} has the highest test ROC-AUC ({t.loc[best, 'ROC-AUC']:.3f}); Logistic Regression is lowest "
            f"({t.loc['Logistic Regression', 'ROC-AUC']:.3f}). All beat the {pat[pat['split'] == 'Test']['target'].mean():.0%} baseline by far.",
            f"All three models are right for {allright} of the 200 test patients.",
            "Scores are high mainly because ST slope almost separates the classes in this file. Without it, "
            "ROC-AUC is still 0.948 to 0.989.",
        ],
        "patients": [
            f"{cp.index[-1]} has the highest heart-disease rate ({cp.iloc[-1]:.0%}); {cp.index[0]} the lowest "
            f"({cp.iloc[0]:.0%}).",
            f"Flat or downsloping ST slope means heart disease in {min(sl.get('Flat', 0), sl.get('Downsloping', 0)):.0%}"
            f" or more of cases; the undocumented code 0 is never positive.",
            f"Average age is {pat['age'].mean():.0f}; {pat['sex'].eq('Male').mean():.0%} of patients are male.",
        ],
        "mumbai": [
            f"{len(fac)} facility records sit at {len(sites)} distinct sites, because "
            f"{len(fac) - len(sites)} sites host two facility types (mostly a dispensary and a UPHC).",
            f"Ward {hi['ward_id']} has {hi['facilities_per_100k']:.2f} sites per 100k people; ward {lo['ward_id']} "
            f"has {lo['facilities_per_100k']:.2f}.",
            f"The hospitals list has {len(hl)} rows; private hospitals hold {beds.get('Private', 0):,.0f} of "
            f"{beds.sum():,.0f} listed beds.",
        ],
        "quality": [
            f"Cholesterol = 0 in {chol} rows and slope = 0 in {slope0} rows were recoded as missing and imputed "
            "inside the model pipeline.",
            "No duplicate rows or patient ids, so no patient is in both the training and the test set.",
            "Population is Census 2011; facility layers date from about 2025. Predictions are experimental, not "
            "clinically validated.",
        ],
    }


def write_report():
    d = RP / "definition"
    if d.exists():
        shutil.rmtree(d)
    (d / "pages").mkdir(parents=True)
    _json(RP / "definition.pbir", {"$schema": f"{SCHEMA}/item/report/definitionProperties/2.0.0/schema.json",
                                   "version": "4.0", "datasetReference": {"byPath": {"path": f"../{NAME}.SemanticModel"}}})
    _json(d / "version.json", {"$schema": f"{SCHEMA}/item/report/definition/versionMetadata/1.0.0/schema.json",
                               "version": "2.0.0"})
    _json(d / "report.json", {
        "$schema": f"{SCHEMA}/item/report/definition/report/1.1.0/schema.json",
        "themeCollection": {
            "baseTheme": {"name": BASE_THEME, "reportVersionAtImport": "5.56", "type": "SharedResources"},
            "customTheme": {"name": f"{THEME}.json", "reportVersionAtImport": "5.56", "type": "RegisteredResources"}},
        "layoutOptimization": "None",
        "objects": {"outspacePane": [_props(expanded=_lit(False), visible=_lit(True))]},
        "resourcePackages": [
            {"name": "SharedResources", "type": "SharedResources",
             "items": [{"name": BASE_THEME, "path": f"BaseThemes/{BASE_THEME}.json", "type": "BaseTheme"}]},
            {"name": "RegisteredResources", "type": "RegisteredResources",
             "items": [{"name": f"{THEME}.json", "path": f"{THEME}.json", "type": "CustomTheme"}]}],
        "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True,
                     "allowChangeFilterTypes": True, "useEnhancedTooltips": True,
                     "useDefaultAggregateDisplayName": True}})
    pages = build_pages(facts())
    _json(d / "pages" / "pages.json", {"$schema": f"{SCHEMA}/item/report/definition/pagesMetadata/1.0.0/schema.json",
                                       "pageOrder": [p.name for p in pages], "activePageName": pages[0].name})
    for p in pages:
        pd_ = d / "pages" / p.name
        page = {"$schema": f"{SCHEMA}/item/report/definition/page/1.1.0/schema.json", "name": p.name,
                "displayName": p.title, "displayOption": "FitToPage", "height": 720, "width": 1280}
        if p.objects:
            page["objects"] = p.objects
        _json(pd_ / "page.json", page)
        for v in p.visuals:
            _json(pd_ / "visuals" / v["name"] / "visual.json", v)
    res = RP / "StaticResources"
    (res / "SharedResources" / "BaseThemes").mkdir(parents=True, exist_ok=True)
    (res / "RegisteredResources").mkdir(parents=True, exist_ok=True)
    shutil.copy(Path(__file__).parent / "powerbi_assets" / f"{BASE_THEME}.json",
                res / "SharedResources" / "BaseThemes" / f"{BASE_THEME}.json")
    _json(res / "RegisteredResources" / f"{THEME}.json", theme())
    return pages


def theme():
    white = {"solid": {"color": "#FFFFFF"}}
    return {
        "name": "Mumbai Health: heart risk and city care",
        "dataColors": [HEART, TEAL, NAVY, SKY, "#E0A030", "#4DB6AC", "#8E5572", "#9AA5B1"],
        "foreground": INK, "background": "#FFFFFF", "tableAccent": NAVY,
        "good": "#199E70", "neutral": "#F2B705", "bad": "#C0392B",
        "textClasses": {
            "callout": {"fontSize": 24, "fontFace": "Segoe UI Semibold", "color": NAVY},
            "title": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": NAVY},
            "header": {"fontSize": 12, "fontFace": "Segoe UI Semibold", "color": NAVY},
            "label": {"fontSize": 10, "fontFace": "Segoe UI", "color": INK}},
        "visualStyles": {
            "*": {"*": {
                "background": [{"show": True, "color": white, "transparency": 0}],
                "border": [{"show": True, "color": {"solid": {"color": LINE}}, "radius": 10}],
                "dropShadow": [{"show": True, "position": "Outer", "preset": "BottomRight"}],
                "title": [{"show": True, "fontColor": {"solid": {"color": NAVY}}, "fontSize": 12,
                           "alignment": "center"}]}},
            "page": {"*": {"background": [{"color": {"solid": {"color": MIST}}, "transparency": 0}],
                           "outspace": [{"color": {"solid": {"color": MIST}}, "transparency": 0}]}}},
    }


def _json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_measures_dax():
    lines = ["// Measures in MumbaiHealth.SemanticModel, generated by src/powerbi_project.py.",
             "// Each sits on the table named in its comment; the project already contains them.", ""]
    for table, name, dax, fmt in MEASURES:
        lines += [f"// {table}" + (f"   format: {fmt}" if fmt else ""), f"{name} = {dax.strip()}", ""]
    (POWERBI / "measures.dax").write_text("\n".join(lines))


def set_data_folder(folder=DATA):
    (SM / "definition" / "expressions.tmdl").write_text(data_folder_expression(folder))


def build(rebuild=False, folder=DATA):
    if (POWERBI / f"{NAME}.pbip").exists() and not rebuild:
        set_data_folder(folder)
        return "updated DataFolder"
    for d in (SM, RP):
        if d.exists():
            shutil.rmtree(d)
    write_semantic_model(folder)
    pages = write_report()
    _json(POWERBI / f"{NAME}.pbip", {"$schema": f"{SCHEMA}/pbip/pbipProperties/1.0.0/schema.json",
                                      "version": "1.0", "artifacts": [{"report": {"path": f"{NAME}.Report"}}],
                                      "settings": {"enableAutoRecovery": True}})
    (POWERBI / ".gitignore").write_text("**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
    write_measures_dax()
    return f"wrote {len(TABLES)} tables, {len(MEASURES)} measures, {len(pages)} pages, " \
           f"{sum(len(p.visuals) for p in pages)} visuals"


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true")
    ap.add_argument("--set-data-folder", action="store_true")
    a = ap.parse_args()
    print(set_data_folder() or "DataFolder set" if a.set_data_folder else build(rebuild=a.rebuild))

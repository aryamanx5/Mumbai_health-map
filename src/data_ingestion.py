"""Read raw KML/CSV inputs without modifying them."""
import hashlib
import xml.etree.ElementTree as ET

import pandas as pd
from shapely.geometry import MultiPolygon, Polygon

from .config import RAW

KML_NS = "{http://www.opengis.net/kml/2.2}"


def _tag(el):
    return el.tag.replace(KML_NS, "")


def _parse_coords(text):
    pts = []
    for tok in text.split():
        parts = tok.split(",")
        pts.append((float(parts[0]), float(parts[1])))
    return pts


def read_kml_points(path):
    """One row per Placemark: ExtendedData fields, raw coordinate string, geometry type."""
    rows = []
    for pm in ET.parse(path).getroot().iter(f"{KML_NS}Placemark"):
        rec = {sd.get("name"): (sd.text or "").strip() for sd in pm.iter(f"{KML_NS}SimpleData")}
        point = pm.find(f".//{KML_NS}Point/{KML_NS}coordinates")
        rec["_raw_coordinates"] = point.text.strip() if point is not None and point.text else None
        rec["_geometry_type"] = "Point" if point is not None else None
        rows.append(rec)
    return pd.DataFrame(rows)


def read_kml_polygons(path, name_field="NAME"):
    """Ward polygons as (name, shapely geometry, attributes) rows."""
    rows = []
    for pm in ET.parse(path).getroot().iter(f"{KML_NS}Placemark"):
        rec = {sd.get("name"): (sd.text or "").strip() for sd in pm.iter(f"{KML_NS}SimpleData")}
        polys = []
        for poly in pm.iter(f"{KML_NS}Polygon"):
            outer = poly.find(f"{KML_NS}outerBoundaryIs//{KML_NS}coordinates")
            inners = [_parse_coords(c.text) for c in poly.findall(f"{KML_NS}innerBoundaryIs//{KML_NS}coordinates")]
            polys.append(Polygon(_parse_coords(outer.text), inners))
        rec["geometry"] = polys[0] if len(polys) == 1 else MultiPolygon(polys)
        rows.append(rec)
    return pd.DataFrame(rows).rename(columns={name_field: "source_ward_name"})


def read_hospitals_csv(path=RAW / "mumbai_hospitals_list.csv"):
    # The file is Windows-1252 encoded (contains 0xA0 non-breaking spaces), not UTF-8.
    return pd.read_csv(path, encoding="cp1252", dtype=str)


def file_inventory(raw_dir=RAW):
    rows = []
    for p in sorted(raw_dir.iterdir()):
        if p.is_file() and not p.name.startswith("."):
            rows.append(dict(file=p.name, format=p.suffix.lstrip(".").upper(), size_bytes=p.stat().st_size,
                             sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    return pd.DataFrame(rows)

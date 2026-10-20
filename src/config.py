"""Paths and constants shared by the pipeline."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
INTERIM = ROOT / "data" / "interim"
PROCESSED = ROOT / "data" / "processed"
MODELS = ROOT / "models"
FIGURES = ROOT / "outputs" / "figures"
TABLES = ROOT / "outputs" / "tables"
REPORTS = ROOT / "outputs" / "reports"
POWERBI = ROOT / "powerbi"

RANDOM_SEED = 42

# Facility layers: file, category label, id prefix, and the source column for each field.
FACILITY_LAYERS = {
    "dispensary": dict(file="dispensaries.kml", prefix="DISP", id="OBJECTID",
                       name="Current_Na", address="Current_co", ward="Ward", owner="Owner_Dept", subtype=None),
    "uphc": dict(file="uphcs.kml", prefix="UPHC", id="OBJECTID",
                 name="UPHC_Name", address="UPHC_Addre", ward="Ward", owner="OwnerDept", subtype=None),
    "public_hospital": dict(file="public_hospitals.kml", prefix="HOSP", id="OBJECTID_1",
                            name="NAME_OF_HO", address="ADDRESS", ward="WARD", owner="OWNER_DEPT", subtype="TYPE"),
    "maternity_hospital": dict(file="maternity_hospitals.kml", prefix="MAT", id="OBJECTID",
                               name="Name_of_Mat_Home", address="Address", ward="Ward", owner="Owner_Dept", subtype=None),
}
CATEGORIES = list(FACILITY_LAYERS)

# The 24 BMC administrative wards, in the order used by the 2011 Census ward codes
# (first two digits of the census ward code; verified against the census file in population.py).
WARD_ORDER = ["A", "B", "C", "D", "E", "F/S", "F/N", "G/S", "G/N", "H/E", "H/W", "K/E",
              "K/W", "P/S", "P/N", "R/S", "R/C", "R/N", "L", "M/E", "M/W", "N", "S", "T"]
SUFFIX_NAMES = {"N": "North", "S": "South", "E": "East", "W": "West", "C": "Central"}

# Bounding box used only as a coarse plausibility check (Greater Mumbai, generous margin).
MUMBAI_BBOX = dict(lon_min=72.75, lon_max=73.05, lat_min=18.85, lat_max=19.35)
PROJECTED_CRS = "EPSG:32643"  # UTM zone 43N, metres

# Co-location matching: base tolerance plus the worst-case rounding error of each point.
COLOCATION_BASE_TOLERANCE_M = 300

# Data dictionary

## data/processed/facility_master.csv (one row per source facility record; 456 rows)
| Column | Type | Description |
|---|---|---|
| facility_id | text | `{DISP,UPHC,HOSP,MAT}-{source id}`; unique |
| site_id | text | Physical-site id; co-located records share it |
| category | text | dispensary / uphc / public_hospital / maternity_hospital (from the source layer) |
| facility_name, address | text | Cleaned source values |
| source_subtype | text | Hospital TYPE from source (Major / Peripheral / Special Hospital); empty for other layers |
| owner_dept | text | Source owner department (all "Public Health Dept") |
| source_ward_value | text | Ward exactly as in the source |
| ward_id / ward_name | text | Canonical ward id (e.g. `K/E`) and display name (`K East`) |
| longitude, latitude | float | WGS84; empty if missing |
| coordinate_decimals | int | Estimated precision (decimal places) |
| coordinate_status | text | valid / missing / outside_study_bbox |
| spatial_ward_id | text | Polygon containing the point (check only) |
| distance_to_source_ward_m | float | Distance from point to its source-ward polygon (0 if inside) |
| assignment_check | text | agree / disagree_within_coordinate_rounding / disagree_review / outside_polygons_* / no_valid_coordinates |
| source_file, source_record_id | | Provenance |
| name_stem | text | Name with facility-type words removed (used for matching) |

## data/processed/facility_sites.csv (one row per distinct site; 402 rows)
site_id, ward_id, site_name (first record's name), categories (`;`-joined), n_records, mean lon/lat, `is_<category>` flags.

## data/processed/ward_indicators.csv (24 rows)
| Column | Description |
|---|---|
| ward_id, ward_name, ward_order | Canonical id, display name, census order (1 = A … 24 = T) |
| area_km2 | Polygon area (EPSG:32643) |
| population_2011, census_wards, census_district | Census 2011 population, number of census wards summed, district |
| population_density_per_km2 | population_2011 / area_km2 |
| `<category>_count` | Facility records of that category |
| total_distinct_public_facilities | Distinct sites |
| total_facility_records | Records (≥ sites) |
| facilities_per_100k | Sites / population × 100,000 |
| population_per_facility | Population / sites (NaN if 0 sites) |
| `<category>_per_100k` | Category records / population × 100,000 |
| `<category>_share_pct` | Category records / sites × 100 (can sum > 100) |
| population_share_pct, facility_share_pct | Shares of the 24-ward totals |
| population_facility_share_gap | Population share − facility share (percentage points) |

## data/processed/ward_clusters.csv
ward_id, cluster_label (1–4, ordered by mean sites per 100k), kmeans_raw_label (model's internal id),
cluster_name (descriptor generated from the profile), silhouette_sample, cluster_k2_label (K = 2 alternative).

## ML features (outputs/tables/ml_feature_dictionary.csv)
dispensary_per_100k, uphc_per_100k, public_hospital_per_100k, maternity_hospital_per_100k, each log1p-transformed
and then z-scored, in that order.

## Power BI tables
See `powerbi/powerbi_spec.md`.

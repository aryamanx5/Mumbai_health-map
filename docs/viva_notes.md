# Viva preparation notes

**What is the question?** Whether listed public health facilities are spread across Mumbai's 24 wards in
proportion to population, and which wards look alike. It is about the distribution of facilities, not access.

**Where does the data come from?** OpenCity republishes MCGM's facility KMLs (2025), the ward polygons and Census
2011 tables. All were downloaded unchanged and hashed.

**Why Census 2011 and not 2023?** No official 2023 ward population was available. 2011 is the latest official
ward-level count. Expect the suburban rates to be overstated, since those wards have grown more.

**How do you avoid double counting?** A UPHC often runs inside a dispensary building. Two records merge into one
site only if the ward, the type-stripped name and the location (within tolerance) all match. That rule gave 54
merges, so 456 records become 402 sites. Same-named facilities in different wards stay separate.

**Why trust the source ward over the map?** Most coordinates are rounded to about 1 km, so a spatial join would
misplace facilities near boundaries. The join is used as a check: 431 of 455 records agree or are within rounding
error, and the other 24 are flagged for review.

**Main findings (all measured):**
* City-wide rate: 3.23 sites per 100k.
* Ward rates range from 2.17 (R/S) to 5.95 (A).
* The island city has 4.02 sites per 100k against 2.97 in the suburbs.
* 14 wards have a positive population/facility share gap; the largest are R/S, K/W and P/N.
* Public hospitals are concentrated in A and E: 9 of 31.

**Why K-Means, and why K = 4?** It is unsupervised because there is no valid target. K = 2 has the best silhouette
but only isolates A and E, and it is unstable under subsampling. K = 3–6 have flat silhouettes. K = 4 keeps the A/E
split and adds the natural split of the other 22 wards. It is a documented judgement, not an optimum.

**How good is the clustering?** It is modest: silhouette 0.32, one cluster with mean silhouette ≈ 0, and results
that change with the feature set (ARI 0.24–0.89). The clustering summarises the data; it is not ground truth.

**Why no supervised model?** Any label would be built from the same rates (circular), and 24 rows is too few to
validate.

**What would you add?**
1. Current population estimates.
2. Beds and staff per facility.
3. Network travel times.
4. Private and state/central facilities.
5. Utilisation and outcome data.

**What is the Power BI status?** CSVs, DAX and the spec are complete. The PBIX was not built because the
development machine is a Mac; this is stated openly.

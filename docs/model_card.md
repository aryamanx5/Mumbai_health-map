# Model card: K-Means ward provision clusters

| | |
|---|---|
| Task | Unsupervised grouping of the 24 BMC wards by listed public-facility provision profile |
| Algorithm | scikit-learn 1.9.1 `Pipeline(log1p → StandardScaler → KMeans)` |
| Config | K = 4, n_init = 50, max_iter = 500, random_state = 42 (`outputs/tables/ml_model_config.json`) |
| Artifact | `models/kmeans_pipeline.joblib` (pipeline, feature order, label mapping, ward ids) |
| Data | 24 wards × 4 features (`data/processed/ml_modelling_table.csv`); no rows excluded |
| Code | `src/model_training.py`, `src/model_evaluation.py`; tests in `tests/test_model.py` |

## Intended use
Describe which wards have similar mixes of listed dispensaries, UPHCs, public hospitals and maternity homes per
resident, as an input for choosing wards to investigate further. **Not** for judging access adequacy, ranking ward
performance or allocating resources. There is no target variable, and nothing here is a prediction.

## Features and why
`dispensary_per_100k`, `uphc_per_100k`, `public_hospital_per_100k`, `maternity_hospital_per_100k`.
* These are the four provision dimensions the project studies. Pairwise Spearman |ρ| ≤ 0.29, so they are not redundant.
* Excluded:
  * `facilities_per_100k` and `population_per_facility` are deterministic functions of the four rates and would
    double-weight them.
  * Raw population is already the denominator of every rate.
  * Ward ids are identifiers, not features.
* log1p damps the two hospital-rate outliers (A = 2.16, E = 1.27 per 100k, against a median of 0.18).
* No feature was undefined, so no imputation was needed. Undefined rates would have excluded the ward, not
  produced a zero.

## Selecting K (evidence: `outputs/tables/ml_k_evaluation.csv`, `outputs/figures/10_ml_elbow_silhouette.png`)

| K | silhouette | sizes | min seed ARI | mean subsample ARI | p10 subsample ARI | mean noise ARI |
|---|---|---|---|---|---|---|
| 2 | 0.456 | 22, 2 | 1.00 | 0.60 | −0.03 | 0.96 |
| 3 | 0.303 | 13, 9, 2 | 1.00 | 0.69 | 0.37 | 0.67 |
| **4** | **0.316** | **11, 8, 3, 2** | 0.89 | 0.73 | 0.34 | 0.64 |
| 5 | 0.315 | 10, 7, 3, 2, 2 | 0.78 | 0.75 | 0.51 | 0.63 |
| 6 | 0.327 | 8, 7, 3, 2, 2, 2 | 0.75 | 0.77 | 0.56 | 0.66 |

* The rule set in advance (highest silhouette among non-degenerate K) gives **K = 2**. That solution only separates
  A and E from the other 22 wards, and its subsample stability collapses whenever A or E is left out.
* For K = 3–6 the silhouette is flat (0.303–0.327) and the inertia curve has no clear elbow.
* **K = 4 was chosen by judgement, and the rule was revised after seeing the data.** This is disclosed, not hidden:
  1. K = 4 keeps the A/E group.
  2. The other three clusters are exactly the K = 3 solution on the 22 wards without A and E, so the solution is nested.
  3. Only one cluster has two wards, against two at K = 5 and three at K = 6.
  4. Stability is moderate.

  K = 5 or K = 6 would be defensible alternatives. The K = 2 labels are exported as `cluster_k2_label`.

## Results (clusters ordered by mean sites per 100k)

| Cluster | Wards | Profile (vs 24-ward mean, ±0.5 SD) | Mean sites/100k | Mean silhouette |
|---|---|---|---|---|
| 1 | D, F/N, G/N, H/E, K/E, K/W, P/N, R/S (8) | Relatively lower UPHC & dispensary rates | 2.65 | 0.43 |
| 2 | F/S, H/W, P/S, R/C, R/N, L, M/E, M/W, N, S, T (11) | Relatively higher UPHC rates | 3.34 | 0.26 |
| 3 | B, C, G/S (3) | Relatively higher dispensary rates; no listed public hospital | 4.91 | 0.00 |
| 4 | A, E (2) | Relatively higher public-hospital & dispensary rates; no listed maternity home | 5.90 | 0.64 |

Original-scale centroids: `outputs/tables/ml_centroids_original_scale.csv`. Full profiles:
`outputs/tables/ml_cluster_profiles.csv`.

## Evaluation and robustness
* Overall silhouette is 0.316, which indicates weak to moderate structure. Cluster 3's members sit on the boundary
  (mean silhouette ≈ 0).
* Across random seeds the minimum ARI is 0.89, so some seeds reach a different local optimum even with 50 inits.
* Feature-set sensitivity at K = 4 (ARI against the final solution):
  * without log1p: 0.89
  * primary vs secondary care: 0.24
  * overall rate + density: 0.37

  The grouping depends on which provision dimensions are modelled.
* Reproducibility: the saved pipeline's `predict` on the modelling table reproduces the exported labels exactly
  (tested).

## Why no supervised model
No independent target exists, such as measured access, travel time or health outcomes. Labels built from these
same rates would make any "accuracy" circular. With 24 observations, a supervised model could not be validated
meaningfully anyway.

## Limitations
* Only 24 observations.
* Population is from 2011.
* Facility counts carry no capacity weighting.
* Some public hospitals are missing from the source layers.
* Internal metrics do not establish external or clinical validity.
* Cluster names are descriptive comparisons within this dataset only.

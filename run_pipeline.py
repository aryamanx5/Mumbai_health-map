"""Run the full pipeline.

Mumbai infrastructure: data -> indicators -> EDA -> exploratory K-Means -> Power BI exports -> boundary cross-check.
Clinical: Indian cardiovascular dataset -> cleaning -> Logistic Regression / Random Forest / ANN -> evaluation.
Power BI: report tables for both modules -> the MumbaiHealth.pbip project (written once; later runs keep edits).

Usage:  .venv/bin/python run_pipeline.py            (Windows: .venv\\Scripts\\python run_pipeline.py)
"""
import json
import time

from src import (boundary_check, build_data, clinical_pipeline, exploratory_analysis, export_reporting,
                 model_evaluation, powerbi_data, powerbi_project)


def main():
    t0 = time.time()
    data = build_data.run()
    print(f"[data] {data['summary']['master_records']} facility records -> {data['summary']['distinct_sites']} sites; "
          f"population checks passed: {data['summary']['population_checks_passed']}")
    eda, _ = exploratory_analysis.run(data["master"], data["sites"], data["ward_table"], data["wards"])
    print(f"[eda] {len(eda['figures'])} figures; city-wide {eda['city_rate_per_100k']} sites per 100k")
    ml = model_evaluation.run(data["ward_table"], data["wards"])
    print(f"[ward clusters] K={ml['config']['k']} silhouette={ml['config']['final_silhouette']} "
          f"sizes={ml['config']['final_sizes']} (exploratory, not one of the three classifiers)")
    kpis = export_reporting.run(data["master"], data["sites"], data["ward_table"], ml["assign"], ml["profiles"],
                                ml["k_table"])
    print(f"[powerbi] {json.dumps(kpis)}")
    bc, _ = boundary_check.run(data["master"])
    print(f"[boundaries] median IoU vs BMC_admin_wards {bc['median_iou']:.3f}; lowest {bc['min_iou_ward']} {bc['min_iou']:.3f}")
    clin = clinical_pipeline.run()
    print("[clinical] test ROC-AUC " + ", ".join(f"{m['short']} {m['test']['roc_auc']}" for m in clin["models"].values()))
    print(f"[powerbi] tables {json.dumps(powerbi_data.run())}; project: {powerbi_project.build()}")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

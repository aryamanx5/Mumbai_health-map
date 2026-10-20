"""Run the full pipeline: data -> indicators -> EDA -> K-Means -> Power BI exports.

Usage:  .venv/bin/python run_pipeline.py
"""
import json
import time

from src import build_data, exploratory_analysis, export_reporting, model_evaluation


def main():
    t0 = time.time()
    data = build_data.run()
    print(f"[data] {data['summary']['master_records']} facility records -> {data['summary']['distinct_sites']} sites; "
          f"population checks passed: {data['summary']['population_checks_passed']}")
    eda, _ = exploratory_analysis.run(data["master"], data["sites"], data["ward_table"], data["wards"])
    print(f"[eda] {len(eda['figures'])} figures; city-wide {eda['city_rate_per_100k']} sites per 100k")
    ml = model_evaluation.run(data["ward_table"], data["wards"])
    print(f"[ml] K={ml['config']['k']} silhouette={ml['config']['final_silhouette']} sizes={ml['config']['final_sizes']}")
    kpis = export_reporting.run(data["master"], data["sites"], data["ward_table"], ml["assign"], ml["profiles"],
                                ml["k_table"])
    print(f"[powerbi] {json.dumps(kpis)}")
    print(f"done in {time.time() - t0:.0f}s")


if __name__ == "__main__":
    main()

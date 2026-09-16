"""Run the whole project end to end.

    python run_pipeline.py            # generate data -> ETL -> analysis -> ML -> dashboard
    python run_pipeline.py --skip-generate   # reuse the workbook already in data/survey/
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
STEPS = [
    ("Generate survey workbook", "src/generate_survey_data.py"),
    ("ETL: workbook -> SQLite", "src/etl/pipeline.py"),
    ("Analysis: SQL questions + Plotly figures", "src/analysis/questions.py"),
    ("Predictive models", "src/ml/predict.py"),
    ("Interactive dashboard", "src/dashboard/build_dashboard.py"),
]

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-14s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-generate", action="store_true", help="reuse the existing survey workbook")
    args = ap.parse_args()
    for title, script in STEPS:
        if args.skip_generate and script.endswith("generate_survey_data.py"):
            continue
        print(f"\n=== {title} ===")
        subprocess.run([sys.executable, str(ROOT / script)], check=True, cwd=ROOT)
    print("\nDone. Open docs/index.html for the dashboard.")

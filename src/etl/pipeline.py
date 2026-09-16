"""ETL orchestration: workbook -> cleaned tables -> SQLite.

Run:  python src/etl/pipeline.py [--workbook PATH] [--db PATH]
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from etl.extract import extract  # noqa: E402
from etl.load import load  # noqa: E402
from etl.transform import transform, validate  # noqa: E402


def run(workbook: Path = C.SURVEY_XLSX, db_path: Path = C.DB_PATH) -> Path:
    t0 = time.perf_counter()
    raw = extract(workbook)
    tables = transform(raw)
    problems = validate(tables)
    if problems:
        raise RuntimeError("Data-quality gate failed: " + "; ".join(problems))
    load(tables, db_path, source=str(workbook.name))
    logging.getLogger("etl").info("pipeline finished in %.1fs -> %s", time.perf_counter() - t0, db_path)
    return db_path


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)-14s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workbook", type=Path, default=C.SURVEY_XLSX)
    ap.add_argument("--db", type=Path, default=C.DB_PATH)
    a = ap.parse_args()
    run(a.workbook, a.db)

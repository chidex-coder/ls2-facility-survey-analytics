"""Extract step: read every sheet of the survey workbook into DataFrames."""
from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

log = logging.getLogger("etl.extract")

EXPECTED_SHEETS = [
    "facilities", "facility_visits", "staffing_by_cadre", "absence_reasons",
    "cold_chain_equipment", "service_sessions", "trainings", "commodity_stock",
    "vaccine_stock",
]


def extract(workbook: Path) -> dict[str, pd.DataFrame]:
    if not workbook.exists():
        raise FileNotFoundError(f"Survey workbook not found: {workbook}")
    # keep_default_na=False stops pandas turning legitimate answers such as
    # "None" or "NA" into nulls; we normalise blanks ourselves in transform.
    sheets = pd.read_excel(workbook, sheet_name=None, keep_default_na=False, na_values=[""])
    missing = [s for s in EXPECTED_SHEETS if s not in sheets]
    if missing:
        raise ValueError(f"Workbook is missing sheets: {missing}")
    for name in EXPECTED_SHEETS:
        log.info("extracted %-22s %7d rows", name, len(sheets[name]))
    return {k: sheets[k] for k in EXPECTED_SHEETS}

"""Smoke tests for the ETL and analysis layers (run: python -m pytest -q)."""
import sqlite3
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import config as C  # noqa: E402
from etl.transform import transform, validate  # noqa: E402
from etl.extract import extract  # noqa: E402


def test_workbook_has_expected_sheets():
    tables = extract(C.SURVEY_XLSX)
    assert {"facility_visits", "commodity_stock", "staffing_by_cadre", "vaccine_stock"} <= set(tables)
    assert len(tables["facility_visits"]) == tables["facility_visits"]["visit_id"].nunique()


def test_transform_passes_quality_gate():
    tables = transform(extract(C.SURVEY_XLSX))
    assert validate(tables) == []
    v = tables["facility_visits"]
    assert v["readiness_score"].between(0, 100).all()
    assert v["attendance_rate"].dropna().between(0, 1).all()
    com = tables["commodity_stock"]
    assert set(com.loc[com.stocked_flag == 1, "stockout_flag"].dropna().unique()) <= {0, 1}


def test_warehouse_views_answer_queries():
    assert C.DB_PATH.exists(), "run src/etl/pipeline.py first"
    con = sqlite3.connect(C.DB_PATH)
    try:
        rate = pd.read_sql_query("SELECT AVG(stockout_flag) r FROM v_commodity WHERE stocked_flag=1", con).iloc[0].r
        assert 0 < rate < 1
        n = pd.read_sql_query("SELECT COUNT(*) n FROM v_visits", con).iloc[0].n
        assert n == 184 * 6
    finally:
        con.close()

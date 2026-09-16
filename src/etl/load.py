"""Load step: write the transformed tables into SQLite with indexes and views."""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

log = logging.getLogger("etl.load")

INDEXES = {
    "facility_visits": ["facility_id", "round_number", "lga", "facility_type"],
    "staffing_by_cadre": ["visit_id", "cadre"],
    "absence_reasons": ["visit_id", "reason"],
    "commodity_stock": ["visit_id", "commodity", "category"],
    "vaccine_stock": ["visit_id", "vaccine"],
    "service_sessions": ["visit_id", "service"],
    "cold_chain_equipment": ["visit_id"],
    "trainings": ["facility_id"],
}

VIEWS = {
    # One row per visit with the facility attributes joined in (the workhorse)
    "v_visits": """
        SELECT v.*, f.facility_name, f.latitude, f.longitude
        FROM facility_visits v JOIN facilities f USING (facility_id)
    """,
    # Commodity rows joined to visit/facility context
    "v_commodity": """
        SELECT c.*, v.facility_id, v.round_number, v.round_name, v.visit_date, v.lga, v.facility_type,
               v.urban_rural, v.security_risk_lga, v.requisition_submitted_last_cycle_flag,
               v.requisition_complete_on_time_flag, v.requisition_receipt_status, v.knows_min_stock_calculation
        FROM commodity_stock c JOIN facility_visits v USING (visit_id)
    """,
    "v_staffing": """
        SELECT s.*, v.facility_id, v.round_number, v.lga, v.facility_type, v.urban_rural,
               v.salary_paid_on_time_last_3_months_flag, v.roster_updated_this_week_flag, v.distance_to_lga_hq_km
        FROM staffing_by_cadre s JOIN facility_visits v USING (visit_id)
    """,
    "v_absence": """
        SELECT a.*, v.facility_id, v.round_number, v.lga, v.facility_type,
               v.salary_paid_on_time_last_3_months_flag, v.security_incident_reported_flag
        FROM absence_reasons a JOIN facility_visits v USING (visit_id)
    """,
    "v_vaccine": """
        SELECT x.*, v.facility_id, v.round_number, v.lga, v.facility_type, v.vaccine_fridge_functional_flag,
               v.cold_chain_interruption_since_last_visit_flag
        FROM vaccine_stock x JOIN facility_visits v USING (visit_id)
    """,
    "v_sessions": """
        SELECT s.*, v.facility_id, v.round_number, v.lga, v.facility_type, v.security_incident_reported_flag
        FROM service_sessions s JOIN facility_visits v USING (visit_id)
    """,
}


def load(tables: dict[str, pd.DataFrame], db_path: Path, source: str) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(db_path)
    try:
        for name, df in tables.items():
            df.to_sql(name, con, index=False, if_exists="replace")
            for col in INDEXES.get(name, []):
                con.execute(f'CREATE INDEX IF NOT EXISTS idx_{name}_{col} ON "{name}" ("{col}")')
            log.info("loaded %-24s %7d rows", name, len(df))
        for name, sql in VIEWS.items():
            con.execute(f"CREATE VIEW {name} AS {sql}")
        con.execute("""CREATE TABLE etl_log (run_at TEXT, source TEXT, table_name TEXT, row_count INTEGER)""")
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        con.executemany("INSERT INTO etl_log VALUES (?,?,?,?)",
                        [(now, source, n, len(df)) for n, df in tables.items()])
        con.commit()
    finally:
        con.close()

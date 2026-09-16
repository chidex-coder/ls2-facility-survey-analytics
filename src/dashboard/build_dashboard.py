"""Assemble the interactive HTML dashboard (docs/index.html).

The page is fully self-contained: the filtered-visit data, per-commodity /
per-cadre / per-vaccine tables, model predictions and the answered questions
are embedded as JSON, and every chart is recomputed client-side from the
active filters (LGA, facility type, setting, security-risk, round range,
readiness/risk sliders). Plotly.js is loaded from its CDN.

Run:  python src/dashboard/build_dashboard.py
"""
from __future__ import annotations

import json
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402

TEMPLATE = Path(__file__).with_name("template.html")
OUT = C.DOCS_DIR / "index.html"


def columnar(df: pd.DataFrame) -> dict:
    """Column-oriented JSON is ~40% smaller than records for these tables."""
    out = {}
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_float_dtype(s):
            out[col] = [None if pd.isna(v) else round(float(v), 4) for v in s]
        elif pd.api.types.is_integer_dtype(s) or str(s.dtype) == "Int64":
            out[col] = [None if pd.isna(v) else int(v) for v in s]
        elif pd.api.types.is_bool_dtype(s):
            out[col] = [bool(v) for v in s]
        else:
            out[col] = [None if pd.isna(v) else v for v in s.astype(object)]
    return out


def build_payload() -> dict:
    con = sqlite3.connect(C.DB_PATH)
    visits = pd.read_sql_query("""
        SELECT visit_id, facility_id, facility_name, lga, ward, facility_type, urban_rural, security_risk_lga, round_number, round_name,
               visit_date, latitude, longitude, hours_of_operation, days_open_per_week, facility_open_on_arrival_flag AS open_flag, wait_minutes,
               reason_closed_on_arrival, can_refer_emergencies_flag AS refer_flag, emergency_transport_available_2wks_flag AS transport_flag,
               total_health_workers, permanent_health_workers, male_health_workers, female_health_workers, doctors, nurses_midwives,
               permanent_scheduled_today, permanent_present_today, attendance_rate, stockout_rate, tracer_stockout_rate, below_min_rate,
               commodities_stocked, commodities_stocked_out, vaccine_availability_rate, vaccines_in_stock, vaccines_tracked,
               session_completion_rate, cce_functionality_rate, readiness_score, readiness_band,
               salary_paid_on_time_last_3_months_flag AS salary_on_time, salary_delay_length, salary_issues_past_6_months_flag AS salary_issues,
               staff_leave_facility_for_salary_frequency AS leave_for_salary, has_duty_roster_flag AS has_roster, roster_updated_this_week_flag AS roster_updated,
               maintains_attendance_register_flag AS has_register, requisition_frequency, requisition_submitted_last_cycle_flag AS req_submitted,
               requisition_complete_on_time_flag AS req_on_time, requisition_receipt_status, requisition_system, delivery_documentation_provided_flag AS documented,
               knows_min_stock_calculation, has_cold_chain_equipment_flag AS has_cce, vaccine_fridge_functional_flag AS fridge_ok,
               cold_chain_interruption_since_last_visit_flag AS cc_interruption, cold_chain_interruption_reason, vaccine_stock_status,
               vaccines_available_during_sessions_flag AS vac_at_sessions, immunization_sessions_all_conducted_flag AS imm_sessions_ok,
               security_incident_reported_flag AS security_incident, staff_trained_past_2_years_flag AS trained, distance_to_lga_hq_km
        FROM v_visits ORDER BY facility_id, round_number""", con)
    commodities = pd.read_sql_query("""
        SELECT visit_id, commodity, category, stockout_flag, stockout_duration, stockout_reason, below_min_stock_flag, supplier,
               stock_balance, minimum_stock_level, quantity_received, physically_verified_flag AS verified
        FROM commodity_stock WHERE stocked_flag=1""", con)
    staffing = pd.read_sql_query("""
        SELECT visit_id, cadre, total_staff, permanent, adhoc_a, adhoc_b, volunteer, permanent_scheduled_today AS scheduled,
               permanent_present_today AS present, present_today AS all_present FROM staffing_by_cadre""", con)
    absences = pd.read_sql_query("SELECT visit_id, cadre, reason, staff_count FROM absence_reasons", con)
    vaccines = pd.read_sql_query("SELECT visit_id, vaccine, in_stock_flag, doses_used, doses_received, current_balance_doses, most_dispensed_flag, reason_most_dispensed FROM vaccine_stock", con)
    sessions = pd.read_sql_query("SELECT visit_id, service, offered_flag, all_conducted_flag, reason_not_conducted, dedicated_days FROM service_sessions", con)
    cce = pd.read_sql_query("SELECT visit_id, cce_type, available_flag, functional_flag FROM cold_chain_equipment", con)
    trainings = pd.read_sql_query("SELECT facility_id, training FROM trainings", con)
    con.close()

    ml_dir = C.OUTPUT_DIR / "ml"
    facility_pred = pd.read_csv(ml_dir / "facility_predictions.csv")
    commodity_pred = pd.read_csv(ml_dir / "commodity_stockout_predictions.csv")
    metrics = json.loads((ml_dir / "metrics.json").read_text())
    ml_figs = json.loads((ml_dir / "figures.json").read_text())
    analysis = json.loads((C.OUTPUT_DIR / "analysis_results.json").read_text())
    for a in analysis:
        a.pop("figure_json", None); a.pop("data", None)

    return {
        "generated": date.today().isoformat(),
        "meta": {"lgas": sorted(visits.lga.unique()), "facility_types": C.FACILITY_TYPES, "rounds": visits[["round_number", "round_name"]].drop_duplicates().sort_values("round_number").to_dict(orient="records"),
                 "cadres": C.CADRES, "commodities": [c[0] for c in C.COMMODITIES], "categories": sorted({c[1] for c in C.COMMODITIES}), "vaccines": C.VACCINES, "services": C.SERVICES},
        "visits": columnar(visits), "commodities": columnar(commodities), "staffing": columnar(staffing), "absences": columnar(absences),
        "vaccines": columnar(vaccines), "sessions": columnar(sessions), "cce": columnar(cce), "trainings": columnar(trainings),
        "facility_pred": columnar(facility_pred), "commodity_pred": columnar(commodity_pred), "ml": metrics, "ml_figs": ml_figs, "analysis": analysis,
    }


def main():
    payload = build_payload()
    html = TEMPLATE.read_text()
    data_json = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/", data_json)
    C.DOCS_DIR.mkdir(exist_ok=True)
    OUT.write_text(html)
    fig_out = C.DOCS_DIR / "figures"
    if fig_out.exists():
        shutil.rmtree(fig_out)
    shutil.copytree(C.FIGURE_DIR, fig_out)
    print(f"dashboard written to {OUT} ({OUT.stat().st_size/1e6:.1f} MB); {len(list(fig_out.glob('*.html')))} figures copied")


if __name__ == "__main__":
    main()

"""Transform step: clean, standardise and derive analysis-ready tables.

Responsibilities
* normalise Yes/No answers to 1/0 integer flags (keeping the original text)
* parse dates, coerce numerics, trim whitespace, drop exact duplicates
* explode multi-select answers (stored as ';'-separated text) into long tables
* derive per-visit indicators: attendance rate, stock-out rate, readiness score
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

log = logging.getLogger("etl.transform")

YES_NO_COLUMNS = [
    "facility_open_on_arrival", "can_refer_emergencies", "emergency_transport_available_2wks",
    "has_cold_chain_equipment", "vaccine_fridge_functional", "cold_chain_interruption_since_last_visit",
    "staff_trained_past_2_years", "has_dedicated_service_days", "immunization_sessions_all_conducted",
    "maintains_attendance_register", "attendance_register_updated_daily", "has_duty_roster",
    "roster_updated_this_week", "salary_paid_on_time_last_3_months", "salary_issues_past_6_months",
    "stocks_essential_medicines", "requisition_submitted_last_cycle", "requisition_complete_on_time",
    "delivery_documentation_provided", "vaccines_available_during_sessions", "security_incident_reported",
]

MULTI_SELECT_COLUMNS = {
    "services_provided": "visit_services",
    "cce_types_available": "visit_cce_types",
    "salary_issue_types": "visit_salary_issues",
    "requisition_commodity_types": "visit_requisition_types",
    "commodity_sources": "visit_commodity_sources",
    "vaccine_sources": "visit_vaccine_sources",
    "vaccines_most_dispensed_this_week": "visit_vaccines_dispensed",
}

TRACER_MNCH = ["Oxytocin", "Misoprostol", "Magnesium Sulphate Injection", "Amoxicillin Dispersible",
               "ORS", "Zinc", "Chlorhexidine Gel", "Artemether + Lumefantrine"]


def _flag(series: pd.Series) -> pd.Series:
    return series.map({"Yes": 1, "No": 0}).astype("Int64")


def _clean_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].astype("string").str.strip()
        df[col] = df[col].mask(df[col].isin(["", "nan", "NaN"]))
    before = len(df)
    df = df.drop_duplicates()
    if len(df) != before:
        log.warning("dropped %d duplicate rows", before - len(df))
    return df


def transform(raw: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {k: _clean_frame(v) for k, v in raw.items()}

    visits = out["facility_visits"]
    visits["visit_date"] = pd.to_datetime(visits["visit_date"]).dt.date.astype(str)
    visits["wait_minutes"] = pd.to_numeric(visits["wait_minutes"], errors="coerce").fillna(0).astype(int)
    for col in YES_NO_COLUMNS:
        visits[f"{col}_flag"] = _flag(visits[col])

    # ---- multi-select answers -> long tables ----
    for col, table in MULTI_SELECT_COLUMNS.items():
        long = (visits[["visit_id", col]].dropna()
                .assign(value=lambda d: d[col].str.split(";"))
                .explode("value")[["visit_id", "value"]]
                .rename(columns={"value": col.replace("_types", "").replace("_provided", "")}))
        long.columns = ["visit_id", "value"]
        out[table] = long.reset_index(drop=True)

    # ---- staffing derived metrics ----
    staff = out["staffing_by_cadre"]
    num_cols = ["total_staff", "permanent", "adhoc_a", "adhoc_b", "volunteer", "scheduled_morning",
                "scheduled_afternoon", "scheduled_evening", "scheduled_off", "scheduled_leave",
                "present_today", "permanent_present_today", "permanent_absent_unscheduled"]
    staff[num_cols] = staff[num_cols].apply(pd.to_numeric, errors="coerce").fillna(0).astype(int)
    staff["permanent_scheduled_today"] = staff["scheduled_morning"] + staff["scheduled_afternoon"] + staff["scheduled_evening"]
    staff["attendance_rate"] = np.where(staff["permanent_scheduled_today"] > 0,
                                        staff["permanent_present_today"] / staff["permanent_scheduled_today"], np.nan)
    per_visit_staff = staff.groupby("visit_id").agg(
        permanent_scheduled_today=("permanent_scheduled_today", "sum"),
        permanent_present_today=("permanent_present_today", "sum"),
        staff_present_today=("present_today", "sum"),
        nurses_midwives=("permanent", lambda s: int(s[staff.loc[s.index, "cadre"] == "Nurse/Midwife"].sum())),
        doctors=("permanent", lambda s: int(s[staff.loc[s.index, "cadre"] == "Medical Officer"].sum())),
    ).reset_index()
    per_visit_staff["attendance_rate"] = (per_visit_staff["permanent_present_today"]
                                          / per_visit_staff["permanent_scheduled_today"].replace(0, np.nan))
    per_visit_staff["absenteeism_rate"] = 1 - per_visit_staff["attendance_rate"]

    # ---- commodity derived metrics ----
    com = out["commodity_stock"]
    for col in ["quantity_received", "minimum_stock_level", "stock_balance"]:
        com[col] = pd.to_numeric(com[col], errors="coerce")
    com["stocked_flag"] = (com["facility_stocks_item"] == "Yes").astype(int)
    com["stockout_flag"] = np.where(com["stocked_flag"] == 1,
                                    (com["stockout_duration"] != "No stock-out").astype(int), np.nan)
    com["stockout_days_est"] = com["stockout_duration"].map(
        {"No stock-out": 0, "Less than 1 week": 3, "1 to 4 weeks": 14, "More than 4 weeks": 35})
    com["zero_balance_flag"] = np.where(com["stocked_flag"] == 1, (com["stock_balance"].fillna(0) <= 0).astype(int), np.nan)
    com["below_min_stock_flag"] = np.where(com["minimum_stock_level"].notna() & (com["stocked_flag"] == 1),
                                           (com["stock_balance"] < com["minimum_stock_level"]).astype(float), np.nan)
    com["stock_adequacy_ratio"] = com["stock_balance"] / com["minimum_stock_level"].replace(0, np.nan)
    com["is_tracer_mnch"] = com["commodity"].isin(TRACER_MNCH).astype(int)
    com["physically_verified_flag"] = _flag(com["physically_verified"])
    stocked = com[com["stocked_flag"] == 1]
    per_visit_com = stocked.groupby("visit_id").agg(
        commodities_stocked=("commodity", "count"),
        commodities_stocked_out=("stockout_flag", "sum"),
        commodities_below_min=("below_min_stock_flag", "sum"),
        commodities_with_min_known=("below_min_stock_flag", "count"),
        tracer_stockouts=("stockout_flag", lambda s: s[stocked.loc[s.index, "is_tracer_mnch"] == 1].sum()),
        tracer_stocked=("is_tracer_mnch", "sum"),
    ).reset_index()
    per_visit_com["stockout_rate"] = per_visit_com["commodities_stocked_out"] / per_visit_com["commodities_stocked"]
    per_visit_com["tracer_stockout_rate"] = per_visit_com["tracer_stockouts"] / per_visit_com["tracer_stocked"].replace(0, np.nan)
    per_visit_com["below_min_rate"] = per_visit_com["commodities_below_min"] / per_visit_com["commodities_with_min_known"].replace(0, np.nan)

    # ---- vaccine derived metrics ----
    vac = out["vaccine_stock"]
    for col in ["opening_balance_doses", "doses_received", "current_balance_doses", "doses_used"]:
        vac[col] = pd.to_numeric(vac[col], errors="coerce")
    vac["in_stock_flag"] = _flag(vac["in_stock"])
    vac["physically_verified_flag"] = _flag(vac["physically_verified"])
    vac["most_dispensed_flag"] = _flag(vac["most_dispensed_this_week"])
    per_visit_vac = vac.groupby("visit_id").agg(
        vaccines_tracked=("vaccine", "count"), vaccines_in_stock=("in_stock_flag", "sum"),
        vaccine_doses_used=("doses_used", "sum"),
    ).reset_index()
    per_visit_vac["vaccine_availability_rate"] = per_visit_vac["vaccines_in_stock"] / per_visit_vac["vaccines_tracked"]

    # ---- sessions ----
    ses = out["service_sessions"]
    ses["offered_flag"] = _flag(ses["offered"])
    ses["all_conducted_flag"] = _flag(ses["all_planned_sessions_conducted"])
    per_visit_ses = ses.groupby("visit_id").agg(
        services_offered=("offered_flag", "sum"),
        services_with_sessions=("all_conducted_flag", "count"),
        services_all_conducted=("all_conducted_flag", "sum"),
    ).reset_index()
    per_visit_ses["session_completion_rate"] = per_visit_ses["services_all_conducted"] / per_visit_ses["services_with_sessions"].replace(0, np.nan)

    cce = out["cold_chain_equipment"]
    cce["available_flag"] = _flag(cce["available"])
    cce["functional_flag"] = _flag(cce["functional"])
    per_visit_cce = cce.groupby("visit_id").agg(cce_available=("available_flag", "sum"), cce_functional=("functional_flag", "sum")).reset_index()
    per_visit_cce["cce_functionality_rate"] = per_visit_cce["cce_functional"] / per_visit_cce["cce_available"].replace(0, np.nan)

    # ---- merge into the visit-level fact table ----
    visits = (visits.merge(per_visit_staff, on="visit_id", how="left")
                    .merge(per_visit_com, on="visit_id", how="left")
                    .merge(per_visit_vac, on="visit_id", how="left")
                    .merge(per_visit_ses, on="visit_id", how="left")
                    .merge(per_visit_cce, on="visit_id", how="left"))
    visits = visits.merge(out["facilities"][["facility_id", "lga", "ward", "facility_type", "urban_rural",
                                            "security_risk_lga", "distance_to_lga_hq_km"]], on="facility_id", how="left")

    # Composite readiness score (0-100): equal-weight average of six pillars
    pillars = pd.DataFrame({
        "open": visits["facility_open_on_arrival_flag"].astype(float),
        "attendance": visits["attendance_rate"],
        "stock": 1 - visits["stockout_rate"],
        "vaccines": visits["vaccine_availability_rate"].fillna(visits["vaccine_availability_rate"].mean()),
        "sessions": visits["session_completion_rate"],
        "cold_chain": visits["cce_functionality_rate"].fillna(0),
    })
    visits["readiness_score"] = (pillars.mean(axis=1, skipna=True) * 100).round(1)
    visits["readiness_band"] = pd.cut(visits["readiness_score"], [-1, 50, 65, 80, 101],
                                      labels=["Critical", "Weak", "Fair", "Strong"]).astype(str)
    out["facility_visits"] = visits

    for name, df in out.items():
        log.info("transformed %-24s %7d rows x %3d cols", name, len(df), df.shape[1])
    return out


def validate(tables: dict[str, pd.DataFrame]) -> list[str]:
    """Light data-quality gate; returns a list of problems (empty == pass)."""
    problems = []
    v = tables["facility_visits"]
    if v["visit_id"].duplicated().any():
        problems.append("duplicate visit_id in facility_visits")
    if not set(tables["staffing_by_cadre"]["visit_id"]).issubset(set(v["visit_id"])):
        problems.append("staffing rows reference unknown visits")
    if not set(tables["commodity_stock"]["visit_id"]).issubset(set(v["visit_id"])):
        problems.append("commodity rows reference unknown visits")
    bad_att = v["attendance_rate"].dropna()
    if ((bad_att < 0) | (bad_att > 1)).any():
        problems.append("attendance_rate outside [0,1]")
    if (v["readiness_score"].isna()).any():
        problems.append("readiness_score has nulls")
    return problems

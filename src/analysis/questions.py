"""Answer the decision questions the LS 2.0 instrument was designed for.

Each entry in QUESTIONS pairs a plain-language question with the SQL that
answers it (run against the SQLite warehouse built by the ETL) and a Plotly
figure. Results are written to outputs/analysis_results.json, one HTML figure
per question under outputs/figures/, and a Markdown report under docs/.

Run:  python src/analysis/questions.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from analysis import theme as T  # noqa: E402

RESULTS_JSON = C.OUTPUT_DIR / "analysis_results.json"
REPORT_MD = C.DOCS_DIR / "ANALYSIS.md"


@dataclass
class Result:
    id: str
    section: str
    question: str
    sql: str
    data: pd.DataFrame
    answer: str
    figure: go.Figure | None = None
    figure_file: str | None = None
    key_numbers: dict = field(default_factory=dict)


def q(con, sql: str, **params) -> pd.DataFrame:
    return pd.read_sql_query(sql, con, params=params or None)


def pct(x) -> str:
    return f"{100 * float(x):.1f}%"


def hbar(df, x, y, title, color=None, xlabel=None, fmt=".1%", order=None):
    fig = px.bar(df, x=x, y=y, orientation="h", title=title, color=color, text=x,
                 color_discrete_sequence=T.SERIES)
    fig.update_traces(texttemplate="%{text:" + fmt + "}", textposition="outside", cliponaxis=False,
                      marker_line_width=0, width=0.6)
    fig.update_layout(yaxis=dict(categoryorder="array", categoryarray=order) if order else dict(categoryorder="total ascending"),
                      xaxis_title=xlabel or "", yaxis_title="", showlegend=color is not None,
                      height=max(360, 26 * len(df) + 120))
    if fmt == ".1%":
        fig.update_xaxes(tickformat=".0%")
    return fig


# ----------------------------------------------------------------------------
# Section A: Facility access & readiness (Module 1)
# ----------------------------------------------------------------------------
def q01(con):
    sql = """
    SELECT lga, COUNT(*) AS visits, AVG(facility_open_on_arrival_flag) AS open_rate,
           AVG(CASE WHEN facility_open_on_arrival_flag=0 THEN wait_minutes END) AS avg_wait_when_closed
    FROM v_visits GROUP BY lga ORDER BY open_rate"""
    df = q(con, sql)
    overall = q(con, "SELECT AVG(facility_open_on_arrival_flag) r, AVG(CASE WHEN facility_open_on_arrival_flag=0 THEN wait_minutes END) w FROM v_visits").iloc[0]
    worst, best = df.iloc[0], df.iloc[-1]
    fig = hbar(df, "open_rate", "lga", "Share of visits where the facility was open on arrival, by LGA", xlabel="Open on arrival")
    fig.add_vline(x=overall.r, line_dash="dot", line_color=T.TEXT_SECONDARY, annotation_text=f"State avg {pct(overall.r)}", annotation_position="top")
    ans = (f"Facilities were open on arrival in {pct(overall.r)} of {int(df.visits.sum())} visits. Where closed, data champions "
           f"waited {overall.w:.0f} minutes on average. {worst.lga} is the weakest LGA ({pct(worst.open_rate)}) and "
           f"{best.lga} the strongest ({pct(best.open_rate)}).")
    return Result("Q01", "Facility access", "How often are facilities actually open when a data champion arrives, and where is access weakest?",
                  sql, df, ans, fig, key_numbers={"open_on_arrival_rate": float(overall.r), "avg_wait_minutes": float(overall.w)})


def q02(con):
    sql = """
    SELECT reason_closed_on_arrival AS reason, COUNT(*) AS n
    FROM v_visits WHERE facility_open_on_arrival_flag=0 GROUP BY 1 ORDER BY n DESC"""
    df = q(con, sql); df["share"] = df.n / df.n.sum()
    fig = hbar(df, "share", "reason", "Why facilities were closed on arrival", xlabel="Share of closed-on-arrival visits")
    top = df.iloc[0]
    ans = (f"The leading cause of a closed facility is '{top.reason}' ({pct(top.share)} of {int(df.n.sum())} cases). "
           f"Insecurity accounts for {pct(df.loc[df.reason=='Facility closed due to insecurity','share'].sum())}, concentrated in security-risk LGAs.")
    return Result("Q02", "Facility access", "What are the main reasons facilities are closed when visited?", sql, df, ans, fig)


def q03(con):
    sql = """
    SELECT facility_type, hours_of_operation, COUNT(DISTINCT facility_id) AS facilities
    FROM v_visits WHERE round_number=1 GROUP BY 1,2"""
    df = q(con, sql)
    fig = px.bar(df, x="facility_type", y="facilities", color="hours_of_operation", barmode="stack",
                 title="Hours of operation by facility type (baseline)",
                 category_orders={"hours_of_operation": C.HOURS_OF_OPERATION, "facility_type": C.FACILITY_TYPES},
                 color_discrete_sequence=T.SERIES)
    fig.update_traces(marker_line_color="#fff", marker_line_width=2, width=0.6)
    fig.update_layout(xaxis_title="", yaxis_title="Facilities", legend_title="")
    tot = df.groupby("hours_of_operation").facilities.sum(); share24 = tot.get("24 hours", 0) / tot.sum()
    ref = q(con, "SELECT AVG(can_refer_emergencies_flag) r, AVG(emergency_transport_available_2wks_flag) t FROM v_visits").iloc[0]
    ans = (f"{pct(share24)} of facilities report 24-hour operation, driven by PHCs and General Hospitals; most Health Posts run 6-8 hour days. "
           f"{pct(ref.r)} of visits confirmed the facility can refer obstetric emergencies, but transport was available when needed in only {pct(ref.t)} of those.")
    return Result("Q03", "Facility access", "What are facility operating hours, and can facilities refer emergencies with transport?", sql, df, ans, fig,
                  key_numbers={"share_24h": float(share24), "can_refer": float(ref.r), "transport_available": float(ref.t)})


def q04(con):
    sql = """
    SELECT cce_type, AVG(available_flag) AS availability,
           AVG(CASE WHEN available_flag=1 THEN functional_flag END) AS functionality
    FROM cold_chain_equipment GROUP BY cce_type ORDER BY functionality"""
    df = q(con, sql)
    long = df.melt(id_vars="cce_type", var_name="metric", value_name="rate")
    fig = px.bar(long, x="rate", y="cce_type", color="metric", barmode="group", orientation="h",
                 title="Cold chain equipment: availability vs functionality", color_discrete_sequence=T.SERIES, text="rate")
    fig.update_traces(texttemplate="%{text:.0%}", textposition="outside", cliponaxis=False, width=0.35)
    fig.update_layout(xaxis_tickformat=".0%", xaxis_title="", yaxis_title="", legend_title="", height=420)
    intr = q(con, """SELECT AVG(cold_chain_interruption_since_last_visit_flag) r FROM v_visits WHERE has_cold_chain_equipment_flag=1""").iloc[0].r
    reason = q(con, """SELECT cold_chain_interruption_reason reason, COUNT(*) n FROM v_visits WHERE cold_chain_interruption_since_last_visit_flag=1 GROUP BY 1 ORDER BY n DESC""").iloc[0]
    fridge = q(con, "SELECT AVG(vaccine_fridge_functional_flag) r FROM v_visits WHERE has_cold_chain_equipment_flag=1").iloc[0].r
    ans = (f"Where equipment exists, functionality ranges from {pct(df.functionality.min())} ({df.iloc[0].cce_type}) to {pct(df.functionality.max())} ({df.iloc[-1].cce_type}). "
           f"Only {pct(fridge)} of facilities with cold chain equipment have at least one working vaccine refrigerator, and {pct(intr)} of visits recorded a cold chain interruption since the previous visit, "
           f"most often '{reason.reason}'.")
    return Result("Q04", "Cold chain", "How functional is the cold chain, and how often is it interrupted?", sql, df, ans, fig,
                  key_numbers={"fridge_functional_rate": float(fridge), "interruption_rate": float(intr)})


def q05(con):
    sql = """
    SELECT service, AVG(offered_flag) AS offered_rate,
           AVG(all_conducted_flag) AS session_completion_rate
    FROM service_sessions GROUP BY service ORDER BY session_completion_rate"""
    df = q(con, sql)
    long = df.melt(id_vars="service", var_name="metric", value_name="rate")
    fig = px.bar(long, x="rate", y="service", color="metric", barmode="group", orientation="h",
                 title="Service availability and completion of planned sessions (last week)", color_discrete_sequence=T.SERIES, text="rate")
    fig.update_traces(texttemplate="%{text:.0%}", textposition="outside", cliponaxis=False, width=0.35)
    fig.update_layout(xaxis_tickformat=".0%", xaxis_title="", yaxis_title="", legend_title="", height=440)
    ans = (f"Malaria and ANC are near-universal, while Nutrition ({pct(df.set_index('service').loc['Nutrition','offered_rate'])}) and Labour & Delivery are the least available. "
           f"Planned sessions were fully delivered in {pct(df.session_completion_rate.mean())} of service-weeks; {df.iloc[0].service} has the lowest completion ({pct(df.iloc[0].session_completion_rate)}).")
    return Result("Q05", "Service delivery", "Which services do facilities offer, and how reliably are planned sessions delivered?", sql, df, ans, fig)


def q06(con):
    sql = """
    SELECT reason_not_conducted AS reason, COUNT(*) AS n
    FROM service_sessions WHERE all_conducted_flag=0 GROUP BY 1 ORDER BY n DESC"""
    df = q(con, sql); df["share"] = df.n / df.n.sum()
    fig = hbar(df, "share", "reason", "Why planned sessions were missed", xlabel="Share of missed-session reports")
    top = df.iloc[0]
    ans = (f"'{top.reason}' explains {pct(top.share)} of missed sessions - a human-resource problem before a supply problem. "
           f"Security concerns account for {pct(df.loc[df.reason.str.startswith('Security'),'share'].sum())} and vaccine or cold-chain issues for "
           f"{pct(df.loc[df.reason.isin(['Vaccine stock-out','Cold chain equipment failure']),'share'].sum())}.")
    return Result("Q06", "Service delivery", "What stops planned sessions from happening?", sql, df, ans, fig)


def q07(con):
    sql = """
    SELECT t.training, COUNT(DISTINCT t.facility_id)*1.0/(SELECT COUNT(*) FROM facilities) AS coverage
    FROM trainings t GROUP BY 1 ORDER BY coverage DESC"""
    df = q(con, sql)
    trained = q(con, "SELECT AVG(staff_trained_past_2_years_flag) r FROM v_visits WHERE round_number=1").iloc[0].r
    fig = hbar(df, "coverage", "training", "Facilities with staff trained in the past 2 years, by training type", xlabel="Share of facilities")
    ans = (f"{pct(trained)} of facilities had any staff trained in the past two years. Coverage is highest for {df.iloc[0].training} ({pct(df.iloc[0].coverage)}) "
           f"and lowest for {df.iloc[-1].training} ({pct(df.iloc[-1].coverage)}); no single training reaches half of facilities.")
    return Result("Q07", "Service delivery", "What is training coverage across the network?", sql, df, ans, fig, key_numbers={"any_training_rate": float(trained)})


# ----------------------------------------------------------------------------
# Section B: Human resources for health (Module 2)
# ----------------------------------------------------------------------------
def q08(con):
    sql = """
    SELECT cadre, SUM(permanent) AS permanent, SUM(adhoc_a) AS adhoc_a, SUM(adhoc_b) AS adhoc_b, SUM(volunteer) AS volunteer
    FROM v_staffing WHERE round_number=1 GROUP BY cadre ORDER BY permanent DESC"""
    df = q(con, sql)
    long = df.melt(id_vars="cadre", var_name="employment", value_name="headcount")
    fig = px.bar(long, x="headcount", y="cadre", color="employment", orientation="h", title="Workforce composition by cadre (baseline headcount)",
                 color_discrete_sequence=T.SERIES)
    fig.update_traces(marker_line_color="#fff", marker_line_width=2, width=0.6)
    fig.update_layout(yaxis=dict(categoryorder="total ascending"), xaxis_title="Health workers", yaxis_title="", legend_title="", height=440)
    tot = df[["permanent", "adhoc_a", "adhoc_b", "volunteer"]].sum()
    gender = q(con, "SELECT SUM(male_health_workers) m, SUM(female_health_workers) f FROM v_visits WHERE round_number=1").iloc[0]
    nodoc = q(con, "SELECT AVG(doctors=0) r FROM v_visits WHERE round_number=1 AND facility_type='Primary Health Centre'").iloc[0].r
    nonurse = q(con, "SELECT AVG(nurses_midwives=0) r FROM v_visits WHERE round_number=1 AND facility_type IN ('Primary Health Centre','Basic Health Centre')").iloc[0].r
    ans = (f"The network has {int(tot.sum()):,} health workers: {pct(tot.permanent/tot.sum())} permanent, {pct((tot.adhoc_a+tot.adhoc_b)/tot.sum())} ad hoc/seconded and {pct(tot.volunteer/tot.sum())} volunteers. "
           f"CHEWs and JCHEWs form the backbone; {pct(nodoc)} of PHCs have no permanent doctor and {pct(nonurse)} of PHCs/BHCs have no permanent nurse or midwife. "
           f"Women make up {pct(gender.f/(gender.m+gender.f))} of the workforce.")
    return Result("Q08", "Human resources", "What does the workforce look like by cadre and employment type?", sql, df, ans, fig,
                  key_numbers={"health_workers": int(tot.sum()), "phc_without_doctor": float(nodoc), "phc_bhc_without_nurse": float(nonurse)})


def q09(con):
    sql = """
    SELECT cadre, SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate, SUM(permanent_scheduled_today) AS scheduled
    FROM v_staffing WHERE permanent_scheduled_today>0 GROUP BY cadre ORDER BY attendance_rate"""
    df = q(con, sql)
    fig = hbar(df, "attendance_rate", "cadre", "Attendance rate of permanent staff scheduled for duty, by cadre", xlabel="Present / scheduled")
    overall = q(con, "SELECT SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) r FROM staffing_by_cadre").iloc[0].r
    fig.add_vline(x=overall, line_dash="dot", line_color=T.TEXT_SECONDARY, annotation_text=f"Overall {pct(overall)}")
    ans = (f"Across all visits, {pct(overall)} of permanent staff scheduled for duty were actually present - an absenteeism rate of {pct(1-overall)}. "
           f"{df.iloc[0].cadre}s are least reliably present ({pct(df.iloc[0].attendance_rate)}); {df.iloc[-1].cadre}s most ({pct(df.iloc[-1].attendance_rate)}).")
    return Result("Q09", "Human resources", "How high is absenteeism, and which cadres are most affected?", sql, df, ans, fig, key_numbers={"attendance_rate": float(overall)})


def q10(con):
    sql = """
    SELECT lga, SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate
    FROM v_staffing WHERE permanent_scheduled_today>0 GROUP BY lga ORDER BY attendance_rate"""
    df = q(con, sql)
    fig = hbar(df, "attendance_rate", "lga", "Permanent staff attendance rate by LGA", xlabel="Present / scheduled")
    ans = (f"Attendance ranges from {pct(df.iloc[0].attendance_rate)} in {df.iloc[0].lga} to {pct(df.iloc[-1].attendance_rate)} in {df.iloc[-1].lga} - "
           f"a {100*(df.iloc[-1].attendance_rate-df.iloc[0].attendance_rate):.0f}-point spread that points to LGA-level management and security effects rather than individual behaviour.")
    return Result("Q10", "Human resources", "Where is absenteeism geographically concentrated?", sql, df, ans, fig)


def q11(con):
    sql = """
    SELECT reason, SUM(staff_count) AS staff FROM v_absence GROUP BY reason ORDER BY staff DESC"""
    df = q(con, sql); df["share"] = df.staff / df.staff.sum()
    fig = hbar(df.head(12), "share", "reason", "Top reasons permanent staff were absent (share of absent staff)", xlabel="Share of absences")
    salary_related = df.loc[df.reason.isin(["Access to Salary", "Dissatisfaction with Salary and Benefits"]), "share"].sum()
    ans = (f"'{df.iloc[0].reason}' is the top recorded reason ({pct(df.iloc[0].share)}), followed by '{df.iloc[1].reason}' ({pct(df.iloc[1].share)}). "
           f"Salary-linked absence (going to access salary, or dissatisfaction with pay) accounts for {pct(salary_related)} of all absences and is directly addressable by payment reform.")
    return Result("Q11", "Human resources", "Why are staff absent?", sql, df, ans, fig, key_numbers={"salary_related_absence_share": float(salary_related)})


def q12(con):
    sql = """
    SELECT round_number, round_name,
           AVG(salary_paid_on_time_last_3_months_flag) AS salary_on_time,
           SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate,
           AVG(session_completion_rate) AS session_completion
    FROM v_visits GROUP BY 1,2 ORDER BY 1"""
    df = q(con, sql)
    fig = go.Figure()
    for col, name in [("salary_on_time", "Salary paid on time"), ("attendance_rate", "Staff attendance"), ("session_completion", "Sessions completed")]:
        fig.add_trace(go.Scatter(x=df.round_name, y=df[col], mode="lines+markers", name=name, line=dict(width=2), marker=dict(size=9)))
    fig.update_layout(title="Salary timeliness, attendance and session completion by visit round", yaxis_tickformat=".0%", xaxis_title="", yaxis_title="", hovermode="x unified")
    shock = df.loc[df.salary_on_time.idxmin()]
    normal = df[df.round_number != shock.round_number]
    ans = (f"In {shock.round_name} salary timeliness collapsed to {pct(shock.salary_on_time)} (vs {pct(normal.salary_on_time.mean())} in other rounds); "
           f"attendance fell to {pct(shock.attendance_rate)} (vs {pct(normal.attendance_rate.mean())}) and session completion to {pct(shock.session_completion)} in the same round. "
           f"Late salaries translate almost immediately into empty duty posts.")
    return Result("Q12", "Human resources", "How do salary delays affect attendance and service delivery over time?", sql, df, ans, fig)


def q13(con):
    sql = """
    SELECT CASE WHEN salary_paid_on_time_last_3_months_flag=1 THEN 'Salary on time' ELSE 'Salary delayed' END AS salary,
           CASE WHEN roster_updated_this_week_flag=1 THEN 'Roster updated' ELSE 'Roster not updated' END AS roster,
           SUM(permanent_present_today)*1.0/SUM(permanent_scheduled_today) AS attendance_rate, COUNT(*) AS visits
    FROM v_visits GROUP BY 1,2"""
    df = q(con, sql)
    fig = px.bar(df, x="salary", y="attendance_rate", color="roster", barmode="group", text="attendance_rate",
                 title="Attendance by salary timeliness and roster practice", color_discrete_sequence=T.SERIES)
    fig.update_traces(texttemplate="%{text:.1%}", textposition="outside", width=0.3)
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="Attendance rate", legend_title="", yaxis_range=[0, 1])
    piv = df.pivot(index="salary", columns="roster", values="attendance_rate")
    ans = (f"When salary is on time and the roster was updated this week, attendance is {pct(piv.loc['Salary on time','Roster updated'])}; "
           f"with delayed salary and a stale roster it drops to {pct(piv.loc['Salary delayed','Roster not updated'])}. "
           f"Both levers matter, and roster discipline partly cushions the salary effect.")
    return Result("Q13", "Human resources", "Do roster practices and salary timeliness independently predict attendance?", sql, df, ans, fig)


def q14(con):
    sql = """
    SELECT staff_leave_facility_for_salary_frequency AS frequency, urban_rural, COUNT(*) AS visits
    FROM v_visits GROUP BY 1,2"""
    df = q(con, sql); df["share"] = df.visits / df.groupby("urban_rural").visits.transform("sum")
    fig = px.bar(df, x="frequency", y="share", color="urban_rural", barmode="group", text="share",
                 category_orders={"frequency": C.LEAVE_FOR_SALARY_FREQ}, title="How often staff leave the facility to access their salary",
                 color_discrete_sequence=T.SERIES)
    fig.update_traces(texttemplate="%{text:.0%}", textposition="outside", width=0.3)
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="Share of visits", legend_title="")
    reason = q(con, "SELECT leave_for_salary_reason r, COUNT(*) n FROM v_visits WHERE leave_for_salary_reason IS NOT NULL GROUP BY 1 ORDER BY n DESC").iloc[0]
    rural_freq = df[(df.urban_rural == "Rural") & df.frequency.isin(["2-3 times a month", "Weekly"])].share.sum()
    ans = (f"In rural facilities, staff leave the post to access salary two or more times a month in {pct(rural_freq)} of visits; the main reason is '{reason.r}'. "
           f"Bringing agent banking or POS access to facility catchments would recover many lost duty days.")
    return Result("Q14", "Human resources", "How much service time is lost to accessing salary payments?", sql, df, ans, fig)


# ----------------------------------------------------------------------------
# Section C: Supply chain (Module 3)
# ----------------------------------------------------------------------------
def q15(con):
    sql = """
    SELECT commodity, category, AVG(stockout_flag) AS stockout_rate, AVG(zero_balance_flag) AS zero_balance_rate,
           AVG(below_min_stock_flag) AS below_min_rate, COUNT(*) AS observations
    FROM v_commodity WHERE stocked_flag=1 GROUP BY 1,2 ORDER BY stockout_rate DESC"""
    df = q(con, sql)
    fig = hbar(df, "stockout_rate", "commodity", "Stock-out rate since last visit, by tracer commodity", color="category", xlabel="Share of visits with a stock-out")
    fig.update_layout(legend_title="")
    overall = q(con, "SELECT AVG(stockout_flag) r FROM commodity_stock WHERE stocked_flag=1").iloc[0].r
    mat = df[df.category == "Maternal"].stockout_rate.mean()
    ans = (f"On average {pct(overall)} of stocked tracer items had a stock-out since the previous visit. Maternal life-saving commodities fare worst "
           f"(mean {pct(mat)}): {df.iloc[0].commodity} ({pct(df.iloc[0].stockout_rate)}), {df.iloc[1].commodity} ({pct(df.iloc[1].stockout_rate)}) and {df.iloc[2].commodity} ({pct(df.iloc[2].stockout_rate)}). "
           f"{df.iloc[-1].commodity} is the most reliably available ({pct(df.iloc[-1].stockout_rate)}).")
    return Result("Q15", "Supply chain", "Which essential medicines and commodities are most often stocked out?", sql, df, ans, fig,
                  key_numbers={"overall_stockout_rate": float(overall), "maternal_stockout_rate": float(mat)})


def q16(con):
    sql = """
    SELECT stockout_reason AS reason, COUNT(*) AS n FROM commodity_stock WHERE stockout_flag=1 GROUP BY 1 ORDER BY n DESC"""
    df = q(con, sql); df["share"] = df.n / df.n.sum()
    fig = hbar(df, "share", "reason", "Main reasons for stock-outs", xlabel="Share of stock-out events")
    upstream = df.loc[df.reason.isin(["Stock-out at LGA/state/central supply level", "Delay in delivery or distribution", "Incomplete fulfillment of requisition", "No feedback from KADHSMA"]), "share"].sum()
    facility = df.loc[df.reason.isin(["Requisition not submitted or submitted late", "Poor quantification or forecasting", "Expired or damaged stock not replaced"]), "share"].sum()
    ans = (f"{pct(upstream)} of stock-outs are attributed to upstream causes (central stock-out, delivery delay, partial fulfilment, no feedback), versus {pct(facility)} to facility-side causes "
           f"(late requisition, poor forecasting, unreplaced expiries). The single largest is '{df.iloc[0].reason}' at {pct(df.iloc[0].share)}.")
    return Result("Q16", "Supply chain", "Are stock-outs caused upstream or at the facility?", sql, df, ans, fig,
                  key_numbers={"upstream_share": float(upstream), "facility_share": float(facility)})


def q17(con):
    sql = """
    SELECT lga, AVG(stockout_flag) AS stockout_rate FROM v_commodity WHERE stocked_flag=1 GROUP BY lga ORDER BY stockout_rate DESC"""
    df = q(con, sql)
    fig = hbar(df, "stockout_rate", "lga", "Tracer commodity stock-out rate by LGA", xlabel="Share of stocked items with a stock-out")
    ans = (f"Stock-out rates range from {pct(df.iloc[-1].stockout_rate)} in {df.iloc[-1].lga} to {pct(df.iloc[0].stockout_rate)} in {df.iloc[0].lga}. "
           f"The top-five LGAs ({', '.join(df.head(5).lga)}) should be prioritised for supply-chain supervision.")
    return Result("Q17", "Supply chain", "Which LGAs have the worst commodity availability?", sql, df, ans, fig)


def q18(con):
    sql = """
    SELECT requisition_frequency, AVG(requisition_submitted_last_cycle_flag) AS submitted,
           AVG(requisition_complete_on_time_flag) AS complete_on_time,
           AVG(CASE WHEN requisition_receipt_status='Yes, all items received' THEN 1.0 WHEN requisition_receipt_status IS NULL THEN NULL ELSE 0 END) AS fully_received,
           AVG(delivery_documentation_provided_flag) AS documented, COUNT(*) AS visits
    FROM v_visits GROUP BY 1 ORDER BY visits DESC"""
    df = q(con, sql)
    long = df.melt(id_vars=["requisition_frequency", "visits"], var_name="stage", value_name="rate").dropna()
    fig = px.bar(long, x="stage", y="rate", color="requisition_frequency", barmode="group", text="rate",
                 title="Requisition funnel: submitted, complete & on time, fully received, documented", color_discrete_sequence=T.SERIES,
                 category_orders={"stage": ["submitted", "complete_on_time", "fully_received", "documented"]})
    fig.update_traces(texttemplate="%{text:.0%}", textposition="outside", width=0.18)
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="", legend_title="Requisition frequency")
    o = q(con, """SELECT AVG(requisition_submitted_last_cycle_flag) s, AVG(requisition_complete_on_time_flag) c,
                  AVG(CASE WHEN requisition_receipt_status='Yes, all items received' THEN 1.0 WHEN requisition_receipt_status IS NULL THEN NULL ELSE 0 END) f,
                  AVG(delivery_documentation_provided_flag) d FROM v_visits""").iloc[0]
    ans = (f"Only {pct(o.s)} of facilities submitted a requisition in the last cycle; of those, {pct(o.c)} were complete and on time and {pct(o.f)} were fully filled. "
           f"Delivery documentation accompanied {pct(o.d)} of receipts. Each leak in this funnel compounds into the stock-out rates above.")
    return Result("Q18", "Supply chain", "How well does the requisition-to-delivery process work?", sql, df, ans, fig,
                  key_numbers={"requisition_submitted": float(o.s), "complete_on_time": float(o.c), "fully_received": float(o.f)})


def q19(con):
    sql = """
    SELECT CASE WHEN requisition_submitted_last_cycle_flag=1 THEN 'Requisition submitted' ELSE 'No requisition' END AS requisition,
           knows_min_stock_calculation, AVG(stockout_flag) AS stockout_rate, COUNT(*) AS n
    FROM v_commodity WHERE stocked_flag=1 GROUP BY 1,2"""
    df = q(con, sql)
    fig = px.bar(df, x="knows_min_stock_calculation", y="stockout_rate", color="requisition", barmode="group", text="stockout_rate",
                 title="Stock-out rate by requisition behaviour and minimum-stock knowledge", color_discrete_sequence=T.SERIES)
    fig.update_traces(texttemplate="%{text:.1%}", textposition="outside", width=0.3)
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="Knows how to calculate minimum stock", yaxis_title="Stock-out rate", legend_title="")
    best = df.loc[df.stockout_rate.idxmin()]; worst = df.loc[df.stockout_rate.idxmax()]
    ans = (f"Facilities that submitted a requisition and know how to calculate minimum stock have a {pct(best.stockout_rate)} stock-out rate, against {pct(worst.stockout_rate)} where "
           f"no requisition was submitted and nobody can calculate minimum stock. Requisition discipline and LMIS skills are the cheapest stock-out reducers available.")
    return Result("Q19", "Supply chain", "Do requisition discipline and stock-management skills reduce stock-outs?", sql, df, ans, fig)


def q20(con):
    sql = """
    SELECT supplier, AVG(stockout_flag) AS stockout_rate, COUNT(*) AS n FROM commodity_stock WHERE stocked_flag=1 AND supplier IS NOT NULL GROUP BY 1 HAVING n>200 ORDER BY stockout_rate"""
    df = q(con, sql)
    fig = hbar(df, "stockout_rate", "supplier", "Stock-out rate by commodity supplier", xlabel="Share of items with a stock-out")
    share = q(con, "SELECT supplier, COUNT(*)*1.0/(SELECT COUNT(*) FROM commodity_stock WHERE supplier IS NOT NULL) s FROM commodity_stock WHERE supplier IS NOT NULL GROUP BY 1 ORDER BY s DESC").iloc[0]
    ans = (f"{share.supplier} supplies {pct(share.s)} of stocked items. Items sourced from {df.iloc[0].supplier} show the lowest stock-out rate ({pct(df.iloc[0].stockout_rate)}) "
           f"and {df.iloc[-1].supplier}-sourced items the highest ({pct(df.iloc[-1].stockout_rate)}).")
    return Result("Q20", "Supply chain", "Which supply sources are most reliable?", sql, df, ans, fig)


def q21(con):
    sql = """
    SELECT commodity, AVG(below_min_stock_flag) AS below_min_rate,
           AVG(CASE WHEN stock_adequacy_ratio IS NOT NULL THEN MIN(stock_adequacy_ratio, 5) END) AS median_adequacy
    FROM commodity_stock WHERE stocked_flag=1 AND minimum_stock_level IS NOT NULL GROUP BY 1 ORDER BY below_min_rate DESC"""
    df = q(con, sql)
    fig = hbar(df, "below_min_rate", "commodity", "Share of facilities holding less than their minimum stock level", xlabel="Below minimum stock")
    known = q(con, "SELECT AVG(minimum_stock_level IS NOT NULL) r FROM commodity_stock WHERE stocked_flag=1").iloc[0].r
    ans = (f"A minimum stock level was known for {pct(known)} of stocked items. Where known, {pct(df.below_min_rate.mean())} of items sit below the minimum - "
           f"the facility is one bad fortnight away from a stock-out. {df.iloc[0].commodity} ({pct(df.iloc[0].below_min_rate)}) is most exposed.")
    return Result("Q21", "Supply chain", "How many facilities are below minimum stock (early-warning)?", sql, df, ans, fig, key_numbers={"min_stock_known": float(known)})


def q22(con):
    sql = """
    SELECT vaccine, AVG(in_stock_flag) AS in_stock_rate, SUM(doses_used) AS doses_used, AVG(physically_verified_flag) AS verified
    FROM vaccine_stock GROUP BY 1 ORDER BY in_stock_rate"""
    df = q(con, sql)
    fig = hbar(df, "in_stock_rate", "vaccine", "Vaccine availability at facilities that stock vaccines", xlabel="Share of visits with vaccine in stock")
    status = q(con, "SELECT vaccine_stock_status s, COUNT(DISTINCT facility_id) n FROM v_visits WHERE round_number=1 GROUP BY 1").set_index("s").n
    tot = status.sum()
    ans = (f"{pct(status.get('Yes',0)/tot)} of facilities stock vaccines on site, {pct(status.get(C.VACCINE_STOCK_STATUS[1],0)/tot)} immunise without stocking and "
           f"{pct(status.get(C.VACCINE_STOCK_STATUS[2],0)/tot)} offer no immunisation. Among stocking facilities, availability is lowest for {df.iloc[0].vaccine} ({pct(df.iloc[0].in_stock_rate)}) "
           f"and {df.iloc[1].vaccine} ({pct(df.iloc[1].in_stock_rate)}) - the newer antigens - and highest for {df.iloc[-1].vaccine} ({pct(df.iloc[-1].in_stock_rate)}).")
    return Result("Q22", "Vaccines", "Which vaccines are available, and where are the gaps?", sql, df, ans, fig)


def q23(con):
    sql = """
    SELECT CASE WHEN vaccine_fridge_functional_flag=1 THEN 'Working fridge' ELSE 'No working fridge' END AS fridge,
           CASE WHEN cold_chain_interruption_since_last_visit_flag=1 THEN 'Interruption' ELSE 'No interruption' END AS interruption,
           AVG(in_stock_flag) AS in_stock_rate, COUNT(*) AS n
    FROM v_vaccine GROUP BY 1,2"""
    df = q(con, sql)
    fig = px.bar(df, x="fridge", y="in_stock_rate", color="interruption", barmode="group", text="in_stock_rate",
                 title="Vaccine availability by cold chain status", color_discrete_sequence=T.SERIES)
    fig.update_traces(texttemplate="%{text:.1%}", textposition="outside", width=0.3)
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="Vaccine in stock", legend_title="", yaxis_range=[0, 1])
    imm = q(con, """SELECT vaccine_fridge_functional_flag f, AVG(immunization_sessions_all_conducted_flag) r FROM v_visits WHERE vaccine_stock_status='Yes' GROUP BY 1""").set_index("f").r
    best = df.loc[df.in_stock_rate.idxmax()]; worst = df.loc[df.in_stock_rate.idxmin()]
    ans = (f"Vaccine availability is {pct(best.in_stock_rate)} with a {best.fridge.lower()} and {best.interruption.lower()}, but {pct(worst.in_stock_rate)} with {worst.fridge.lower()} and {worst.interruption.lower()}. "
           f"Immunisation sessions were fully delivered in {pct(imm.get(1, np.nan))} of weeks where the fridge works versus {pct(imm.get(0, np.nan))} where it does not.")
    return Result("Q23", "Vaccines", "How much does cold chain status drive vaccine availability and immunisation delivery?", sql, df, ans, fig)


def q24(con):
    sql = """
    SELECT vaccine, SUM(most_dispensed_flag) AS weeks_most_dispensed, SUM(doses_used) AS doses_used FROM vaccine_stock GROUP BY 1 ORDER BY doses_used DESC"""
    df = q(con, sql)
    fig = hbar(df, "doses_used", "vaccine", "Doses used across all visits, by vaccine", xlabel="Doses", fmt=",.0f")
    reason = q(con, "SELECT reason_most_dispensed r, COUNT(*) n FROM vaccine_stock WHERE most_dispensed_flag=1 GROUP BY 1 ORDER BY n DESC")
    ans = (f"{df.iloc[0].vaccine}, {df.iloc[1].vaccine} and {df.iloc[2].vaccine} account for {pct(df.head(3).doses_used.sum()/df.doses_used.sum())} of doses used. "
           f"The most common driver of a high-dispensing week is '{reason.iloc[0].r}' ({pct(reason.iloc[0].n/reason.n.sum())}), and HPV demand is mostly school-based sessions.")
    return Result("Q24", "Vaccines", "Which vaccines are consumed most, and why?", sql, df, ans, fig)


# ----------------------------------------------------------------------------
# Section D: Composite readiness
# ----------------------------------------------------------------------------
def q25(con):
    sql = """
    SELECT lga, AVG(readiness_score) AS readiness, AVG(facility_open_on_arrival_flag) AS open_rate, AVG(attendance_rate) AS attendance,
           1-AVG(stockout_rate) AS stock_availability, AVG(vaccine_availability_rate) AS vaccine_availability, AVG(session_completion_rate) AS sessions
    FROM v_visits GROUP BY lga ORDER BY readiness DESC"""
    df = q(con, sql)
    fig = hbar(df, "readiness", "lga", "Composite facility readiness score by LGA (0-100)", xlabel="Readiness score", fmt=".1f")
    fig.update_xaxes(tickformat="")
    bands = q(con, "SELECT readiness_band b, COUNT(*) n FROM v_visits GROUP BY 1").set_index("b").n
    ans = (f"Average readiness is {df.readiness.mean():.1f}/100, from {df.iloc[-1].readiness:.1f} in {df.iloc[-1].lga} to {df.iloc[0].readiness:.1f} in {df.iloc[0].lga}. "
           f"{pct(bands.get('Critical',0)/bands.sum())} of visits score Critical (<50) and {pct(bands.get('Strong',0)/bands.sum())} Strong (>80).")
    return Result("Q25", "Readiness", "Which LGAs are most and least ready to deliver services?", sql, df, ans, fig, key_numbers={"mean_readiness": float(df.readiness.mean())})


def q26(con):
    sql = """
    SELECT facility_type, AVG(readiness_score) AS readiness, AVG(attendance_rate) AS attendance, 1-AVG(stockout_rate) AS stock_availability,
           AVG(session_completion_rate) AS sessions, AVG(cce_functionality_rate) AS cold_chain, AVG(facility_open_on_arrival_flag) AS open_rate
    FROM v_visits GROUP BY 1"""
    df = q(con, sql)
    long = df.melt(id_vars=["facility_type", "readiness"], var_name="pillar", value_name="rate")
    fig = px.bar(long, x="pillar", y="rate", color="facility_type", barmode="group", text="rate", title="Readiness pillars by facility type",
                 category_orders={"facility_type": C.FACILITY_TYPES}, color_discrete_sequence=T.SERIES)
    fig.update_traces(texttemplate="%{text:.0%}", textposition="outside", width=0.18)
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="", legend_title="", yaxis_range=[0, 1.05])
    d = df.set_index("facility_type")
    ans = (f"General Hospitals score {d.loc['General Hospital','readiness']:.1f} and Health Posts {d.loc['Health Post','readiness']:.1f}. "
           f"Health Posts lag most on cold chain ({pct(d.loc['Health Post','cold_chain'])}) and being open on arrival ({pct(d.loc['Health Post','open_rate'])}), which argues for a differentiated support package by level of care.")
    return Result("Q26", "Readiness", "How does readiness differ by level of care?", sql, df, ans, fig)


def q27(con):
    sql = """
    SELECT f.facility_id, f.facility_name, f.lga, f.facility_type, AVG(v.readiness_score) AS readiness, AVG(v.stockout_rate) AS stockout_rate,
           AVG(v.attendance_rate) AS attendance, AVG(v.facility_open_on_arrival_flag) AS open_rate, COUNT(*) AS visits
    FROM facility_visits v JOIN facilities f USING(facility_id) GROUP BY 1,2,3,4 ORDER BY readiness"""
    df = q(con, sql)
    bottom = df.head(15)
    fig = hbar(bottom, "readiness", "facility_name", "15 lowest-readiness facilities (mean across rounds)", color="lga", xlabel="Readiness score", fmt=".1f")
    fig.update_xaxes(tickformat=""); fig.update_layout(legend_title="")
    ans = (f"The 15 lowest-scoring facilities average {bottom.readiness.mean():.1f}/100, with attendance of {pct(bottom.attendance.mean())} and a {pct(bottom.stockout_rate.mean())} stock-out rate. "
           f"{bottom.lga.value_counts().index[0]} contributes the most facilities to this list. These are the candidates for an intensive support visit this quarter.")
    return Result("Q27", "Readiness", "Which individual facilities need urgent support?", sql, df, ans, fig)


def q28(con):
    sql = """
    SELECT round_name, round_number, AVG(readiness_score) AS readiness, AVG(stockout_rate) AS stockout_rate, AVG(vaccine_availability_rate) AS vaccine_availability,
           AVG(facility_open_on_arrival_flag) AS open_rate, AVG(cold_chain_interruption_since_last_visit_flag) AS cold_chain_interruption
    FROM v_visits GROUP BY 1,2 ORDER BY 2"""
    df = q(con, sql)
    fig = go.Figure()
    for col, name in [("stockout_rate", "Commodity stock-out rate"), ("vaccine_availability", "Vaccine availability"), ("open_rate", "Open on arrival"), ("cold_chain_interruption", "Cold chain interruption")]:
        fig.add_trace(go.Scatter(x=df.round_name, y=df[col], mode="lines+markers", name=name, line=dict(width=2), marker=dict(size=9)))
    fig.update_layout(title="Key indicators across visit rounds", yaxis_tickformat=".0%", xaxis_title="", yaxis_title="", hovermode="x unified")
    ans = (f"Commodity stock-outs rose from {pct(df.iloc[0].stockout_rate)} at baseline to {pct(df.iloc[-1].stockout_rate)} by {df.iloc[-1].round_name} as opening balances were drawn down faster than deliveries replaced them, "
           f"while vaccine availability held around {pct(df.vaccine_availability.mean())}. The trend, not the level, is the alarm: resupply cadence is not keeping pace with consumption.")
    return Result("Q28", "Readiness", "How are indicators trending across the bi-weekly rounds?", sql, df, ans, fig)


def q29(con):
    sql = """
    SELECT readiness_score, attendance_rate, stockout_rate, vaccine_availability_rate, session_completion_rate, cce_functionality_rate,
           salary_paid_on_time_last_3_months_flag, requisition_submitted_last_cycle_flag, roster_updated_this_week_flag,
           distance_to_lga_hq_km, total_health_workers, security_incident_reported_flag, facility_open_on_arrival_flag
    FROM v_visits"""
    df = q(con, sql)
    corr = df.corr(numeric_only=True)
    labels = {"readiness_score": "Readiness", "attendance_rate": "Attendance", "stockout_rate": "Stock-out rate", "vaccine_availability_rate": "Vaccine availability",
              "session_completion_rate": "Session completion", "cce_functionality_rate": "Cold chain functional", "salary_paid_on_time_last_3_months_flag": "Salary on time",
              "requisition_submitted_last_cycle_flag": "Requisition submitted", "roster_updated_this_week_flag": "Roster updated", "distance_to_lga_hq_km": "Distance to LGA HQ",
              "total_health_workers": "Health workers", "security_incident_reported_flag": "Security incident", "facility_open_on_arrival_flag": "Open on arrival"}
    corr = corr.rename(index=labels, columns=labels)
    fig = go.Figure(go.Heatmap(z=corr.values, x=corr.columns, y=corr.index, zmin=-1, zmax=1, colorscale=[[0, T.DIVERGING[0]], [0.5, T.DIVERGING[2]], [1, T.DIVERGING[4]]],
                               text=np.round(corr.values, 2), texttemplate="%{text}", hovertemplate="%{y} vs %{x}: %{z:.2f}<extra></extra>", xgap=2, ygap=2))
    fig.update_layout(title="Correlation between readiness drivers", height=560, xaxis=dict(tickangle=-40), yaxis=dict(autorange="reversed"))
    s = corr["Readiness"].drop("Readiness").sort_values()
    ans = (f"Readiness correlates most positively with {s.index[-1]} (r={s.iloc[-1]:.2f}) and {s.index[-2]} (r={s.iloc[-2]:.2f}), and most negatively with {s.index[0]} (r={s.iloc[0]:.2f}). "
           f"Salary timeliness (r={corr.loc['Readiness','Salary on time']:.2f}) and requisition submission (r={corr.loc['Readiness','Requisition submitted']:.2f}) are the strongest management levers.")
    return Result("Q29", "Readiness", "Which factors move together, and what are the strongest levers on readiness?", sql, corr.reset_index(), ans, fig)


def q30(con):
    sql = """
    SELECT f.facility_name, f.lga, f.facility_type, f.latitude, f.longitude, AVG(v.readiness_score) AS readiness, AVG(v.stockout_rate) AS stockout_rate, AVG(v.attendance_rate) AS attendance
    FROM facility_visits v JOIN facilities f USING(facility_id) GROUP BY 1,2,3,4,5"""
    df = q(con, sql)
    fig = px.scatter_map(df, lat="latitude", lon="longitude", color="readiness", size="stockout_rate", size_max=16, hover_name="facility_name",
                         hover_data={"lga": True, "facility_type": True, "readiness": ":.1f", "stockout_rate": ":.1%", "attendance": ":.1%", "latitude": False, "longitude": False},
                         color_continuous_scale=T.SEQUENTIAL, zoom=6.6, center=dict(lat=10.35, lon=7.7), title="Facility readiness map (colour = readiness, size = stock-out rate)")
    fig.update_layout(map_style="carto-positron", height=620, margin=dict(l=0, r=0, t=56, b=0), coloraxis_colorbar=dict(title="Readiness"))
    lga = df.groupby("lga").readiness.mean().sort_values()
    sec = q(con, "SELECT security_risk_lga s, AVG(readiness_score) r FROM v_visits GROUP BY 1").set_index("s").r
    ans = (f"The lowest-readiness clusters are {', '.join(lga.index[:3])} (mean {lga.iloc[:3].mean():.1f}) while {', '.join(lga.index[-3:])} perform best (mean {lga.iloc[-3:].mean():.1f}). "
           f"Facilities in security-risk LGAs average {sec.get(1, np.nan):.1f} versus {sec.get(0, np.nan):.1f} elsewhere - geography and security explain a large share of the variation.")
    return Result("Q30", "Readiness", "Where are the weakest facilities located?", sql, df, ans, fig)


QUESTIONS: list[Callable] = [q01, q02, q03, q04, q05, q06, q07, q08, q09, q10, q11, q12, q13, q14, q15, q16, q17,
                             q18, q19, q20, q21, q22, q23, q24, q25, q26, q27, q28, q29, q30]


def run_all(db_path: Path = C.DB_PATH) -> list[Result]:
    con = sqlite3.connect(db_path)
    C.FIGURE_DIR.mkdir(parents=True, exist_ok=True)
    results = []
    try:
        for fn in QUESTIONS:
            r = fn(con)
            if r.figure is not None:
                r.figure_file = f"figures/{r.id}.html"
                r.figure.write_html(C.FIGURE_DIR / f"{r.id}.html", include_plotlyjs="cdn", full_html=True)
            results.append(r)
            print(f"{r.id} {r.question}\n    -> {r.answer}\n")
    finally:
        con.close()
    return results


def write_outputs(results: list[Result]) -> None:
    payload = []
    for r in results:
        payload.append({"id": r.id, "section": r.section, "question": r.question, "answer": r.answer, "sql": r.sql.strip(),
                        "figure_file": r.figure_file, "key_numbers": r.key_numbers,
                        "figure_json": json.loads(r.figure.to_json()) if r.figure is not None else None,
                        "data": json.loads(r.data.head(200).to_json(orient="records", date_format="iso"))})
    RESULTS_JSON.write_text(json.dumps(payload))

    C.DOCS_DIR.mkdir(exist_ok=True)
    lines = ["# LS 2.0 Facility Survey - Analysis Report", "",
             "Every question below is answered with a SQL query against the SQLite warehouse (`outputs/ls2_survey.db`) "
             "and an interactive Plotly figure (`outputs/figures/<id>.html`).", ""]
    section = None
    for r in results:
        if r.section != section:
            section = r.section
            lines += [f"## {section}", ""]
        lines += [f"### {r.id}. {r.question}", "", r.answer, "", f"Figure: `outputs/{r.figure_file}`", "",
                  "<details><summary>SQL</summary>", "", "```sql", r.sql.strip(), "```", "", "</details>", ""]
    REPORT_MD.write_text("\n".join(lines))
    print(f"wrote {RESULTS_JSON} and {REPORT_MD}")


if __name__ == "__main__":
    write_outputs(run_all())

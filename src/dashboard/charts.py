"""Shared data access, filtering and figure builders for the Python dashboards.

Both the Dash edition (src/dashboard/dash_app.py) and the Streamlit edition
(streamlit_app.py) call these functions, so the two apps stay identical: a
filter state goes in, plain Plotly figures / DataFrames come out. Nothing in
here depends on either framework.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from analysis import theme as T  # noqa: E402

CTX_COLS = ["visit_id", "lga", "facility_type", "round_number", "urban_rural", "salary_paid_on_time_last_3_months_flag",
            "roster_updated_this_week_flag", "requisition_submitted_last_cycle_flag", "knows_min_stock_calculation",
            "vaccine_fridge_functional_flag", "cold_chain_interruption_since_last_visit_flag"]


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
def load_data() -> dict:
    con = sqlite3.connect(C.DB_PATH)
    d = {
        "visits": pd.read_sql_query("SELECT * FROM v_visits ORDER BY facility_id, round_number", con),
        "com": pd.read_sql_query("SELECT * FROM commodity_stock WHERE stocked_flag=1", con),
        "stf": pd.read_sql_query("SELECT * FROM staffing_by_cadre", con),
        "abs": pd.read_sql_query("SELECT * FROM absence_reasons", con),
        "vac": pd.read_sql_query("SELECT * FROM vaccine_stock", con),
        "ses": pd.read_sql_query("SELECT * FROM service_sessions", con),
        "cce": pd.read_sql_query("SELECT * FROM cold_chain_equipment", con),
        "trn": pd.read_sql_query("SELECT * FROM trainings", con),
    }
    con.close()
    ml_dir = C.OUTPUT_DIR / "ml"
    d["fpred"] = pd.read_csv(ml_dir / "facility_predictions.csv")
    d["cpred"] = pd.read_csv(ml_dir / "commodity_stockout_predictions.csv").merge(
        d["visits"][["facility_id", "facility_name"]].drop_duplicates(), on="facility_id", how="left")
    d["ml"] = json.loads((ml_dir / "metrics.json").read_text())
    d["ml_figs"] = json.loads((ml_dir / "figures.json").read_text())
    d["analysis"] = json.loads((C.OUTPUT_DIR / "analysis_results.json").read_text())
    rounds = d["visits"][["round_number", "round_name"]].drop_duplicates().sort_values("round_number")
    d["round_name"] = dict(zip(rounds.round_number, rounds.round_name))
    d["n_rounds"] = int(d["visits"].round_number.max())
    d["lgas"] = sorted(d["visits"].lga.unique())
    return d


def filtered(D: dict, lgas, types, setting, security, rounds, readiness) -> dict:
    v = D["visits"]
    if lgas:
        v = v[v.lga.isin(lgas)]
    if types:
        v = v[v.facility_type.isin(types)]
    if setting:
        v = v[v.urban_rural == setting]
    if security in ("1", "0"):
        v = v[v.security_risk_lga == int(security)]
    v = v[v.round_number.between(rounds[0], rounds[1]) & v.readiness_score.between(readiness[0], readiness[1])]
    ids = set(v.visit_id)
    ctx = v[CTX_COLS]
    sub = lambda t: D[t][D[t].visit_id.isin(ids)].merge(ctx, on="visit_id", how="left")  # noqa: E731
    return {"v": v, "com": sub("com"), "stf": sub("stf"), "abs": sub("abs"), "vac": sub("vac"), "ses": sub("ses"), "cce": sub("cce"),
            "trn": D["trn"][D["trn"].facility_id.isin(set(v.facility_id))],
            "fpred": D["fpred"][D["fpred"].facility_id.isin(set(v.facility_id))],
            "cpred": D["cpred"][D["cpred"].facility_id.isin(set(v.facility_id))],
            "r0": rounds[0], "r1": rounds[1], "round_name": D["round_name"]}


def summary_text(f: dict, lgas, types, rounds) -> str:
    rn = f["round_name"]
    return (f"Showing {len(f['v']):,} visits to {f['v'].facility_id.nunique()} facilities · rounds {rounds[0]}–{rounds[1]} "
            f"({rn[rounds[0]]} → {rn[rounds[1]]}) · {len(lgas) if lgas else 'all 23'} LGA(s) · {', '.join(types) if types else 'all facility types'}")


# ----------------------------------------------------------------------------
# Primitives
# ----------------------------------------------------------------------------
def pct(x, d=1):
    return "–" if x is None or pd.isna(x) else f"{100 * x:.{d}f}%"


def rate(df, col):
    return float(df[col].mean()) if len(df) and df[col].notna().any() else np.nan


def empty(msg="No data for the current filters"):
    fig = go.Figure()
    fig.update_layout(xaxis_visible=False, yaxis_visible=False, height=300,
                      annotations=[dict(text=msg, showarrow=False, font=dict(color=T.TEXT_SECONDARY))])
    return fig


def _txt(v, fmt):
    if v is None or pd.isna(v):
        return ""
    return f"{v:,.0f}" if fmt == "," else f"{v:{fmt}}"


def hbar(labels, values, fmt=".0%", color=T.SERIES[0], line=None, xmax=None, height=None):
    labels, vals = list(labels), list(values)
    if not labels:
        return empty()
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation="h", marker_color=color, width=0.62, text=[_txt(v, fmt) for v in vals],
                           textposition="outside", cliponaxis=False, textfont=dict(size=11, color=T.TEXT_SECONDARY),
                           hovertemplate="%{y}: %{x:" + (".1%" if "%" in fmt else fmt) + "}<extra></extra>"))
    top = np.nanmax([v for v in vals if v is not None and not pd.isna(v)] or [0])
    fig.update_layout(margin=dict(l=10, r=60, t=10, b=40), xaxis=dict(tickformat=(".0%" if "%" in fmt else fmt), range=[0, xmax or top * 1.25]),
                      yaxis=dict(automargin=True), height=height or max(320, 24 * len(labels) + 90), showlegend=False)
    if line is not None and not pd.isna(line):
        fig.add_vline(x=line, line_dash="dot", line_color=T.TEXT_SECONDARY)
    return fig


def grouped(cats, series: dict, horizontal=False, stacked=False, fmt=".0%", tickformat=".0%", yrange=None, height=None):
    fig = go.Figure()
    for i, (name, vals) in enumerate(series.items()):
        vals = list(vals)
        fig.add_bar(name=name, x=vals if horizontal else cats, y=cats if horizontal else vals, orientation="h" if horizontal else "v",
                    marker=dict(color=T.SERIES[i % 8], line=dict(color="#fff", width=2 if stacked else 0)),
                    text=[_txt(v, fmt) for v in vals] if fmt else None,
                    textposition="inside" if stacked else "outside", cliponaxis=False, textfont=dict(size=10, color="#fff" if stacked else T.TEXT_SECONDARY))
    fig.update_layout(barmode="stack" if stacked else "group", bargroupgap=0.08, height=height or 360, legend_title="",
                      margin=dict(l=10 if horizontal else 50, r=50 if horizontal else 16, t=30, b=40 if horizontal else 60))
    if horizontal:
        fig.update_xaxes(tickformat=tickformat)
    else:
        fig.update_yaxes(tickformat=tickformat, range=yrange)
    return fig


def lines(x, series: dict, tickformat=".0%", height=340):
    fig = go.Figure()
    for name, y in series.items():
        fig.add_scatter(x=list(x), y=list(y), mode="lines+markers", name=name, line=dict(width=2), marker=dict(size=8),
                        hovertemplate=name + ": %{y:" + (".1%" if tickformat == ".0%" else ".1f") + "}<extra></extra>")
    fig.update_layout(hovermode="x unified", yaxis=dict(tickformat=tickformat, rangemode="tozero"), margin=dict(t=40), height=height)
    return fig


def heat(x, y, z, zmin=0, zmax=1, height=560):
    fig = go.Figure(go.Heatmap(x=list(x), y=list(y), z=z, colorscale=T.SEQUENTIAL, zmin=zmin, zmax=zmax, xgap=2, ygap=2,
                               colorbar=dict(tickformat=".0%", thickness=10), hovertemplate="%{y} · %{x}: %{z:.0%}<extra></extra>"))
    fig.update_layout(xaxis=dict(tickangle=-45, tickfont=dict(size=10)), yaxis=dict(autorange="reversed", tickfont=dict(size=10)),
                      margin=dict(l=10, r=10, t=10, b=120), height=height)
    return fig


def tone(x, good, bad, invert=False):
    if x is None or pd.isna(x):
        return ""
    g = x <= good if invert else x >= good
    b = x >= bad if invert else x <= bad
    return "good" if g else "bad" if b else "warn"


# ----------------------------------------------------------------------------
# Tab builders: each returns a dict of figures (and small data) for a filter state
# ----------------------------------------------------------------------------
def overview(f: dict) -> dict:
    v = f["v"]; rn = f["round_name"]
    if v.empty:
        return {"kpis": [("Visits", "0", "no visits match", "")], "trend": empty(), "bands": empty(), "lga": empty(), "map": empty(), "pillars": empty()}
    att = v.permanent_present_today.sum() / max(1, v.permanent_scheduled_today.sum())
    so = rate(f["com"], "stockout_flag"); vac = rate(f["vac"], "in_stock_flag"); ready = rate(v, "readiness_score")
    cc = rate(v[v.has_cold_chain_equipment_flag == 1], "cold_chain_interruption_since_last_visit_flag")
    op = rate(v, "facility_open_on_arrival_flag"); ses = rate(v, "session_completion_rate"); sal = rate(v, "salary_paid_on_time_last_3_months_flag")
    kpis = [("Visits", f"{len(v):,}", f"{v.facility_id.nunique()} facilities", ""), ("Mean readiness", f"{ready:.1f}", "composite score /100", tone(ready, 75, 60)),
            ("Open on arrival", pct(op), "share of visits", tone(op, .85, .7)), ("Staff attendance", pct(att), "permanent present ÷ scheduled", tone(att, .8, .65)),
            ("Stock-out rate", pct(so), "tracer items stocked out", tone(so, .2, .35, True)), ("Vaccine availability", pct(vac), "antigens in stock", tone(vac, .8, .6)),
            ("Sessions completed", pct(ses), "planned sessions delivered", tone(ses, .85, .7)), ("Cold chain interruptions", pct(cc), "facilities with CCE", tone(cc, .1, .25, True)),
            ("Salary on time", pct(sal), "last 3 months", tone(sal, .8, .5))]
    byr = v.groupby("round_number"); x = [rn[r] for r in byr.groups]
    trend = go.Figure()
    for i, (col, name, m) in enumerate([("readiness_score", "Readiness", 1), ("facility_open_on_arrival_flag", "Open on arrival", 100), ("attendance_rate", "Attendance", 100),
                                         ("stockout_rate", "Stock-out rate", 100), ("vaccine_availability_rate", "Vaccine availability", 100), ("session_completion_rate", "Session completion", 100)]):
        trend.add_scatter(x=x, y=list(byr[col].mean() * m), mode="lines+markers", name=name, line=dict(width=3 if i == 0 else 2), marker=dict(size=8),
                          visible=True if i == 0 else "legendonly", hovertemplate=name + ": %{y:.1f}<extra></extra>")
    trend.update_layout(hovermode="x unified", yaxis=dict(title="Score / rate (0-100)", rangemode="tozero"), margin=dict(t=40), height=340)
    bands = ["Strong", "Fair", "Weak", "Critical"]; bc = v.readiness_band.value_counts()
    pie = go.Figure(go.Pie(labels=bands, values=[int(bc.get(b, 0)) for b in bands], hole=.55, sort=False, textinfo="label+percent",
                           marker=dict(colors=[T.STATUS["good"], T.SERIES[0], T.STATUS["serious"], T.STATUS["critical"]], line=dict(color="#fff", width=2))))
    pie.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=340)
    byl = v.groupby("lga").readiness_score.mean().sort_values()
    lga = hbar(byl.index, byl.values, fmt=".1f", line=ready, xmax=100, height=460)
    byf = v.groupby(["facility_id", "facility_name", "lga", "facility_type", "latitude", "longitude"]).agg(r=("readiness_score", "mean"), so=("stockout_rate", "mean"), att=("attendance_rate", "mean")).reset_index()
    mp = px.scatter_map(byf, lat="latitude", lon="longitude", color="r", size=byf.so.fillna(0) * 18 + 4, size_max=18, hover_name="facility_name",
                        hover_data={"lga": True, "facility_type": True, "r": ":.1f", "so": ":.1%", "att": ":.1%", "latitude": False, "longitude": False},
                        color_continuous_scale=T.SEQUENTIAL, range_color=[40, 95], zoom=6.4, center=dict(lat=10.35, lon=7.7), labels={"r": "Readiness", "so": "Stock-out", "att": "Attendance"})
    mp.update_layout(map_style="carto-positron", margin=dict(l=0, r=0, t=0, b=0), height=460, coloraxis_colorbar=dict(title="Readiness", thickness=10))
    types = [t for t in C.FACILITY_TYPES if (v.facility_type == t).any()]; byt = v.groupby("facility_type")
    pl = [("facility_open_on_arrival_flag", "Open on arrival", False), ("attendance_rate", "Attendance", False), ("stockout_rate", "Stock availability", True),
          ("vaccine_availability_rate", "Vaccine availability", False), ("session_completion_rate", "Session completion", False), ("cce_functionality_rate", "Cold chain functional", False)]
    pillars = grouped([p[1] for p in pl], {t: [(1 - byt.get_group(t)[c].mean()) if inv else byt.get_group(t)[c].mean() for c, _, inv in pl] for t in types}, yrange=[0, 1.08])
    return {"kpis": kpis, "trend": trend, "bands": pie, "lga": lga, "map": mp, "pillars": pillars}


def access(f: dict, service=None) -> dict:
    v = f["v"]
    keys = ["open_lga", "closed", "hours", "referral", "cce", "services", "session_reasons", "training"]
    if v.empty:
        return {k: empty() for k in keys}
    byl = v.groupby("lga").facility_open_on_arrival_flag.mean().sort_values()
    closed = v[v.facility_open_on_arrival_flag == 0].reason_closed_on_arrival.fillna("Not recorded").value_counts(normalize=True).sort_values()
    first = v.sort_values("round_number").drop_duplicates("facility_id"); types = [t for t in C.FACILITY_TYPES if (first.facility_type == t).any()]
    c = f["cce"].groupby("cce_type"); cce_t = list(c.groups)
    s = f["ses"].groupby("service")
    missed = f["ses"][(f["ses"].all_conducted_flag == 0) & ((f["ses"].service == service) if service else True)].reason_not_conducted.fillna("Not recorded").value_counts(normalize=True).sort_values()
    n = max(1, v.facility_id.nunique()); tr = (f["trn"].groupby("training").facility_id.nunique() / n).sort_values()
    return {
        "open_lga": hbar(byl.index, byl.values, line=rate(v, "facility_open_on_arrival_flag"), xmax=1.1, height=460),
        "closed": hbar(closed.index, closed.values, color=T.SERIES[1], height=460),
        "hours": grouped(types, {h: [int(((first.facility_type == t) & (first.hours_of_operation == h)).sum()) for t in types] for h in C.HOURS_OF_OPERATION}, stacked=True, fmt=None, tickformat=""),
        "referral": hbar(["Can refer emergencies", "Transport available when needed"], [rate(v, "can_refer_emergencies_flag"), rate(v[v.can_refer_emergencies_flag == 1], "emergency_transport_available_2wks_flag")], color=T.SERIES[2], xmax=1.15, height=340),
        "cce": grouped(cce_t, {"Available": [c.get_group(t).available_flag.mean() for t in cce_t], "Functional (where available)": [c.get_group(t).query("available_flag==1").functional_flag.mean() for t in cce_t]}, horizontal=True, fmt=None, height=340),
        "services": grouped(C.SERVICES, {"Offered": [s.get_group(x).offered_flag.mean() for x in C.SERVICES], "All planned sessions conducted": [s.get_group(x).query("offered_flag==1").all_conducted_flag.mean() for x in C.SERVICES]}, horizontal=True, fmt=None, height=440),
        "session_reasons": hbar(missed.index, missed.values, color=T.SERIES[1], height=440),
        "training": hbar(tr.index, tr.values, color=T.SERIES[6], height=440),
    }


def hrh(f: dict, cadre=None, top=10) -> dict:
    v = f["v"]; st = f["stf"]
    keys = ["att_cadre", "att_lga", "absence", "workforce", "salary_trend", "salary_roster", "leave", "distance"]
    if v.empty:
        return {k: empty() for k in keys}
    overall = st.permanent_present_today.sum() / max(1, st.permanent_scheduled_today.sum())
    g = st.groupby("cadre")[["permanent_present_today", "permanent_scheduled_today"]].sum(); g = g[g.permanent_scheduled_today > 0]
    att_c = (g.permanent_present_today / g.permanent_scheduled_today).sort_values()
    gl = st.groupby("lga")[["permanent_present_today", "permanent_scheduled_today"]].sum(); att_l = (gl.permanent_present_today / gl.permanent_scheduled_today.replace(0, np.nan)).sort_values()
    ab = f["abs"][f["abs"].cadre == cadre] if cadre else f["abs"]
    ar = (ab.groupby("reason").staff_count.sum() / max(1, ab.staff_count.sum())).sort_values(ascending=False).head(int(top)).sort_values()
    base = st[st.round_number == f["r0"]].groupby("cadre")[["permanent", "adhoc_a", "adhoc_b", "volunteer"]].sum().reindex(C.CADRES[::-1]).fillna(0)
    byr = v.groupby("round_number"); x = [f["round_name"][r] for r in byr.groups]

    def att_of(mask):
        a = v[mask]; s = a.permanent_scheduled_today.sum(); return a.permanent_present_today.sum() / s if s else np.nan
    sal_on, sal_off = v.salary_paid_on_time_last_3_months_flag == 1, v.salary_paid_on_time_last_3_months_flag == 0
    ro_on = v.roster_updated_this_week_flag == 1
    byf = v.groupby(["facility_name", "lga", "facility_type", "distance_to_lga_hq_km", "total_health_workers"]).attendance_rate.mean().reset_index()
    dist = px.scatter(byf, x="distance_to_lga_hq_km", y="attendance_rate", size="total_health_workers", hover_name="facility_name", hover_data=["lga", "facility_type"],
                      color_discrete_sequence=[T.SERIES[0]], opacity=.6, size_max=16)
    dist.update_layout(xaxis_title="Distance to LGA HQ (km)", yaxis=dict(tickformat=".0%", title="Mean attendance", range=[0, 1.05]), height=340)
    return {
        "att_cadre": hbar(att_c.index, att_c.values, fmt=".1%", line=overall, xmax=1.1, height=420),
        "att_lga": hbar(att_l.index, att_l.values, line=overall, xmax=1.1, height=460),
        "absence": hbar(ar.index, ar.values, fmt=".1%", color=T.SERIES[1], height=440),
        "workforce": grouped(list(base.index), {n: base[c].tolist() for c, n in [("permanent", "Permanent"), ("adhoc_a", "Ad hoc A"), ("adhoc_b", "Ad hoc B"), ("volunteer", "Volunteer")]}, horizontal=True, stacked=True, fmt=None, tickformat="", height=440),
        "salary_trend": lines(x, {"Salary paid on time": byr.salary_paid_on_time_last_3_months_flag.mean(), "Staff attendance": byr.attendance_rate.mean(), "Sessions completed": byr.session_completion_rate.mean()}),
        "salary_roster": grouped(["Salary on time", "Salary delayed"], {"Roster updated this week": [att_of(sal_on & ro_on), att_of(sal_off & ro_on)], "Roster not updated": [att_of(sal_on & ~ro_on), att_of(sal_off & ~ro_on)]}, yrange=[0, 1]),
        "leave": grouped(C.LEAVE_FOR_SALARY_FREQ, {s: [((v.urban_rural == s) & (v.staff_leave_facility_for_salary_frequency == fq)).sum() / max(1, (v.urban_rural == s).sum()) for fq in C.LEAVE_FOR_SALARY_FREQ] for s in ["Urban", "Rural"]}, yrange=[0, .7]),
        "distance": dist,
    }


def supply(f: dict, category=None, commodity=None, minrate=0) -> dict:
    v = f["v"]; com = f["com"]
    keys = ["stockout_com", "heat", "reasons", "funnel", "supplier", "req", "below_min", "trend"]
    if com.empty:
        return {k: empty() for k in keys}
    cm = com[com.category == category] if category else com
    byc = cm.groupby(["commodity", "category"]).stockout_flag.mean().reset_index().sort_values("stockout_flag")
    so_com = px.bar(byc, x="stockout_flag", y="commodity", color="category", orientation="h", text=byc.stockout_flag.map(lambda x: f"{x:.0%}"),
                    color_discrete_map={"Maternal": T.SERIES[1], "Child": T.SERIES[2], "General": T.SERIES[0], "Family Planning": T.SERIES[6]})
    so_com.update_traces(textposition="outside", cliponaxis=False, width=.62)
    so_com.update_layout(xaxis=dict(tickformat=".0%", range=[0, byc.stockout_flag.max() * 1.2]), yaxis_title="", xaxis_title="", legend_title="", margin=dict(l=10, r=40, t=30, b=40), height=560)
    piv = cm.pivot_table(index="lga", columns="commodity", values="stockout_flag", aggfunc="mean").reindex(columns=byc.commodity)
    so = com[(com.stockout_flag == 1) & ((com.commodity == commodity) if commodity else True)].stockout_reason.fillna("Not recorded").value_counts(normalize=True).sort_values()
    sub = v[v.requisition_submitted_last_cycle_flag == 1]; rec = sub[sub.requisition_receipt_status.notna()]
    stages = [("Submitted requisition", rate(v, "requisition_submitted_last_cycle_flag")), ("Complete & on time", rate(sub, "requisition_complete_on_time_flag")),
              ("Fully received", (rec.requisition_receipt_status == "Yes, all items received").mean() if len(rec) else np.nan),
              ("Delivery documented", rate(rec[rec.requisition_receipt_status != "No, none received yet"], "delivery_documentation_provided_flag"))]
    funnel = go.Figure(go.Funnel(y=[s[0] for s in stages], x=[s[1] for s in stages], texttemplate="%{value:.0%}", marker=dict(color=[T.SERIES[0], T.SERIES[2], T.SERIES[3], T.SERIES[6]])))
    funnel.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=440, yaxis=dict(automargin=True))
    sp = com[com.supplier.notna()].groupby("supplier").stockout_flag.agg(["mean", "count"]); sp = sp[sp["count"] >= 30]["mean"].sort_values()
    kn = ["Yes, I know how to calculate", "Yes, someone else is assigned to calculate", "No"]
    bm = com[com.below_min_stock_flag.notna()].groupby("commodity").below_min_stock_flag.mean(); bm = bm[bm >= minrate / 100].sort_values()
    byr = com.groupby(["round_number", "category"]).stockout_flag.mean().unstack(); x = [f["round_name"][r] for r in byr.index]
    return {
        "stockout_com": so_com,
        "heat": heat(piv.columns, piv.index, piv.values, zmax=.7),
        "reasons": hbar(so.index, so.values, color=T.SERIES[1], height=440),
        "funnel": funnel,
        "supplier": hbar(sp.index, sp.values, height=340),
        "req": grouped(["Knows how", "Someone else does", "Nobody"], {n: [com[(com.knows_min_stock_calculation == k) & (com.requisition_submitted_last_cycle_flag == flag)].stockout_flag.mean() for k in kn] for n, flag in [("Requisition submitted", 1), ("No requisition", 0)]}, yrange=[0, .6]),
        "below_min": hbar(bm.index, bm.values, color=T.SERIES[3], xmax=1.15, height=340),
        "trend": lines(x, {c: byr[c] for c in byr.columns}),
    }


def vaccines(f: dict) -> dict:
    v = f["v"]; vac = f["vac"]
    keys = ["avail", "doses", "status", "cce", "cc_reasons", "heat"]
    if v.empty or vac.empty:
        return {k: empty() for k in keys}
    byv = vac.groupby("vaccine").agg(r=("in_stock_flag", "mean"), d=("doses_used", "sum"))
    first = v.sort_values("round_number").drop_duplicates("facility_id"); vc = first.vaccine_stock_status.value_counts()
    status = go.Figure(go.Pie(labels=["Stocks vaccines", "Immunises, no stock", "No immunisation"], values=[int(vc.get(s, 0)) for s in C.VACCINE_STOCK_STATUS], hole=.55, sort=False,
                              marker=dict(colors=[T.SERIES[0], T.SERIES[3], T.SERIES[7]], line=dict(color="#fff", width=2)), textinfo="label+percent"))
    status.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=340)
    fr = vac.vaccine_fridge_functional_flag == 1; it = vac.cold_chain_interruption_since_last_visit_flag == 1
    ccr = v[v.cold_chain_interruption_since_last_visit_flag == 1].cold_chain_interruption_reason.fillna("Not recorded").value_counts().sort_values()
    piv = vac.pivot_table(index="lga", columns="round_number", values="in_stock_flag", aggfunc="mean")
    vh = heat([f["round_name"][r] for r in piv.columns], piv.index, piv.values, zmin=.3, zmax=1, height=520)
    vh.update_layout(margin=dict(b=40)); vh.update_xaxes(tickangle=0)
    return {
        "avail": hbar(byv.r.sort_values().index, byv.r.sort_values().values, line=rate(vac, "in_stock_flag"), xmax=1.15, height=420),
        "doses": hbar(byv.d.sort_values().index, byv.d.sort_values().values, fmt=",", color=T.SERIES[2], height=420),
        "status": status,
        "cce": grouped(["Working fridge", "No working fridge"], {"No interruption": [vac[fr & ~it].in_stock_flag.mean(), vac[~fr & ~it].in_stock_flag.mean()], "Interruption since last visit": [vac[fr & it].in_stock_flag.mean(), vac[~fr & it].in_stock_flag.mean()]}, yrange=[0, 1]),
        "cc_reasons": hbar(ccr.index, ccr.values, fmt=",", color=T.SERIES[1], height=340),
        "heat": vh,
    }


RISK_COLS = [("facility_name", "Facility"), ("lga", "LGA"), ("facility_type", "Type"), ("segment", "Segment"), ("readiness_score", "Readiness (latest)"), ("at_risk_probability", "At-risk prob."),
             ("mean_stockout_risk", "Mean stock-out risk"), ("attendance_rate", "Attendance (latest)"), ("expected_attendance_if_salary_on_time", "Expected att. if salary on time"), ("stockout_rate", "Stock-out rate (latest)")]
RISK_PCT = {"At-risk prob.", "Mean stock-out risk", "Attendance (latest)", "Expected att. if salary on time", "Stock-out rate (latest)"}


def model_cards(m: dict) -> list[tuple[str, list[tuple[str, str]], str]]:
    best = m["stockout"]["best_model"]; cs = m["stockout"]["candidates"][best]
    return [
        (m["stockout"]["name"], [("Best model", best.replace("_", " ")), ("ROC AUC (held-out round)", f"{cs['roc_auc']:.3f}"), ("Average precision", f"{cs['avg_precision']:.3f}"), ("Base rate", pct(m["stockout"]["positive_rate_test"])), ("Training rows", f"{m['stockout']['train_rows']:,}")],
         "Predicts, per facility × commodity, whether a stock-out will be recorded at the next visit."),
        (m["at_risk"]["name"], [("Model", "random forest"), ("ROC AUC (held-out round)", f"{m['at_risk']['metrics']['roc_auc']:.3f}"), ("Average precision", f"{m['at_risk']['metrics']['avg_precision']:.3f}"), ("Base rate", pct(m["at_risk"]["metrics"]["positive_rate_test"])), ("Training rows", f"{m['at_risk']['train_rows']:,}")],
         "Flags facilities likely to fall into the Weak/Critical bands next round."),
        (m["attendance"]["name"], [("Model", "gradient boosting"), ("R² (grouped CV)", f"{m['attendance']['metrics']['grouped_cv_r2']:.2f}"), ("R² headcount-weighted", f"{m['attendance']['metrics']['grouped_cv_r2_headcount_weighted']:.2f}"),
                                   ("MAE vs naive", f"{m['attendance']['metrics']['grouped_cv_mae']:.3f} vs {m['attendance']['metrics']['naive_global_mean_mae']:.3f}"), ("Gain if salary on time", "+" + pct(m["attendance"]["metrics"]["mean_gain_salary_on_time"]))],
         "Explains expected attendance from salary, roster, distance, size and security; used for what-if scenarios."),
        ("Facility segmentation", [("Method", f"k-means (k={m['segmentation']['k']})"), ("Silhouette", f"{m['segmentation']['silhouette']:.2f}")] + [(k, f"{n} facilities") for k, n in m["segmentation"]["segment_sizes"].items()],
         "Mean profile across the readiness pillars; segments guide, not dictate, the support package."),
    ]


def importance_fig(items):
    items = items[:12][::-1]
    return hbar([i["feature"].replace("_", " ") for i in items], [i["importance"] for i in items], fmt=".3f", color=T.SERIES[6], height=440)


def predict(f: dict, D: dict, risk_thr=50, so_thr=60) -> dict:
    m = D["ml"]
    fp = f["fpred"].sort_values("at_risk_probability", ascending=False); flagged = fp[fp.at_risk_probability >= risk_thr / 100]
    table = flagged[[c for c, _ in RISK_COLS]].rename(columns=dict(RISK_COLS)).round(3).reset_index(drop=True)
    cp = f["cpred"][f["cpred"].stockout_risk >= so_thr / 100].sort_values("stockout_risk", ascending=False).head(30)[::-1]
    cf = f["fpred"].assign(gain=lambda d: d.expected_attendance_if_salary_on_time - d.expected_attendance); cf = cf[cf.gain > .005].sort_values("gain", ascending=False).head(30)[::-1]
    roc = go.Figure(D["ml_figs"]["stockout_roc"]); roc.update_layout(title=None, height=440, template="ls2")
    cen = pd.DataFrame(m["segmentation"]["centres"]); seg_cols = [c for c in cen.columns if c != "segment_id"]
    return {
        "cards": model_cards(m), "table": table, "risk_count": f"{len(flagged)} of {len(fp)} facilities flagged",
        "so_risk": hbar((cp.facility_name + " · " + cp.commodity).tolist(), cp.stockout_risk.tolist(), color=T.STATUS["critical"], xmax=1.15, height=560),
        "cf_salary": hbar((cf.facility_name + " (" + cf.lga + ")").tolist(), cf.gain.tolist(), fmt=".1%", color=T.STATUS["good"], height=560),
        "so_imp": importance_fig(m["stockout"]["importance"]), "roc": roc, "risk_imp": importance_fig(m["at_risk"]["importance"]), "att_imp": importance_fig(m["attendance"]["importance"]),
        "segments": grouped([c.replace("_flag", "").replace("_rate", "").replace("_", " ") for c in seg_cols], {r["segment_id"]: [r[c] for c in seg_cols] for _, r in cen.iterrows()}, yrange=[0, 1.1], height=440),
    }


DATA_COLS = [("facility_name", "Facility"), ("lga", "LGA"), ("facility_type", "Type"), ("round_name", "Round"), ("visit_date", "Date"), ("readiness_score", "Readiness"), ("readiness_band", "Band"),
             ("facility_open_on_arrival_flag", "Open"), ("attendance_rate", "Attendance"), ("stockout_rate", "Stock-out"), ("vaccine_availability_rate", "Vaccines"), ("session_completion_rate", "Sessions"),
             ("cce_functionality_rate", "Cold chain"), ("salary_paid_on_time_last_3_months_flag", "Salary on time"), ("requisition_submitted_last_cycle_flag", "Requisition"), ("total_health_workers", "Health workers")]
DATA_PCT = {"Attendance", "Stock-out", "Vaccines", "Sessions", "Cold chain"}


def data_table(f: dict) -> pd.DataFrame:
    return f["v"][[c for c, _ in DATA_COLS]].rename(columns=dict(DATA_COLS)).round(3).reset_index(drop=True)

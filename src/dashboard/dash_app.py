"""Pure-Python interactive dashboard (Plotly Dash) for the LS 2.0 survey warehouse.

Same content as the static docs/index.html dashboard — KPIs, eight tabs, global
filters and sliders, predictions tables, the thirty answered questions and a
filtered data table with CSV download — but every component, filter and chart
is defined and recomputed in Python callbacks against the SQLite warehouse.

Run:  python src/dashboard/dash_app.py            (http://127.0.0.1:8050)
      python src/dashboard/dash_app.py --port 8060 --debug
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dash import Dash, Input, Output, State, dash_table, dcc, html, no_update

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from analysis import theme as T  # noqa: E402

# ----------------------------------------------------------------------------
# Data (loaded once at start-up)
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
    d["rounds"] = d["visits"][["round_number", "round_name"]].drop_duplicates().sort_values("round_number")
    return d


D = load_data()
V = D["visits"]
ROUND_NAME = dict(zip(D["rounds"].round_number, D["rounds"].round_name))
N_ROUNDS = int(V.round_number.max())
LGAS = sorted(V.lga.unique())


# ----------------------------------------------------------------------------
# Filtering + chart helpers
# ----------------------------------------------------------------------------
def filtered(lgas, types, setting, security, rounds, readiness) -> dict:
    v = V
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
    ctx = v[["visit_id", "lga", "facility_type", "round_number", "urban_rural", "salary_paid_on_time_last_3_months_flag",
             "roster_updated_this_week_flag", "requisition_submitted_last_cycle_flag", "knows_min_stock_calculation",
             "vaccine_fridge_functional_flag", "cold_chain_interruption_since_last_visit_flag"]]
    sub = lambda t: D[t][D[t].visit_id.isin(ids)].merge(ctx, on="visit_id", how="left")  # noqa: E731
    return {"v": v, "com": sub("com"), "stf": sub("stf"), "abs": sub("abs"), "vac": sub("vac"), "ses": sub("ses"), "cce": sub("cce"),
            "trn": D["trn"][D["trn"].facility_id.isin(set(v.facility_id))],
            "fpred": D["fpred"][D["fpred"].facility_id.isin(set(v.facility_id))],
            "cpred": D["cpred"][D["cpred"].facility_id.isin(set(v.facility_id))], "r0": rounds[0], "r1": rounds[1]}


def pct(x, d=1):
    return "–" if x is None or pd.isna(x) else f"{100 * x:.{d}f}%"


def empty(msg="No data for the current filters"):
    fig = go.Figure()
    fig.update_layout(xaxis_visible=False, yaxis_visible=False, annotations=[dict(text=msg, showarrow=False, font=dict(color=T.TEXT_SECONDARY))])
    return fig


def hbar(labels, values, fmt=".0%", color=T.SERIES[0], line=None, xmax=None, height=None):
    if len(labels) == 0:
        return empty()
    vals = list(values)
    text = [("" if v is None or pd.isna(v) else (f"{v:{fmt}}" if fmt != "," else f"{v:,.0f}")) for v in vals]
    fig = go.Figure(go.Bar(x=vals, y=list(labels), orientation="h", marker_color=color, width=0.62, text=text, textposition="outside",
                           cliponaxis=False, textfont=dict(size=11, color=T.TEXT_SECONDARY),
                           hovertemplate="%{y}: %{x:" + (".1%" if "%" in fmt else fmt) + "}<extra></extra>"))
    top = np.nanmax([v for v in vals if v is not None] or [0])
    fig.update_layout(margin=dict(l=10, r=60, t=10, b=40), xaxis=dict(tickformat="%" and (".0%" if "%" in fmt else fmt), range=[0, xmax or top * 1.25]),
                      yaxis=dict(automargin=True), height=height or max(320, 24 * len(labels) + 90), showlegend=False)
    if line is not None and not pd.isna(line):
        fig.add_vline(x=line, line_dash="dot", line_color=T.TEXT_SECONDARY)
    return fig


def grouped(cats, series: dict, horizontal=False, stacked=False, fmt=".0%", tickformat=".0%", yrange=None, height=None):
    fig = go.Figure()
    for i, (name, vals) in enumerate(series.items()):
        text = [("" if v is None or pd.isna(v) else (f"{v:{fmt}}" if fmt != "," else f"{v:,.0f}")) if fmt else "" for v in vals]
        fig.add_bar(name=name, x=vals if horizontal else cats, y=cats if horizontal else vals, orientation="h" if horizontal else "v",
                    marker=dict(color=T.SERIES[i % 8], line=dict(color="#fff", width=2 if stacked else 0)), text=text,
                    textposition="inside" if stacked else "outside", cliponaxis=False, textfont=dict(size=10, color="#fff" if stacked else T.TEXT_SECONDARY))
    fig.update_layout(barmode="stack" if stacked else "group", bargroupgap=0.08, height=height or 360, legend_title="",
                      margin=dict(l=10 if horizontal else 50, r=50 if horizontal else 16, t=30, b=40 if horizontal else 60))
    if horizontal:
        fig.update_xaxes(tickformat=tickformat); fig.update_yaxes(automargin=True)
    else:
        fig.update_yaxes(tickformat=tickformat, range=yrange)
    return fig


def lines(x, series: dict, tickformat=".0%", height=340):
    fig = go.Figure()
    for name, y in series.items():
        fig.add_scatter(x=x, y=y, mode="lines+markers", name=name, line=dict(width=2), marker=dict(size=8),
                        hovertemplate=name + ": %{y:" + (".1%" if tickformat == ".0%" else ".1f") + "}<extra></extra>")
    fig.update_layout(hovermode="x unified", yaxis=dict(tickformat=tickformat, rangemode="tozero"), margin=dict(t=40), height=height)
    return fig


def heat(x, y, z, zmin=0, zmax=1, height=560):
    fig = go.Figure(go.Heatmap(x=x, y=y, z=z, colorscale=T.SEQUENTIAL, zmin=zmin, zmax=zmax, xgap=2, ygap=2,
                               colorbar=dict(tickformat=".0%", thickness=10), hovertemplate="%{y} · %{x}: %{z:.0%}<extra></extra>"))
    fig.update_layout(xaxis=dict(tickangle=-45, tickfont=dict(size=10)), yaxis=dict(autorange="reversed", tickfont=dict(size=10), automargin=True),
                      margin=dict(l=10, r=10, t=10, b=120), height=height)
    return fig


def rate(df, col):
    return float(df[col].mean()) if len(df) and df[col].notna().any() else np.nan


# ----------------------------------------------------------------------------
# Layout
# ----------------------------------------------------------------------------
CARD = {"background": "#fff", "border": "1px solid #e3e2dd", "borderRadius": "14px", "padding": "14px 16px 8px", "boxShadow": "0 1px 2px rgba(0,0,0,.04), 0 8px 24px -12px rgba(0,0,0,.12)", "minWidth": 0}
LABEL = {"fontSize": "11px", "textTransform": "uppercase", "letterSpacing": ".06em", "color": "#8a8985", "fontWeight": 600, "marginBottom": "4px"}


def card(title, graph_id, hint=None, span=6, controls=None, height=340, body=None):
    children = [html.H3(title, style={"margin": "0 0 2px", "fontSize": "15px", "fontWeight": 600})]
    if hint:
        children.append(html.P(hint, style={"margin": "0 0 6px", "color": "#8a8985", "fontSize": "12px"}))
    if controls:
        children.append(html.Div(controls, style={"display": "flex", "gap": "12px", "alignItems": "center", "flexWrap": "wrap", "margin": "4px 0 6px", "fontSize": "12px", "color": "#52514e"}))
    children.append(body if body is not None else dcc.Graph(id=graph_id, config={"displayModeBar": False, "responsive": True}, style={"height": f"{height}px"}))
    return html.Div(children, style={**CARD, "gridColumn": f"span {span}"})


def grid(children):
    return html.Div(children, style={"display": "grid", "gridTemplateColumns": "repeat(12, 1fr)", "gap": "14px"})


def slider(id_, lo, hi, val, step=1, marks=None, **kw):
    return dcc.Slider(id=id_, min=lo, max=hi, value=val, step=step, marks=marks, tooltip={"placement": "bottom", "always_visible": False}, **kw)


app = Dash(__name__, title="LS 2.0 Facility Dashboard")
app.index_string = """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>body{margin:0;background:#f4f4f1;color:#0b0b0b;font-family:Inter,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:14px}
.tab{padding:8px 14px!important;border:0!important;background:transparent!important;color:#52514e!important;font-weight:500;border-radius:999px}
.tab--selected{background:#e4effb!important;color:#2a78d6!important;font-weight:600}
.Select-control,.Select-menu-outer{border-color:#e3e2dd!important;border-radius:8px}
@media (max-width:1024px){div[style*="span 4"],div[style*="span 6"],div[style*="span 8"]{grid-column:span 12!important}}</style>
</head><body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body></html>"""

filters = html.Div([
    html.Div([html.Div("LGA", style=LABEL), dcc.Dropdown(id="f-lga", options=LGAS, multi=True, placeholder="All 23 LGAs")]),
    html.Div([html.Div("Facility type", style=LABEL), dcc.Dropdown(id="f-type", options=C.FACILITY_TYPES, multi=True, placeholder="All types")]),
    html.Div([html.Div("Setting", style=LABEL), dcc.Dropdown(id="f-setting", options=["Urban", "Rural"], placeholder="All", clearable=True)]),
    html.Div([html.Div("Security-risk LGA", style=LABEL), dcc.Dropdown(id="f-security", options=[{"label": "Security-risk only", "value": "1"}, {"label": "Other LGAs only", "value": "0"}], placeholder="All", clearable=True)]),
    html.Div([html.Div("Visit rounds", style=LABEL), dcc.RangeSlider(id="f-rounds", min=1, max=N_ROUNDS, step=1, value=[1, N_ROUNDS], marks={r: str(r) for r in range(1, N_ROUNDS + 1)})]),
    html.Div([html.Div("Readiness score range", style=LABEL), dcc.RangeSlider(id="f-readiness", min=0, max=100, step=5, value=[0, 100], marks={0: "0", 50: "50", 100: "100"}, tooltip={"placement": "bottom"})]),
    html.Div([html.Button("Reset filters", id="reset", n_clicks=0, style={"padding": "8px 12px", "borderRadius": "8px", "border": "1px solid #e3e2dd", "background": "#f8f8f6", "cursor": "pointer"}),
              html.Button("Export CSV", id="export", n_clicks=0, style={"padding": "8px 12px", "borderRadius": "8px", "border": "1px solid #2a78d6", "background": "#2a78d6", "color": "#fff", "cursor": "pointer", "marginLeft": "8px"}),
              dcc.Download(id="download")], style={"display": "flex", "alignItems": "end"}),
], style={**CARD, "display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(190px, 1fr))", "gap": "12px 16px", "marginBottom": "12px"})

sel_style = {"fontSize": "12px", "minWidth": "220px"}
tabs = dcc.Tabs(id="tabs", value="overview", parent_className="tabs", className="tabs", children=[
    dcc.Tab(label="Overview", value="overview", className="tab", selected_className="tab--selected", children=[
        html.Div(id="kpis", style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(150px, 1fr))", "gap": "12px", "margin": "14px 0"}),
        grid([card("Readiness score trend by round", "g-trend", "Composite of six pillars; click legend items to compare pillars.", 8),
              card("Readiness band distribution", "g-bands", "Share of filtered visits in each band.", 4),
              card("Readiness by LGA", "g-lga-readiness", "Mean composite score; dotted line is the filtered average.", 6, height=460),
              card("Facility map", "g-map", "Colour = readiness, size = stock-out rate.", 6, height=460),
              card("Readiness pillars by facility type", "g-pillars", None, 12)])]),
    dcc.Tab(label="Access & readiness", value="access", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}), grid([
        card("Open on arrival, by LGA", "g-open-lga", None, 6, height=460), card("Why facilities were closed", "g-closed", None, 6, height=460),
        card("Hours of operation", "g-hours", "By facility type (unique facilities).", 4), card("Emergency referral capacity", "g-referral", None, 4), card("Cold chain equipment", "g-cce", "Availability vs functionality where available.", 4),
        card("Service availability & session completion", "g-services", None, 6, height=440),
        card("Why planned sessions were missed", "g-session-reasons", None, 6, height=440, controls=[html.Span("Service"), dcc.Dropdown(id="s-service", options=C.SERVICES, placeholder="All services", style=sel_style)]),
        card("Training coverage (past 2 years)", "g-training", "Share of filtered facilities with staff trained, by training type.", 12, height=440)])]),
    dcc.Tab(label="Human resources", value="hrh", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}), grid([
        card("Attendance of scheduled permanent staff, by cadre", "g-att-cadre", "Present ÷ scheduled.", 6, height=420), card("Attendance by LGA", "g-att-lga", None, 6, height=460),
        card("Why permanent staff were absent", "g-absence", None, 6, height=440, controls=[html.Span("Cadre"), dcc.Dropdown(id="s-cadre", options=C.CADRES, placeholder="All cadres", style=sel_style), html.Span("Top"), html.Div(slider("s-top", 5, 20, 10, marks={5: "5", 10: "10", 15: "15", 20: "20"}), style={"width": "200px"})]),
        card("Workforce composition by cadre", "g-workforce", "Headcount at the first selected round.", 6, height=440),
        card("Salary timeliness & attendance by round", "g-salary-trend", None, 6), card("Attendance by salary timeliness and roster practice", "g-salary-roster", None, 6),
        card("How often staff leave the post to access salary", "g-leave-salary", None, 6), card("Attendance vs distance to LGA headquarters", "g-att-distance", "Each point is a facility.", 6)])]),
    dcc.Tab(label="Supply chain", value="supply", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}), grid([
        card("Stock-out rate by commodity", "g-stockout-com", None, 6, height=560, controls=[html.Span("Category"), dcc.Dropdown(id="s-category", options=sorted({c[1] for c in C.COMMODITIES}), placeholder="All categories", style=sel_style)]),
        card("Stock-out heatmap: LGA × commodity", "g-stockout-heat", None, 6, height=560),
        card("Main reasons for stock-outs", "g-stockout-reasons", None, 6, height=440, controls=[html.Span("Commodity"), dcc.Dropdown(id="s-commodity", options=[c[0] for c in C.COMMODITIES], placeholder="All commodities", style=sel_style)]),
        card("Requisition funnel", "g-funnel", "Submitted → complete & on time → fully received → documented.", 6, height=440),
        card("Stock-out rate by supplier", "g-supplier", None, 4), card("Requisition behaviour vs stock-outs", "g-req-behaviour", None, 4),
        card("Below minimum stock (early warning)", "g-below-min", None, 4, controls=[html.Span("Show items ≥"), html.Div(slider("s-minrate", 0, 100, 0, 5, marks={0: "0%", 50: "50%", 100: "100%"}), style={"width": "200px"})]),
        card("Stock-out trend by category and round", "g-stockout-trend", None, 12)])]),
    dcc.Tab(label="Vaccines", value="vaccines", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}), grid([
        card("Vaccine availability (stocking facilities)", "g-vac-avail", None, 6, height=420), card("Doses used, by vaccine", "g-vac-doses", None, 6, height=420),
        card("Vaccine stocking status", "g-vac-status", None, 4), card("Availability by cold chain status", "g-vac-cce", None, 4), card("Cold chain interruption reasons", "g-cc-reasons", None, 4),
        card("Vaccine availability by LGA and round", "g-vac-heat", None, 12, height=520)])]),
    dcc.Tab(label="Predictions", value="predict", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}),
        html.Div("Models are trained on one visit to predict the next. Scores are for the latest round of each facility in the current LGA / type filter (round sliders do not apply).",
                 style={"background": "#e4effb", "border": "1px solid #bcd3f0", "borderRadius": "10px", "padding": "10px 14px", "color": "#52514e", "fontSize": "13px", "marginBottom": "14px"}),
        html.Div(id="models", style={"display": "grid", "gridTemplateColumns": "repeat(auto-fit, minmax(260px, 1fr))", "gap": "12px", "marginBottom": "14px"}),
        grid([card("Facilities at risk of dropping below readiness 65 at the next visit", None, None, 12,
                   controls=[html.Span("Risk threshold"), html.Div(slider("s-risk", 0, 100, 50, 5, marks={0: "0%", 50: "50%", 100: "100%"}), style={"width": "260px"}), html.Span(id="risk-count")],
                   body=dash_table.DataTable(id="risk-table", page_size=15, sort_action="native", style_table={"overflowX": "auto"},
                                             style_cell={"fontFamily": "Inter", "fontSize": "12px", "padding": "6px 8px", "textAlign": "left"},
                                             style_header={"fontWeight": 600, "textTransform": "uppercase", "fontSize": "11px", "color": "#8a8985", "backgroundColor": "#fff"},
                                             style_data_conditional=[{"if": {"filter_query": "{At-risk prob.} >= 0.8", "column_id": "At-risk prob."}, "color": "#d03b3b", "fontWeight": 600}])),
              card("Commodity stock-out risk at next visit", "g-so-risk", "Facility × commodity pairs above the threshold, ranked.", 6, height=560,
                   controls=[html.Span("Min risk"), html.Div(slider("s-sorisk", 0, 100, 60, 5, marks={0: "0%", 50: "50%", 100: "100%"}), style={"width": "220px"})]),
              card("Expected attendance gain if salary is paid on time", "g-cf-salary", "Counterfactual from the attendance driver model (latest round).", 6, height=560),
              card("Stock-out model: what matters", "g-ml-so-imp", None, 6, height=440), card("Stock-out model: ROC (held-out round)", "g-ml-so-roc", None, 6, height=440),
              card("At-risk model: what matters", "g-ml-risk-imp", None, 6, height=440), card("Attendance driver model: what matters", "g-ml-att-imp", None, 6, height=440),
              card("Facility segments", "g-segments", "K-means on the mean readiness pillars per facility.", 12, height=440)])]),
    dcc.Tab(label="Insights", value="insights", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}), html.Div(id="qa")]),
    dcc.Tab(label="Data", value="data", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}),
        html.Div(id="data-count", style={"color": "#52514e", "marginBottom": "8px"}),
        dash_table.DataTable(id="data-table", page_size=25, sort_action="native", filter_action="native", style_table={"overflowX": "auto"},
                             style_cell={"fontFamily": "Inter", "fontSize": "12px", "padding": "6px 8px", "textAlign": "left"},
                             style_header={"fontWeight": 600, "textTransform": "uppercase", "fontSize": "11px", "color": "#8a8985", "backgroundColor": "#fff"})]),
])

app.layout = html.Div([
    html.Div([html.Div([html.Span(style={"display": "inline-block", "width": "12px", "height": "12px", "borderRadius": "50%", "background": "#2a78d6", "marginRight": "10px"}),
                        html.Span("LS 2.0 Facility Dashboard", style={"fontWeight": 700, "fontSize": "16px"}),
                        html.Span(" · Bi-weekly PHC monitoring · Kaduna State · pure-Python (Dash) edition", style={"color": "#8a8985", "fontSize": "12px"})],
                       style={"maxWidth": "1440px", "margin": "0 auto", "padding": "12px 16px"})],
             style={"background": "#fff", "borderBottom": "1px solid #e3e2dd", "position": "sticky", "top": 0, "zIndex": 10}),
    html.Div([filters, html.P(id="summary", style={"color": "#52514e", "margin": "0 0 8px 2px", "fontSize": "13px"}), tabs,
              html.Footer(f"LS 2.0 facility survey analytics · {len(V):,} visits · {len(LGAS)} LGAs · dataset generated from the questionnaire structure",
                          style={"color": "#8a8985", "fontSize": "12px", "textAlign": "center", "padding": "24px 0"})],
             style={"maxWidth": "1440px", "margin": "0 auto", "padding": "16px"}),
])

FILTER_INPUTS = [Input("f-lga", "value"), Input("f-type", "value"), Input("f-setting", "value"), Input("f-security", "value"), Input("f-rounds", "value"), Input("f-readiness", "value")]


# ----------------------------------------------------------------------------
# Callbacks
# ----------------------------------------------------------------------------
@app.callback(Output("f-lga", "value"), Output("f-type", "value"), Output("f-setting", "value"), Output("f-security", "value"),
              Output("f-rounds", "value"), Output("f-readiness", "value"), Input("reset", "n_clicks"), prevent_initial_call=True)
def reset(_):
    return [], [], None, None, [1, N_ROUNDS], [0, 100]


@app.callback(Output("summary", "children"), *FILTER_INPUTS)
def summary(lgas, types, setting, security, rounds, readiness):
    f = filtered(lgas, types, setting, security, rounds, readiness)
    return [f"Showing ", html.B(f"{len(f['v']):,}"), " visits to ", html.B(str(f["v"].facility_id.nunique())),
            f" facilities · rounds {rounds[0]}–{rounds[1]} ({ROUND_NAME[rounds[0]]} → {ROUND_NAME[rounds[1]]}) · {len(lgas) if lgas else 'all 23'} LGA(s) · {', '.join(types) if types else 'all facility types'}"]


@app.callback(Output("download", "data"), Input("export", "n_clicks"), [State(i.component_id, "value") for i in FILTER_INPUTS], prevent_initial_call=True)
def export(_, *fv):
    return dcc.send_data_frame(filtered(*fv)["v"].to_csv, "ls2_filtered_visits.csv", index=False)


def kpi(label, value, sub, tone=""):
    color = {"good": T.STATUS["good"], "warn": T.STATUS["serious"], "bad": T.STATUS["critical"]}.get(tone, "#0b0b0b")
    return html.Div([html.Div(label, style={**LABEL, "fontSize": "12px"}), html.Div(value, style={"fontSize": "26px", "fontWeight": 700, "color": color, "margin": "4px 0 2px"}),
                     html.Div(sub, style={"fontSize": "12px", "color": "#52514e"})], style=CARD)


def tone(x, good, bad, invert=False):
    if x is None or pd.isna(x):
        return ""
    g = x <= good if invert else x >= good
    b = x >= bad if invert else x <= bad
    return "good" if g else "bad" if b else "warn"


@app.callback(Output("kpis", "children"), Output("g-trend", "figure"), Output("g-bands", "figure"), Output("g-lga-readiness", "figure"),
              Output("g-map", "figure"), Output("g-pillars", "figure"), Input("tabs", "value"), *FILTER_INPUTS)
def overview(tab, *fv):
    if tab != "overview":
        return [no_update] * 6
    f = filtered(*fv); v = f["v"]
    if v.empty:
        return [kpi("Visits", "0", "no visits match")], empty(), empty(), empty(), empty(), empty()
    att = v.permanent_present_today.sum() / max(1, v.permanent_scheduled_today.sum())
    so = rate(f["com"], "stockout_flag"); vac = rate(f["vac"], "in_stock_flag"); ready = rate(v, "readiness_score")
    cc = rate(v[v.has_cold_chain_equipment_flag == 1], "cold_chain_interruption_since_last_visit_flag")
    kp = [kpi("Visits", f"{len(v):,}", f"{v.facility_id.nunique()} facilities"), kpi("Mean readiness", f"{ready:.1f}", "composite score /100", tone(ready, 75, 60)),
          kpi("Open on arrival", pct(rate(v, 'facility_open_on_arrival_flag')), "share of visits", tone(rate(v, 'facility_open_on_arrival_flag'), .85, .7)),
          kpi("Staff attendance", pct(att), "permanent present ÷ scheduled", tone(att, .8, .65)), kpi("Stock-out rate", pct(so), "tracer items stocked out", tone(so, .2, .35, True)),
          kpi("Vaccine availability", pct(vac), "antigens in stock", tone(vac, .8, .6)), kpi("Sessions completed", pct(rate(v, 'session_completion_rate')), "planned sessions delivered", tone(rate(v, 'session_completion_rate'), .85, .7)),
          kpi("Cold chain interruptions", pct(cc), "facilities with CCE", tone(cc, .1, .25, True)), kpi("Salary on time", pct(rate(v, 'salary_paid_on_time_last_3_months_flag')), "last 3 months", tone(rate(v, 'salary_paid_on_time_last_3_months_flag'), .8, .5))]
    byr = v.groupby("round_number"); x = [ROUND_NAME[r] for r in byr.groups]
    trend = go.Figure()
    for i, (col, name, m) in enumerate([("readiness_score", "Readiness", 1), ("facility_open_on_arrival_flag", "Open on arrival", 100), ("attendance_rate", "Attendance", 100), ("stockout_rate", "Stock-out rate", 100), ("vaccine_availability_rate", "Vaccine availability", 100), ("session_completion_rate", "Session completion", 100)]):
        trend.add_scatter(x=x, y=byr[col].mean() * m, mode="lines+markers", name=name, line=dict(width=3 if i == 0 else 2), marker=dict(size=8), visible=True if i == 0 else "legendonly", hovertemplate=name + ": %{y:.1f}<extra></extra>")
    trend.update_layout(hovermode="x unified", yaxis=dict(title="Score / rate (0-100)", rangemode="tozero"), margin=dict(t=40), height=340)
    bands = ["Strong", "Fair", "Weak", "Critical"]; bc = v.readiness_band.value_counts()
    pie = go.Figure(go.Pie(labels=bands, values=[int(bc.get(b, 0)) for b in bands], hole=.55, sort=False, marker=dict(colors=[T.STATUS["good"], T.SERIES[0], T.STATUS["serious"], T.STATUS["critical"]], line=dict(color="#fff", width=2)), textinfo="label+percent"))
    pie.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=340)
    byl = v.groupby("lga").readiness_score.mean().sort_values()
    lga_fig = hbar(byl.index, byl.values, fmt=".1f", line=ready, xmax=100, height=460)
    byf = v.groupby(["facility_id", "facility_name", "lga", "facility_type", "latitude", "longitude"]).agg(r=("readiness_score", "mean"), so=("stockout_rate", "mean"), att=("attendance_rate", "mean")).reset_index()
    mp = px.scatter_map(byf, lat="latitude", lon="longitude", color="r", size=byf.so.fillna(0) * 18 + 4, size_max=18, hover_name="facility_name",
                        hover_data={"lga": True, "facility_type": True, "r": ":.1f", "so": ":.1%", "att": ":.1%", "latitude": False, "longitude": False},
                        color_continuous_scale=T.SEQUENTIAL, range_color=[40, 95], zoom=6.4, center=dict(lat=10.35, lon=7.7), labels={"r": "Readiness", "so": "Stock-out", "att": "Attendance"})
    mp.update_layout(map_style="carto-positron", margin=dict(l=0, r=0, t=0, b=0), height=460, coloraxis_colorbar=dict(title="Readiness", thickness=10))
    types = [t for t in C.FACILITY_TYPES if (v.facility_type == t).any()]; byt = v.groupby("facility_type")
    pl = [("facility_open_on_arrival_flag", "Open on arrival", False), ("attendance_rate", "Attendance", False), ("stockout_rate", "Stock availability", True), ("vaccine_availability_rate", "Vaccine availability", False), ("session_completion_rate", "Session completion", False), ("cce_functionality_rate", "Cold chain functional", False)]
    pillars = grouped([p[1] for p in pl], {t: [(1 - byt.get_group(t)[c].mean()) if inv else byt.get_group(t)[c].mean() for c, _, inv in pl] for t in types}, yrange=[0, 1.08])
    return kp, trend, pie, lga_fig, mp, pillars


@app.callback(Output("g-open-lga", "figure"), Output("g-closed", "figure"), Output("g-hours", "figure"), Output("g-referral", "figure"), Output("g-cce", "figure"),
              Output("g-services", "figure"), Output("g-session-reasons", "figure"), Output("g-training", "figure"), Input("tabs", "value"), Input("s-service", "value"), *FILTER_INPUTS)
def access(tab, service, *fv):
    if tab != "access":
        return [no_update] * 8
    f = filtered(*fv); v = f["v"]
    if v.empty:
        return [empty()] * 8
    byl = v.groupby("lga").facility_open_on_arrival_flag.mean().sort_values()
    open_lga = hbar(byl.index, byl.values, line=rate(v, "facility_open_on_arrival_flag"), xmax=1.1, height=460)
    closed = v[v.facility_open_on_arrival_flag == 0].reason_closed_on_arrival.fillna("Not recorded").value_counts(normalize=True).sort_values()
    closed_fig = hbar(closed.index, closed.values, color=T.SERIES[1], height=460)
    first = v.sort_values("round_number").drop_duplicates("facility_id"); types = [t for t in C.FACILITY_TYPES if (first.facility_type == t).any()]
    hours = grouped(types, {h: [int(((first.facility_type == t) & (first.hours_of_operation == h)).sum()) for t in types] for h in C.HOURS_OF_OPERATION}, stacked=True, fmt=None, tickformat="")
    referral = hbar(["Can refer emergencies", "Transport available when needed"], [rate(v, "can_refer_emergencies_flag"), rate(v[v.can_refer_emergencies_flag == 1], "emergency_transport_available_2wks_flag")], color=T.SERIES[2], xmax=1.15, height=340)
    c = f["cce"].groupby("cce_type"); cce_t = list(c.groups)
    cce = grouped(cce_t, {"Available": [c.get_group(t).available_flag.mean() for t in cce_t], "Functional (where available)": [c.get_group(t).query("available_flag==1").functional_flag.mean() for t in cce_t]}, horizontal=True, fmt=None, height=340)
    s = f["ses"].groupby("service")
    services = grouped(C.SERVICES, {"Offered": [s.get_group(x).offered_flag.mean() for x in C.SERVICES], "All planned sessions conducted": [s.get_group(x).query("offered_flag==1").all_conducted_flag.mean() for x in C.SERVICES]}, horizontal=True, fmt=None, height=440)
    missed = f["ses"][(f["ses"].all_conducted_flag == 0) & ((f["ses"].service == service) if service else True)].reason_not_conducted.fillna("Not recorded").value_counts(normalize=True).sort_values()
    session_reasons = hbar(missed.index, missed.values, color=T.SERIES[1], height=440)
    n = max(1, v.facility_id.nunique()); tr = (f["trn"].groupby("training").facility_id.nunique() / n).sort_values()
    training = hbar(tr.index, tr.values, color=T.SERIES[6], height=440)
    return open_lga, closed_fig, hours, referral, cce, services, session_reasons, training


@app.callback(Output("g-att-cadre", "figure"), Output("g-att-lga", "figure"), Output("g-absence", "figure"), Output("g-workforce", "figure"), Output("g-salary-trend", "figure"),
              Output("g-salary-roster", "figure"), Output("g-leave-salary", "figure"), Output("g-att-distance", "figure"), Input("tabs", "value"), Input("s-cadre", "value"), Input("s-top", "value"), *FILTER_INPUTS)
def hrh(tab, cadre, top, *fv):
    if tab != "hrh":
        return [no_update] * 8
    f = filtered(*fv); v = f["v"]; st = f["stf"]
    if v.empty:
        return [empty()] * 8
    overall = st.permanent_present_today.sum() / max(1, st.permanent_scheduled_today.sum())
    g = st.groupby("cadre")[["permanent_present_today", "permanent_scheduled_today"]].sum(); g = g[g.permanent_scheduled_today > 0]
    att_c = (g.permanent_present_today / g.permanent_scheduled_today).sort_values()
    att_cadre = hbar(att_c.index, att_c.values, fmt=".1%", line=overall, xmax=1.1, height=420)
    gl = st.groupby("lga")[["permanent_present_today", "permanent_scheduled_today"]].sum(); att_l = (gl.permanent_present_today / gl.permanent_scheduled_today.replace(0, np.nan)).sort_values()
    att_lga = hbar(att_l.index, att_l.values, line=overall, xmax=1.1, height=460)
    ab = f["abs"][(f["abs"].cadre == cadre) if cadre else slice(None)] if cadre else f["abs"]
    ar = (ab.groupby("reason").staff_count.sum() / max(1, ab.staff_count.sum())).sort_values(ascending=False).head(int(top)).sort_values()
    absence = hbar(ar.index, ar.values, fmt=".1%", color=T.SERIES[1], height=440)
    base = st[st.round_number == f["r0"]].groupby("cadre")[["permanent", "adhoc_a", "adhoc_b", "volunteer"]].sum().reindex(C.CADRES[::-1]).fillna(0)
    workforce = grouped(list(base.index), {n: base[c].tolist() for c, n in [("permanent", "Permanent"), ("adhoc_a", "Ad hoc A"), ("adhoc_b", "Ad hoc B"), ("volunteer", "Volunteer")]}, horizontal=True, stacked=True, fmt=None, tickformat="", height=440)
    byr = v.groupby("round_number"); x = [ROUND_NAME[r] for r in byr.groups]
    salary_trend = lines(x, {"Salary paid on time": byr.salary_paid_on_time_last_3_months_flag.mean(), "Staff attendance": byr.attendance_rate.mean(), "Sessions completed": byr.session_completion_rate.mean()})
    def att_of(mask):
        a = v[mask]; s = a.permanent_scheduled_today.sum(); return a.permanent_present_today.sum() / s if s else np.nan
    sal_on, sal_off = v.salary_paid_on_time_last_3_months_flag == 1, v.salary_paid_on_time_last_3_months_flag == 0
    ro_on = v.roster_updated_this_week_flag == 1
    salary_roster = grouped(["Salary on time", "Salary delayed"], {"Roster updated this week": [att_of(sal_on & ro_on), att_of(sal_off & ro_on)], "Roster not updated": [att_of(sal_on & ~ro_on), att_of(sal_off & ~ro_on)]}, yrange=[0, 1])
    leave = grouped(C.LEAVE_FOR_SALARY_FREQ, {s: [((v.urban_rural == s) & (v.staff_leave_facility_for_salary_frequency == fq)).sum() / max(1, (v.urban_rural == s).sum()) for fq in C.LEAVE_FOR_SALARY_FREQ] for s in ["Urban", "Rural"]}, yrange=[0, .7])
    byf = v.groupby(["facility_name", "lga", "facility_type", "distance_to_lga_hq_km", "total_health_workers"]).attendance_rate.mean().reset_index()
    dist = px.scatter(byf, x="distance_to_lga_hq_km", y="attendance_rate", size="total_health_workers", hover_name="facility_name", hover_data=["lga", "facility_type"], color_discrete_sequence=[T.SERIES[0]], opacity=.6, size_max=16)
    dist.update_layout(xaxis_title="Distance to LGA HQ (km)", yaxis=dict(tickformat=".0%", title="Mean attendance", range=[0, 1.05]), height=340)
    return att_cadre, att_lga, absence, workforce, salary_trend, salary_roster, leave, dist


@app.callback(Output("g-stockout-com", "figure"), Output("g-stockout-heat", "figure"), Output("g-stockout-reasons", "figure"), Output("g-funnel", "figure"), Output("g-supplier", "figure"),
              Output("g-req-behaviour", "figure"), Output("g-below-min", "figure"), Output("g-stockout-trend", "figure"),
              Input("tabs", "value"), Input("s-category", "value"), Input("s-commodity", "value"), Input("s-minrate", "value"), *FILTER_INPUTS)
def supply(tab, category, commodity, minrate, *fv):
    if tab != "supply":
        return [no_update] * 8
    f = filtered(*fv); v = f["v"]; com = f["com"]
    if com.empty:
        return [empty()] * 8
    cm = com[com.category == category] if category else com
    byc = cm.groupby(["commodity", "category"]).stockout_flag.mean().reset_index().sort_values("stockout_flag")
    so_com = px.bar(byc, x="stockout_flag", y="commodity", color="category", orientation="h", text=byc.stockout_flag.map(lambda x: f"{x:.0%}"), color_discrete_map={"Maternal": T.SERIES[1], "Child": T.SERIES[2], "General": T.SERIES[0], "Family Planning": T.SERIES[6]})
    so_com.update_traces(textposition="outside", cliponaxis=False, width=.62); so_com.update_layout(xaxis=dict(tickformat=".0%", range=[0, byc.stockout_flag.max() * 1.2]), yaxis_title="", xaxis_title="", legend_title="", margin=dict(l=10, r=40, t=30, b=40), height=560)
    piv = cm.pivot_table(index="lga", columns="commodity", values="stockout_flag", aggfunc="mean").reindex(columns=byc.commodity)
    heat_fig = heat(list(piv.columns), list(piv.index), piv.values, zmax=.7)
    so = com[(com.stockout_flag == 1) & ((com.commodity == commodity) if commodity else True)].stockout_reason.fillna("Not recorded").value_counts(normalize=True).sort_values()
    reasons = hbar(so.index, so.values, color=T.SERIES[1], height=440)
    sub = v[v.requisition_submitted_last_cycle_flag == 1]; rec = sub[sub.requisition_receipt_status.notna()]
    stages = [("Submitted requisition", rate(v, "requisition_submitted_last_cycle_flag")), ("Complete & on time", rate(sub, "requisition_complete_on_time_flag")),
              ("Fully received", (rec.requisition_receipt_status == "Yes, all items received").mean() if len(rec) else np.nan), ("Delivery documented", rate(rec[rec.requisition_receipt_status != "No, none received yet"], "delivery_documentation_provided_flag"))]
    funnel = go.Figure(go.Funnel(y=[s[0] for s in stages], x=[s[1] for s in stages], texttemplate="%{value:.0%}", marker=dict(color=[T.SERIES[0], T.SERIES[2], T.SERIES[3], T.SERIES[6]])))
    funnel.update_layout(margin=dict(l=10, r=10, t=10, b=10), height=440, yaxis=dict(automargin=True))
    sp = com[com.supplier.notna()].groupby("supplier").stockout_flag.agg(["mean", "count"]); sp = sp[sp["count"] >= 30]["mean"].sort_values()
    supplier = hbar(sp.index, sp.values, height=340)
    kn = ["Yes, I know how to calculate", "Yes, someone else is assigned to calculate", "No"]
    req = grouped(["Knows how", "Someone else does", "Nobody"], {n: [com[(com.knows_min_stock_calculation == k) & (com.requisition_submitted_last_cycle_flag == flag)].stockout_flag.mean() for k in kn] for n, flag in [("Requisition submitted", 1), ("No requisition", 0)]}, yrange=[0, .6])
    bm = com[com.below_min_stock_flag.notna()].groupby("commodity").below_min_stock_flag.mean(); bm = bm[bm >= minrate / 100].sort_values()
    below = hbar(bm.index, bm.values, color=T.SERIES[3], xmax=1.15, height=340)
    byr = com.groupby(["round_number", "category"]).stockout_flag.mean().unstack(); x = [ROUND_NAME[r] for r in byr.index]
    trend = lines(x, {c: byr[c] for c in byr.columns})
    return so_com, heat_fig, reasons, funnel, supplier, req, below, trend


@app.callback(Output("g-vac-avail", "figure"), Output("g-vac-doses", "figure"), Output("g-vac-status", "figure"), Output("g-vac-cce", "figure"), Output("g-cc-reasons", "figure"), Output("g-vac-heat", "figure"),
              Input("tabs", "value"), *FILTER_INPUTS)
def vaccines(tab, *fv):
    if tab != "vaccines":
        return [no_update] * 6
    f = filtered(*fv); v = f["v"]; vac = f["vac"]
    if v.empty:
        return [empty()] * 6
    byv = vac.groupby("vaccine").agg(r=("in_stock_flag", "mean"), d=("doses_used", "sum"))
    avail = hbar(byv.r.sort_values().index, byv.r.sort_values().values, line=rate(vac, "in_stock_flag"), xmax=1.15, height=420)
    doses = hbar(byv.d.sort_values().index, byv.d.sort_values().values, fmt=",", color=T.SERIES[2], height=420)
    first = v.sort_values("round_number").drop_duplicates("facility_id"); vc = first.vaccine_stock_status.value_counts()
    status = go.Figure(go.Pie(labels=["Stocks vaccines", "Immunises, no stock", "No immunisation"], values=[int(vc.get(s, 0)) for s in C.VACCINE_STOCK_STATUS], hole=.55, sort=False, marker=dict(colors=[T.SERIES[0], T.SERIES[3], T.SERIES[7]], line=dict(color="#fff", width=2)), textinfo="label+percent"))
    status.update_layout(showlegend=False, margin=dict(l=10, r=10, t=10, b=10), height=340)
    fr = vac.vaccine_fridge_functional_flag == 1; it = vac.cold_chain_interruption_since_last_visit_flag == 1
    vac_cce = grouped(["Working fridge", "No working fridge"], {"No interruption": [vac[fr & ~it].in_stock_flag.mean(), vac[~fr & ~it].in_stock_flag.mean()], "Interruption since last visit": [vac[fr & it].in_stock_flag.mean(), vac[~fr & it].in_stock_flag.mean()]}, yrange=[0, 1])
    ccr = v[v.cold_chain_interruption_since_last_visit_flag == 1].cold_chain_interruption_reason.fillna("Not recorded").value_counts().sort_values()
    cc_reasons = hbar(ccr.index, ccr.values, fmt=",", color=T.SERIES[1], height=340)
    piv = vac.pivot_table(index="lga", columns="round_number", values="in_stock_flag", aggfunc="mean")
    vac_heat = heat([ROUND_NAME[r] for r in piv.columns], list(piv.index), piv.values, zmin=.3, zmax=1, height=520)
    vac_heat.update_layout(margin=dict(b=40)); vac_heat.update_xaxes(tickangle=0)
    return avail, doses, status, vac_cce, cc_reasons, vac_heat


def model_card(title, rows, desc):
    return html.Div([html.H4(title, style={"margin": "0 0 6px", "fontSize": "14px"})] +
                    [html.Div([html.Span(k), html.B(str(val))], style={"display": "flex", "justifyContent": "space-between", "fontSize": "13px", "padding": "3px 0", "borderBottom": "1px dashed #e3e2dd"}) for k, val in rows] +
                    [html.Div(desc, style={"color": "#8a8985", "fontSize": "12px", "marginTop": "6px"})], style=CARD)


def importance_fig(items):
    items = items[:12][::-1]
    return hbar([i["feature"].replace("_", " ") for i in items], [i["importance"] for i in items], fmt=".3f", color=T.SERIES[6], height=440)


@app.callback(Output("models", "children"), Output("risk-table", "data"), Output("risk-table", "columns"), Output("risk-count", "children"), Output("g-so-risk", "figure"), Output("g-cf-salary", "figure"),
              Output("g-ml-so-imp", "figure"), Output("g-ml-so-roc", "figure"), Output("g-ml-risk-imp", "figure"), Output("g-ml-att-imp", "figure"), Output("g-segments", "figure"),
              Input("tabs", "value"), Input("s-risk", "value"), Input("s-sorisk", "value"), *FILTER_INPUTS)
def predict(tab, risk_thr, so_thr, *fv):
    if tab != "predict":
        return [no_update] * 11
    f = filtered(*fv); m = D["ml"]
    best = m["stockout"]["best_model"]; cs = m["stockout"]["candidates"][best]
    cards = [model_card(m["stockout"]["name"], [("Best model", best.replace("_", " ")), ("ROC AUC (held-out round)", f"{cs['roc_auc']:.3f}"), ("Average precision", f"{cs['avg_precision']:.3f}"), ("Base rate", pct(m["stockout"]["positive_rate_test"])), ("Training rows", f"{m['stockout']['train_rows']:,}")],
                        "Predicts, per facility × commodity, whether a stock-out will be recorded at the next visit."),
             model_card(m["at_risk"]["name"], [("Model", "random forest"), ("ROC AUC (held-out round)", f"{m['at_risk']['metrics']['roc_auc']:.3f}"), ("Average precision", f"{m['at_risk']['metrics']['avg_precision']:.3f}"), ("Base rate", pct(m["at_risk"]["metrics"]["positive_rate_test"])), ("Training rows", f"{m['at_risk']['train_rows']:,}")],
                        "Flags facilities likely to fall into the Weak/Critical bands next round."),
             model_card(m["attendance"]["name"], [("Model", "gradient boosting"), ("R² (grouped CV)", f"{m['attendance']['metrics']['grouped_cv_r2']:.2f}"), ("R² headcount-weighted", f"{m['attendance']['metrics']['grouped_cv_r2_headcount_weighted']:.2f}"), ("MAE vs naive", f"{m['attendance']['metrics']['grouped_cv_mae']:.3f} vs {m['attendance']['metrics']['naive_global_mean_mae']:.3f}"), ("Gain if salary on time", "+" + pct(m["attendance"]["metrics"]["mean_gain_salary_on_time"]))],
                        "Explains expected attendance from salary, roster, distance, size and security; used for what-if scenarios."),
             model_card("Facility segmentation", [("Method", f"k-means (k={m['segmentation']['k']})"), ("Silhouette", f"{m['segmentation']['silhouette']:.2f}")] + [(k, f"{n} facilities") for k, n in m["segmentation"]["segment_sizes"].items()],
                        "Mean profile across the readiness pillars; segments guide, not dictate, the support package.")]
    fp = f["fpred"].sort_values("at_risk_probability", ascending=False); flagged = fp[fp.at_risk_probability >= risk_thr / 100]
    cols = [("facility_name", "Facility"), ("lga", "LGA"), ("facility_type", "Type"), ("segment", "Segment"), ("readiness_score", "Readiness (latest)"), ("at_risk_probability", "At-risk prob."), ("mean_stockout_risk", "Mean stock-out risk"), ("attendance_rate", "Attendance (latest)"), ("expected_attendance_if_salary_on_time", "Expected att. if salary on time"), ("stockout_rate", "Stock-out rate (latest)")]
    table = flagged[[c for c, _ in cols]].rename(columns=dict(cols)).round(3)
    columns = [{"name": n, "id": n, "type": "numeric", "format": {"specifier": ".0%"}} if n in ("At-risk prob.", "Mean stock-out risk", "Attendance (latest)", "Expected att. if salary on time", "Stock-out rate (latest)") else {"name": n, "id": n} for _, n in cols]
    cp = f["cpred"][f["cpred"].stockout_risk >= so_thr / 100].sort_values("stockout_risk", ascending=False).head(30)[::-1]
    so_risk = hbar((cp.facility_name + " · " + cp.commodity).tolist(), cp.stockout_risk.tolist(), color=T.STATUS["critical"], xmax=1.15, height=560)
    cf = f["fpred"].assign(gain=lambda d: d.expected_attendance_if_salary_on_time - d.expected_attendance); cf = cf[cf.gain > .005].sort_values("gain", ascending=False).head(30)[::-1]
    cf_fig = hbar((cf.facility_name + " (" + cf.lga + ")").tolist(), cf.gain.tolist(), fmt=".1%", color=T.STATUS["good"], height=560)
    roc = go.Figure(D["ml_figs"]["stockout_roc"]); roc.update_layout(title=None, height=440, template="ls2")
    cen = pd.DataFrame(m["segmentation"]["centres"]); seg_cols = [c for c in cen.columns if c != "segment_id"]
    segments = grouped([c.replace("_flag", "").replace("_rate", "").replace("_", " ") for c in seg_cols], {r["segment_id"]: [r[c] for c in seg_cols] for _, r in cen.iterrows()}, yrange=[0, 1.1], height=440)
    return cards, table.to_dict("records"), columns, f"{len(flagged)} of {len(fp)} facilities flagged", so_risk, cf_fig, importance_fig(m["stockout"]["importance"]), roc, importance_fig(m["at_risk"]["importance"]), importance_fig(m["attendance"]["importance"]), segments


@app.callback(Output("qa", "children"), Input("tabs", "value"))
def insights(tab):
    if tab != "insights":
        return no_update
    out, section = [], None
    for a in D["analysis"]:
        if a["section"] != section:
            section = a["section"]; out.append(html.H2(section, style={"fontSize": "18px", "margin": "20px 0 10px"}))
        out.append(html.Details([html.Summary([html.Span(a["id"], style={"color": "#8a8985", "fontSize": "12px", "marginRight": "10px"}), html.B(a["question"])], style={"padding": "10px 14px", "cursor": "pointer"}),
                                 html.Div([html.P(a["answer"]), html.A("Open interactive figure ↗", href=f"/figures/{a['id']}.html", target="_blank", style={"fontSize": "12px"})], style={"padding": "0 14px 12px 40px", "color": "#52514e"})],
                                style={**CARD, "padding": 0, "marginBottom": "8px"}))
    return out


DATA_COLS = [("facility_name", "Facility"), ("lga", "LGA"), ("facility_type", "Type"), ("round_name", "Round"), ("visit_date", "Date"), ("readiness_score", "Readiness"), ("readiness_band", "Band"), ("facility_open_on_arrival_flag", "Open"),
             ("attendance_rate", "Attendance"), ("stockout_rate", "Stock-out"), ("vaccine_availability_rate", "Vaccines"), ("session_completion_rate", "Sessions"), ("cce_functionality_rate", "Cold chain"), ("salary_paid_on_time_last_3_months_flag", "Salary on time"), ("requisition_submitted_last_cycle_flag", "Requisition"), ("total_health_workers", "Health workers")]


@app.callback(Output("data-table", "data"), Output("data-table", "columns"), Output("data-count", "children"), Input("tabs", "value"), *FILTER_INPUTS)
def data(tab, *fv):
    if tab != "data":
        return no_update, no_update, no_update
    v = filtered(*fv)["v"][[c for c, _ in DATA_COLS]].rename(columns=dict(DATA_COLS)).round(3)
    pct_cols = {"Attendance", "Stock-out", "Vaccines", "Sessions", "Cold chain"}
    cols = [{"name": n, "id": n, "type": "numeric", "format": {"specifier": ".1%"}} if n in pct_cols else {"name": n, "id": n} for _, n in DATA_COLS]
    return v.to_dict("records"), cols, f"{len(v):,} filtered visit records (sort or filter any column; Export CSV downloads the full selection)"


# Serve the standalone question figures alongside the app
@app.server.route("/figures/<path:name>")
def figure(name):
    from flask import send_from_directory
    return send_from_directory(C.FIGURE_DIR, name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=8050); ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    app.run(host=a.host, port=a.port, debug=a.debug)

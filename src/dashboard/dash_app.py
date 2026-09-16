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
import os
import sys
from pathlib import Path

import pandas as pd
from dash import Dash, Input, Output, State, dash_table, dcc, html, no_update

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from analysis import theme as T  # noqa: E402

from dashboard import charts as CH  # noqa: E402

D = CH.load_data()
V = D["visits"]
ROUND_NAME = D["round_name"]
N_ROUNDS = D["n_rounds"]
LGAS = D["lgas"]
pct = CH.pct


def filtered(*fv):
    return CH.filtered(D, *fv)


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
server = app.server  # WSGI entry point for gunicorn / Render / Docker: `gunicorn src.dashboard.dash_app:server`
STREAMLIT_URL = os.environ.get("STREAMLIT_APP_URL", "")
PAGES_URL = "https://chidex-coder.github.io/ls2-facility-survey-analytics/"
REPO_URL = "https://github.com/chidex-coder/ls2-facility-survey-analytics"
NB_LOCAL = C.DOCS_DIR / "notebook.html"   # rendered notebook produced by src/analysis/build_notebook.py
NB_SRC = "/notebook" if NB_LOCAL.exists() else PAGES_URL + "notebook.html"
app.index_string = """<!DOCTYPE html><html><head>{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>body{margin:0;background:#f4f4f1;color:#0b0b0b;font-family:Inter,-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;font-size:14px}
.tab{padding:8px 14px!important;border:0!important;background:transparent!important;color:#52514e!important;font-weight:500;border-radius:999px}
.tab--selected{background:#e4effb!important;color:#2a78d6!important;font-weight:600}
.Select-control,.Select-menu-outer{border-color:#e3e2dd!important;border-radius:8px}
.nb-btn{font-size:13px;font-weight:500;text-decoration:none;color:#0b0b0b;background:#f8f8f6;border:1px solid #e3e2dd;border-radius:8px;padding:7px 12px}
.nb-btn.primary{background:#2a78d6;border-color:#2a78d6;color:#fff}
.nb-cmd{flex-basis:100%;font-size:12px;background:#f8f8f6;border:1px solid #e3e2dd;border-radius:8px;padding:8px 10px;color:#52514e;overflow-x:auto;white-space:nowrap}
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
    dcc.Tab(label="Notebook", value="notebook", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}),
        html.Div("The full analysis as an executed Jupyter notebook: the thirty questions (SQL → table → figure → answer), the predictive models trained and evaluated step by step, and an in-notebook filterable dashboard.",
                 style={"background": "#e4effb", "border": "1px solid #bcd3f0", "borderRadius": "10px", "padding": "10px 14px", "color": "#52514e", "fontSize": "13px", "marginBottom": "12px"}),
        html.Div([html.A("View on GitHub ↗", href=f"{REPO_URL}/blob/main/notebooks/ls2_analysis.ipynb", target="_blank", className="nb-btn primary"),
                  html.A("Open in nbviewer ↗", href="https://nbviewer.org/github/chidex-coder/ls2-facility-survey-analytics/blob/main/notebooks/ls2_analysis.ipynb", target="_blank", className="nb-btn"),
                  html.A("Download .ipynb", href="https://raw.githubusercontent.com/chidex-coder/ls2-facility-survey-analytics/main/notebooks/ls2_analysis.ipynb", target="_blank", className="nb-btn"),
                  html.A("Open rendered page in a new tab ↗", href=NB_SRC, target="_blank", className="nb-btn"),
                  html.Code(f"git clone {REPO_URL} && cd ls2-facility-survey-analytics && pip install -r requirements.txt && jupyter lab notebooks/ls2_analysis.ipynb", className="nb-cmd")],
                 style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "alignItems": "center", "marginBottom": "12px"}),
        html.Div(html.Iframe(id="nb-frame", title="LS 2.0 analytics notebook", style={"width": "100%", "height": "calc(100vh - 260px)", "minHeight": "600px", "border": 0, "background": "#fff", "display": "block"}),
                 style={**CARD, "padding": 0, "overflow": "hidden"})]),
    dcc.Tab(label="Data", value="data", className="tab", selected_className="tab--selected", children=[html.Div(style={"height": "14px"}),
        html.Div(id="data-count", style={"color": "#52514e", "marginBottom": "8px"}),
        dash_table.DataTable(id="data-table", page_size=25, sort_action="native", filter_action="native", style_table={"overflowX": "auto"},
                             style_cell={"fontFamily": "Inter", "fontSize": "12px", "padding": "6px 8px", "textAlign": "left"},
                             style_header={"fontWeight": 600, "textTransform": "uppercase", "fontSize": "11px", "color": "#8a8985", "backgroundColor": "#fff"})]),
])

app.layout = html.Div([
    html.Div([html.Div([html.Span(style={"display": "inline-block", "width": "12px", "height": "12px", "borderRadius": "50%", "background": "#2a78d6", "marginRight": "10px"}),
                        html.Span("LS 2.0 Facility Dashboard", style={"fontWeight": 700, "fontSize": "16px"}),
                        html.Span(" · Bi-weekly PHC monitoring · Kaduna State · Dash edition", style={"color": "#8a8985", "fontSize": "12px"}),
                        html.Span([html.A("Streamlit edition ↗", href=STREAMLIT_URL, target="_blank") if STREAMLIT_URL else None, " · " if STREAMLIT_URL else "",
                                   html.A("Static edition ↗", href=PAGES_URL, target="_blank")], style={"float": "right", "fontSize": "12px"})],
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
    return CH.summary_text(filtered(lgas, types, setting, security, rounds, readiness), lgas, types, rounds)


@app.callback(Output("download", "data"), Input("export", "n_clicks"), [State(i.component_id, "value") for i in FILTER_INPUTS], prevent_initial_call=True)
def export(_, *fv):
    return dcc.send_data_frame(filtered(*fv)["v"].to_csv, "ls2_filtered_visits.csv", index=False)


def kpi(label, value, sub, tone=""):
    color = {"good": T.STATUS["good"], "warn": T.STATUS["serious"], "bad": T.STATUS["critical"]}.get(tone, "#0b0b0b")
    return html.Div([html.Div(label, style={**LABEL, "fontSize": "12px"}), html.Div(value, style={"fontSize": "26px", "fontWeight": 700, "color": color, "margin": "4px 0 2px"}),
                     html.Div(sub, style={"fontSize": "12px", "color": "#52514e"})], style=CARD)


@app.callback(Output("kpis", "children"), Output("g-trend", "figure"), Output("g-bands", "figure"), Output("g-lga-readiness", "figure"),
              Output("g-map", "figure"), Output("g-pillars", "figure"), Input("tabs", "value"), *FILTER_INPUTS)
def overview(tab, *fv):
    if tab != "overview":
        return [no_update] * 6
    o = CH.overview(filtered(*fv))
    return [kpi(*k) for k in o["kpis"]], o["trend"], o["bands"], o["lga"], o["map"], o["pillars"]


@app.callback(Output("g-open-lga", "figure"), Output("g-closed", "figure"), Output("g-hours", "figure"), Output("g-referral", "figure"), Output("g-cce", "figure"),
              Output("g-services", "figure"), Output("g-session-reasons", "figure"), Output("g-training", "figure"), Input("tabs", "value"), Input("s-service", "value"), *FILTER_INPUTS)
def access(tab, service, *fv):
    if tab != "access":
        return [no_update] * 8
    o = CH.access(filtered(*fv), service)
    return o["open_lga"], o["closed"], o["hours"], o["referral"], o["cce"], o["services"], o["session_reasons"], o["training"]


@app.callback(Output("g-att-cadre", "figure"), Output("g-att-lga", "figure"), Output("g-absence", "figure"), Output("g-workforce", "figure"), Output("g-salary-trend", "figure"),
              Output("g-salary-roster", "figure"), Output("g-leave-salary", "figure"), Output("g-att-distance", "figure"), Input("tabs", "value"), Input("s-cadre", "value"), Input("s-top", "value"), *FILTER_INPUTS)
def hrh(tab, cadre, top, *fv):
    if tab != "hrh":
        return [no_update] * 8
    o = CH.hrh(filtered(*fv), cadre, top)
    return o["att_cadre"], o["att_lga"], o["absence"], o["workforce"], o["salary_trend"], o["salary_roster"], o["leave"], o["distance"]


@app.callback(Output("g-stockout-com", "figure"), Output("g-stockout-heat", "figure"), Output("g-stockout-reasons", "figure"), Output("g-funnel", "figure"), Output("g-supplier", "figure"),
              Output("g-req-behaviour", "figure"), Output("g-below-min", "figure"), Output("g-stockout-trend", "figure"),
              Input("tabs", "value"), Input("s-category", "value"), Input("s-commodity", "value"), Input("s-minrate", "value"), *FILTER_INPUTS)
def supply(tab, category, commodity, minrate, *fv):
    if tab != "supply":
        return [no_update] * 8
    o = CH.supply(filtered(*fv), category, commodity, minrate)
    return o["stockout_com"], o["heat"], o["reasons"], o["funnel"], o["supplier"], o["req"], o["below_min"], o["trend"]


@app.callback(Output("g-vac-avail", "figure"), Output("g-vac-doses", "figure"), Output("g-vac-status", "figure"), Output("g-vac-cce", "figure"), Output("g-cc-reasons", "figure"), Output("g-vac-heat", "figure"),
              Input("tabs", "value"), *FILTER_INPUTS)
def vaccines(tab, *fv):
    if tab != "vaccines":
        return [no_update] * 6
    o = CH.vaccines(filtered(*fv))
    return o["avail"], o["doses"], o["status"], o["cce"], o["cc_reasons"], o["heat"]


def model_card(title, rows, desc):
    return html.Div([html.H4(title, style={"margin": "0 0 6px", "fontSize": "14px"})] +
                    [html.Div([html.Span(k), html.B(str(val))], style={"display": "flex", "justifyContent": "space-between", "fontSize": "13px", "padding": "3px 0", "borderBottom": "1px dashed #e3e2dd"}) for k, val in rows] +
                    [html.Div(desc, style={"color": "#8a8985", "fontSize": "12px", "marginTop": "6px"})], style=CARD)


@app.callback(Output("models", "children"), Output("risk-table", "data"), Output("risk-table", "columns"), Output("risk-count", "children"), Output("g-so-risk", "figure"), Output("g-cf-salary", "figure"),
              Output("g-ml-so-imp", "figure"), Output("g-ml-so-roc", "figure"), Output("g-ml-risk-imp", "figure"), Output("g-ml-att-imp", "figure"), Output("g-segments", "figure"),
              Input("tabs", "value"), Input("s-risk", "value"), Input("s-sorisk", "value"), *FILTER_INPUTS)
def predict(tab, risk_thr, so_thr, *fv):
    if tab != "predict":
        return [no_update] * 11
    o = CH.predict(filtered(*fv), D, risk_thr, so_thr)
    columns = [{"name": n, "id": n, "type": "numeric", "format": {"specifier": ".0%"}} if n in CH.RISK_PCT else {"name": n, "id": n} for _, n in CH.RISK_COLS]
    return ([model_card(*c) for c in o["cards"]], o["table"].to_dict("records"), columns, o["risk_count"], o["so_risk"], o["cf_salary"],
            o["so_imp"], o["roc"], o["risk_imp"], o["att_imp"], o["segments"])


@app.callback(Output("nb-frame", "src"), Input("tabs", "value"))
def notebook(tab):
    # Load the (large) rendered notebook only when the tab is opened
    return NB_SRC if tab == "notebook" else no_update


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


@app.callback(Output("data-table", "data"), Output("data-table", "columns"), Output("data-count", "children"), Input("tabs", "value"), *FILTER_INPUTS)
def data(tab, *fv):
    if tab != "data":
        return no_update, no_update, no_update
    v = CH.data_table(filtered(*fv))
    cols = [{"name": n, "id": n, "type": "numeric", "format": {"specifier": ".1%"}} if n in CH.DATA_PCT else {"name": n, "id": n} for _, n in CH.DATA_COLS]
    return v.to_dict("records"), cols, f"{len(v):,} filtered visit records (sort or filter any column; Export CSV downloads the full selection)"


# Serve the standalone question figures and the rendered notebook alongside the app
@app.server.route("/figures/<path:name>")
def figure(name):
    from flask import send_from_directory
    return send_from_directory(C.FIGURE_DIR, name)


@app.server.route("/notebook")
def notebook_page():
    from flask import send_from_directory
    return send_from_directory(NB_LOCAL.parent, NB_LOCAL.name)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", default="127.0.0.1"); ap.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8050))); ap.add_argument("--debug", action="store_true")
    a = ap.parse_args()
    app.run(host=a.host, port=a.port, debug=a.debug)

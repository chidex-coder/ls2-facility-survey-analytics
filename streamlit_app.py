"""Streamlit edition of the LS 2.0 facility dashboard (deployable on Streamlit Community Cloud).

Same tabs, filters, sliders and charts as the Dash edition — both call
src/dashboard/charts.py — rendered with Streamlit widgets.

Run locally:  streamlit run streamlit_app.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))
import config as C  # noqa: E402
from analysis import theme as T  # noqa: E402
from dashboard import charts as CH  # noqa: E402

st.set_page_config(page_title="LS 2.0 Facility Dashboard", page_icon="🩺", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
[data-testid="stMetric"] { background: var(--secondary-background-color); border: 1px solid rgba(128,128,128,.18); border-radius: 12px; padding: 12px 16px; }
[data-testid="stMetricLabel"] { font-size: 12px; text-transform: uppercase; letter-spacing: .05em; opacity: .7; }
.block-container { padding-top: 1.4rem; max-width: 1480px; }
.model-card { border: 1px solid rgba(128,128,128,.18); border-radius: 12px; padding: 12px 16px; background: var(--secondary-background-color); height: 100%; }
.model-card h4 { margin: 0 0 6px; font-size: 14px; }
.model-card .m { display: flex; justify-content: space-between; font-size: 13px; padding: 3px 0; border-bottom: 1px dashed rgba(128,128,128,.3); }
.model-card .d { opacity: .65; font-size: 12px; margin-top: 6px; }
</style>
""", unsafe_allow_html=True)


@st.cache_resource(show_spinner="Loading the survey warehouse…")
def data():
    return CH.load_data()


D = data()
PLOT = {"displayModeBar": False}


def chart(fig, key):
    st.plotly_chart(fig, use_container_width=True, config=PLOT, key=key)


def card(title, hint=None):
    st.markdown(f"**{title}**" + (f"  \n<span style='opacity:.6;font-size:12px'>{hint}</span>" if hint else ""), unsafe_allow_html=True)


# ----------------------------------------------------------------------------
# Sidebar filters
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🩺 LS 2.0 Facility Dashboard")
    st.caption("Bi-weekly PHC monitoring · Kaduna State · Streamlit edition")
    if st.button("Reset filters", use_container_width=True):
        for k in ("f_lga", "f_type", "f_setting", "f_security", "f_rounds", "f_readiness"):
            st.session_state.pop(k, None)
        st.rerun()
    lgas = st.multiselect("LGA", D["lgas"], key="f_lga", placeholder="All 23 LGAs")
    types = st.multiselect("Facility type", C.FACILITY_TYPES, key="f_type", placeholder="All types")
    setting = st.selectbox("Setting", ["All", "Urban", "Rural"], key="f_setting")
    security = st.selectbox("Security-risk LGA", ["All", "Security-risk only", "Other LGAs only"], key="f_security")
    rounds = st.slider("Visit rounds", 1, D["n_rounds"], (1, D["n_rounds"]), key="f_rounds")
    readiness = st.slider("Readiness score range", 0, 100, (0, 100), step=5, key="f_readiness")
    st.caption(f"Round {rounds[0]} = {D['round_name'][rounds[0]]}, round {rounds[1]} = {D['round_name'][rounds[1]]}")
    st.markdown("---")
    try:
        dash_url = os.environ.get("DASH_APP_URL") or st.secrets.get("DASH_APP_URL", "")
    except Exception:  # no secrets configured
        dash_url = ""
    st.caption("Other editions: " + (f"[Dash ↗]({dash_url}) · " if dash_url else "")
               + "[Static (GitHub Pages) ↗](https://chidex-coder.github.io/ls2-facility-survey-analytics/)")

F = CH.filtered(D, lgas, types, None if setting == "All" else setting, {"Security-risk only": "1", "Other LGAs only": "0"}.get(security), rounds, readiness)
st.caption(CH.summary_text(F, lgas, types, rounds))
with st.sidebar:
    st.download_button("⬇ Export filtered visits (CSV)", F["v"].to_csv(index=False).encode(), "ls2_filtered_visits.csv", "text/csv", use_container_width=True)

tabs = st.tabs(["Overview", "Access & readiness", "Human resources", "Supply chain", "Vaccines", "Predictions", "Insights", "Data"])

# ----------------------------------------------------------------------------
with tabs[0]:
    o = CH.overview(F)
    cols = st.columns(len(o["kpis"]) if len(o["kpis"]) <= 5 else 5)
    for i, (label, value, sub, tn) in enumerate(o["kpis"]):
        with cols[i % 5]:
            st.metric(label, value, help=sub)
            st.caption(("🟢 " if tn == "good" else "🟠 " if tn == "warn" else "🔴 " if tn == "bad" else "") + sub)
    c1, c2 = st.columns([2, 1])
    with c1:
        card("Readiness score trend by round", "Composite of six pillars; click legend items to compare pillars."); chart(o["trend"], "ov_trend")
    with c2:
        card("Readiness band distribution", "Share of filtered visits in each band."); chart(o["bands"], "ov_bands")
    c1, c2 = st.columns(2)
    with c1:
        card("Readiness by LGA", "Mean composite score; dotted line is the filtered average."); chart(o["lga"], "ov_lga")
    with c2:
        card("Facility map", "Colour = readiness, size = stock-out rate."); chart(o["map"], "ov_map")
    card("Readiness pillars by facility type"); chart(o["pillars"], "ov_pillars")

# ----------------------------------------------------------------------------
with tabs[1]:
    service = st.selectbox("Service (for missed-session reasons)", ["All services"] + C.SERVICES, key="s_service")
    o = CH.access(F, None if service == "All services" else service)
    c1, c2 = st.columns(2)
    with c1:
        card("Open on arrival, by LGA"); chart(o["open_lga"], "ac_open")
    with c2:
        card("Why facilities were closed"); chart(o["closed"], "ac_closed")
    c1, c2, c3 = st.columns(3)
    with c1:
        card("Hours of operation", "By facility type (unique facilities)."); chart(o["hours"], "ac_hours")
    with c2:
        card("Emergency referral capacity"); chart(o["referral"], "ac_ref")
    with c3:
        card("Cold chain equipment", "Availability vs functionality where available."); chart(o["cce"], "ac_cce")
    c1, c2 = st.columns(2)
    with c1:
        card("Service availability & session completion"); chart(o["services"], "ac_services")
    with c2:
        card("Why planned sessions were missed"); chart(o["session_reasons"], "ac_reasons")
    card("Training coverage (past 2 years)", "Share of filtered facilities with staff trained, by training type."); chart(o["training"], "ac_training")

# ----------------------------------------------------------------------------
with tabs[2]:
    c1, c2 = st.columns([1, 1])
    cadre = c1.selectbox("Cadre (for absence reasons)", ["All cadres"] + C.CADRES, key="s_cadre")
    top = c2.slider("Top N absence reasons", 5, 20, 10, key="s_top")
    o = CH.hrh(F, None if cadre == "All cadres" else cadre, top)
    c1, c2 = st.columns(2)
    with c1:
        card("Attendance of scheduled permanent staff, by cadre", "Present ÷ scheduled."); chart(o["att_cadre"], "hr_cadre")
    with c2:
        card("Attendance by LGA"); chart(o["att_lga"], "hr_lga")
    c1, c2 = st.columns(2)
    with c1:
        card("Why permanent staff were absent"); chart(o["absence"], "hr_abs")
    with c2:
        card("Workforce composition by cadre", "Headcount at the first selected round."); chart(o["workforce"], "hr_wf")
    c1, c2 = st.columns(2)
    with c1:
        card("Salary timeliness & attendance by round"); chart(o["salary_trend"], "hr_sal")
    with c2:
        card("Attendance by salary timeliness and roster practice"); chart(o["salary_roster"], "hr_ros")
    c1, c2 = st.columns(2)
    with c1:
        card("How often staff leave the post to access salary"); chart(o["leave"], "hr_leave")
    with c2:
        card("Attendance vs distance to LGA headquarters", "Each point is a facility."); chart(o["distance"], "hr_dist")

# ----------------------------------------------------------------------------
with tabs[3]:
    c1, c2, c3 = st.columns(3)
    category = c1.selectbox("Category", ["All categories"] + sorted({c[1] for c in C.COMMODITIES}), key="s_category")
    commodity = c2.selectbox("Commodity (for stock-out reasons)", ["All commodities"] + [c[0] for c in C.COMMODITIES], key="s_commodity")
    minrate = c3.slider("Below-minimum-stock: show items ≥ (%)", 0, 100, 0, 5, key="s_minrate")
    o = CH.supply(F, None if category == "All categories" else category, None if commodity == "All commodities" else commodity, minrate)
    c1, c2 = st.columns(2)
    with c1:
        card("Stock-out rate by commodity"); chart(o["stockout_com"], "su_com")
    with c2:
        card("Stock-out heatmap: LGA × commodity", "Darker = higher share of visits with a stock-out."); chart(o["heat"], "su_heat")
    c1, c2 = st.columns(2)
    with c1:
        card("Main reasons for stock-outs"); chart(o["reasons"], "su_reasons")
    with c2:
        card("Requisition funnel", "Submitted → complete & on time → fully received → documented."); chart(o["funnel"], "su_funnel")
    c1, c2, c3 = st.columns(3)
    with c1:
        card("Stock-out rate by supplier"); chart(o["supplier"], "su_sup")
    with c2:
        card("Requisition behaviour vs stock-outs"); chart(o["req"], "su_req")
    with c3:
        card("Below minimum stock (early warning)"); chart(o["below_min"], "su_min")
    card("Stock-out trend by category and round"); chart(o["trend"], "su_trend")

# ----------------------------------------------------------------------------
with tabs[4]:
    o = CH.vaccines(F)
    c1, c2 = st.columns(2)
    with c1:
        card("Vaccine availability (facilities that stock vaccines)"); chart(o["avail"], "va_avail")
    with c2:
        card("Doses used, by vaccine"); chart(o["doses"], "va_doses")
    c1, c2, c3 = st.columns(3)
    with c1:
        card("Vaccine stocking status", "Unique facilities in the filter."); chart(o["status"], "va_status")
    with c2:
        card("Availability by cold chain status"); chart(o["cce"], "va_cce")
    with c3:
        card("Cold chain interruption reasons"); chart(o["cc_reasons"], "va_ccr")
    card("Vaccine availability by LGA and round"); chart(o["heat"], "va_heat")

# ----------------------------------------------------------------------------
with tabs[5]:
    st.info("Models are trained on one visit to predict the next. Scores are for the latest round of each facility in the current LGA / type filter (round sliders do not apply).")
    c1, c2 = st.columns(2)
    risk_thr = c1.slider("At-risk probability threshold (%)", 0, 100, 50, 5, key="s_risk")
    so_thr = c2.slider("Minimum stock-out risk (%)", 0, 100, 60, 5, key="s_sorisk")
    o = CH.predict(F, D, risk_thr, so_thr)
    cols = st.columns(4)
    for col, (title, rows, desc) in zip(cols, o["cards"]):
        col.markdown(f"<div class='model-card'><h4>{title}</h4>" + "".join(f"<div class='m'><span>{k}</span><b>{v}</b></div>" for k, v in rows) + f"<div class='d'>{desc}</div></div>", unsafe_allow_html=True)
    st.markdown("")
    card("Facilities at risk of dropping below readiness 65 at the next visit", o["risk_count"])
    st.dataframe(o["table"], use_container_width=True, hide_index=True, height=420,
                 column_config={n: st.column_config.ProgressColumn(n, format="percent", min_value=0, max_value=1) if n in ("At-risk prob.", "Mean stock-out risk") else
                                st.column_config.NumberColumn(n, format="percent") if n in CH.RISK_PCT else st.column_config.NumberColumn(n, format="%.1f") if n == "Readiness (latest)" else None
                                for n in o["table"].columns})
    c1, c2 = st.columns(2)
    with c1:
        card("Commodity stock-out risk at next visit", "Facility × commodity pairs above the threshold, ranked."); chart(o["so_risk"], "pr_so")
    with c2:
        card("Expected attendance gain if salary is paid on time", "Counterfactual from the attendance driver model (latest round)."); chart(o["cf_salary"], "pr_cf")
    c1, c2 = st.columns(2)
    with c1:
        card("Stock-out model: what matters"); chart(o["so_imp"], "pr_soimp")
    with c2:
        card("Stock-out model: ROC (held-out round)"); chart(o["roc"], "pr_roc")
    c1, c2 = st.columns(2)
    with c1:
        card("At-risk model: what matters"); chart(o["risk_imp"], "pr_riskimp")
    with c2:
        card("Attendance driver model: what matters"); chart(o["att_imp"], "pr_attimp")
    card("Facility segments", "K-means on the mean readiness pillars per facility."); chart(o["segments"], "pr_seg")

# ----------------------------------------------------------------------------
with tabs[6]:
    st.info("Thirty decision questions answered with SQL against the survey warehouse (full network, all rounds). The other tabs let you re-cut the same metrics by LGA, facility type and round.")
    section = None
    for a in D["analysis"]:
        if a["section"] != section:
            section = a["section"]; st.markdown(f"### {section}")
        with st.expander(f"{a['id']} · {a['question']}"):
            st.write(a["answer"])
            fig_path = C.FIGURE_DIR / f"{a['id']}.html"
            if fig_path.exists():
                st.link_button("Open standalone figure ↗", f"https://chidex-coder.github.io/ls2-facility-survey-analytics/figures/{a['id']}.html")

# ----------------------------------------------------------------------------
with tabs[7]:
    t = CH.data_table(F)
    st.caption(f"{len(t):,} filtered visit records — sort any column; the sidebar button exports the full selection as CSV.")
    st.dataframe(t, use_container_width=True, hide_index=True, height=600,
                 column_config={n: st.column_config.NumberColumn(n, format="percent") for n in CH.DATA_PCT} | {"Readiness": st.column_config.NumberColumn("Readiness", format="%.1f")})

st.caption(f"LS 2.0 facility survey analytics · {len(D['visits']):,} visits · {len(D['lgas'])} LGAs · dataset generated from the questionnaire structure")

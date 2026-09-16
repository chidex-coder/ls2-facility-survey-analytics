"""Generate and execute the analytics notebook (notebooks/ls2_analysis.ipynb).

One section per question in src/analysis/questions.py: the question, the SQL
against the SQLite warehouse, the result table, the Plotly figure (interactive
in Jupyter / VS Code / nbviewer, with a static PNG fallback so GitHub renders
it) and the plain-language answer. The notebook is generated from the same
functions the pipeline uses, so it never drifts from the published analysis.

Run:  python src/analysis/build_notebook.py [--no-execute]
"""
from __future__ import annotations

import argparse
import inspect
import sys
from pathlib import Path

import nbformat
from nbclient import NotebookClient
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from analysis import questions as Q  # noqa: E402

NB_PATH = C.ROOT / "notebooks" / "ls2_analysis.ipynb"

INTRO = """# LS 2.0 Facility Survey — Analytics & Visualisation

Thirty decision questions the LS 2.0 questionnaire was designed to answer, each worked end to end:
the **SQL** run against the SQLite warehouse built by the ETL (`outputs/ls2_survey.db`), the **result table**,
a **Plotly figure** (interactive when the cell is run), and the **answer** in plain language.

Re-run all cells after `python run_pipeline.py` to refresh every answer.

> The dataset is generated from the structure of the questionnaire (184 facilities × 6 bi-weekly rounds).
> The pipeline, SQL and charts run unchanged on a real export with the same sheet layout.

**Contents**

| Section | Questions |
|---|---|
| Facility access & cold chain | Q01–Q04 |
| Service delivery | Q05–Q07 |
| Human resources for health | Q08–Q14 |
| Supply chain | Q15–Q21 |
| Vaccines | Q22–Q24 |
| Composite readiness & predictors | Q25–Q30 |
| Predictive analytics | stock-out risk, at-risk facilities, attendance drivers, segments |
| Dashboard | in-notebook filterable dashboard + the hosted editions |
"""

SETUP = '''import sqlite3, sys
from pathlib import Path

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import plotly.io as pio

ROOT = Path.cwd().resolve()
while not (ROOT / "src").exists():
    ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))
import config as C
from analysis import theme as T                       # shared Plotly template (registered as "ls2")
from analysis.questions import Result, q, pct, hbar   # helpers used by every question below

# Interactive figures when the notebook is run live; a static PNG is what gets saved so every viewer (GitHub included) shows the charts
pio.renderers.default = "notebook_connected+png"
pio.defaults.default_width, pio.defaults.default_height, pio.defaults.default_scale = 900, 500, 1.5
pio.templates.default = "ls2"
pd.set_option("display.max_columns", 30); pd.set_option("display.width", 160); pd.set_option("display.float_format", "{:.3f}".format)

con = sqlite3.connect(ROOT / "outputs" / "ls2_survey.db")
print(pd.read_sql_query("SELECT table_name, row_count FROM etl_log ORDER BY row_count DESC", con).to_string(index=False))
'''

SCHEMA = """## The warehouse

`facility_visits` is the fact table (one row per facility per round). Long tables hang off it by `visit_id`, and the views
`v_visits`, `v_commodity`, `v_staffing`, `v_absence`, `v_vaccine` and `v_sessions` pre-join facility context.
"""

SCHEMA_CODE = '''views = pd.read_sql_query("SELECT name, type FROM sqlite_master WHERE type IN ('table','view') ORDER BY type, name", con)
print(", ".join(views[views.type == "view"].name), "\\n")
pd.read_sql_query("SELECT * FROM v_visits LIMIT 3", con).T.head(40)
'''

SHOW = '''r = {fn}(con)
display(r.data.head(15))
r.figure.show()
print(r.answer)
'''


ML_INTRO = """---
# Predictive analytics

Three forward-looking models plus a segmentation, trained here on the warehouse exactly as the pipeline does
(`src/ml/predict.py`). Every model uses what was observed at visit *t* to say something about visit *t+1*, so they can be
re-run after each bi-weekly round to steer the next one.

| Model | Question it answers | Validation |
|---|---|---|
| Stock-out risk | will this commodity be stocked out at the next visit? | train rounds 1–4→2–5, test round 5→6 |
| At-risk facility | will readiness fall below 65 at the next visit? | same time split |
| Attendance drivers | what attendance should we expect under these salary / roster / security conditions? | GroupKFold on unseen facilities |
| Segmentation | which facilities share a profile across the readiness pillars? | silhouette |
"""

ML_SETUP = """from ml import predict as ML

visits, com = ML.load_frames(ROOT / "outputs" / "ls2_survey.db")
ML.ML_DIR.mkdir(parents=True, exist_ok=True)
print(f"{len(visits):,} visits, {len(com):,} stocked commodity observations")
"""

ML_STOCKOUT_MD = """## Stock-out risk at the next visit

Per facility × commodity: current balance and adequacy vs the minimum stock level, quantity received, requisition behaviour,
supplier, knowledge of minimum-stock calculation, facility context and whether the item was already stocked out. Three
candidate classifiers are compared on the held-out round and the best one is kept.
"""
ML_STOCKOUT = """so_meta, so_pred, so_figs = ML.stockout_model(visits, com)
print("best model:", so_meta["best_model"], "| positive rate in test round:", f"{so_meta['positive_rate_test']:.1%}",
      "| recommended threshold:", f"{so_meta['recommended_threshold']:.2f}")
display(pd.DataFrame(so_meta["candidates"]).T.round(3))
so_figs["roc"].show()
so_figs["importance"].show()
"""
ML_STOCKOUT_TOP_MD = "### Emergency-resupply list: highest stock-out risk for the next visit"
ML_STOCKOUT_TOP = """top = so_pred.sort_values("stockout_risk", ascending=False).head(20)
top.assign(stockout_risk=top.stockout_risk.map("{:.0%}".format)).reset_index(drop=True)
"""

ML_RISK_MD = """## Facilities at risk of dropping below readiness 65

A random forest over the current readiness pillars, management practices (salary, roster, requisition), cold chain and
security context flags facilities likely to be in the Weak/Critical bands at the next visit, so supportive supervision can be
scheduled before the drop.
"""
ML_RISK = """risk_meta, risk_pred, risk_figs = ML.at_risk_model(visits)
print({k: round(v, 3) for k, v in risk_meta["metrics"].items()})
risk_figs["roc"].show()
risk_figs["importance"].show()
top_risk = (risk_pred.merge(visits[["facility_id", "facility_name", "lga", "facility_type"]].drop_duplicates(), on="facility_id")
            .sort_values("at_risk_probability", ascending=False).head(20))
top_risk.assign(at_risk_probability=top_risk.at_risk_probability.map("{:.0%}".format)).reset_index(drop=True)
"""

ML_ATT_MD = """## What drives permanent-staff attendance?

Next-round attendance is dominated by small-headcount noise (a facility with 8 scheduled staff swings ±12 points by chance),
so instead of forecasting it the model explains the attendance to *expect* under the conditions observed at a visit, validated
on facilities it has never seen. That makes it a what-if tool: the counterfactual below re-scores every facility as if salaries
had been paid on time.
"""
ML_ATT = """att_meta, att_pred, att_figs = ML.attendance_model(visits)
print({k: round(v, 3) for k, v in att_meta["metrics"].items()})
att_figs["scatter"].show()
att_figs["importance"].show()
gain = (att_pred.assign(gain=lambda d: d.expected_attendance_if_salary_on_time - d.expected_attendance)
        .merge(visits[["facility_id", "facility_name", "lga"]].drop_duplicates(), on="facility_id")
        .query("gain > 0.005").sort_values("gain", ascending=False))
print(f"{len(gain)} facilities with late salary at the latest visit; mean expected attendance gain if paid on time: {gain.gain.mean():+.1%}")
top_gain = gain.head(20).assign(facility=lambda d: d.facility_name + " (" + d.lga + ")")
hbar(top_gain, "gain", "facility", "Expected attendance gain if salary is paid on time (top 20)", xlabel="Attendance points", fmt=".1%").show()
"""

ML_SEG_MD = """## Facility segments

K-means on each facility's mean profile across the readiness pillars. The silhouette is modest, so the segments should guide
the support package (light-touch monitoring / supply-side fixes / full supportive supervision) rather than dictate it.
"""
ML_SEG = """seg_meta, seg_df, seg_fig = ML.segmentation(visits)
print("k =", seg_meta["k"], "| silhouette =", round(seg_meta["silhouette"], 3), "|", seg_meta["segment_sizes"])
seg_fig.show()
pd.DataFrame(seg_meta["centres"]).set_index("segment_id").T.round(2)
"""
ML_SCORES_MD = """## Facility score card

All model outputs for the latest round joined into one table — the same table the dashboards' Predictions tab shows."""
ML_SCORES = """scores = (visits[visits.round_number == ML.LAST_ROUND][["facility_id", "facility_name", "lga", "facility_type", "readiness_score", "attendance_rate", "stockout_rate"]]
          .merge(risk_pred.drop(columns=["readiness_score"]), on="facility_id")
          .merge(att_pred.drop(columns=["attendance_rate"]), on="facility_id")
          .merge(seg_df, on="facility_id")
          .merge(so_pred.groupby("facility_id").stockout_risk.mean().rename("mean_stockout_risk").reset_index(), on="facility_id")
          .sort_values("at_risk_probability", ascending=False))
scores.head(25).style.format({c: "{:.0%}" for c in ["attendance_rate", "stockout_rate", "at_risk_probability", "expected_attendance", "expected_attendance_if_salary_on_time", "expected_attendance_if_roster_updated", "mean_stockout_risk"]}).format({"readiness_score": "{:.1f}"}).hide(axis="index")
"""

DASH_INTRO = """---
# Dashboard

The same metrics as a filterable dashboard. `dashboard()` below is built on `src/dashboard/charts.py` — the module behind the
Dash and Streamlit editions — so what you see here is what the hosted apps show. Call it with any combination of filters
(`lgas`, `types`, `setting`, `security`, `rounds`, `readiness`) and it re-renders the KPI tiles and every chart for that slice.

Hosted editions of the full dashboard (8 tabs, sliders, tables, CSV export):

| Edition | Where |
|---|---|
| Static | https://chidex-coder.github.io/ls2-facility-survey-analytics/ |
| Streamlit | `streamlit run streamlit_app.py` (or Streamlit Community Cloud) |
| Dash | `python src/dashboard/dash_app.py` (or the Hugging Face Space / Render service) |
"""
DASH_SETUP = """from dashboard import charts as CH
from IPython.display import HTML, IFrame, display

DATA = CH.load_data()

def dashboard(lgas=None, types=None, setting=None, security=None, rounds=None, readiness=(0, 100), tabs=("overview", "hrh", "supply", "vaccines")):
    rounds = rounds or (1, DATA["n_rounds"])
    F = CH.filtered(DATA, lgas, types, setting, security, rounds, readiness)
    print(CH.summary_text(F, lgas, types, rounds))
    o = CH.overview(F)
    tiles = "".join(f"<div style='flex:1;min-width:150px;border:1px solid #e3e2dd;border-radius:12px;padding:10px 14px'>"
                    f"<div style='font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:#8a8985;font-weight:600'>{l}</div>"
                    f"<div style='font-size:24px;font-weight:700;color:{ {'good':'#0ca30c','warn':'#ec835a','bad':'#d03b3b'}.get(t,'#0b0b0b') }'>{v}</div>"
                    f"<div style='font-size:11px;color:#52514e'>{s}</div></div>" for l, v, s, t in o["kpis"])
    display(HTML(f"<div style='display:flex;flex-wrap:wrap;gap:10px;font-family:Inter,sans-serif'>{tiles}</div>"))
    figs = {"overview": {k: o[k] for k in ("trend", "lga", "map", "pillars")}, "access": CH.access(F), "hrh": CH.hrh(F), "supply": CH.supply(F), "vaccines": CH.vaccines(F)}
    for t in tabs:
        display(HTML(f"<h3 style='font-family:Inter,sans-serif;margin:18px 0 4px'>{TAB_NAMES[t]}</h3>"))
        for key, fig in figs[t].items():
            fig.update_layout(title=TITLES.get((t, key), key), margin=dict(t=90)).show()
    return F

TAB_NAMES = {"overview": "Overview", "access": "Access & readiness", "hrh": "Human resources", "supply": "Supply chain", "vaccines": "Vaccines"}
TITLES = {("overview", "trend"): "Readiness score trend by round", ("overview", "lga"): "Readiness by LGA", ("overview", "map"): "Facility map (colour = readiness, size = stock-out rate)", ("overview", "pillars"): "Readiness pillars by facility type",
          ("access", "open_lga"): "Open on arrival, by LGA", ("access", "closed"): "Why facilities were closed on arrival", ("access", "hours"): "Hours of operation by facility type", ("access", "referral"): "Emergency referral capacity", ("access", "cce"): "Cold chain equipment: availability vs functionality", ("access", "services"): "Service availability & session completion", ("access", "session_reasons"): "Why planned sessions were missed", ("access", "training"): "Training coverage (past 2 years)",
          ("hrh", "att_cadre"): "Attendance of scheduled permanent staff, by cadre", ("hrh", "att_lga"): "Attendance by LGA", ("hrh", "absence"): "Why permanent staff were absent", ("hrh", "workforce"): "Workforce composition by cadre", ("hrh", "salary_trend"): "Salary timeliness & attendance by round", ("hrh", "salary_roster"): "Attendance by salary timeliness and roster practice", ("hrh", "leave"): "How often staff leave the post to access salary", ("hrh", "distance"): "Attendance vs distance to LGA headquarters",
          ("supply", "stockout_com"): "Stock-out rate by commodity", ("supply", "heat"): "Stock-out heatmap: LGA × commodity", ("supply", "reasons"): "Main reasons for stock-outs", ("supply", "funnel"): "Requisition funnel", ("supply", "supplier"): "Stock-out rate by supplier", ("supply", "req"): "Requisition behaviour vs stock-outs", ("supply", "below_min"): "Below minimum stock (early warning)", ("supply", "trend"): "Stock-out trend by category and round",
          ("vaccines", "avail"): "Vaccine availability (stocking facilities)", ("vaccines", "doses"): "Doses used, by vaccine", ("vaccines", "status"): "Vaccine stocking status", ("vaccines", "cce"): "Vaccine availability by cold chain status", ("vaccines", "cc_reasons"): "Cold chain interruption reasons", ("vaccines", "heat"): "Vaccine availability by LGA and round"}
"""
DASH_ALL_MD = "## Whole network, all rounds"
DASH_ALL = 'F = dashboard(tabs=("overview", "supply"))'
DASH_SLICE_MD = """## A slice: security-risk LGAs, Primary Health Centres, rounds 3–6

Change the arguments and re-run to explore any other cut."""
DASH_SLICE = 'F = dashboard(types=["Primary Health Centre"], security="1", rounds=(3, 6), tabs=("overview", "hrh"))'
DASH_WIDGETS_MD = """## Live filters (when run in Jupyter)

With `ipywidgets` installed this cell gives dropdowns and sliders; the outputs are not stored in the saved notebook."""
DASH_WIDGETS = """try:
    import ipywidgets as W
    W.interact(lambda lga, ftype, rounds, tab: dashboard(lgas=[lga] if lga != "All" else None, types=[ftype] if ftype != "All" else None, rounds=rounds, tabs=(tab,)),
               lga=["All"] + DATA["lgas"], ftype=["All"] + C.FACILITY_TYPES,
               rounds=W.IntRangeSlider(value=(1, DATA["n_rounds"]), min=1, max=DATA["n_rounds"]),
               tab=["overview", "access", "hrh", "supply", "vaccines"])
except ImportError:
    print("pip install ipywidgets for live filters; call dashboard(...) directly otherwise.")
"""
DASH_EMBED_MD = """## The full static dashboard, embedded

Renders when this notebook is opened in Jupyter / VS Code (it loads the GitHub Pages build); GitHub's static viewer shows only the link."""
DASH_EMBED = 'IFrame("https://chidex-coder.github.io/ls2-facility-survey-analytics/", width="100%", height=900)'


WRAP = """## Summary of answers

Every answer above, collected in one table (also written to `outputs/analysis_results.json` by the pipeline).
"""

WRAP_CODE = '''summary = pd.DataFrame([{"id": r.id, "section": r.section, "question": r.question, "answer": r.answer} for r in results])
pd.set_option("display.max_colwidth", None)
summary.style.set_properties(**{"text-align": "left", "white-space": "pre-wrap"}).hide(axis="index")
'''


def build() -> nbformat.NotebookNode:
    nb = new_notebook(metadata={"kernelspec": {"name": "python3", "display_name": "Python 3", "language": "python"},
                                "language_info": {"name": "python"}})
    cells = [new_markdown_cell(INTRO), new_code_cell(SETUP), new_markdown_cell(SCHEMA), new_code_cell(SCHEMA_CODE), new_code_cell("results = []")]
    section = None
    for fn in Q.QUESTIONS:
        # Read the question text from the Result the function constructs (cheap: it is a literal in the return statement)
        src = inspect.getsource(fn)
        name = fn.__name__
        meta = _meta(src)
        if meta["section"] != section:
            section = meta["section"]
            cells.append(new_markdown_cell(f"---\n# {section}"))
        cells.append(new_markdown_cell(f"## {name.upper()}. {meta['question']}\n\nThe cell below defines the analysis for this question (SQL + figure), then runs it."))
        cells.append(new_code_cell(src.rstrip()))
        cells.append(new_code_cell(SHOW.format(fn=name) + "results.append(r)"))
    cells += [new_markdown_cell(WRAP), new_code_cell(WRAP_CODE)]
    cells += [new_markdown_cell(ML_INTRO), new_code_cell(ML_SETUP),
              new_markdown_cell(ML_STOCKOUT_MD), new_code_cell(ML_STOCKOUT), new_markdown_cell(ML_STOCKOUT_TOP_MD), new_code_cell(ML_STOCKOUT_TOP),
              new_markdown_cell(ML_RISK_MD), new_code_cell(ML_RISK), new_markdown_cell(ML_ATT_MD), new_code_cell(ML_ATT),
              new_markdown_cell(ML_SEG_MD), new_code_cell(ML_SEG), new_markdown_cell(ML_SCORES_MD), new_code_cell(ML_SCORES)]
    cells += [new_markdown_cell(DASH_INTRO), new_code_cell(DASH_SETUP), new_markdown_cell(DASH_ALL_MD), new_code_cell(DASH_ALL),
              new_markdown_cell(DASH_SLICE_MD), new_code_cell(DASH_SLICE), new_markdown_cell(DASH_WIDGETS_MD), new_code_cell(DASH_WIDGETS),
              new_markdown_cell(DASH_EMBED_MD), new_code_cell(DASH_EMBED), new_code_cell("con.close()")]
    nb.cells = cells
    return nb


def _keep_static_figures(nb) -> None:
    """Save figures as PNG only. Viewers such as GitHub prefer the HTML output but strip its scripts,
    which leaves a blank cell; with a single PNG representation every viewer shows the chart."""
    for c in nb.cells:
        if c.cell_type != "code":
            continue
        for o in c.get("outputs", []):
            d = o.get("data", {})
            if "image/png" in d:
                for k in [k for k in d if k != "image/png"]:
                    d.pop(k)
                o.get("metadata", {}).pop("text/html", None)


def _meta(src: str) -> dict:
    """Pull section and question text out of the Result(...) literal in a question function."""
    import re
    m = re.search(r'Result\("Q\d+",\s*"([^"]+)",\s*"([^"]+)"', src)
    return {"section": m.group(1), "question": m.group(2)} if m else {"section": "Other", "question": src.splitlines()[0]}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--no-execute", action="store_true", help="write the notebook without running it")
    a = ap.parse_args()
    nb = build()
    NB_PATH.parent.mkdir(exist_ok=True)
    if not a.no_execute:
        NotebookClient(nb, timeout=600, kernel_name="python3", resources={"metadata": {"path": str(NB_PATH.parent)}}).execute()
        _keep_static_figures(nb)
    nbformat.write(nb, NB_PATH)
    n_fig = sum(1 for c in nb.cells if c.cell_type == "code" for o in c.get("outputs", []) if "image/png" in o.get("data", {}))
    print(f"notebook written to {NB_PATH} ({NB_PATH.stat().st_size/1e6:.1f} MB, {len(nb.cells)} cells, {n_fig} figures rendered)")


if __name__ == "__main__":
    main()

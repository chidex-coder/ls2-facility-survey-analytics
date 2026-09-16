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
    cells += [new_markdown_cell(WRAP), new_code_cell(WRAP_CODE), new_code_cell("con.close()")]
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

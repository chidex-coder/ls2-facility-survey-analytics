---
title: LS 2.0 Facility Dashboard (Dash)
emoji: 🩺
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 8050
pinned: false
short_description: Kaduna PHC bi-weekly survey analytics - Dash edition
---

# LS 2.0 Facility Survey Analytics

End-to-end analytics for the **LS 2.0 health facility questionnaire** — a bi-weekly
monitoring instrument for primary health care facilities in Kaduna State, Nigeria.
The questionnaire covers three modules:

| Module | What it captures |
|---|---|
| 1. General facility information | opening hours, open-on-arrival checks, emergency referral, cold chain equipment, services offered, planned sessions delivered, staff training |
| 2. Human resources for health | attendance registers and duty rosters, headcount by cadre and employment type, staff present today, reasons for absence, salary timeliness and its effect on service delivery |
| 3. Supply chain | requisition cycle (submitted → complete → received → documented), 23 tracer medicines and commodities (stock-outs, reasons, balance vs minimum stock, supplier, physical verification), 11 vaccines (opening/closing balance, doses used, source) |

The repository turns that instrument into a working decision system:

```
questionnaire (xlsx) ──▶ survey workbook ──▶ ETL ──▶ SQLite warehouse ──▶ 30 answered questions (SQL + Plotly)
                                                             │
                                                             ├──▶ predictive models (stock-out risk, at-risk facilities, attendance drivers, segments)
                                                             └──▶ interactive HTML dashboard with filters and sliders
```

**Live dashboard:** https://chidex-coder.github.io/ls2-facility-survey-analytics/ (the static build in `docs/index.html`).

The dashboard ships in three editions with the same tabs, filters, sliders and charts:

| Edition | File | How it works |
|---|---|---|
| Static (GitHub Pages) | `docs/index.html`, built by `src/dashboard/build_dashboard.py` | data embedded in the page; charts recomputed in the browser; no server needed |
| Pure Python — Dash | `src/dashboard/dash_app.py` | every component, filter, slider and chart is Python; callbacks query the SQLite warehouse live |
| Pure Python — Streamlit | `streamlit_app.py` | same charts via `src/dashboard/charts.py`, rendered with Streamlit widgets; deployable on Streamlit Community Cloud |

```bash
python src/dashboard/dash_app.py          # Dash edition      -> http://127.0.0.1:8050
streamlit run streamlit_app.py            # Streamlit edition -> http://localhost:8501
```

### Hosting the two Python editions side by side

| Edition | Host | Deploy |
|---|---|---|
| Streamlit | Streamlit Community Cloud (free) | one-click link below; needs only a GitHub sign-in |
| Dash | Hugging Face Spaces (free, Docker Space, no sleep on the free CPU tier) | `HF_TOKEN=hf_… python deploy/hf_space.py --owner <hf-username>` — creates the Space and uploads the repo; see below |
| Dash | Render free web service | [Deploy to Render](https://render.com/deploy?repo=https://github.com/chidex-coder/ls2-facility-survey-analytics) — the `render.yaml` blueprint sets everything up |

Set `STREAMLIT_APP_URL` on the Dash service (Render → Environment) and `DASH_APP_URL` on the Streamlit app (Settings → Secrets: `DASH_APP_URL = "https://…"`) and each app links to the other from its header/sidebar.
The Dash app also runs anywhere that speaks WSGI: `gunicorn src.dashboard.dash_app:server --bind 0.0.0.0:$PORT` (see `Procfile`), or `docker build -t ls2-dash . && docker run -p 8050:8050 ls2-dash`.

**Deploy the Dash edition to Hugging Face Spaces.** The YAML front matter at the top of this README is the Space
configuration (`sdk: docker`, `app_port: 8050`) and the `Dockerfile` is the build. Two ways:

```bash
pip install huggingface_hub
export HF_TOKEN=hf_...                                   # write-scoped token from https://huggingface.co/settings/tokens
python deploy/hf_space.py --owner <your-hf-username> --streamlit-url https://<your-app>.streamlit.app
```

or add the repository secrets `HF_TOKEN` and `HF_SPACE` (`<owner>/<space-name>`) on GitHub and the
`sync-hf-space` workflow pushes every commit on `main` to the Space. Alternatively create a Docker Space in the
Hugging Face UI and `git push` this repository to it — the front matter and Dockerfile are all it needs.

**Deploy the Streamlit edition** (Streamlit Community Cloud): sign in at https://share.streamlit.io with the GitHub account that
owns this repository, choose *Create app → Deploy a public app from GitHub*, and point it at `chidex-coder/ls2-facility-survey-analytics`,
branch `main`, main file `streamlit_app.py`. Everything the app needs (`outputs/ls2_survey.db`, model outputs, `requirements.txt`,
`.streamlit/config.toml`) is committed, so no secrets or extra settings are required. One-click link:
https://share.streamlit.io/deploy?repository=chidex-coder/ls2-facility-survey-analytics&branch=main&mainModule=streamlit_app.py

## What you can decide with it

* **Where to send supportive supervision next fortnight** — facilities ranked by the probability of dropping below readiness 65 at the next visit.
* **Which facility × commodity pairs need emergency resupply** — stock-out risk scores for the next visit, driven by stock adequacy vs minimum stock, receipts and requisition behaviour.
* **How much attendance a salary or roster fix would buy** — counterfactual expected attendance per facility if salaries are paid on time or rosters are kept current.
* **Which LGAs, cadres, commodities and vaccines are the weakest links** — every cut is filterable by LGA, facility type, urban/rural, security-risk status, visit round and readiness band.

See [`docs/DECISION_BRIEF.md`](docs/DECISION_BRIEF.md) for the headline findings and recommended actions,
[`docs/ANALYSIS.md`](docs/ANALYSIS.md) for all thirty questions with their SQL, and
[`notebooks/ls2_analysis.ipynb`](notebooks/ls2_analysis.ipynb) for an executed Jupyter notebook that works through the
thirty questions (SQL → result table → figure → answer), trains and evaluates the predictive models, and ends with an
in-notebook filterable dashboard built on the same chart module as the hosted apps.

## Repository layout

```
data/raw/LS_2.0_Questionnaire.xlsx      the instrument (question text, options, skip logic, enumerator notes)
data/survey/ls2_survey_responses.xlsx   populated survey workbook (10 sheets, incl. a data dictionary) + CSV copies
src/config.py                           vocabularies lifted from the questionnaire (cadres, commodities, vaccines, option lists)
src/generate_survey_data.py             builds the survey workbook from the questionnaire structure
src/etl/                                extract (workbook) → transform (clean, flags, derived indicators, readiness score) → load (SQLite + views)
src/analysis/questions.py               30 decision questions answered with SQL, each with a Plotly figure
src/analysis/build_notebook.py          generates + executes notebooks/ls2_analysis.ipynb from those questions
notebooks/ls2_analysis.ipynb            executed analytics notebook (one section per question, figures embedded)
src/ml/predict.py                       stock-out risk, at-risk facility, attendance driver and segmentation models
src/dashboard/build_dashboard.py        builder + template.html for the self-contained static dashboard
src/dashboard/charts.py                 shared filtering + Plotly figure builders used by both Python editions
src/dashboard/dash_app.py               the dashboard as a Plotly Dash application
streamlit_app.py                        the dashboard as a Streamlit application (Streamlit Community Cloud entry point)
.streamlit/config.toml                  Streamlit theme/server settings
Dockerfile, render.yaml, Procfile       production packaging for the Dash edition (gunicorn; Render blueprint; Hugging Face Docker Space)
deploy/hf_space.py                      creates/updates the Hugging Face Space from this repository
.github/workflows/sync-hf-space.yml     optional GitHub -> Space sync (needs HF_TOKEN + HF_SPACE secrets)
outputs/ls2_survey.db                   SQLite warehouse (16 tables, 6 analytic views, ETL log)
outputs/figures/*.html                  one interactive figure per question / model
outputs/ml/                             metrics, predictions (facility and commodity level), fitted models
docs/index.html                         the dashboard (GitHub Pages); its Notebook tab embeds docs/notebook.html
docs/notebook.html                      rendered copy of the analytics notebook
tests/                                  smoke tests for ETL and warehouse
```

## Run it

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run_pipeline.py          # ~1 minute end to end
python -m pytest -q             # optional smoke tests
```

Individual stages can be run on their own (`python src/etl/pipeline.py`, `python src/analysis/questions.py`, …), and
`python src/dashboard/dash_app.py` serves the Dash edition of the dashboard on http://127.0.0.1:8050 once the pipeline has run.
To use real survey exports, drop a workbook with the same sheet layout into `data/survey/` and run with `--skip-generate`.

## About the data

The file is a *questionnaire*, not a response export, so `src/generate_survey_data.py` produces a
response dataset that follows the instrument exactly — 184 facilities across all 23 LGAs, visited at baseline and
five bi-weekly rounds (1,104 visits), with per-cadre staffing, per-commodity stock and per-vaccine stock tables.
Facility quality, LGA security context, level of care and a state-wide salary delay in one round shape the outcomes
so that the analysis and models have real structure to find. Every row is synthetic; no facility, person or phone
number is real.

## Data model

`facility_visits` is the fact table (one row per facility per round, 69 questionnaire fields plus derived indicators
such as `attendance_rate`, `stockout_rate`, `vaccine_availability_rate`, `session_completion_rate`, `cce_functionality_rate`
and the composite `readiness_score`). Long tables hang off it by `visit_id`: `staffing_by_cadre`, `absence_reasons`,
`commodity_stock`, `vaccine_stock`, `service_sessions`, `cold_chain_equipment`, plus exploded multi-select answers
(`visit_services`, `visit_cce_types`, `visit_salary_issues`, …). Views `v_visits`, `v_commodity`, `v_staffing`,
`v_absence`, `v_vaccine` and `v_sessions` pre-join facility context for analysis.

## Models

| Model | Target | Validation | Result |
|---|---|---|---|
| Stock-out risk | commodity stocked out at next visit | train rounds 1–4→2–5, test round 5→6 | ROC AUC 0.86, AP 0.72 (base rate 39%) |
| At-risk facility | readiness < 65 at next visit | same time split | ROC AUC 0.87, AP 0.78 (base rate 32%) |
| Attendance drivers | permanent-staff attendance under observed conditions | GroupKFold by facility | R² 0.26 (0.40 headcount-weighted); +3.6 pts expected if salary on time |
| Segmentation | k-means on readiness pillars | silhouette | 3 segments: High performers / Stock-constrained / Multi-constraint |

Next-round attendance is deliberately *not* forecast: with 5–15 scheduled staff per facility, a single visit's
attendance swings ±12 points by chance, so the driver model is used for what-if scenarios instead.

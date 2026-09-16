"""Predictive analytics on the LS 2.0 warehouse.

Three forward-looking models, all trained on what was observed at visit *t*
to predict what happens at visit *t+1* (so they can be run after every
bi-weekly round to steer the next one), plus an unsupervised segmentation:

1. Stock-out risk          - will a commodity be stocked out at the next visit?   (classifier)
2. Attendance drivers      - what attendance to expect under observed conditions, with salary/roster counterfactuals (regressor)
3. At-risk facility        - will the facility's readiness fall below 65 next visit? (classifier)
4. Facility segments       - k-means profiles across the readiness pillars

Evaluation uses a strict time split: rounds 1-4 -> 2-5 for training, round 5 -> 6 held out.
Outputs land in outputs/ml/ (metrics.json, predictions, figures) for the dashboard.

Run:  python src/ml/predict.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from sklearn.cluster import KMeans
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (average_precision_score, mean_absolute_error, precision_recall_curve, r2_score,
                             roc_auc_score, roc_curve, silhouette_score)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config as C  # noqa: E402
from analysis import theme as T  # noqa: E402

ML_DIR = C.OUTPUT_DIR / "ml"
LAST_ROUND = 6
AT_RISK_THRESHOLD = 65.0


def load_frames(db_path: Path):
    con = sqlite3.connect(db_path)
    visits = pd.read_sql_query("SELECT * FROM v_visits", con)
    com = pd.read_sql_query("SELECT * FROM v_commodity WHERE stocked_flag=1", con)
    con.close()
    return visits, com


def make_pipeline(model, cat_cols, num_cols):
    pre = ColumnTransformer([
        ("cat", OneHotEncoder(handle_unknown="ignore"), cat_cols),
        ("num", Pipeline([("scale", StandardScaler())]), num_cols),
    ])
    return Pipeline([("prep", pre), ("model", model)])


def feature_importance(pipe, X, y, scoring, n_repeats=5):
    r = permutation_importance(pipe, X, y, scoring=scoring, n_repeats=n_repeats, random_state=C.RANDOM_SEED, n_jobs=-1)
    return pd.DataFrame({"feature": X.columns, "importance": r.importances_mean}).sort_values("importance", ascending=False)


def importance_fig(imp: pd.DataFrame, title: str):
    imp = imp.head(12).sort_values("importance")
    fig = go.Figure(go.Bar(x=imp.importance, y=imp.feature, orientation="h", marker_color=T.SERIES[0], width=0.6,
                           text=imp.importance.round(3), textposition="outside", cliponaxis=False))
    fig.update_layout(title=title, xaxis_title="Permutation importance (drop in score)", yaxis_title="", height=420)
    return fig


# ---------------------------------------------------------------------------
# 1. Stock-out risk
# ---------------------------------------------------------------------------
STOCK_CAT = ["commodity", "category", "facility_type", "supplier", "requisition_receipt_status", "knows_min_stock_calculation", "urban_rural"]
STOCK_NUM = ["stock_balance", "stock_adequacy_ratio", "quantity_received", "stockout_days_est", "requisition_submitted_last_cycle_flag",
             "requisition_complete_on_time_flag", "security_risk_lga", "distance_to_lga_hq_km", "readiness_score", "attendance_rate",
             "prev_stockout_flag", "round_number"]


def stockout_model(visits, com):
    df = com.merge(visits[["visit_id", "readiness_score", "attendance_rate", "distance_to_lga_hq_km"]], on="visit_id")
    df = df.sort_values(["facility_id", "commodity", "round_number"])
    key = ["facility_id", "commodity"]
    df["prev_stockout_flag"] = df.groupby(key)["stockout_flag"].shift(1).fillna(0)
    df["target_next"] = df.groupby(key)["stockout_flag"].shift(-1)
    df["stock_adequacy_ratio"] = df["stock_adequacy_ratio"].clip(upper=10)
    for c in ["requisition_receipt_status", "supplier", "knows_min_stock_calculation"]:
        df[c] = df[c].fillna("Unknown")
    df[STOCK_NUM] = df[STOCK_NUM].astype(float).fillna(0)

    labelled = df[df.target_next.notna()]
    train = labelled[labelled.round_number < LAST_ROUND - 1]
    test = labelled[labelled.round_number == LAST_ROUND - 1]
    X_tr, y_tr = train[STOCK_CAT + STOCK_NUM], train.target_next.astype(int)
    X_te, y_te = test[STOCK_CAT + STOCK_NUM], test.target_next.astype(int)

    candidates = {
        "logistic_regression": LogisticRegression(max_iter=2000, C=0.5),
        "random_forest": RandomForestClassifier(n_estimators=200, min_samples_leaf=10, max_depth=14, random_state=C.RANDOM_SEED, n_jobs=-1),
        "gradient_boosting": GradientBoostingClassifier(n_estimators=300, learning_rate=0.05, max_depth=3, random_state=C.RANDOM_SEED),
    }
    scores, fitted = {}, {}
    for name, model in candidates.items():
        pipe = make_pipeline(model, STOCK_CAT, STOCK_NUM).fit(X_tr, y_tr)
        p = pipe.predict_proba(X_te)[:, 1]
        scores[name] = {"roc_auc": float(roc_auc_score(y_te, p)), "avg_precision": float(average_precision_score(y_te, p))}
        fitted[name] = (pipe, p)
    best = max(scores, key=lambda k: scores[k]["roc_auc"])
    pipe, p = fitted[best]

    fpr, tpr, _ = roc_curve(y_te, p)
    prec, rec, thr = precision_recall_curve(y_te, p)
    roc_fig = go.Figure()
    roc_fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"{best} (AUC {scores[best]['roc_auc']:.3f})", line=dict(width=2, color=T.SERIES[0])))
    roc_fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Chance", line=dict(dash="dot", color=T.TEXT_SECONDARY)))
    roc_fig.update_layout(title="Stock-out risk model - ROC curve (held-out round)", xaxis_title="False positive rate", yaxis_title="True positive rate")
    imp = feature_importance(pipe, X_te, y_te, "roc_auc")

    # Risk scores for the next (unobserved) round, from the latest visit of each facility x commodity
    latest = df[df.round_number == LAST_ROUND].copy()
    latest["stockout_risk"] = pipe.predict_proba(latest[STOCK_CAT + STOCK_NUM])[:, 1]
    preds = latest[["facility_id", "lga", "facility_type", "commodity", "category", "stock_balance", "minimum_stock_level", "supplier", "stockout_flag", "stockout_risk"]]
    # Threshold chosen to maximise F1 on the held-out round
    f1 = 2 * prec[:-1] * rec[:-1] / np.clip(prec[:-1] + rec[:-1], 1e-9, None)
    best_thr = float(thr[int(np.nanargmax(f1))])
    joblib.dump(pipe, ML_DIR / "stockout_model.joblib", compress=3)
    return {
        "name": "Stock-out risk (next visit)", "task": "classification", "best_model": best, "candidates": scores,
        "train_rows": int(len(train)), "test_rows": int(len(test)), "positive_rate_test": float(y_te.mean()),
        "recommended_threshold": best_thr, "features": STOCK_CAT + STOCK_NUM,
        "importance": imp.head(12).to_dict(orient="records"),
    }, preds, {"roc": roc_fig, "importance": importance_fig(imp, "What predicts a stock-out at the next visit?")}


# ---------------------------------------------------------------------------
# 2. Attendance driver model
# ---------------------------------------------------------------------------
# Next-round attendance is dominated by small-headcount sampling noise (a
# facility with 8 scheduled staff swings +/-12 points by chance), so instead of
# forecasting it we model what attendance to *expect* under the conditions
# observed at a visit (salary, roster, security, distance, size). The model is
# validated on facilities it has never seen (GroupKFold) and used for a
# counterfactual: expected attendance for each facility if salary were on time.
ATT_CAT = ["facility_type", "urban_rural", "lga", "hours_of_operation", "salary_delay_length", "staff_leave_facility_for_salary_frequency"]
ATT_NUM = ["salary_paid_on_time_last_3_months_flag", "salary_issues_past_6_months_flag", "roster_updated_this_week_flag",
           "has_duty_roster_flag", "maintains_attendance_register_flag", "attendance_register_updated_daily_flag", "distance_to_lga_hq_km",
           "total_health_workers", "permanent_health_workers", "security_risk_lga", "security_incident_reported_flag"]


def attendance_model(visits):
    from sklearn.model_selection import GroupKFold, cross_val_predict
    df = visits[visits.attendance_rate.notna()].copy()
    df[ATT_NUM] = df[ATT_NUM].astype(float).fillna(0)
    for c in ATT_CAT:
        df[c] = df[c].fillna("Unknown")
    X, y = df[ATT_CAT + ATT_NUM], df.attendance_rate
    w = df.permanent_scheduled_today.clip(lower=1)
    model = GradientBoostingRegressor(n_estimators=300, learning_rate=0.05, max_depth=2, random_state=C.RANDOM_SEED)
    pipe = make_pipeline(model, ATT_CAT, ATT_NUM)
    cv_pred = cross_val_predict(pipe, X, y, groups=df.facility_id, cv=GroupKFold(5), params={"model__sample_weight": w})
    metrics = {"grouped_cv_r2": float(r2_score(y, cv_pred)), "grouped_cv_r2_headcount_weighted": float(r2_score(y, cv_pred, sample_weight=w)),
               "grouped_cv_mae": float(mean_absolute_error(y, cv_pred)),
               "naive_global_mean_mae": float(mean_absolute_error(y, np.full(len(y), y.mean())))}
    pipe.fit(X, y, model__sample_weight=w)
    imp = feature_importance(pipe, X, y, "neg_mean_absolute_error")
    scatter = px.scatter(x=y, y=cv_pred, labels={"x": "Observed attendance", "y": "Expected attendance (out-of-sample)"},
                         title=f"Attendance driver model - grouped cross-validation (R² {metrics['grouped_cv_r2']:.2f}, MAE {metrics['grouped_cv_mae']:.3f})",
                         color_discrete_sequence=[T.SERIES[0]], opacity=0.5)
    scatter.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", line=dict(dash="dot", color=T.TEXT_SECONDARY), name="Perfect"))
    scatter.update_layout(xaxis_tickformat=".0%", yaxis_tickformat=".0%", showlegend=False)

    latest = df[df.round_number == LAST_ROUND].copy()
    latest["expected_attendance"] = np.clip(pipe.predict(latest[ATT_CAT + ATT_NUM]), 0, 1)
    cf = latest[ATT_CAT + ATT_NUM].copy()
    cf["salary_paid_on_time_last_3_months_flag"] = 1.0; cf["salary_issues_past_6_months_flag"] = 0.0; cf["salary_delay_length"] = "No delay"
    latest["expected_attendance_if_salary_on_time"] = np.clip(pipe.predict(cf), 0, 1)
    cf2 = latest[ATT_CAT + ATT_NUM].copy(); cf2["roster_updated_this_week_flag"] = 1.0; cf2["has_duty_roster_flag"] = 1.0
    latest["expected_attendance_if_roster_updated"] = np.clip(pipe.predict(cf2), 0, 1)
    metrics["mean_gain_salary_on_time"] = float((latest.expected_attendance_if_salary_on_time - latest.expected_attendance).mean())
    metrics["mean_gain_roster_updated"] = float((latest.expected_attendance_if_roster_updated - latest.expected_attendance).mean())
    joblib.dump(pipe, ML_DIR / "attendance_model.joblib", compress=3)
    return {"name": "Permanent staff attendance drivers", "task": "regression", "best_model": "gradient_boosting", "metrics": metrics,
            "train_rows": int(len(df)), "validation": "GroupKFold(5) by facility", "features": ATT_CAT + ATT_NUM, "importance": imp.head(12).to_dict(orient="records")}, \
        latest[["facility_id", "attendance_rate", "expected_attendance", "expected_attendance_if_salary_on_time", "expected_attendance_if_roster_updated"]], \
        {"scatter": scatter, "importance": importance_fig(imp, "What drives permanent staff attendance?")}


# ---------------------------------------------------------------------------
# 3. At-risk facility
# ---------------------------------------------------------------------------
RISK_CAT = ["facility_type", "urban_rural", "requisition_frequency", "vaccine_stock_status"]
RISK_NUM = ["readiness_score", "attendance_rate", "stockout_rate", "vaccine_availability_rate", "session_completion_rate", "cce_functionality_rate",
            "facility_open_on_arrival_flag", "salary_paid_on_time_last_3_months_flag", "requisition_submitted_last_cycle_flag", "roster_updated_this_week_flag",
            "cold_chain_interruption_since_last_visit_flag", "security_risk_lga", "security_incident_reported_flag", "distance_to_lga_hq_km",
            "total_health_workers", "commodities_below_min", "round_number"]


def at_risk_model(visits):
    df = visits.sort_values(["facility_id", "round_number"]).copy()
    df["target_next"] = (df.groupby("facility_id")["readiness_score"].shift(-1) < AT_RISK_THRESHOLD).astype(float)
    df.loc[df.groupby("facility_id")["readiness_score"].shift(-1).isna(), "target_next"] = np.nan
    df[RISK_NUM] = df[RISK_NUM].astype(float).fillna(0)
    labelled = df[df.target_next.notna()]
    train = labelled[labelled.round_number < LAST_ROUND - 1]
    test = labelled[labelled.round_number == LAST_ROUND - 1]
    X_tr, y_tr = train[RISK_CAT + RISK_NUM], train.target_next.astype(int)
    X_te, y_te = test[RISK_CAT + RISK_NUM], test.target_next.astype(int)
    pipe = make_pipeline(RandomForestClassifier(n_estimators=300, min_samples_leaf=4, max_depth=12, class_weight="balanced", random_state=C.RANDOM_SEED, n_jobs=-1), RISK_CAT, RISK_NUM).fit(X_tr, y_tr)
    p = pipe.predict_proba(X_te)[:, 1]
    metrics = {"roc_auc": float(roc_auc_score(y_te, p)), "avg_precision": float(average_precision_score(y_te, p)), "positive_rate_test": float(y_te.mean())}
    imp = feature_importance(pipe, X_te, y_te, "roc_auc")
    fpr, tpr, _ = roc_curve(y_te, p)
    roc_fig = go.Figure()
    roc_fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name=f"Random forest (AUC {metrics['roc_auc']:.3f})", line=dict(width=2, color=T.SERIES[2])))
    roc_fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="Chance", line=dict(dash="dot", color=T.TEXT_SECONDARY)))
    roc_fig.update_layout(title=f"At-risk facility model (readiness < {AT_RISK_THRESHOLD:.0f} next visit) - ROC curve", xaxis_title="False positive rate", yaxis_title="True positive rate")
    latest = df[df.round_number == LAST_ROUND].copy()
    latest["at_risk_probability"] = pipe.predict_proba(latest[RISK_CAT + RISK_NUM])[:, 1]
    joblib.dump(pipe, ML_DIR / "at_risk_model.joblib", compress=3)
    return {"name": f"Facility at risk (readiness < {AT_RISK_THRESHOLD:.0f} next visit)", "task": "classification", "best_model": "random_forest", "metrics": metrics,
            "train_rows": int(len(train)), "test_rows": int(len(test)), "features": RISK_CAT + RISK_NUM, "importance": imp.head(12).to_dict(orient="records")}, \
        latest[["facility_id", "readiness_score", "at_risk_probability"]], {"roc": roc_fig, "importance": importance_fig(imp, "What predicts a facility slipping into the at-risk band?")}


# ---------------------------------------------------------------------------
# 4. Facility segmentation
# ---------------------------------------------------------------------------
SEG_COLS = ["facility_open_on_arrival_flag", "attendance_rate", "stockout_rate", "vaccine_availability_rate", "session_completion_rate", "cce_functionality_rate", "salary_paid_on_time_last_3_months_flag", "requisition_submitted_last_cycle_flag"]


def segmentation(visits):
    prof = visits.groupby("facility_id")[SEG_COLS].mean()
    prof = prof.fillna(prof.mean())
    X = StandardScaler().fit_transform(prof)
    best_k, best_s = 3, -1
    for k in (3, 4, 5):
        labels = KMeans(n_clusters=k, n_init=10, random_state=C.RANDOM_SEED).fit_predict(X)
        s = silhouette_score(X, labels)
        if s > best_s:
            best_k, best_s = k, s
    km = KMeans(n_clusters=best_k, n_init=10, random_state=C.RANDOM_SEED).fit(X)
    prof["segment_id"] = km.labels_
    centres = prof.groupby("segment_id")[SEG_COLS].mean()
    order = centres.mean(axis=1).sort_values(ascending=False).index.tolist()
    z = (centres - centres.mean()) / centres.std().replace(0, 1)
    z["stockout_rate"] *= -1  # higher stock-out is worse
    good_cols = ["attendance_rate", "stockout_rate", "vaccine_availability_rate", "session_completion_rate"]
    name_map, used = {}, set()
    for i, sid in enumerate(order):
        if i == 0:
            name = "High performers"
        else:
            weakest = z.loc[sid, good_cols].idxmin()
            name = {"attendance_rate": "Staffing-constrained", "stockout_rate": "Stock-constrained",
                    "vaccine_availability_rate": "Vaccine-constrained", "session_completion_rate": "Service-delivery-constrained"}[weakest]
            if i == len(order) - 1 and best_k > 2:
                name = "Multi-constraint / priority"
        while name in used:
            name += " (2)"
        used.add(name); name_map[sid] = name
    names = [name_map[s] for s in order]
    prof["segment"] = prof.segment_id.map(name_map)
    centres = centres.rename(index=name_map).loc[names]
    long = centres.reset_index().melt(id_vars="segment_id", var_name="indicator", value_name="value")
    long["indicator"] = long.indicator.str.replace("_flag", "").str.replace("_rate", "").str.replace("_", " ")
    fig = px.bar(long, x="indicator", y="value", color="segment_id", barmode="group", text="value", title=f"Facility segments (k={best_k}, silhouette {best_s:.2f}) - mean indicator profile",
                 color_discrete_sequence=T.SERIES, category_orders={"segment_id": names})
    fig.update_traces(texttemplate="%{text:.0%}", textposition="outside", width=0.8 / best_k)
    fig.update_layout(yaxis_tickformat=".0%", xaxis_title="", yaxis_title="", legend_title="", yaxis_range=[0, 1.1])
    return {"k": best_k, "silhouette": float(best_s), "segment_sizes": prof.segment.value_counts().to_dict(),
            "centres": centres.round(3).reset_index().to_dict(orient="records")}, prof[["segment"]].reset_index(), fig


def main(db_path: Path = C.DB_PATH):
    ML_DIR.mkdir(parents=True, exist_ok=True)
    visits, com = load_frames(db_path)
    figures = {}

    so_meta, so_pred, so_figs = stockout_model(visits, com)
    att_meta, att_pred, att_figs = attendance_model(visits)
    risk_meta, risk_pred, risk_figs = at_risk_model(visits)
    seg_meta, seg_df, seg_fig = segmentation(visits)
    figures.update({"stockout_roc": so_figs["roc"], "stockout_importance": so_figs["importance"], "attendance_scatter": att_figs["scatter"],
                    "attendance_importance": att_figs["importance"], "at_risk_roc": risk_figs["roc"], "at_risk_importance": risk_figs["importance"], "segments": seg_fig})

    facility_scores = (visits[visits.round_number == LAST_ROUND][["facility_id", "facility_name", "lga", "facility_type", "readiness_score", "attendance_rate", "stockout_rate", "vaccine_availability_rate"]]
                       .merge(att_pred.drop(columns=["attendance_rate"]), on="facility_id")
                       .merge(risk_pred.drop(columns=["readiness_score"]), on="facility_id")
                       .merge(seg_df, on="facility_id")
                       .merge(so_pred.groupby("facility_id").stockout_risk.mean().rename("mean_stockout_risk").reset_index(), on="facility_id"))
    facility_scores = facility_scores.sort_values("at_risk_probability", ascending=False)
    facility_scores.to_csv(ML_DIR / "facility_predictions.csv", index=False)
    so_pred.sort_values("stockout_risk", ascending=False).to_csv(ML_DIR / "commodity_stockout_predictions.csv", index=False)

    metrics = {"stockout": so_meta, "attendance": att_meta, "at_risk": risk_meta, "segmentation": seg_meta,
               "figures": {k: f"figures/ml_{k}.html" for k in figures}}
    for k, fig in figures.items():
        fig.write_html(C.FIGURE_DIR / f"ml_{k}.html", include_plotlyjs="cdn")
    (ML_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float))
    (ML_DIR / "figures.json").write_text(json.dumps({k: json.loads(fig.to_json()) for k, fig in figures.items()}))

    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk in ("best_model", "candidates", "metrics", "positive_rate_test", "recommended_threshold", "k", "silhouette", "segment_sizes")}
                      for k, v in metrics.items() if k != "figures"}, indent=2, default=float))
    print("\nTop-10 facilities by at-risk probability:")
    print(facility_scores[["facility_id", "facility_name", "lga", "readiness_score", "at_risk_probability", "expected_attendance", "expected_attendance_if_salary_on_time", "mean_stockout_risk", "segment"]].head(10).to_string(index=False))


if __name__ == "__main__":
    main()

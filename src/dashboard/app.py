"""
Module 8 -- Streamlit Dashboard.

Reads all NeuroFence tables and shows:
    - Total tests, normal vs adversarial breakdown
    - Detected anomalies, detection rate
    - Model behavior statistics
    - Security risk distribution (Member-2 risk scorer)
    - Suspicious executions
    - Test history table
    - Security score + evaluation metrics with accuracy
    - Charts (category breakdown, anomaly method comparison, metrics)

Run:
    streamlit run src/dashboard/app.py
"""

import sys
import os

# Allow running via `streamlit run src/dashboard/app.py` from project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import streamlit as st
import pandas as pd
import plotly.express as px

from src.db.db_manager import get_session
from src.db.models import (
    Prompt, FuzzResult, BackdoorTest, AnomalyResult, EvaluationMetric,
    EvaluationConfusion, RiskAssessmentRow
)


st.set_page_config(page_title="NeuroFence Dashboard", layout="wide")


@st.cache_data(ttl=30)
def load_data():
    session = get_session()
    try:
        prompts = pd.read_sql(session.query(Prompt).statement, session.bind)
        fuzz = pd.read_sql(session.query(FuzzResult).statement, session.bind)
        backdoor = pd.read_sql(session.query(BackdoorTest).statement, session.bind)
        anomalies = pd.read_sql(session.query(AnomalyResult).statement, session.bind)
        metrics = pd.read_sql(session.query(EvaluationMetric).statement, session.bind)
        confusion = pd.read_sql(session.query(EvaluationConfusion).statement, session.bind)
        risk = pd.read_sql(session.query(RiskAssessmentRow).statement, session.bind)
        return prompts, fuzz, backdoor, anomalies, metrics, confusion, risk
    finally:
        session.close()


def _latest_cohort(df: pd.DataFrame) -> pd.DataFrame:
    """Select only the rows from the most-recent pipeline run so that
    counts are not inflated by repeated runs."""
    if df.empty or "created_at" not in df.columns:
        return df
    max_ts = df["created_at"].max()
    return df[df["created_at"] == max_ts].copy()


def _build_prompt_text_map(fuzz_df: pd.DataFrame, backdoor_df: pd.DataFrame,
                           prompts_df: pd.DataFrame) -> dict:
    prompt_text = dict(zip(prompts_df["prompt_id"], prompts_df["text"])) if not prompts_df.empty else {}
    lookup = {}
    if not fuzz_df.empty:
        for _, row in fuzz_df.iterrows():
            lookup[(row["fuzz_id"], "fuzz")] = prompt_text.get(row["prompt_id"], row["original_prompt"])
    if not backdoor_df.empty:
        for _, row in backdoor_df.iterrows():
            lookup[(row["test_id"], "backdoor")] = row["trigger_prompt"]
    return lookup


st.title("🛡️ NeuroFence -- AI Security & Backdoor Detection Dashboard")
st.caption("All results below are from local/simulated testing only. No real third-party systems were tested.")

prompts_df, fuzz_df, backdoor_df, anomalies_df, metrics_df, confusion_df, risk_df = load_data()

if prompts_df.empty:
    st.warning("No data found. Run Modules 2-7 first (dataset_builder, fuzz_runner, "
               "trigger_injector, analyzer, model_comparator, metrics) to populate the database.")
    st.stop()

# ---- Top-level KPIs ----
col1, col2, col3, col4 = st.columns(4)

total_prompts = len(prompts_df)
total_fuzz_tests = len(fuzz_df)
total_backdoor_tests = len(backdoor_df)
total_anomalies = int(anomalies_df["is_anomaly"].sum()) if not anomalies_df.empty else 0

col1.metric("Total Prompts", total_prompts)
col2.metric("Fuzz Test Runs", total_fuzz_tests)
col3.metric("Backdoor Tests", total_backdoor_tests)
col4.metric("Anomalies Detected (all methods)", total_anomalies)

st.divider()

# ---- Security Risk Distribution ----
st.subheader("Security Risk Distribution (Module 6c)")
latest_risk = _latest_cohort(risk_df)

if not latest_risk.empty:
    risk_level_counts = latest_risk["risk_level"].value_counts()
    risk_totals = pd.DataFrame({
        "level": risk_level_counts.index,
        "count": risk_level_counts.values,
    })
    risk_totals = risk_totals.set_index("level").reindex(["CRITICAL", "HIGH", "MEDIUM", "LOW"]).dropna().reset_index()
    fig_risk = px.pie(risk_totals, names="level", values="count", color="level",
                      color_discrete_map={"CRITICAL": "#d32f2f", "HIGH": "#f57c00",
                                          "MEDIUM": "#fbc02d", "LOW": "#4caf50"},
                      title="Risk Level Distribution (latest run)")
    st.plotly_chart(fig_risk, use_container_width=True)
    st.dataframe(risk_totals, use_container_width=True)

    high_critical = int(risk_totals[risk_totals["level"].isin(["HIGH", "CRITICAL"])]["count"].sum())
    low_med = int(risk_totals[risk_totals["level"].isin(["LOW", "MEDIUM"])]["count"].sum())
    st.metric("Executions LOW/MEDIUM (safe)", f"{low_med}  ({round(100*low_med/len(latest_risk),1)}%)")
    st.metric("Executions HIGH/CRITICAL (investigate)", f"{high_critical}")
else:
    st.info("No risk assessments yet. Run Module 6c first.")

# ---- Suspicious Cases ----
st.subheader("Top Suspicious Executions")
if not latest_risk.empty:
    prompt_map = _build_prompt_text_map(fuzz_df, backdoor_df, prompts_df)
    top = latest_risk.sort_values("risk_score", ascending=False).head(8)
    rows = []
    for _, r in top.iterrows():
        notes = []
        if float(r.get("trigger_signal", 0)) > 0:
            notes.append("trigger")
        if float(r.get("injection_signal", 0)) > 0:
            notes.append("injection")
        if not notes:
            notes.append("behavioral anomaly")
        text = prompt_map.get((r["source_ref_id"], r["source_type"]), "(source not found)")
        rows.append({
            "risk_score": round(r["risk_score"], 1),
            "risk_level": r["risk_level"],
            "source_type": r["source_type"],
            "prompt (truncated)": (text[:80] + "...") if len(str(text)) > 80 else text,
            "signals": ", ".join(notes),
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
else:
    st.info("Run Module 6c to view suspicious execution cases.")

st.divider()

# ---- Category breakdown ----
st.subheader("Prompt Category Breakdown")
cat_counts = prompts_df["category"].value_counts().reset_index()
cat_counts.columns = ["category", "count"]
fig_cat = px.bar(cat_counts, x="category", y="count", color="category",
                  title="Normal vs Adversarial vs Malicious vs Trigger Prompts")
st.plotly_chart(fig_cat, use_container_width=True)

# ---- Fuzz detection rate ----
st.subheader("Fuzz Detection Rate (heuristic first-pass)")
if not fuzz_df.empty:
    detection_counts = fuzz_df["detection_result"].value_counts().reset_index()
    detection_counts.columns = ["result", "count"]
    fig_detect = px.pie(detection_counts, names="result", values="count",
                         title="Flagged vs Clean (heuristic)")
    st.plotly_chart(fig_detect, use_container_width=True)
else:
    st.info("No fuzz results yet.")

# ---- Backdoor results ----
st.subheader("Simulated Backdoor Test Results")
if not backdoor_df.empty:
    fired_count = int(backdoor_df["triggered_flag"].sum())
    total_bd = len(backdoor_df)
    st.write(f"Backdoor fired as expected in **{fired_count}/{total_bd}** synthetic trigger tests.")
    st.dataframe(
        backdoor_df[["trigger_name", "triggered_flag", "trigger_prompt"]],
        use_container_width=True,
    )
else:
    st.info("No backdoor test results yet.")

# ---- Anomaly detection method comparison ----
st.subheader("Anomaly Detection: Method Comparison")
if not anomalies_df.empty:
    method_summary = (
        anomalies_df.groupby("model_used")["is_anomaly"]
        .agg(["sum", "count"])
        .reset_index()
    )
    method_summary.columns = ["method", "anomalies_flagged", "total_tested"]
    method_summary["detection_rate_%"] = (
        100 * method_summary["anomalies_flagged"] / method_summary["total_tested"]
    ).round(1)

    fig_methods = px.bar(
        method_summary, x="method", y="anomalies_flagged", color="method",
        title="Anomalies Flagged per Method"
    )
    st.plotly_chart(fig_methods, use_container_width=True)
    st.dataframe(method_summary, use_container_width=True)
else:
    st.info("No anomaly detection results yet.")

# ---- Security score ----
st.subheader("Security Score")
if not latest_risk.empty:
    low_med_count = int(latest_risk["risk_level"].isin(["LOW", "MEDIUM"]).sum())
    security_score = round(100 * low_med_count / len(latest_risk), 1)
    st.metric("Security Score (LOW/MEDIUM risk share)", f"{security_score} / 100")
    st.caption(
        "Security score = share of test executions rated LOW or MEDIUM risk "
        "(higher is stronger). A score of 100 means no HIGH/CRITICAL cases. "
        "Derived from Module 6c risk scoring, not an absolute real-world rating."
    )
else:
    st.info("Run Module 6c to compute a security score.")

# ---- Evaluation metrics with accuracy ----
st.subheader("Detection Metrics (Module 7)")
if not metrics_df.empty:
    if not confusion_df.empty:
        metrics_df = metrics_df.merge(
            confusion_df[["run_id", "accuracy", "true_positive", "true_negative",
                          "false_positive", "false_negative"]],
            on="run_id", how="left"
        )

    st.metric("Avg ML F1 (detector cross-check, NOT the security score)",
              f"{metrics_df['f1_score'].mean():.3f}")
    st.caption(
        "ML detector F1 measures agreement with NeuroFence's own heuristic "
        "ground truth, not an absolute detection rate. The deterministic "
        "trigger/risk stages are the primary signals."
    )
    st.dataframe(
        metrics_df[["run_id", "precision", "recall", "f1_score",
                     "accuracy", "false_positive_rate", "false_negative_rate", "coverage"]]
            .rename(columns={
                "precision": "Prec", "recall": "Rec", "f1_score": "F1",
                "accuracy": "Acc", "false_positive_rate": "FPR",
                "false_negative_rate": "FNR"
            }),
        use_container_width=True,
    )
    fig_metrics = px.bar(
        metrics_df, x="run_id",
        y=["precision", "recall", "f1_score", "accuracy"] if "accuracy" in metrics_df.columns
        else ["precision", "recall", "f1_score"],
        barmode="group", title="Evaluation Metrics by Run"
    )
    st.plotly_chart(fig_metrics, use_container_width=True)
else:
    st.info("No evaluation metrics yet. Run Module 7 first.")

# ---- Test history table ----
st.subheader("Test History (Fuzz Results)")
if not fuzz_df.empty:
    st.dataframe(
        fuzz_df[["fuzz_id", "prompt_id", "mutation_type", "detection_result", "created_at"]]
        .sort_values("fuzz_id", ascending=False)
        .head(50),
        use_container_width=True,
    )

"""
Module 8 -- Streamlit Dashboard.

Reads all NeuroFence tables and shows:
    - Total tests, normal vs adversarial breakdown
    - Detected anomalies, detection rate
    - Model behavior statistics
    - Test history table
    - Security score
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
    Prompt, FuzzResult, BackdoorTest, AnomalyResult, EvaluationMetric
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
        return prompts, fuzz, backdoor, anomalies, metrics
    finally:
        session.close()


st.title("🛡️ NeuroFence -- AI Security & Backdoor Detection Dashboard")
st.caption("All results below are from local/simulated testing only. No real third-party systems were tested.")

prompts_df, fuzz_df, backdoor_df, anomalies_df, metrics_df = load_data()

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
if not metrics_df.empty:
    avg_f1 = metrics_df["f1_score"].mean()
    security_score = round(avg_f1 * 100, 1)
    st.metric("Overall Security Score (avg F1 across methods x 100)", f"{security_score}")
    st.caption(
        "Security score is a simple composite of detector F1-scores against "
        "the toy model's known heuristic/backdoor labels -- not an absolute "
        "real-world security rating."
    )

    fig_metrics = px.bar(
        metrics_df, x="run_id", y=["precision", "recall", "f1_score"],
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

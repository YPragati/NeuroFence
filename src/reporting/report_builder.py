"""
Module 9 -- Automated Security Testing Report Generator.

Reads all NeuroFence tables, fills in report_template.md, and
writes a timestamped Markdown report to outputs/reports/. Also
logs the report's path into the `reports` table.

Run:
    python -m src.reporting.report_builder
"""

import os
import uuid
from datetime import datetime, timezone

import pandas as pd

from src.db.db_manager import get_session
from src.db.models import (
    Prompt, FuzzResult, BackdoorTest, AnomalyResult, EvaluationMetric, Report
)
from src.config_loader import get_config


def _project_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _template_path() -> str:
    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "templates", "report_template.md"
    )


def build_category_table(prompts_df: pd.DataFrame) -> str:
    if prompts_df.empty:
        return "| (no data) | 0 |"
    counts = prompts_df["category"].value_counts()
    lines = [f"| {cat} | {count} |" for cat, count in counts.items()]
    return "\n".join(lines)


def build_backdoor_findings(backdoor_df: pd.DataFrame) -> str:
    if backdoor_df.empty:
        return "No backdoor tests were run in this session."

    fired = int(backdoor_df["triggered_flag"].sum())
    total = len(backdoor_df)
    lines = [
        f"Out of **{total}** synthetic trigger tests, the toy model's "
        f"backdoor fired as expected in **{fired}** cases "
        f"({round(100 * fired / total, 1)}%).",
        "",
        "| Trigger | Fired as Expected |",
        "|---|---|",
    ]
    for _, row in backdoor_df.iterrows():
        lines.append(f"| {row['trigger_name']} | {'Yes' if row['triggered_flag'] else 'No'} |")
    return "\n".join(lines)


def build_anomaly_table(anomalies_df: pd.DataFrame) -> str:
    if anomalies_df.empty:
        return "No anomaly detection results available."

    summary = (
        anomalies_df.groupby("model_used")["is_anomaly"]
        .agg(["sum", "count"])
        .reset_index()
    )
    summary.columns = ["method", "flagged", "total"]

    lines = ["| Method | Flagged | Total | Detection Rate |", "|---|---|---|---|"]
    for _, row in summary.iterrows():
        rate = round(100 * row["flagged"] / row["total"], 1) if row["total"] else 0
        lines.append(f"| {row['method']} | {row['flagged']} | {row['total']} | {rate}% |")
    return "\n".join(lines)


def build_metrics_table(metrics_df: pd.DataFrame) -> str:
    if metrics_df.empty:
        return "No evaluation metrics available. Run Module 7 first."

    lines = [
        "| Run | Precision | Recall | F1 | FPR | FNR | Coverage |",
        "|---|---|---|---|---|---|---|",
    ]
    for _, row in metrics_df.iterrows():
        lines.append(
            f"| {row['run_id']} | {row['precision']} | {row['recall']} | "
            f"{row['f1_score']} | {row['false_positive_rate']} | "
            f"{row['false_negative_rate']} | {row['coverage']} |"
        )
    return "\n".join(lines)


def build_recommendations(backdoor_df: pd.DataFrame, metrics_df: pd.DataFrame) -> str:
    recs = []

    if not backdoor_df.empty and backdoor_df["triggered_flag"].sum() > 0:
        recs.append(
            "- The toy model showed synthetic backdoor behavior for known trigger "
            "tags. In a real deployment scenario, this pattern (output changing "
            "only in the presence of a specific input marker) should be "
            "investigated as a potential backdoor/data-poisoning indicator."
        )

    if not metrics_df.empty:
        avg_recall = metrics_df["recall"].mean()
        if avg_recall < 0.5:
            recs.append(
                "- Average recall across anomaly detection methods is below 0.5. "
                "Consider adding more behavior-score features (beyond consistency/"
                "similarity/confidence) or tuning the `contamination` parameter "
                "in config/settings.yaml to improve sensitivity."
            )
        else:
            recs.append(
                "- Anomaly detection recall is reasonable for this test set. "
                "Continue expanding the trigger/adversarial prompt dataset to "
                "validate detection robustness against new variants."
            )

    recs.append(
        "- Expand the prompt dataset (Module 2) with additional adversarial and "
        "malicious-pattern examples over time to keep fuzzing coverage current."
    )

    return "\n".join(recs) if recs else "No specific recommendations at this time."


def generate_report():
    session = get_session()
    try:
        prompts_df = pd.read_sql(session.query(Prompt).statement, session.bind)
        fuzz_df = pd.read_sql(session.query(FuzzResult).statement, session.bind)
        backdoor_df = pd.read_sql(session.query(BackdoorTest).statement, session.bind)
        anomalies_df = pd.read_sql(session.query(AnomalyResult).statement, session.bind)
        metrics_df = pd.read_sql(session.query(EvaluationMetric).statement, session.bind)

        run_id = str(uuid.uuid4())[:8]
        generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

        security_score = (
            round(metrics_df["f1_score"].mean() * 100, 1) if not metrics_df.empty else "N/A"
        )

        with open(_template_path(), "r") as f:
            template = f.read()

        filled = template
        filled = filled.replace("{{ run_id }}", run_id)
        filled = filled.replace("{{ generated_at }}", generated_at)
        filled = filled.replace("{{ total_prompts }}", str(len(prompts_df)))
        filled = filled.replace("{{ total_fuzz_runs }}", str(len(fuzz_df)))
        filled = filled.replace("{{ total_backdoor_tests }}", str(len(backdoor_df)))
        filled = filled.replace("{{ security_score }}", str(security_score))
        filled = filled.replace("{{ mutation_type_count }}", "7")
        filled = filled.replace("{{ category_table }}", build_category_table(prompts_df))
        filled = filled.replace("{{ backdoor_findings }}", build_backdoor_findings(backdoor_df))
        filled = filled.replace("{{ anomaly_results_table }}", build_anomaly_table(anomalies_df))
        filled = filled.replace("{{ metrics_table }}", build_metrics_table(metrics_df))
        filled = filled.replace(
            "{{ recommendations }}", build_recommendations(backdoor_df, metrics_df)
        )

        cfg = get_config()
        reports_dir = os.path.join(_project_root(), cfg["paths"]["outputs_reports"])
        os.makedirs(reports_dir, exist_ok=True)

        filename = f"neurofence_report_{run_id}.md"
        out_path = os.path.join(reports_dir, filename)

        with open(out_path, "w") as f:
            f.write(filled)

        report_row = Report(run_id=run_id, file_path=out_path)
        session.add(report_row)
        session.commit()

        print(f"Report generated: {out_path}")
        return out_path

    finally:
        session.close()


if __name__ == "__main__":
    generate_report()

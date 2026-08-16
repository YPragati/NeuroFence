"""
Module 6 -- Anomaly Detection: Model Comparator.

Runs Isolation Forest, One-Class SVM, and LOF on the same feature
matrix, writes all results to anomaly_results (tagged by
model_used), and prints a comparison summary so you can see which
method flags the most/fewest anomalies and how they overlap.

"Best" method selection here is a simple heuristic: since we don't
have hand-labeled ground truth at this stage (that's Module 7's
job, against a labeled validation subset), we default to
Isolation Forest as specified in config (anomaly_detection.default_method)
unless overridden. The comparison numbers are printed either way
so you can judge for yourself.

Run:
    python -m src.anomaly_detection.model_comparator
"""

from src.db.db_manager import get_session
from src.db.models import AnomalyResult
from src.anomaly_detection.feature_extractor import extract_features
from src.anomaly_detection.isolation_forest_model import run_isolation_forest
from src.anomaly_detection.ocsvm_model import run_ocsvm
from src.anomaly_detection.lof_model import run_lof
from src.config_loader import get_config


METHODS = {
    "isolation_forest": run_isolation_forest,
    "ocsvm": run_ocsvm,
    "lof": run_lof,
}


def run_comparison():
    score_ids, X = extract_features()

    if len(score_ids) == 0:
        print("No behavior_scores found. Run Module 5 (behavior_analyzer) first.")
        return

    session = get_session()
    results_summary = {}

    try:
        for method_name, method_fn in METHODS.items():
            is_anomaly, scores = method_fn(X)

            flagged_count = int(is_anomaly.sum())
            results_summary[method_name] = flagged_count

            for i, score_id in enumerate(score_ids):
                result = AnomalyResult(
                    score_id=score_id,
                    model_used=method_name,
                    anomaly_score=float(scores[i]),
                    is_anomaly=bool(is_anomaly[i]),
                )
                session.add(result)

        session.commit()

        print(f"Anomaly detection complete on {len(score_ids)} feature vectors.\n")
        print("Comparison (anomalies flagged out of total):")
        for method_name, count in results_summary.items():
            pct = 100.0 * count / len(score_ids)
            print(f"  {method_name:20s}: {count:4d} / {len(score_ids)} ({pct:.1f}%)")

        cfg = get_config()
        default_method = cfg["anomaly_detection"]["default_method"]
        print(f"\nDefault/selected method (per config): {default_method}")
        print(
            "Note: final method selection should be validated against a "
            "labeled subset in Module 7 (Security Evaluation) before "
            "trusting these numbers as ground truth."
        )

    finally:
        session.close()


if __name__ == "__main__":
    run_comparison()

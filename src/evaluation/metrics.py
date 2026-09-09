"""
Module 7 -- Security Evaluation.

Computes detection metrics by comparing anomaly_results against a
"ground truth" label derived from the fuzz_results.detection_result
heuristic (flagged/clean) and backdoor_tests.triggered_flag -- i.e.
the labels we already know from how the toy model was built to
behave. This lets us compute precision/recall/F1/etc. without
needing a separately hand-labeled dataset for this project's scale.

IMPORTANT: this ground truth is itself a simple heuristic (see
Module 3's heuristic_detect and Module 4's backdoor firing check),
not independently verified labels. Metrics here measure "how well
does the ML anomaly detector agree with our own heuristic/known
backdoor labels" -- clearly labeled as such, not an absolute claim
of real-world detection accuracy.

Run:
    python -m src.evaluation.metrics
"""

import uuid
from sklearn.metrics import (
    precision_score, recall_score, f1_score, confusion_matrix
)

from src.db.db_manager import get_session
from src.db.models import (
    BehaviorScore, AnomalyResult, FuzzResult, BackdoorTest,
    EvaluationMetric, EvaluationConfusion
)


def build_ground_truth(session):
    """
    Returns dict: {score_id: is_actually_anomalous (bool)}
    based on the known heuristic/backdoor labels.
    """
    ground_truth = {}

    # fuzz-sourced scores: ground truth = heuristic detection_result == 'flagged'
    fuzz_scores = (
        session.query(BehaviorScore)
        .filter_by(source_type="fuzz")
        .all()
    )
    fuzz_by_id = {f.fuzz_id: f for f in session.query(FuzzResult).all()}

    for score in fuzz_scores:
        fuzz_row = fuzz_by_id.get(score.source_ref_id)
        if fuzz_row is not None:
            ground_truth[score.score_id] = (fuzz_row.detection_result == "flagged")

    # backdoor-sourced scores: ground truth = triggered_flag
    backdoor_scores = (
        session.query(BehaviorScore)
        .filter_by(source_type="backdoor")
        .all()
    )
    backdoor_by_id = {b.test_id: b for b in session.query(BackdoorTest).all()}

    for score in backdoor_scores:
        backdoor_row = backdoor_by_id.get(score.source_ref_id)
        if backdoor_row is not None:
            ground_truth[score.score_id] = bool(backdoor_row.triggered_flag)

    return ground_truth


def evaluate_method(session, method_name: str, ground_truth: dict) -> dict:
    anomaly_rows = (
        session.query(AnomalyResult)
        .filter_by(model_used=method_name)
        .order_by(AnomalyResult.created_at.desc(), AnomalyResult.anomaly_id.desc())
        .all()
    )

    # If the same score was scored more than once (e.g. module re-runs),
    # keep only the newest prediction so a score is never double counted.
    newest_by_score = {}
    for row in anomaly_rows:
        if row.score_id not in newest_by_score:
            newest_by_score[row.score_id] = row

    y_true = []
    y_pred = []

    for row in newest_by_score.values():
        if row.score_id in ground_truth:
            y_true.append(int(ground_truth[row.score_id]))
            y_pred.append(int(row.is_anomaly))

    if len(y_true) == 0:
        return None

    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0
    accuracy = (tp + tn) / len(y_true) if len(y_true) > 0 else 0.0
    # At most every ground-truth score can be assessed once -> never > 1.0.
    coverage = min(len(y_true) / max(len(ground_truth), 1), 1.0)

    return {
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1_score": round(f1, 3),
        "false_positive_rate": round(fpr, 3),
        "false_negative_rate": round(fnr, 3),
        "accuracy": round(accuracy, 3),
        "true_positive": int(tp),
        "true_negative": int(tn),
        "false_positive": int(fp),
        "false_negative": int(fn),
        "coverage": round(coverage, 3),
    }


def run_evaluation():
    session = get_session()
    run_id = str(uuid.uuid4())[:8]

    try:
        ground_truth = build_ground_truth(session)
        if not ground_truth:
            print("No ground truth available. Run Modules 3-6 first.")
            return

        methods = ["isolation_forest", "ocsvm", "lof"]
        print(f"Evaluation run_id: {run_id}\n")

        for method in methods:
            metrics = evaluate_method(session, method, ground_truth)
            if metrics is None:
                print(f"{method}: no anomaly_results found, skipping.")
                continue

            metric_row = EvaluationMetric(
                run_id=f"{run_id}_{method}",
                precision=metrics["precision"],
                recall=metrics["recall"],
                f1_score=metrics["f1_score"],
                false_positive_rate=metrics["false_positive_rate"],
                false_negative_rate=metrics["false_negative_rate"],
                coverage=metrics["coverage"],
            )
            session.add(metric_row)

            confusion_row = EvaluationConfusion(
                run_id=f"{run_id}_{method}",
                true_positive=metrics["true_positive"],
                true_negative=metrics["true_negative"],
                false_positive=metrics["false_positive"],
                false_negative=metrics["false_negative"],
                accuracy=metrics["accuracy"],
            )
            session.add(confusion_row)

            print(f"-- {method} --")
            print(f"  Precision : {metrics['precision']}")
            print(f"  Recall    : {metrics['recall']}")
            print(f"  F1-score  : {metrics['f1_score']}")
            print(f"  Accuracy  : {metrics['accuracy']}")
            print(f"  FPR       : {metrics['false_positive_rate']}")
            print(f"  FNR       : {metrics['false_negative_rate']}")
            print(f"  Coverage  : {metrics['coverage']}")
            print()

        session.commit()
        print("Metrics saved to evaluation_metrics table.")

    finally:
        session.close()


if __name__ == "__main__":
    run_evaluation()

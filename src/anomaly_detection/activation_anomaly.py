"""
Member-2 -- Activation Anomaly Detector.

Compares activation statistics from a new model execution against
the normal activation baseline collected by NeuroFence.

This module does not collect activations itself.
The leader's ActivationTracker is responsible for collection.

This module performs security analysis on those activations.
"""

import json
from math import sqrt
from typing import Dict, List, Any

from src.db.db_manager import get_session
from src.db.models import ActivationFeature, ActivationAnomalyResult


ACTIVATION_METRICS = [
    "mean",
    "max",
    "min",
    "std",
]


def _mean(values: List[float]) -> float:
    if not values:
        return 0.0

    return sum(values) / len(values)


def _std(values: List[float], mean: float) -> float:
    if len(values) <= 1:
        return 0.0

    variance = sum(
        (value - mean) ** 2
        for value in values
    ) / len(values)

    return sqrt(variance)


def build_baseline_statistics(
    baseline_data: List[Dict[str, Any]]
) -> Dict[str, Dict[str, Dict[str, float]]]:
    """
    Convert raw baseline activation records into statistics.

    Output structure:

        {
            "0": {
                "mean": {"mean": ..., "std": ...},
                "max":  {"mean": ..., "std": ...},
                ...
            }
        }
    """

    layer_values = {}

    for record in baseline_data:
        activations = record.get("activations", {})

        for layer_id, metrics in activations.items():
            layer_id = str(layer_id)

            if layer_id not in layer_values:
                layer_values[layer_id] = {
                    metric: []
                    for metric in ACTIVATION_METRICS
                }

            for metric in ACTIVATION_METRICS:
                if metric in metrics:
                    layer_values[layer_id][metric].append(
                        float(metrics[metric])
                    )

    statistics = {}

    for layer_id, metrics in layer_values.items():
        statistics[layer_id] = {}

        for metric, values in metrics.items():
            if not values:
                continue

            mean = _mean(values)
            std = _std(values, mean)

            statistics[layer_id][metric] = {
                "mean": mean,
                "std": std,
            }

    return statistics


def compare_activations(
    current_activations: Dict[str, Any],
    baseline_statistics: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare one execution's activations against the normal baseline.

    Returns per-layer deviation information and an overall anomaly score.
    """

    layer_results = []
    all_deviations = []

    for layer_id, current_metrics in current_activations.items():

        layer_id = str(layer_id)

        if layer_id not in baseline_statistics:
            continue

        baseline_metrics = baseline_statistics[layer_id]

        metric_deviations = {}

        for metric in ACTIVATION_METRICS:

            if metric not in current_metrics:
                continue

            if metric not in baseline_metrics:
                continue

            current_value = float(current_metrics[metric])

            baseline_mean = float(
                baseline_metrics[metric]["mean"]
            )

            baseline_std = float(
                baseline_metrics[metric]["std"]
            )

            # Prevent division by zero when normal behaviour
            # has almost no variation.
            denominator = max(baseline_std, 1e-6)

            deviation = abs(
                current_value - baseline_mean
            ) / denominator

            metric_deviations[metric] = deviation
            all_deviations.append(deviation)

        if metric_deviations:

            layer_score = _mean(
                list(metric_deviations.values())
            )

            layer_results.append({
                "layer": layer_id,
                "score": layer_score,
                "metrics": metric_deviations,
            })

    overall_score = _mean(all_deviations)

    # Convert deviation into a 0-100 security score.
    anomaly_score = min(
        100.0,
        overall_score * 10.0
    )

    return {
        "anomaly_score": anomaly_score,
        "layers_analyzed": len(layer_results),
        "layer_results": layer_results,
    }


# ---------------------------------------------------------------------------
# Feature-vector activation anomaly detection (member-2).
#
# The collector's ActivationFeatures are a flat 6-feature vector. These
# helpers build a baseline distribution over those features from normal
# executions and compare any new execution against it, producing an
# interpretable 0-100 anomaly score plus per-feature deviations.
# ---------------------------------------------------------------------------

FEATURE_NAMES = [
    "prompt_length",
    "response_length",
    "prompt_hash_score",
    "trigger_signal",
    "injection_signal",
    "response_change_signal",
]


def _denominator(std: float, mean: float) -> float:
    """
    Safe denominator for deviation.

    Uses the observed std when it is meaningful, otherwise a small
    fraction of the mean so that constant features do not explode on
    tiny numerical differences, while a feature that flips from 0 -> 1
    (e.g. a trigger appearing) still produces a huge deviation.
    """
    return max(std, 0.25 * abs(mean) + 1e-6)


def build_feature_baseline_statistics(
    baseline_rows: List[Dict[str, Any]]
) -> Dict[str, Dict[str, float]]:
    """
    Convert raw baseline activation feature rows into per-feature
    {mean, std} statistics.

    Output structure:
        {
            "prompt_length": {"mean": ..., "std": ...},
            "response_length": {"mean": ..., "std": ...},
            ...
        }
    """
    values = {name: [] for name in FEATURE_NAMES}

    for row in baseline_rows:
        for name in FEATURE_NAMES:
            values[name].append(float(row[name]))

    statistics = {}
    for name, samples in values.items():
        mean = _mean(samples)
        statistics[name] = {"mean": mean, "std": _std(samples, mean)}

    return statistics


def compare_feature_vector(
    features: Dict[str, Any],
    baseline_statistics: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Compare one execution's feature vector against the normal baseline.

    Returns:
        {
            "anomaly_score": 0-100,
            "features_analyzed": int,
            "deviations": {feature_name: deviation_value, ...},
        }
    """
    deviations = {}

    for name in FEATURE_NAMES:
        if name not in features or name not in baseline_statistics:
            continue

        current = float(features[name])
        baseline = baseline_statistics[name]

        denominator = _denominator(float(baseline["std"]), float(baseline["mean"]))
        deviations[name] = abs(current - float(baseline["mean"])) / denominator

    overall_deviation = _mean(list(deviations.values()))
    anomaly_score = min(100.0, overall_deviation * 10.0)

    return {
        "anomaly_score": round(anomaly_score, 3),
        "features_analyzed": len(deviations),
        "deviations": {name: round(value, 4) for name, value in deviations.items()},
    }


def run_activation_anomaly_detection() -> int:
    """
    Pipeline step: build the baseline from normal activation features,
    compare every collected execution against it, and persist the
    results to activation_anomaly_results.

    Returns the number of executions scored.
    """
    session = get_session()
    try:
        rows = session.query(ActivationFeature).all()

        if not rows:
            print("No activation features found. Run Modules 3/4 first.")
            return 0

        baseline_rows = [row for row in rows if row.is_baseline]
        if not baseline_rows:
            print(
                "No baseline activation features found "
                "(no normal-category prompts were fuzzed)."
            )
            return 0

        baseline_stats = build_feature_baseline_statistics([
            {name: getattr(row, name) for name in FEATURE_NAMES}
            for row in baseline_rows
        ])

        scored = 0
        for row in rows:
            features = {name: getattr(row, name) for name in FEATURE_NAMES}
            result = compare_feature_vector(features, baseline_stats)

            session.add(ActivationAnomalyResult(
                source_ref_id=row.source_ref_id,
                source_type=row.source_type,
                anomaly_score=result["anomaly_score"],
                features_analyzed=result["features_analyzed"],
                deviations_text=json.dumps(result["deviations"]),
            ))
            scored += 1

        session.commit()

        n_baseline = len(baseline_rows)
        n_trigger = sum(
            1 for row in rows if float(getattr(row, "trigger_signal")) > 0
        )
        n_high = sum(
            1 for row in rows
            if float(getattr(row, "trigger_signal")) > 0
            or float(getattr(row, "injection_signal")) > 0
        )
        print(
            f"Activation anomaly detection complete: {scored} executions scored "
            f"against a {n_baseline}-row normal baseline."
        )
        print(f"  -> executions with trigger signal: {n_trigger}")
        print(f"  -> executions with trigger/injection signal: {n_high}")

        return scored
    finally:
        session.close()

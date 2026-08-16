"""
Member-2 -- Activation Anomaly Detector.

Compares activation statistics from a new model execution against
the normal activation baseline collected by NeuroFence.

This module does not collect activations itself.
The leader's ActivationTracker is responsible for collection.

This module performs security analysis on those activations.
"""

from math import sqrt
from typing import Dict, List, Any


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
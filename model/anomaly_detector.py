
import json
import math


BASELINE_FILE = "baseline_data.json"


class ActivationAnomalyDetector:
    """
    Compares current Transformer activation statistics
    against the normal baseline collected by baseline.py.
    """

    def __init__(self, baseline_file=BASELINE_FILE):
        self.baseline_file = baseline_file
        self.baseline = self._load_baseline()

    def _load_baseline(self):
        with open(
            self.baseline_file,
            "r",
            encoding="utf-8"
        ) as file:
            return json.load(file)

    def _calculate_baseline(self):
        """
        Calculate average and standard deviation for
        each activation metric across all baseline samples.
        """

        layer_values = {}

        for sample in self.baseline:

            for layer, stats in sample["activations"].items():

                if layer not in layer_values:
                    layer_values[layer] = {
                        "mean": [],
                        "std": [],
                        "max": [],
                        "min": []
                    }

                layer_values[layer]["mean"].append(
                    stats["mean"]
                )

                layer_values[layer]["std"].append(
                    stats["std"]
                )

                layer_values[layer]["max"].append(
                    stats["max"]
                )

                layer_values[layer]["min"].append(
                    stats["min"]
                )

        baseline_stats = {}

        for layer, values in layer_values.items():

            baseline_stats[layer] = {}

            for metric, numbers in values.items():

                average = sum(numbers) / len(numbers)

                variance = sum(
                    (x - average) ** 2
                    for x in numbers
                ) / len(numbers)

                standard_deviation = math.sqrt(
                    variance
                )

                baseline_stats[layer][metric] = {
                    "mean": average,
                    "std": standard_deviation
                }

        return baseline_stats

    def analyze(self, activations):
        """
        Compare current activations against the
        normal baseline.

        Returns:
            score
            status
            layer_scores
        """

        baseline_stats = self._calculate_baseline()

        layer_scores = {}

        for layer, current in activations.items():

            # JSON converts integer layer keys into strings.
            layer_key = str(layer)

            if layer_key not in baseline_stats:
                continue

            scores = []

            for metric in [
                "mean",
                "std",
                "max",
                "min"
            ]:

                baseline_mean = (
                    baseline_stats[layer_key]
                    [metric]["mean"]
                )

                baseline_std = (
                    baseline_stats[layer_key]
                    [metric]["std"]
                )

                # Prevent division by zero.
                if baseline_std < 1e-8:
                    baseline_std = 1e-8

                z_score = abs(
                    current[metric] - baseline_mean
                ) / baseline_std

                scores.append(z_score)

            if scores:
                layer_scores[layer_key] = (
                    sum(scores) / len(scores)
                )

        # No matching layers found.
        if not layer_scores:
            return {
                "score": 0.0,
                "status": "UNKNOWN",
                "layer_scores": {}
            }

        # Calculate overall anomaly score.
        overall_score = (
            sum(layer_scores.values())
            / len(layer_scores)
        )

        # Initial thresholds.
        if overall_score < 2.0:
            status = "NORMAL"

        elif overall_score < 4.0:
            status = "SUSPICIOUS"

        else:
            status = "ANOMALOUS"

        return {
            "score": round(
                overall_score,
                4
            ),
            "status": status,
            "layer_scores": {
                layer: round(score, 4)
                for layer, score
                in layer_scores.items()
            }
        }

"""
Explainable baseline + anomaly detector.

This module provides a clean, modular front-end for the activation
anomaly scoring already implemented in `activation_anomaly`. It wraps
that logic in a small, readable class so a reviewer can follow the
explainable flow:

    Normal inputs  -> build baseline statistics (per-feature mean/std)
    Test inputs    -> compare each feature against the baseline
    Deviation above threshold -> flagged as suspicious/anomalous

The underlying computations are delegated to the existing functions so
nothing is duplicated. A more advanced statistical/ML detector can be
swapped in later by implementing the same `BaselineDetector` interface.

This is prototype / explainable logic -- it does not claim to detect
confirmed real-LLM backdoors, only statistically suspicious deviations
from an established normal baseline.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.anomaly_detection.activation_anomaly import (
    FEATURE_NAMES,
    build_feature_baseline_statistics,
    compare_feature_vector,
)


@dataclass
class Deviation:
    """One feature's deviation from its baseline (explainable evidence)."""

    feature: str
    current: float
    baseline_mean: float
    deviation_z: float

    def describe(self) -> str:
        return (
            f"{self.feature}: value={self.current:.3f} vs baseline "
            f"mean={self.baseline_mean:.3f} (z~{self.deviation_z:.2f})"
        )


@dataclass
class AnomalyVerdict:
    """Result of checking one input against the baseline."""

    anomaly_score: float  # 0-100
    is_suspicious: bool
    threshold: float
    deviations: List[Deviation] = field(default_factory=list)

    def explain(self) -> str:
        parts = [
            f"Score {self.anomaly_score:.1f} (threshold {self.threshold:.1f}) -> "
            f"{'SUSPICIOUS' if self.is_suspicious else 'normal'}"
        ]
        if self.deviations:
            parts.append("Top deviations: " + "; ".join(d.describe() for d in self.deviations[:3]))
        return " | ".join(parts)


class BaselineDetector:
    """
    Build a baseline from normal inputs and score test inputs against it.

    `threshold` is the anomaly score (0-100) above which an input is
    considered suspicious. It is configurable so the prototype can be
    tuned without code changes.
    """

    def __init__(self, threshold: float = 40.0):
        self.threshold = float(threshold)
        self.baseline: Dict[str, Dict[str, float]] = {}

    # -- baseline building ----------------------------------
    def fit(self, normal_features: List[Dict[str, float]]) -> "BaselineDetector":
        """Build per-feature {mean, std} baseline from normal inputs."""
        if not normal_features:
            self.baseline = {}
            return self
        self.baseline = build_feature_baseline_statistics(normal_features)
        return self

    # -- comparison -----------------------------------------
    def check(self, features: Dict[str, float]) -> AnomalyVerdict:
        """Compare one feature dict against the baseline."""
        result = compare_feature_vector(features, self.baseline)
        score = float(result["anomaly_score"])
        deviations = [
            Deviation(
                feature=name,
                current=float(features.get(name, 0.0)),
                baseline_mean=float(self.baseline[name]["mean"]) if name in self.baseline else 0.0,
                deviation_z=float(dev),
            )
            for name, dev in result["deviations"].items()
        ]
        deviations.sort(key=lambda d: d.deviation_z, reverse=True)
        return AnomalyVerdict(
            anomaly_score=score,
            is_suspicious=score >= self.threshold,
            threshold=self.threshold,
            deviations=deviations,
        )

    # -- aggregate helper -----------------------------------
    def summarize(self, feature_rows: List[Dict[str, float]]) -> Dict[str, int]:
        """Count how many rows are suspicious given the baseline."""
        if not self.baseline:
            return {"total": len(feature_rows), "suspicious": 0, "normal": len(feature_rows)}
        suspicious = sum(1 for row in feature_rows if self.check(row).is_suspicious)
        return {
            "total": len(feature_rows),
            "suspicious": suspicious,
            "normal": len(feature_rows) - suspicious,
        }

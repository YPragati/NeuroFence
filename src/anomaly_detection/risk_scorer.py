"""
Module 2 -- Security Risk Scoring.

Combines security signals into a normalized 0-100 risk score.

Signals:
    - activation anomaly
    - prompt injection
    - backdoor trigger
    - response behaviour change

This module is model-independent and can later consume both:
    1. behavioural features from Member-2's collector
    2. real Transformer activation anomaly scores
"""

from dataclasses import dataclass


@dataclass
class RiskAssessment:
    """Final security risk assessment."""

    risk_score: float
    risk_level: str
    activation_anomaly: float
    injection_signal: float
    trigger_signal: float
    response_change: float

    def as_dict(self):
        return {
            "risk_score": self.risk_score,
            "risk_level": self.risk_level,
            "activation_anomaly": self.activation_anomaly,
            "injection_signal": self.injection_signal,
            "trigger_signal": self.trigger_signal,
            "response_change": self.response_change,
        }


class SecurityRiskScorer:
    """
    Converts multiple security indicators into a single risk score.

    All input signals are expected to be in the range [0, 1].
    """

    DEFAULT_WEIGHTS = {
        "activation_anomaly": 0.40,
        "injection_signal": 0.20,
        "trigger_signal": 0.25,
        "response_change": 0.15,
    }

    def __init__(self, weights=None):
        self.weights = weights or self.DEFAULT_WEIGHTS.copy()
        self._validate_weights()

    def _validate_weights(self):
        required = set(self.DEFAULT_WEIGHTS)

        if set(self.weights) != required:
            raise ValueError(
                f"Weights must contain exactly: {sorted(required)}"
            )

        if any(value < 0 for value in self.weights.values()):
            raise ValueError("Risk weights cannot be negative.")

        total = sum(self.weights.values())

        if total <= 0:
            raise ValueError("Risk weights must have a positive total.")

        # Normalize weights so custom weights do not need to sum exactly to 1.
        for key in self.weights:
            self.weights[key] /= total

    @staticmethod
    def _clamp(value):
        """Keep a signal inside the expected [0, 1] range."""
        return max(0.0, min(1.0, float(value)))

    @staticmethod
    def _get_risk_level(score):
        if score < 25:
            return "LOW"
        if score < 50:
            return "MEDIUM"
        if score < 75:
            return "HIGH"
        return "CRITICAL"

    def calculate(
        self,
        activation_anomaly,
        injection_signal,
        trigger_signal,
        response_change,
    ):
        """
        Calculate a normalized security risk score.

        Returns:
            RiskAssessment
        """

        signals = {
            "activation_anomaly": self._clamp(activation_anomaly),
            "injection_signal": self._clamp(injection_signal),
            "trigger_signal": self._clamp(trigger_signal),
            "response_change": self._clamp(response_change),
        }

        weighted_score = sum(
            signals[name] * self.weights[name]
            for name in signals
        )

        risk_score = round(weighted_score * 100.0, 2)

        return RiskAssessment(
            risk_score=risk_score,
            risk_level=self._get_risk_level(risk_score),
            **signals,
        )


if __name__ == "__main__":
    scorer = SecurityRiskScorer()

    assessment = scorer.calculate(
        activation_anomaly=0.90,
        injection_signal=1.0,
        trigger_signal=1.0,
        response_change=0.80,
    )

    print("NeuroFence Security Risk Assessment")
    print("------------------------------------")
    print(f"Risk score : {assessment.risk_score}/100")
    print(f"Risk level : {assessment.risk_level}")
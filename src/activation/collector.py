"""
Member-2 Security Research -- Activation/Behaviour Collector.

This module creates a model-independent representation of internal
security-related signals.

For the current NeuroFence ToyModel, there is no neural activation
tensor, so we use deterministic behavioural signals as a bridge.

When a real PyTorch/HuggingFace model is connected later, this module
can be extended with forward hooks to collect actual layer activations.
"""

from dataclasses import dataclass
import hashlib
import math
from typing import Dict


@dataclass
class ActivationFeatures:
    """
    Numeric security features generated for one model execution.

    These are intentionally model-independent so the current
    ToyModel can be tested before integrating a real neural model.
    """

    prompt_length: float
    response_length: float
    prompt_hash_score: float
    trigger_signal: float
    injection_signal: float
    response_change_signal: float

    def as_dict(self) -> Dict[str, float]:
        """Return features as a dictionary."""
        return {
            "prompt_length": self.prompt_length,
            "response_length": self.response_length,
            "prompt_hash_score": self.prompt_hash_score,
            "trigger_signal": self.trigger_signal,
            "injection_signal": self.injection_signal,
            "response_change_signal": self.response_change_signal,
        }

    def as_vector(self):
        """Return features as a numeric vector."""
        return [
            self.prompt_length,
            self.response_length,
            self.prompt_hash_score,
            self.trigger_signal,
            self.injection_signal,
            self.response_change_signal,
        ]


class SecurityActivationCollector:
    """
    Collects deterministic security signals from model executions.

    This is the first-stage abstraction for Member-2's activation
    analysis. Real neural activations will be supported separately.
    """

    TRIGGER_TAGS = (
        "TRIGGER_ALPHA",
        "TRIGGER_BETA",
        "TRIGGER_GAMMA",
        "Pineapple",
    )

    INJECTION_PATTERNS = (
        "ignore all previous instructions",
        "ignore previous instructions",
        "system override",
        "disregard your guidelines",
        "no restrictions",
        "admin override",
        "reveal your system prompt",
    )

    def collect(
        self,
        prompt: str,
        response: str,
        baseline_response: str | None = None,
    ) -> ActivationFeatures:
        """
        Generate deterministic security features.

        Args:
            prompt: Input sent to the model.
            response: Model response.
            baseline_response: Expected response for comparison.

        Returns:
            ActivationFeatures instance.
        """

        prompt_lower = prompt.lower()

        prompt_length = float(len(prompt))
        response_length = float(len(response))

        # Stable numeric representation of the prompt.
        digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()
        hash_value = int(digest[:8], 16)

        # Normalize to [0, 1].
        prompt_hash_score = hash_value / 0xFFFFFFFF

        trigger_signal = float(
            any(tag in prompt for tag in self.TRIGGER_TAGS)
        )

        injection_signal = float(
            any(pattern in prompt_lower for pattern in self.INJECTION_PATTERNS)
        )

        if baseline_response is None:
            response_change_signal = 0.0
        else:
            max_length = max(
                len(response),
                len(baseline_response),
                1,
            )

            response_change_signal = (
                abs(len(response) - len(baseline_response))
                / max_length
            )

        return ActivationFeatures(
            prompt_length=prompt_length,
            response_length=response_length,
            prompt_hash_score=prompt_hash_score,
            trigger_signal=trigger_signal,
            injection_signal=injection_signal,
            response_change_signal=response_change_signal,
        )
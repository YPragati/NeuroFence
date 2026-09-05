"""
Membership sensor abstraction -- ActivationTracker.

This module defines a clean, model-independent interface for capturing
"activation" statistics from a model execution. The current NeuroFence
prototype uses a rule-based synthetic model, so its implementation of
this interface reports *deterministic behaviour/feature signals* rather
than real neuron-level tensors.

The interface is deliberately shaped so a real HuggingFace/PyTorch model
can be plugged in later (via forward hooks) WITHOUT changing the desktop
UI or the rest of the pipeline:

    register_hooks()      -> attach capture hooks to the model
    capture_activation()  -> run one input and return a feature dict
    remove_hooks()        -> detach hooks (cleanup)
    calculate_statistics() -> per-feature {mean, std} baseline statistics

No real neuron/backdoor detection is claimed here. The synthetic
implementation is used purely to exercise the workflow end-to-end and
is clearly labelled as prototype / synthetic validation data.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.activation.collector import SecurityActivationCollector
from src.anomaly_detection.activation_anomaly import (
    FEATURE_NAMES,
    build_feature_baseline_statistics,
    compare_feature_vector,
)
from src.model_interface.toy_model import ToyModel


@dataclass
class ActivationSnapshot:
    """
    One captured activation/feature vector plus its computed anomaly score.

    This is the model-agnostic payload that flows to findings/reports so
    the upstream UI never depends on how the signals were produced.
    """

    prompt: str = ""
    response: str = ""
    features: Dict[str, float] = field(default_factory=dict)
    anomaly_score: float = 0.0
    trigger_signal: float = 0.0
    injection_signal: float = 0.0


class ActivationTracker(ABC):
    """
    Interface contract for capture + baseline + anomaly scoring.

    A concrete tracker pairs a model with a collection strategy. The
    synthetic tracker shadows this with behavioural signals; a future
    Torch tracker will use forward hooks on real layers.
    """

    #: Features the tracker can produce (used for consistent columns/plots).
    FEATURE_NAMES: List[str] = list(FEATURE_NAMES)

    def __init__(self) -> None:
        self._hooks: List[Any] = []

    @abstractmethod
    def register_hooks(self) -> None:  # pragma: no cover - interface
        """Attach capture hooks to the underlying model."""

    @abstractmethod
    def capture_activation(self, prompt: str) -> ActivationSnapshot:
        """Run a single input and capture its feature/activation snapshot."""

    def remove_hooks(self) -> None:
        """Detach any registered hooks (no-op for stateless trackers)."""
        self._hooks.clear()

    @abstractmethod
    def calculate_statistics(
        self, snapshots: List[ActivationSnapshot]
    ) -> Dict[str, Dict[str, float]]:
        """Compute per-feature {mean, std} baseline statistics."""


class SyntheticActivationTracker(ActivationTracker):
    """
    Prototype tracker backed by the rule-based ToyModel.

    Because the toy model has no neural tensors, this reports the
    deterministic behavioural features produced by
    SecurityActivationCollector. It implements the full ActivationTracker
    interface so swapping in a real Torch tracker does not affect the UI.
    """

    def __init__(self, model: Optional[ToyModel] = None) -> None:
        super().__init__()
        self.model = model if model is not None else ToyModel()
        self.collector = SecurityActivationCollector()

    def register_hooks(self) -> None:
        # No neural tensors in the synthetic model -- nothing to attach.
        # Kept for interface parity with the real Tracker.
        self._hooks = []

    def capture_activation(self, prompt: str) -> ActivationSnapshot:
        response = self.model.generate(prompt)
        features = self.collector.collect(prompt=prompt, response=response)
        return ActivationSnapshot(
            prompt=prompt,
            response=response,
            features=features.as_dict(),
        )

    def calculate_statistics(
        self, snapshots: List[ActivationSnapshot]
    ) -> Dict[str, Dict[str, float]]:
        rows = [s.features for s in snapshots]
        return build_feature_baseline_statistics(rows)

    def score_against_baseline(
        self,
        snapshot: ActivationSnapshot,
        baseline: Dict[str, Dict[str, float]],
    ) -> float:
        """Return a 0-100 anomaly score for a snapshot vs a baseline."""
        result = compare_feature_vector(snapshot.features, baseline)
        snapshot.anomaly_score = float(result["anomaly_score"])
        snapshot.trigger_signal = float(snapshot.features.get("trigger_signal", 0.0))
        snapshot.injection_signal = float(snapshot.features.get("injection_signal", 0.0))
        return snapshot.anomaly_score


class TorchActivationTracker(ActivationTracker):
    """
    Torch/HuggingFace-ready tracker.

    This is NOT wired to a real model in this mid-review prototype. It
    documents how the interface will be implemented for a real transformer
    so that the upgrade path is obvious. Guarded import of torch keeps the
    current synthetic prototype fully offline and dependency-light.
    """

    def __init__(self, model: Any = None, layer_attr: str = "transformer.h") -> None:
        super().__init__()
        self._torch = None
        try:
            import torch  # noqa: PLC0415 - optional dependency
            self._torch = torch
        except Exception:  # pragma: no cover - torch optional
            self._torch = None
        self.model = model
        self._layer_attr = layer_attr
        self._activated: Dict[int, Dict[str, Any]] = {}

    def register_hooks(self) -> None:
        if self.model is None or self._torch is None:
            raise RuntimeError(
                "TorchActivationTracker requires a real torch model. "
                "This is a future-integration stub for the NeuroFence prototype."
            )
        layers = getattr(self.model, self._layer_attr, None)
        if layers is None:
            raise RuntimeError(f"No attribute '{self._layer_attr}' found on model.")
        for index, layer in enumerate(layers):
            hook = layer.register_forward_hook(self._create_hook(index))
            self._hooks.append(hook)
        self._activated.clear()

    def _create_hook(self, layer_index: int):
        def hook(_module, _inputs, output):
            if isinstance(output, tuple):
                output = output[0]
            activation = output.detach().cpu()
            self._activated[layer_index] = {
                "mean": activation.mean().item(),
                "max": activation.max().item(),
                "min": activation.min().item(),
                "std": activation.std().item(),
                "shape": list(activation.shape),
            }
        return hook

    def capture_activation(self, prompt: str) -> ActivationSnapshot:
        if self._torch is None or self.model is None:
            raise RuntimeError(
                "TorchActivationTracker requires a real torch model. "
                "This is a future-integration stub for the NeuroFence prototype."
            )
        # Not implemented end-to-end in the prototype; document the contract.
        raise NotImplementedError(
            "Real PyTorch capture is part of the next development phase. "
            "register_hooks() + forward hooks are prepared; wire tokenizer here."
        )

    def calculate_statistics(
        self, snapshots: List[ActivationSnapshot]
    ) -> Dict[str, Dict[str, float]]:
        # Placeholder to keep the interface contract; unused in prototype.
        return build_feature_baseline_statistics(
            [s.features for s in snapshots]
        )

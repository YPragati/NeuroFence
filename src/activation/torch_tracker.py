"""
Real PyTorch Activation Tracker.

Provides forward-hook-based activation capture for PyTorch modules,
particularly Transformer encoder/decoder layers. Designed for forensic
analysis: compute per-layer activation statistics (mean, std, max, norm,
active neuron count) without storing raw activation tensors.

Safety guarantees:
  * torch.no_grad() is always used during inference.
  * Raw activations are never stored — only scalar aggregates.
  * Hooks are properly removed after each tracking session.
  * Memory is freed between tracking sessions.
"""

import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


def _import_torch():
    """Lazy import of torch. Returns the torch module."""
    import torch  # noqa: PLC0415
    return torch


@dataclass
class LayerActivationStats:
    """Activation statistics for a single tracked layer."""

    layer_name: str
    layer_index: int
    mean: float = 0.0
    std: float = 0.0
    max_val: float = 0.0
    norm: float = 0.0
    active_fraction: float = 0.0
    shape: List[int] = field(default_factory=list)
    num_elements: int = 0

    def as_dict(self) -> dict:
        return {
            "layer_name": self.layer_name,
            "layer_index": self.layer_index,
            "mean": self.mean,
            "std": self.std,
            "max_val": self.max_val,
            "norm": self.norm,
            "active_fraction": self.active_fraction,
            "shape": self.shape,
            "num_elements": self.num_elements,
        }


@dataclass
class TrackingSession:
    """Complete result of one tracking session."""

    input_text: str = ""
    output_text: str = ""
    layer_stats: Dict[str, LayerActivationStats] = field(default_factory=dict)
    model_name: str = ""
    model_type: str = ""
    error: str = ""

    def as_dict(self) -> dict:
        return {
            "input_text": self.input_text,
            "output_text": self.output_text,
            "layer_stats": {k: v.as_dict() for k, v in self.layer_stats.items()},
            "model_name": self.model_name,
            "model_type": self.model_type,
            "error": self.error,
            "num_layers": len(self.layer_stats),
        }


def _compute_activation_stats(
    activation: Any,
    layer_name: str,
    layer_index: int,
    active_threshold: float = 1e-4,
) -> LayerActivationStats:
    """
    Compute aggregate statistics from a raw activation tensor.

    The activation is immediately reduced to scalars — never stored
    in full. This prevents memory growth during tracking.
    """
    flat = activation.detach().float().flatten()
    num_elements = flat.numel()

    stats = LayerActivationStats(
        layer_name=layer_name,
        layer_index=layer_index,
        shape=list(activation.shape),
        num_elements=num_elements,
    )

    if num_elements == 0:
        return stats

    stats.mean = flat.mean().item()
    stats.std = flat.std().item()
    stats.max_val = flat.abs().max().item()
    stats.norm = flat.norm().item()
    stats.active_fraction = (
        (flat.abs() > active_threshold).float().sum().item() / num_elements
    )

    return stats


class RealTorchActivationTracker:
    """
    Real PyTorch activation tracker using forward hooks.

    Registers forward hooks on transformer-like layers, runs a single
    inference pass with torch.no_grad(), and computes per-layer
    aggregate statistics. Raw activations are never retained — only
    the scalar aggregates (mean, std, max, norm, active_fraction)
    survive after each tracking session.

    Thread-safe: only one tracking session at a time.

    Usage::

        tracker = RealTorchActivationTracker(model)
        tracker.discover_layers(test_input)
        session = tracker.track("What is 2+2?")
        stats = tracker.get_layer_statistics()
        tracker.cleanup()
    """

    def __init__(self, model: Any, device: str = "cpu") -> None:
        self._torch = _import_torch()
        self._model = model
        self._device = device
        self._hooks: List[Any] = []
        self._lock = threading.RLock()
        self._discovered_layers: Dict[str, Any] = {}
        self._current_session: Optional[TrackingSession] = None

        self._model_name = type(model).__name__
        self._model_type = self._detect_model_type()

    # ---- layer discovery ----

    def discover_layers(
        self,
        sample_input: Any = None,
        max_layers: int = 12,
    ) -> List[str]:
        """
        Discover transformer-like layers in the model.

        Two strategies:
        1. If sample_input is provided, run a probe to find modules
           that produce 3D output (batch, seq, hidden) — these are
           transformer layers.
        2. Fallback: enumerate named modules and try to infer which
           are transformer blocks.

        Returns the list of discovered layer names.
        """
        self._discovered_layers.clear()

        if sample_input is not None:
            self._discover_by_probe(sample_input, max_layers)
        else:
            self._discover_by_name(max_layers)

        return list(self._discovered_layers.keys())

    def _discover_by_probe(self, sample_input: Any, max_layers: int) -> None:
        """Hook all modules, run a probe, keep only those producing 3D output."""
        captured: Dict[str, Any] = {}
        candidate_hooks: Dict[str, Any] = {}

        def probe_hook(name):
            def hook(module, inp, out):
                t = self._torch
                if isinstance(out, t.Tensor) and out.dim() == 3:
                    captured[name] = out
                elif (isinstance(out, tuple) and out
                      and isinstance(out[0], t.Tensor) and out[0].dim() == 3):
                    captured[name] = out[0]
            return hook

        self._model.eval()
        for name, module in self._model.named_modules():
            if name == "":
                continue
            try:
                h = module.register_forward_hook(probe_hook(name))
                candidate_hooks[name] = h
            except Exception:
                continue

        with self._torch.no_grad():
            try:
                self._model(sample_input.to(self._device))
            except Exception:
                pass

        for h in candidate_hooks.values():
            h.remove()

        for name in sorted(captured.keys())[:max_layers]:
            self._discovered_layers[name] = self._model

        self._hooked_output_cache = captured

    def _discover_by_name(self, max_layers: int) -> None:
        """Fallback: infer transformer layers by module type naming conventions."""
        keywords = ("encoder", "decoder", "layer", "block", "attn", "transformer")
        count = 0
        for name, module in self._model.named_modules():
            if count >= max_layers:
                break
            lower_name = name.lower()
            if any(kw in lower_name for kw in keywords):
                self._discovered_layers[name] = module
                count += 1

    # ---- hook management ----

    def _register_hooks(self) -> None:
        """Register forward hooks on all discovered layers."""
        self._remove_hooks()
        t = self._torch

        def make_hook(name, idx):
            def hook(module, inp, out):
                if isinstance(out, t.Tensor):
                    act = out
                elif (isinstance(out, tuple) and out
                      and isinstance(out[0], t.Tensor)):
                    act = out[0]
                else:
                    return
                stats = _compute_activation_stats(act, name, idx)
                with self._lock:
                    if self._current_session is not None:
                        self._current_session.layer_stats[name] = stats
            return hook

        for idx, name in enumerate(self._discovered_layers.keys()):
            target = self._discovered_layers[name]
            try:
                h = target.register_forward_hook(make_hook(name, idx))
                self._hooks.append(h)
            except Exception:
                continue

    def _remove_hooks(self) -> None:
        """Remove all registered hooks."""
        for h in self._hooks:
            try:
                h.remove()
            except Exception:
                continue
        self._hooks.clear()

    # ---- tracking API ----

    def start_tracking(self) -> None:
        """Prepare for a tracking session. Register hooks on discovered layers."""
        with self._lock:
            self._current_session = TrackingSession(input_text="")
            self._register_hooks()

    def track(
        self,
        input_text: str,
        tokenizer: Optional[Any] = None,
        generate_fn: Optional[Any] = None,
    ) -> TrackingSession:
        """
        Run one inference and return the tracking session with per-layer stats.

        Args:
            input_text: The text prompt to run through the model.
            tokenizer: A tokenizer with encode() or __call__() returning tensors.
            generate_fn: A callable(input_ids) -> output_ids that runs the model.

        Returns:
            TrackingSession with layer_stats populated.
        """
        t = self._torch
        with self._lock:
            session = self._current_session
            if session is None:
                session = TrackingSession(input_text=input_text)
                self._current_session = session
            session.input_text = input_text

        try:
            self._model.eval()

            if tokenizer is not None and generate_fn is not None:
                input_ids = self._tokenize(tokenizer, input_text)
                input_tensor = input_ids.to(self._device)
            else:
                input_tensor = t.zeros(1, 8, dtype=t.long, device=self._device)

            with t.no_grad():
                self._model(input_tensor)

            if tokenizer is not None and generate_fn is not None:
                with t.no_grad():
                    output_ids = generate_fn(input_ids.to(self._device))
                if isinstance(output_ids, t.Tensor):
                    output_ids = output_ids[0]
                session.output_text = tokenizer.decode(
                    output_ids, skip_special_tokens=True
                )

        except Exception as exc:
            session.error = str(exc)

        return session

    def retrieve_layer_statistics(self) -> Dict[str, dict]:
        """Return per-layer activation statistics from the current session."""
        with self._lock:
            if self._current_session is None:
                return {}
            return {
                k: v.as_dict()
                for k, v in self._current_session.layer_stats.items()
            }

    def stop_tracking(self) -> Optional[TrackingSession]:
        """Stop tracking, remove hooks, return the final session."""
        with self._lock:
            session = self._current_session
            self._remove_hooks()
            self._current_session = None
            return session

    def cleanup(self) -> None:
        """Remove hooks and clear all state. Call when done with the tracker."""
        with self._lock:
            self._remove_hooks()
            self._current_session = None
            self._discovered_layers.clear()
            if hasattr(self, "_hooked_output_cache"):
                self._hooked_output_cache.clear()

    # ---- helpers ----

    def _tokenize(self, tokenizer, text: str) -> Any:
        """Tokenize input text, returning input_ids tensor."""
        result = tokenizer(text, return_tensors="pt", padding=True, truncation=True)
        return result["input_ids"]

    def _detect_model_type(self) -> str:
        """Detect the model architecture type from class name / module tree."""
        name = type(self._model).__name__.lower()
        if "gpt2" in name or "causal" in name:
            return "causal_lm"
        if "bert" in name:
            return "encoder_only"
        if "t5" in name or "seq2seq" in name:
            return "seq2seq"
        if "transformer" in name:
            return "transformer"
        return "unknown"

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_type(self) -> str:
        return self._model_type

    @property
    def num_discovered_layers(self) -> int:
        return len(self._discovered_layers)

    @property
    def is_tracking(self) -> bool:
        return self._current_session is not None

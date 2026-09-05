"""
Activation Tracking Service -- service layer connecting the real
PyTorch activation tracker to the desktop app.

Provides start_tracking, track_inference, get_statistics, stop_tracking
as a clean interface that the frontend page calls. The desktop app
never imports torch directly.

The service works with the ForensicModelLoader's in-process registry
to find the currently loaded model and its tokenizer.
"""

import os
import threading
from typing import Any, Dict, Optional


def _import_tracker():
    """Lazy import of the real torch tracker."""
    from src.activation.torch_tracker import RealTorchActivationTracker  # noqa: PLC0415
    return RealTorchActivationTracker


# Process-level singleton tracker. Only one tracking session at a time.
_tracker: Any = None  # Optional[RealTorchActivationTracker] but lazy
_tracker_lock = threading.Lock()


def _get_model_and_tokenizer():
    """
    Resolve the currently loaded model from the import_service loader
    registry, plus a tokenizer for it.

    Returns (model, tokenizer, error_string_or_None).
    """
    from src.model_interface import import_service

    # Find any loaded model in the process registry
    with import_service._ACTIVE_LOADERS_LOCK:
        if not import_service._ACTIVE_LOADERS:
            return None, None, "No model is loaded. Load a model first."

        # Use the most recently loaded model
        mid = max(import_service._ACTIVE_LOADERS.keys())
        loader = import_service._ACTIVE_LOADERS.get(mid)

    if loader is None or loader.loaded_model() is None:
        return None, None, "No model is loaded. Load a model first."

    model_obj = loader.loaded_model()
    loader_meta = loader.model_metadata()

    # Case 1: raw safetensors tensor dict from SafetensorsModelLoader
    if isinstance(model_obj, dict) and "tensors" in model_obj:
        return model_obj, None, (
            "Loaded model is a raw tensor dict (safetensors weights). "
            "Activation tracking requires a full nn.Module with transformer "
            "layers. Import a tiny_test_model or a full transformer model."
        )

    # Case 2: HuggingFace model object or nn.Module
    try:
        import torch.nn as nn
        if isinstance(model_obj, nn.Module):
            tokenizer = _load_tokenizer_for_model(loader_meta)
            return model_obj, tokenizer, None
    except (ImportError, Exception):
        pass

    return model_obj, None, (
        f"Loaded object is type {type(model_obj).__name__}, not an nn.Module. "
        "Activation tracking requires a PyTorch nn.Module."
    )


def _load_tokenizer_for_model(loader_meta: dict) -> Optional[Any]:
    """
    Load a tokenizer for the currently loaded model.

    Looks for a tokenizer.json next to the model file, or in the
    test model directory. Never downloads from the internet.
    """
    model_path = loader_meta.get("model_path", "")

    # Try loading the tiny_test_model tokenizer
    from src.model_interface.tiny_test_model import (
        tiny_model_dir,
        load_tiny_model,
        TinyVocabTokenizer,
    )
    try:
        _, tokenizer = load_tiny_model(tiny_model_dir())
        return tokenizer
    except FileNotFoundError:
        pass

    if not model_path:
        return None

    # Try a tokenizer.json next to the model file
    model_dir = os.path.dirname(model_path)
    tok_path = os.path.join(model_dir, "tokenizer.json")
    if os.path.exists(tok_path):
        import json
        with open(tok_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if "vocab" in data:
            return TinyVocabTokenizer(vocab=data["vocab"], max_len=data.get("max_len", 16))

    return None


def start_tracking(sample_text: Optional[str] = None) -> Dict[str, Any]:
    """
    Start a tracking session: load the model, discover layers, register hooks.

    Returns a status dict with model info and discovered layers.
    """
    global _tracker

    with _tracker_lock:
        if _tracker is not None and _tracker.is_tracking:
            return {
                "status": "already_tracking",
                "message": "A tracking session is already active.",
                "model_name": _tracker.model_name,
                "num_layers": _tracker.num_discovered_layers,
            }

    model, tokenizer, err = _get_model_and_tokenizer()
    if err:
        return {"status": "failed", "message": err}

    try:
        import torch.nn as nn
        if not isinstance(model, nn.Module):
            return {
                "status": "failed",
                "message": f"Model is type {type(model).__name__}, not nn.Module.",
            }
    except ImportError:
        return {"status": "failed", "message": "PyTorch is not available."}

    TrackerClass = _import_tracker()
    tracker = TrackerClass(model)

    # Discover layers using a sample input if available
    sample_input = None
    if tokenizer is not None and sample_text:
        try:
            encoded = tokenizer(sample_text, return_tensors="pt")
            sample_input = encoded["input_ids"]
        except Exception:
            pass

    try:
        layers = tracker.discover_layers(sample_input=sample_input)
    except Exception as exc:
        tracker.cleanup()
        return {"status": "failed", "message": f"Layer discovery failed: {exc}"}

    if not layers:
        tracker.cleanup()
        return {
            "status": "failed",
            "message": (
                "No transformer layers discovered. The model may not have "
                "standard transformer encoder/decoder blocks."
            ),
        }

    tracker.start_tracking()

    with _tracker_lock:
        _tracker = tracker

    return {
        "status": "started",
        "message": f"Tracking active on {len(layers)} layers.",
        "model_name": tracker.model_name,
        "model_type": tracker.model_type,
        "num_layers": len(layers),
        "layers": layers,
    }


def track_inference(
    input_text: str,
    max_new_tokens: int = 10,
) -> Dict[str, Any]:
    """
    Run one inference pass with hooks active and return the tracking session.

    Args:
        input_text: The text prompt to send to the model.
        max_new_tokens: Max tokens to generate (only for causal models).

    Returns:
        Dict with the TrackingSession data.
    """
    with _tracker_lock:
        tracker = _tracker

    if tracker is None or not tracker.is_tracking:
        return {
            "status": "failed",
            "message": "No active tracking session. Call start_tracking() first.",
        }

    _, tokenizer, _ = _get_model_and_tokenizer()

    def gen_fn(input_ids):
        return tracker._model.generate(input_ids, max_new_tokens=max_new_tokens)

    session = tracker.track(
        input_text=input_text,
        tokenizer=tokenizer,
        generate_fn=gen_fn,
    )

    return {
        "status": "tracked",
        "session": session.as_dict(),
    }


def get_statistics() -> Dict[str, Any]:
    """
    Return the current per-layer activation statistics.

    Returns a dict with layer statistics or an error message.
    """
    with _tracker_lock:
        tracker = _tracker

    if tracker is None:
        return {
            "status": "no_tracker",
            "message": "No tracker initialized. Call start_tracking() first.",
            "layer_stats": {},
        }

    stats = tracker.retrieve_layer_statistics()
    return {
        "status": "ok" if stats else "no_data",
        "message": f"{len(stats)} layers with statistics." if stats else "No inference run yet.",
        "model_name": tracker.model_name,
        "model_type": tracker.model_type,
        "num_layers": tracker.num_discovered_layers,
        "layer_stats": stats,
    }


def stop_tracking() -> Dict[str, Any]:
    """
    Stop tracking, remove hooks, return the final session summary.
    """
    global _tracker

    with _tracker_lock:
        tracker = _tracker
        _tracker = None

    if tracker is None:
        return {"status": "no_tracker", "message": "No tracker to stop."}

    session = tracker.stop_tracking()
    tracker.cleanup()

    result = {
        "status": "stopped",
        "message": "Tracking stopped, hooks removed.",
        "model_name": tracker.model_name,
    }
    if session:
        result["session"] = session.as_dict()
    return result


def tracking_status() -> Dict[str, Any]:
    """Return the current tracking state without running inference."""
    with _tracker_lock:
        tracker = _tracker

    if tracker is None:
        return {"active": False, "message": "No tracker initialized."}

    return {
        "active": tracker.is_tracking,
        "model_name": tracker.model_name,
        "model_type": tracker.model_type,
        "num_layers": tracker.num_discovered_layers,
        "message": "Tracking active." if tracker.is_tracking else "Tracker exists but not active.",
    }

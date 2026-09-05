"""
Supported-model test path.

Heads-up: NeuroFence does NOT download models. When a real supported
model is not present in the repository, this module documents and
creates a small, fully local safetensors test model so the Safe Local
Model Loading path can be exercised end-to-end without an internet
connection.

The generated model is a tiny, deterministic CPU tensor checkpoint used
only to verify that the loader can: validate -> load -> report metadata.
It is not a trained network.
"""

import os

from src.model_interface import model_forensics

DEFAULT_FILENAME = "neurofence_small_test_model.safetensors"


def default_test_model_dir() -> str:
    """Directory where the generated test model is written."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(root, "outputs", "test_models")


def small_test_model_path(force_new: bool = False) -> str:
    """
    Return the path to a small local safetensors test model, creating it
    on first use if it does not already exist.

    Creation uses a small number of deterministic tensors so the loader
    has real (if tiny) weights to load. Safe: writes tensors only.
    """
    path = os.path.join(default_test_model_dir(), DEFAULT_FILENAME)
    if os.path.exists(path) and not force_new:
        return path

    os.makedirs(default_test_model_dir(), exist_ok=True)

    try:
        import torch

        tensors = {
            "embed.weight": torch.randn(64, 64, dtype=torch.float32),
            "proj.weight": torch.randn(16, 64, dtype=torch.float32),
            "proj.bias": torch.zeros(16, dtype=torch.float32),
        }
        from safetensors.torch import save_file

        save_file(tensors, path)
    except Exception:  # pragma: no cover - torch/safetensors missing
        import numpy as _np
        from safetensors.numpy import save_file as _save_np

        _save_np(
            {
                "embed.weight": _np.random.RandomState(0)
                .randn(64, 64)
                .astype(_np.float32),
                "proj.weight": _np.random.RandomState(1)
                .randn(16, 64)
                .astype(_np.float32),
                "proj.bias": _np.zeros(16, dtype=_np.float32),
            },
            path,
        )

    return path


def model_marker_path(save_dir: str) -> str:
    """Path where a JSON marker describing the generated test model lives."""
    return os.path.join(os.path.abspath(save_dir), "neurofence_small_test_model.json")


def write_small_model_marker(save_dir: str) -> str:
    """Write a JSON marker for the generated small test model."""
    meta = {
        "name": "NeuroFence Small Test Model (local, generated)",
        "model_type": "safetensors_test",
        "architecture": "Tiny deterministic CPU checkpoint (not a trained network)",
        "num_parameters": 64 * 64 + 16 * 64 + 16,
        "layers": 2,
        "description": (
            "A tiny, fully local safetensors checkpoint generated on first use "
            "so the Safe Local Model Loading path can be verified offline. "
            "Generated deterministically; never downloaded."
        ),
    }
    os.makedirs(save_dir, exist_ok=True)
    path = model_marker_path(save_dir)
    with open(path, "w", encoding="utf-8") as f:
        import json

        json.dump(meta, f, indent=2)
    return path


def ensure_test_model_imported() -> str:
    """
    Generate the small test model and import it into the registry.

    Returns the model's safetensors path. Imported records are written
    to the model_metadata table via the import service so the Models
    page can list and load it.
    """
    from src.model_interface.import_service import import_model

    path = small_test_model_path()
    result = import_model(path)
    if not result["success"] and not any(m.get("duplicate") for m in result["models"]):
        raise RuntimeError(f"Failed to register test model: {result['errors']}")
    return path


if __name__ == "__main__":
    p = small_test_model_path()
    print("Test model:", p)
    print("Size:", model_forensics.format_size(os.path.getsize(p)))
    meta = model_forensics.inspect_model_file(p)
    print("Supported:", meta.supported, "| type:", meta.model_type)

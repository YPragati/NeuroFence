"""
Model Forensics -- hashing, metadata inspection and file validation.

These functions give the forensic tool (and the PyQt desktop app) the
ability to fingerprint a model file without executing it:

    - SHA-256 cryptographic hash (streamed, memory-efficient for large
      multi-gigabyte model files).
    - File size and name.
    - Best-effort metadata (architecture, parameter/layer counts) for
      recognised model file formats.
    - Validation that a file is a supported/safe format.

Everything is local and offline. No model is downloaded and no code
from the model file is ever executed here.
"""

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional


# File extensions / markers we accept as model inputs.
# The toy/mock model is registered via a small marker file so the
# forensic flow has a real, selectable "model" to demonstrate against.
SUPPORTED_EXTENSIONS = {
    ".pt",
    ".pth",
    ".bin",
    ".safetensors",
    ".onnx",
    ".json",
}


@dataclass
class ModelForensics:
    """Result of inspecting a local model asset for the report/app."""
    file_name: str = ""
    file_path: str = ""
    file_size_bytes: int = 0
    sha256_hash: str = ""
    model_type: str = "unknown"
    architecture: Optional[str] = None
    num_parameters: Optional[int] = None
    layer_count: Optional[int] = None
    layer_info: List[Dict] = field(default_factory=list)
    supported: bool = False
    notes: List[str] = field(default_factory=list)
    validation_error: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "file_name": self.file_name,
            "file_path": self.file_path,
            "file_size_bytes": self.file_size_bytes,
            "sha256_hash": self.sha256_hash,
            "model_type": self.model_type,
            "architecture": self.architecture,
            "num_parameters": self.num_parameters,
            "layer_count": self.layer_count,
            "layer_info": self.layer_info,
            "supported": self.supported,
            "notes": self.notes,
            "validation_error": self.validation_error,
        }


def compute_sha256(path: str, chunk_size: int = 8192) -> str:
    """Streamed SHA-256 of a file (memory-safe for large models)."""
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha.update(chunk)
    return sha.hexdigest()


def format_size(num_bytes: int) -> str:
    """Human readable file size."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024.0 or unit == "TB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} {unit}"
        size /= 1024.0
    return f"{num_bytes} B"


def _is_marker_file(name: str) -> bool:
    return name.lower().startswith("neurofence-toy")


def _extract_parameter_count_from_json(meta: dict) -> Optional[int]:
    for key in (
        "num_parameters",
        "n_params",
        "params",
        "parameter_count",
    ):
        if isinstance(meta.get(key), (int, float)):
            return int(meta[key])
    return None


def _extract_layer_count(name: str, meta: dict) -> Optional[int]:
    for key in ("num_layers", "n_layer", "layers", "layer_count"):
        if isinstance(meta.get(key), (int, float)):
            return int(meta[key])
    return None


def inspect_model_file(path: str) -> ModelForensics:
    """
    Inspect a local model file thoroughly and return its forensics.

    Validates the extension, computes the hash and size, and attempts
    to parse lightweight metadata where the format allows it. This
    never loads the model into memory and never executes remote code.
    """
    forensics = ModelForensics()
    if not path or not os.path.exists(path):
        forensics.validation_error = f"Path does not exist: {path}"
        return forensics
    if os.path.isdir(path):
        forensics.validation_error = (
            "Path is a directory; point at a single model file "
            "(or use the bundled toy-model marker)."
        )
        return forensics

    forensics.file_path = os.path.abspath(path)
    forensics.file_name = os.path.basename(path)
    forensics.file_size_bytes = os.path.getsize(path)
    forensics.sha256_hash = compute_sha256(path)

    name = os.path.basename(path).lower()
    ext = os.path.splitext(name)[1]

    if ext not in SUPPORTED_EXTENSIONS and not name.startswith("neurofence-toy"):
        forensics.supported = False
        forensics.validation_error = (
            f"Unsupported file type '{ext}'. Supported: {sorted(SUPPORTED_EXTENSIONS)}."
        )
        return forensics

    forensics.supported = True

    # ---- Recognised formats --------------------------------
    if ext == ".json":
        # JSON-backed model description (e.g. our toy model marker or a
        # HuggingFace config.json). Parse metadata safely.
        try:
            with open(path, "r", encoding="utf-8") as f:
                meta = json.load(f)
            if not isinstance(meta, dict):
                raise ValueError("JSON root is not an object")
            forensics.model_type = meta.get("model_type", "unknown")
            forensics.architecture = meta.get("architecture") or meta.get("architectures") or \
                meta.get("model_type") or forensics.architecture
            forensics.num_parameters = _extract_parameter_count_from_json(meta)
            forensics.layer_count = _extract_layer_count(name, meta)
            cfg = meta.get("config") if isinstance(meta.get("config"), dict) else {}
            if cfg and not forensics.num_parameters:
                forensics.num_parameters = _extract_parameter_count_from_json(cfg)
            for key, val in (cfg or {}).items():
                if isinstance(val, int) and val > 0:
                    forensics.layer_info.append({"layer": key, "dimension": val})
        except Exception as exc:  # noqa: BLE001 -- report unsupported gracefully
            forensics.supported = False
            forensics.validation_error = f"Could not parse JSON metadata: {exc}"

    elif name.startswith("neurofence-toy"):
        # Bundled synthetic toy-model marker.
        forensics.model_type = "toy_model"
        forensics.architecture = "Rule-based synthetic toy model (simulated)"
        forensics.num_parameters = 0
        forensics.layer_count = 0
        forensics.notes.append(
            "This is a fully local, rule-based SIMULATED model for safe "
            "testing -- not a real neural network. Activation analysis "
            "uses aggregated behavior features, clearly labeled."
        )

    elif ext in (".pt", ".pth", ".bin", ".safetensors", ".onnx"):
        # Recognised ML tensor/serialization formats. We do NOT load them
        # here (loading can trigger arbitrary code / huge memory use).
        # Best-effort type labelling only.
        forensics.model_type = "pytorch_state_dict" if ext in (".pt", ".pth") else (
            "safetensors" if ext == ".safetensors" else ("onnx" if ext == ".onnx" else "bin_weights")
        )
        forensics.architecture = None
        forensics.notes.append(
            f"Recognised {ext} model file. Activation extraction depends on "
            "the architecture; a config.json with metadata is required for "
            "parameter/layer details."
        )

    return forensics


# -------------------------------------------------------------------------
# Bundled toy-model marker
# -------------------------------------------------------------------------
TOY_MODEL_INTERNAL_NAME = "NeuroFence Synthetic Toy Model (simulated)"


def toy_model_marker_path(save_dir: str) -> str:
    """Path where the bundled toy-model marker file lives."""
    return os.path.join(os.path.abspath(save_dir), "neurofence-toy-model.json")


def write_toy_model_marker(save_dir: str) -> str:
    """Create a small marker JSON for the bundled synthetic toy model so
    the desktop app's 'open model' flow has a real file to select."""
    meta = {
        "name": TOY_MODEL_INTERNAL_NAME,
        "model_type": "toy_model",
        "architecture": "Rule-based synthetic toy model (simulated)",
        "num_parameters": 0,
        "layers": 0,
        "description": (
            "Fully local, deterministic, rule-based SIMULATED model used to "
            "validate NeuroFence's pipeline safely. Contains synthetic backdoor "
            "triggers (e.g. 'Pineapple') for defensive testing only."
        ),
    }
    os.makedirs(save_dir, exist_ok=True)
    path = toy_model_marker_path(save_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        path = write_toy_model_marker(
            os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "outputs")
        )
    result = inspect_model_file(path)
    for key in ("file_name", "file_size_bytes", "sha256_hash"):
        print(f"{key}: {result.as_dict()[key]}")
    print(f"model_type: {result.model_type}")
    print(f"supported : {result.supported}")
    for note in result.notes:
        print(f"note      : {note}")
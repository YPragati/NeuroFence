"""
Forensic Model Loader -- safe, offline, local-only model loading.

This module provides the abstraction that separates the scanner / UI
from the details of loading a model. Its core guarantees:

  * LOCAL-ONLY: models are loaded from the locally imported model
    directory only. Nothing is ever downloaded and no HuggingFace
    internet APIs are called.
  * CODE-SAFE: safetensors weight files are preferred because they
    cannot execute arbitrary Python on load (unlike pickle-based
    PyTorch `.pt`/`.bin` payloads). We never load a repository's
    Python modules.
  * CPU-FIRST: models are loaded with ``torch.device("cpu")`` by
    default so the tool runs on machines without an accelerator.
  * GRACEFUL FAILURE: out-of-memory and other resource errors are
    caught and reported instead of crashing the scanner / app.
  * CLEAR STATES: every loader exposes a status of
    ``loading`` | ``ready`` | ``failed`` | ``unsupported`` so the
    frontend can render a badge instead of guessing.

The public interface (``load_model``, ``unload_model``, ``model_status``,
``model_metadata``) is intentionally UI-free: the scanner can depend on
it without touching desktop code.
"""

import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.model_interface import model_forensics

# Status values exposed to the frontend.
STATUS_LOADING = "loading"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUS_UNSUPPORTED = "unsupported"

VALID_STATUSES = {STATUS_LOADING, STATUS_READY, STATUS_FAILED, STATUS_UNSUPPORTED}

# Weight formats we consider SAFE to load (no arbitrary code execution).
SAFE_WEIGHT_EXTENSIONS = {".safetensors", ".onnx"}
# Known-bad load paths: pickle-backed PyTorch assets can execute code
# on unpickle and must NEVER be loaded by the forensic loader.
UNSAFE_LOAD_EXTENSIONS = {".py", ".pyc", ".pt", ".pth", ".bin"}
# Formats we cannot run inference on (metadata / config only).
NON_LOADABLE_EXTENSIONS = {".json"}


@dataclass
class LoaderStatus:
    """Current load state plus a human-readable message."""

    status: str = STATUS_UNSUPPORTED
    message: str = "Model not loaded."
    loaded_path: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "status": self.status,
            "message": self.message,
            "loaded_path": self.loaded_path,
            "metadata": self.metadata,
        }


class ForensicModelLoader:
    """
    Abstract loader for local model files.

    Implementations must provide ``_do_load`` and ``_do_unload``. The
    base class handles status transitions, thread safety, path
    validation and resource error reporting, so subclasses stay thin.
    """

    #: Human-readable name used in the model_metadata() record.
    loader_name = "base"

    def __init__(self, model_path: Optional[str] = None) -> None:
        self._lock = threading.RLock()
        self._status = LoaderStatus()
        self._model: Any = None
        self._model_path: Optional[str] = None
        if model_path is None:
            model_path = os.environ.get("NEUROFENCE_MODEL_PATH")
        if model_path:
            self._set_path(model_path)

    # ---- public API ----------------------------------------------------

    def load_model(self, model_path: Optional[str] = None) -> LoaderStatus:
        """
        Load a local model into memory.

        Validates the path and that it is a supported (safe-to-load)
        format before dispatching to ``_do_load``. Returns the final
        status; never raises for expected resource failures.
        """
        if model_path:
            self._set_path(model_path)
        if self._model_path is None:
            self._set_status(
                STATUS_UNSUPPORTED,
                "No model path provided. Provide a path or set NEUROFENCE_MODEL_PATH.",
            )
            return self._status

        with self._lock:
            if self._model is not None:
                self._set_status(
                    STATUS_READY,
                    "Model is already loaded.",
                    loaded_path=self._model_path,
                )
                return self._status

            self._set_status(
                STATUS_LOADING,
                "Validating model file and preparing the CPU loading environment.",
                loaded_path=self._model_path,
            )

            err = self._validate_for_load()
            if err:
                self._set_status(
                    STATUS_UNSUPPORTED, err, loaded_path=self._model_path
                )
                return self._status

            try:
                self._model = self._do_load()
            except MemoryError as exc:
                self._model = None
                self._set_status(
                    STATUS_FAILED,
                    f"Insufficient memory to load the model: {exc}",
                    loaded_path=self._model_path,
                )
                return self._status
            except Exception as exc:  # noqa: BLE001 -- surface cleanly to UI
                self._model = None
                self._set_status(
                    STATUS_FAILED,
                    f"Model failed to load: {exc}",
                    loaded_path=self._model_path,
                )
                return self._status

            self._set_status(
                STATUS_READY,
                "Model loaded successfully (CPU, local, offline).",
                loaded_path=self._model_path,
            )
            return self._status

    def unload_model(self) -> LoaderStatus:
        """Release the loaded model and free its resources."""
        with self._lock:
            self._do_unload()
            self._model = None
            self._set_status(
                STATUS_UNSUPPORTED, "Model unloaded. No model in memory.",
                loaded_path=None,
            )
            return self._status

    def model_status(self) -> LoaderStatus:
        """Return the current load status without performing I/O."""
        with self._lock:
            return LoaderStatus(
                status=self._status.status,
                message=self._status.message,
                loaded_path=self._status.loaded_path,
                metadata=dict(self._status.metadata),
            )

    def model_metadata(self) -> Dict[str, Any]:
        """Return static metadata about the loader and its model path."""
        with self._lock:
            meta: Dict[str, Any] = {
                "loader_name": self.loader_name,
                "device": "cpu",
                "offline": True,
                "download_allowed": False,
                "status": self._status.status,
                "model_path": self._status.loaded_path,
            }
            if self._model_path and os.path.exists(self._model_path):
                try:
                    fr = model_forensics.inspect_model_file(self._model_path)
                    meta["forensics"] = fr.as_dict()
                except Exception:  # noqa: BLE001 -- never block metadata
                    meta["forensics"] = None
            meta.update(self._status.metadata)
            return meta

    def loaded_model(self) -> Any:
        """Return the in-memory loaded model object, or None."""
        with self._lock:
            return self._model

    # ---- internal ---------------------------------------------------------

    def _set_path(self, path: str) -> None:
        self._model_path = os.path.abspath(path)

    def _set_status(self, status: str, message: str,
                    loaded_path: Optional[str] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> None:
        self._status.status = status
        self._status.message = message
        if loaded_path is not None:
            self._status.loaded_path = loaded_path
        if metadata is not None:
            self._status.metadata = metadata

    def _validate_for_load(self) -> Optional[str]:
        """
        Return an error string if the model cannot be loaded safely,
        otherwise None.

        Enforces the core safety rule: we only load weight files that
        cannot execute arbitrary code (safetensors / onnx). Repository
        Python and pickle-backed PyTorch payloads are explicitly refused.
        """
        path = self._model_path
        if not path or not os.path.exists(path):
            return f"Model path does not exist: {path}"
        if os.path.isdir(path):
            return (
                "Directories cannot be loaded directly. Select a single "
                "safetensors weight file, or import the directory and then "
                "load a specific model record."
            )
        ext = os.path.splitext(path)[1].lower()
        if ext in UNSAFE_LOAD_EXTENSIONS:
            return (
                f"Refusing to load '{ext}' files: this format can execute "
                "arbitrary Python code on load. Only safe weight formats "
                f"({sorted(SAFE_WEIGHT_EXTENSIONS)}) are loaded."
            )
        if ext in NON_LOADABLE_EXTENSIONS:
            return (
                f"'{ext}' is a metadata/config file, not a loadable weight "
                "format."
            )
        if ext not in SAFE_WEIGHT_EXTENSIONS:
            return (
                f"Unsupported load format '{ext}'. Supported safe formats: "
                f"{sorted(SAFE_WEIGHT_EXTENSIONS)}."
            )
        size = os.path.getsize(path)
        if size == 0:
            return "Model file is empty (0 bytes) and cannot be loaded."
        return None

    def _do_load(self) -> Any:  # pragma: no cover - abstract
        raise NotImplementedError

    def _do_unload(self) -> None:  # pragma: no cover - abstract
        pass


class SafetensorsModelLoader(ForensicModelLoader):
    """
    Loads a local safetensors weights file into a CPU tensor container.

    Uses safetensors (which just decodes binary tensors -- no pickle, no
    code execution) with torch CPU tensors. This is the preferred loader
    because it is both safe and CPU-first. If torch is unavailable it
    falls back to a numpy-backed container so metadata/validation still
    works.
    """

    loader_name = "safetensors_cpu"

    def __init__(self, model_path: Optional[str] = None,
                 device: str = "cpu") -> None:
        super().__init__(model_path)
        self._device = device
        self._torch = None
        try:
            import torch  # noqa: PLC0415 - optional dependency
            self._torch = torch
        except Exception:  # pragma: no cover - torch optional
            self._torch = None

    def _do_load(self) -> Any:
        from safetensors import safe_open

        if self._torch is None:
            raise RuntimeError(
                "PyTorch is required to load safetensors tensors but is not "
                "installed. Install torch, or use a metadata-only import."
            )

        # CPU-first: never move to an accelerator.
        tensors: Dict[str, Any] = {}
        with safe_open(self._model_path, framework="pt", device=self._device) as f:
            for key in f.keys():
                tensors[key] = f.get_tensor(key)

        # Wrap in a small container exposing the raw tensors plus metadata.
        return {
            "path": self._model_path,
            "device": self._device,
            "tensor_count": len(tensors),
            "tensors": tensors,
            "shapes": {k: list(v.shape) for k, v in tensors.items()},
        }


class OnnxModelLoader(ForensicModelLoader):
    """
    Loads a local ONNX model for CPU inference using onnxruntime
    (if available). ONNX is a safe (no code execution) weight format.
    """

    loader_name = "onnx_cpu"

    def _do_load(self) -> Any:
        try:
            import onnxruntime  # noqa: PLC0415 - optional dependency
        except Exception as exc:  # pragma: no cover - dependency missing
            raise RuntimeError(
                "onnxruntime is not installed and is required to load ONNX "
                f"models: {exc}"
            )
        providers = ["CPUExecutionProvider"]
        session = onnxruntime.InferenceSession(
            self._model_path, providers=providers
        )
        return {
            "path": self._model_path,
            "providers": session.get_providers(),
            "inputs": [i.name for i in session.get_inputs()],
            "outputs": [o.name for o in session.get_outputs()],
        }


# Factory: pick the safest loader for a given model file based on its
# extension. Returns STATUS_UNSUPPORTED result if no safe loader exists.
def loader_factory(model_path: Optional[str] = None) -> ForensicModelLoader:
    """
    Return the appropriate safe loader for a model file, or a loader
    pre-marked unsupported if none is available.

    This keeps the factory safe even when called with an unsafe format:
    the returned loader refuses to load and reports ``unsupported``.
    """
    ext = ""
    if model_path:
        ext = os.path.splitext(model_path)[1].lower()

    if ext == ".safetensors":
        return SafetensorsModelLoader(model_path)
    if ext == ".onnx":
        return OnnxModelLoader(model_path)

    loader = ForensicModelLoader(model_path)
    # Pre-mark unsupported so model_metadata() reflects it immediately.
    loader._set_status(
        STATUS_UNSUPPORTED,
        "No safe loader registered for this model format.",
        loaded_path=loader._model_path,
    )
    return loader

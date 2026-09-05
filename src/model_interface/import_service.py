"""
Model Import Service -- import, validate, hash and store local models.

Accepts a file or directory path, validates supported formats,
computes SHA-256, extracts metadata, and persists to SQLite.

This is the core backend for the Models page. No code from the model
file is ever executed -- only metadata is inspected.
"""

import json
import os
import threading
from datetime import datetime
from typing import Dict, List, Optional

from src.db.db_manager import get_session
from src.db.models import ModelMetadata
from src.model_interface.model_forensics import (
    SUPPORTED_EXTENSIONS,
    ModelForensics,
    inspect_model_file,
    format_size,
)
from src.model_interface.loader import loader_factory

# Max file size: 10 GB
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024 * 1024

# Unsafe extensions that should never be loaded
UNSAFE_EXTENSIONS = {".py", ".pyc", ".sh", ".bat", ".cmd", ".exe", ".dll", ".so", ".dylib"}

# Preferred model extensions in order of preference
PREFERRED_EXTENSIONS = [".safetensors", ".bin", ".pt", ".pth", ".onnx", ".json"]


def _find_model_files_in_dir(dir_path: str) -> List[str]:
    """
    Scan a directory for model files. Returns a list of candidate
    model file paths, ordered by preference (safetensors first).
    """
    candidates = []
    for root, _dirs, files in os.walk(dir_path):
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            if ext in SUPPORTED_EXTENSIONS and ext not in UNSAFE_EXTENSIONS:
                candidates.append(os.path.join(root, fname))
    # Sort by preference
    def _sort_key(path):
        ext = os.path.splitext(path)[1].lower()
        try:
            return PREFERRED_EXTENSIONS.index(ext)
        except ValueError:
            return len(PREFERRED_EXTENSIONS)
    candidates.sort(key=_sort_key)
    return candidates


def _validate_file(path: str) -> Optional[str]:
    """
    Validate a single model file. Returns an error string if
    invalid, or None if valid.
    """
    if not os.path.exists(path):
        return f"Path does not exist: {path}"
    if os.path.isdir(path):
        return None  # directories are valid (will scan for model files)
    ext = os.path.splitext(path)[1].lower()
    if ext in UNSAFE_EXTENSIONS:
        return (
            f"Rejected: '{ext}' files are executable code and cannot be "
            "imported. NeuroFence only accepts model weight files "
            f"(safetensors, pytorch, onnx, json)."
        )
    if ext not in SUPPORTED_EXTENSIONS:
        return (
            f"Unsupported format '{ext}'. Supported: "
            f"{sorted(SUPPORTED_EXTENSIONS - UNSAFE_EXTENSIONS)}."
        )
    size = os.path.getsize(path)
    if size > MAX_FILE_SIZE_BYTES:
        return f"File too large: {format_size(size)} exceeds {format_size(MAX_FILE_SIZE_BYTES)} limit."
    if size == 0:
        return "File is empty (0 bytes)."
    return None


def import_model(path: str) -> Dict:
    """
    Import a model file or directory.

    Returns a dict with:
      - success: bool
      - models: list of imported model records
      - errors: list of error strings
    """
    errors = []
    imported = []

    if not path or not os.path.exists(path):
        return {"success": False, "models": [], "errors": [f"Path does not exist: {path}"]}

    if os.path.isdir(path):
        model_files = _find_model_files_in_dir(path)
        if not model_files:
            return {
                "success": False,
                "models": [],
                "errors": [f"No supported model files found in directory: {path}"],
            }
        for mf in model_files:
            result = _import_single_file(mf)
            if result.get("error"):
                errors.append(result["error"])
            else:
                imported.append(result["model"])
    else:
        err = _validate_file(path)
        if err:
            return {"success": False, "models": [], "errors": [err]}
        result = _import_single_file(path)
        if result.get("error"):
            errors.append(result["error"])
        else:
            imported.append(result["model"])

    return {
        "success": len(imported) > 0,
        "models": imported,
        "errors": errors,
    }


def _import_single_file(path: str) -> Dict:
    """
    Import a single model file: validate, inspect, store in DB.
    Returns {"model": record_dict} or {"error": str}.
    """
    err = _validate_file(path)
    if err:
        return {"error": err}

    forensics = inspect_model_file(path)

    if not forensics.supported:
        return {"error": f"Validation failed for {forensics.file_name}: {forensics.validation_error}"}

    session = get_session()
    try:
        # Check for duplicate by SHA-256
        existing = session.query(ModelMetadata).filter_by(
            sha256_hash=forensics.sha256_hash
        ).first()
        if existing:
            record = _row_to_dict(existing)
            record["duplicate"] = True
            return {"model": record}

        row = ModelMetadata(
            file_name=forensics.file_name,
            file_path=forensics.file_path,
            file_size_bytes=forensics.file_size_bytes,
            sha256_hash=forensics.sha256_hash,
            model_type=forensics.model_type,
            architecture=forensics.architecture,
            num_parameters=forensics.num_parameters,
            layer_count=forensics.layer_count,
            layer_info=json.dumps(forensics.layer_info) if forensics.layer_info else None,
            supported=forensics.supported,
            status="validated",
            notes="; ".join(forensics.notes) if forensics.notes else None,
        )
        session.add(row)
        session.commit()
        return {"model": _row_to_dict(row)}
    finally:
        session.close()


def _row_to_dict(row: ModelMetadata) -> Dict:
    return {
        "metadata_id": row.metadata_id,
        "file_name": row.file_name,
        "file_path": row.file_path,
        "file_size_bytes": row.file_size_bytes,
        "sha256_hash": row.sha256_hash,
        "model_type": row.model_type,
        "architecture": row.architecture,
        "num_parameters": row.num_parameters,
        "layer_count": row.layer_count,
        "layer_info": row.layer_info,
        "supported": row.supported,
        "status": row.status or "imported",
        "notes": row.notes,
        "scanned_at": row.scanned_at.isoformat() if row.scanned_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def list_models() -> List[Dict]:
    """Return all imported models, most recent first."""
    session = get_session()
    try:
        rows = (
            session.query(ModelMetadata)
            .order_by(ModelMetadata.metadata_id.desc())
            .all()
        )
        return [_row_to_dict(r) for r in rows]
    finally:
        session.close()


def get_model(metadata_id: int) -> Optional[Dict]:
    """Return a single model by ID, or None."""
    session = get_session()
    try:
        row = session.query(ModelMetadata).get(metadata_id)
        if row is None:
            return None
        return _row_to_dict(row)
    finally:
        session.close()


def update_model_status(metadata_id: int, status: str) -> Optional[Dict]:
    """Update a model's status field. Returns the updated record."""
    session = get_session()
    try:
        row = session.query(ModelMetadata).get(metadata_id)
        if row is None:
            return None
        row.status = status
        if status == "scanned":
            row.scanned_at = datetime.utcnow()
        session.commit()
        return _row_to_dict(row)
    finally:
        session.close()


def delete_model(metadata_id: int) -> bool:
    """Delete a model record. Returns True if deleted."""
    session = get_session()
    try:
        row = session.query(ModelMetadata).get(metadata_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
        return True
    finally:
        session.close()


def mark_model_scanned(metadata_id: Optional[int] = None) -> Optional[Dict]:
    """
    Mark the model just scanned as 'scanned' (status + scanned_at).

    The scan pipeline does not know the registry id, so when metadata_id
    is None the most recent registry entry is marked instead. Returns the
    updated record, or None when no model is registered. Called only by
    the scan process (subprocess/CLI), never from the GUI thread.
    """
    session = get_session()
    try:
        if metadata_id is not None:
            row = session.query(ModelMetadata).get(metadata_id)
        else:
            row = (
                session.query(ModelMetadata)
                .order_by(ModelMetadata.metadata_id.desc())
                .first()
            )
        if row is None:
            return None
        row.status = "scanned"
        row.scanned_at = datetime.utcnow()
        session.commit()
        return _row_to_dict(row)
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Safe local model loading integration
#
# These functions pair a model registry record with a ForensicModelLoader
# so the scanner / UI can load, inspect and release a local model without
# touching loader internals. The loader abstraction lives in:
#     src/model_interface/loader.py
#
# A process-local registry (``_ACTIVE_LOADERS``) tracks the loaders that
# currently hold an in-memory model, keyed by metadata_id, so that
# ``model_status()`` reflects the real in-memory state within this process.
# ---------------------------------------------------------------------------

_ACTIVE_LOADERS: Dict[int, "object"] = {}
_ACTIVE_LOADERS_LOCK = threading.Lock()


def _get_or_create_loader(metadata_id: int) -> "object":
    """Return the active loader for a metadata_id, or create one from disk."""
    from src.model_interface.loader import loader_factory

    with _ACTIVE_LOADERS_LOCK:
        loader = _ACTIVE_LOADERS.get(metadata_id)
        if loader is not None:
            return loader
        model = get_model(metadata_id)
        if model is None:
            return loader_factory(None)
        path = model.get("file_path")
        if path and os.path.exists(path):
            loader = loader_factory(path)
        else:
            loader = loader_factory(None)
        _ACTIVE_LOADERS[metadata_id] = loader
        return loader


def _release_loader(metadata_id: int) -> None:
    with _ACTIVE_LOADERS_LOCK:
        _ACTIVE_LOADERS.pop(metadata_id, None)


def load_model_file(metadata_id: int) -> dict:
    """
    Load a locally imported model for analysis.

    Resolves the model's on-disk file, picks a safe loader for its
    format, loads it into the in-process registry, and returns a dict
    with the loader status plus the registry record. Never downloads.
    """
    model = get_model(metadata_id)
    if model is None:
        return {
            "status": "failed",
            "message": "Model record not found in the registry.",
            "metadata": {},
            "model": None,
        }
    path = model.get("file_path")
    if not path or not os.path.exists(path):
        return {
            "status": "failed",
            "message": f"Model file is missing on disk: {path}",
            "metadata": {},
            "model": model,
        }
    loader = _get_or_create_loader(metadata_id)
    status = loader.load_model()

    # Enrich metadata with a digest of what actually got loaded so the
    # UI/frontend can confirm the load without importing torch itself.
    metadata = loader.model_metadata()
    loaded = loader.loaded_model()
    if isinstance(loaded, dict) and metadata.get("status") == "ready":
        summary = {k: v for k, v in loaded.items() if k != "tensors"}
        metadata.setdefault("load_summary", summary)

    if status.status == "ready" and model.get("status") != "scanned":
        update_model_status(metadata_id, "scanned")
    return {
        "status": status.status,
        "message": status.message,
        "metadata": metadata,
        "model": get_model(metadata_id),
    }


def unload_model_file(metadata_id: int) -> dict:
    """Unload an imported model, releasing its in-memory resources."""
    model = get_model(metadata_id)
    if model is None:
        return {"status": "failed", "message": "Model record not found."}
    loader = _get_or_create_loader(metadata_id)
    status = loader.unload_model()
    _release_loader(metadata_id)
    return {"status": status.status, "message": status.message, "model": model}


def model_load_status(metadata_id: int) -> dict:
    """
    Report the current in-process load status for a model.

    Uses the active in-memory loader when present so the UI shows the
    real state (Loading/Ready/Failed/Unsupported).
    """
    model = get_model(metadata_id)
    if model is None:
        return {"status": "failed", "message": "Model record not found."}
    loader = _get_or_create_loader(metadata_id)
    return {
        "status": loader.model_status().status,
        "message": loader.model_status().message,
        "model": model,
    }


def model_loader_metadata(metadata_id: int) -> dict:
    """Return loader metadata + forensics for an imported model."""
    model = get_model(metadata_id)
    if model is None:
        return {"metadata": {}, "model": None}
    path = model.get("file_path")
    if not path or not os.path.exists(path):
        return {
            "metadata": {"offline": True, "status": "failed",
                          "error": "file missing"},
            "model": model,
        }
    loader = _get_or_create_loader(metadata_id)
    return {"metadata": loader.model_metadata(), "model": model}

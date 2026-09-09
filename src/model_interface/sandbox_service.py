"""
Model sandbox integration helpers -- store forensics in SQLite and
provide a thin service layer used by both the CLI pipeline and the
PyQt desktop app.
"""

from typing import Optional

from src.db.db_manager import get_session
from src.db.models import ModelMetadata
from src.model_interface.model_forensics import ModelForensics, inspect_model_file
from src.model_interface.model_sandbox import ModelSandbox


def persist_model_metadata(forensics: ModelForensics) -> dict:
    """
    Save a ModelForensics record into the model_metadata table and
    return the stored row as a plain dict (safe to use after the
    session closes).
    """
    session = get_session()
    try:
        row = ModelMetadata(
            file_name=forensics.file_name,
            file_path=forensics.file_path,
            file_size_bytes=forensics.file_size_bytes,
            sha256_hash=forensics.sha256_hash,
            model_type=forensics.model_type,
            architecture=forensics.architecture,
            num_parameters=forensics.num_parameters,
            layer_count=forensics.layer_count,
            layer_info=str(forensics.layer_info) if forensics.layer_info else None,
            supported=forensics.supported,
            notes="; ".join(forensics.notes) if forensics.notes else None,
        )
        session.add(row)
        session.commit()
        returned = {
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
            "notes": row.notes,
        }
        return returned
    finally:
        session.close()


def latest_model_metadata() -> Optional[dict]:
    """Most recently stored model metadata (or None)."""
    session = get_session()
    try:
        row = (
            session.query(ModelMetadata)
            .order_by(ModelMetadata.metadata_id.desc())
            .first()
        )
        if row is None:
            return None
        return {
            "file_name": row.file_name,
            "file_path": row.file_path,
            "file_size_bytes": row.file_size_bytes,
            "sha256_hash": row.sha256_hash,
            "model_type": row.model_type,
            "architecture": row.architecture,
            "num_parameters": row.num_parameters,
            "layer_count": row.layer_count,
            "supported": row.supported,
            "notes": row.notes,
        }
    finally:
        session.close()


def inspect_and_persist_toy_model(marker_path: Optional[str] = None) -> dict:
    """
    Convenience for the demo: build forensics for the bundled toy model
    (optionally from a generated marker file) and persist it. Returns
    the stored row as a dict.
    """
    forensics = inspect_model_file(marker_path) if marker_path else ModelForensics()
    if not marker_path:
        forensics.file_name = "toy_model"
        forensics.file_path = "bundled://toy_model"
        forensics.sha256_hash = "simulated-bundled-toy-model"
        forensics.file_size_bytes = 0
        forensics.model_type = "toy_model"
        forensics.architecture = "Rule-based synthetic toy model (simulated)"
        forensics.supported = True
        forensics.notes.append(
            "Bundled synthetic toy model used for offline demo/review."
        )
    return persist_model_metadata(forensics)


def build_sandbox(model_file: Optional[str] = None) -> ModelSandbox:
    """Create a sandboxed model instance (offline, safe)."""
    return ModelSandbox(target_name="toy_model", model_file=model_file)
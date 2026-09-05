"""
Model import and management API routes.

Provides endpoints to import, list, retrieve, update status, and
delete local model files. All operations are offline and safe.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.model_interface.import_service import (
    import_model,
    list_models,
    get_model,
    update_model_status,
    delete_model,
    load_model_file,
    unload_model_file,
    model_load_status,
    model_loader_metadata,
)

router = APIRouter()


class ImportRequest(BaseModel):
    path: str


class ImportResponse(BaseModel):
    success: bool
    models: List[dict]
    errors: List[str]


class ModelRecord(BaseModel):
    metadata_id: int
    file_name: str
    file_path: str
    file_size_bytes: int
    sha256_hash: str
    model_type: Optional[str] = None
    architecture: Optional[str] = None
    num_parameters: Optional[int] = None
    layer_count: Optional[int] = None
    layer_info: Optional[str] = None
    supported: bool = True
    status: str = "imported"
    notes: Optional[str] = None
    scanned_at: Optional[str] = None
    created_at: Optional[str] = None


class StatusUpdate(BaseModel):
    status: str


@router.post("/import", response_model=ImportResponse)
def api_import_model(req: ImportRequest):
    """Import a local model file or directory."""
    result = import_model(req.path)
    if not result["success"] and result["errors"]:
        raise HTTPException(status_code=400, detail=result["errors"])
    return result


@router.get("/", response_model=List[dict])
def api_list_models():
    """List all imported models."""
    return list_models()


@router.get("/{metadata_id}", response_model=dict)
def api_get_model(metadata_id: int):
    """Get a single model by ID."""
    model = get_model(metadata_id)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.patch("/{metadata_id}/status")
def api_update_status(metadata_id: int, req: StatusUpdate):
    """Update a model's status."""
    model = update_model_status(metadata_id, req.status)
    if model is None:
        raise HTTPException(status_code=404, detail="Model not found")
    return model


@router.delete("/{metadata_id}")
def api_delete_model(metadata_id: int):
    """Delete a model record."""
    deleted = delete_model(metadata_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"deleted": True, "metadata_id": metadata_id}


@router.post("/{metadata_id}/load")
def api_load_model(metadata_id: int):
    """Load a local model file into memory for analysis (CPU, offline, safe)."""
    result = load_model_file(metadata_id)
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/{metadata_id}/unload")
def api_unload_model(metadata_id: int):
    """Unload a model, releasing its in-memory resources."""
    result = unload_model_file(metadata_id)
    if result["status"] == "failed":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/{metadata_id}/load-status")
def api_model_load_status(metadata_id: int):
    """Report the current load status for a model."""
    result = model_load_status(metadata_id)
    return result


@router.get("/{metadata_id}/loader-metadata")
def api_model_loader_metadata(metadata_id: int):
    """Return loader metadata and forensics for a model."""
    return model_loader_metadata(metadata_id)

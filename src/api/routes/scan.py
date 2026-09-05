"""
Adversarial Scan API routes.

Exposes the modular adversarial input generator + activation tracking
flow as a REST backend so the desktop Start Scan button can call a real
backend. Fully offline; only targets the local model.
"""

from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from src.fuzzer.adversarial_generator import CATEGORY_KEYS, AdversarialInputGenerator
from src.fuzzer import adversarial_scan
from src.scanner import pipeline as pipeline_mod

router = APIRouter()


class ScanRequest(BaseModel):
    model: str = "tiny"
    num_prompts: int = 10
    max_seq_len: int = 16
    categories: Optional[List[str]] = None
    seed: int = 42
    layers: int = 12


class ScanResponse(BaseModel):
    status: str
    run_id: int
    run_label: str
    model: str
    num_prompts: int
    measured_prompts: int
    layers_tracked: int
    layers: List[str]
    measurements: int
    categories: List[str]
    seed: int
    errors: List[str]


@router.get("/categories", response_model=dict)
def api_scan_categories():
    """Return the available input categories and their labels."""
    from src.fuzzer.adversarial_generator import CATEGORY_LABELS
    return {
        "categories": CATEGORY_KEYS,
        "labels": {c: CATEGORY_LABELS.get(c, c) for c in CATEGORY_KEYS},
    }


@router.get("/models", response_model=List[dict])
def api_scan_models():
    """Return the offline local model choices for the scan UI."""
    return adversarial_scan.show_available_models()


@router.post("/estimate", response_model=dict)
def api_scan_estimate(req: ScanRequest):
    """Estimate scan size (prompts and activation measurements) without running."""
    gen = AdversarialInputGenerator(seed=req.seed)
    categories = req.categories and [c for c in req.categories if c in CATEGORY_KEYS]
    return gen.estimate_size(
        count=req.num_prompts,
        categories=categories,
        layers=req.layers,
    )


@router.post("", response_model=dict)
def api_run_adversarial_scan(req: ScanRequest):
    """Run the full fuzzer -> model -> hooks -> database flow."""
    try:
        result = adversarial_scan.run_adversarial_scan(
            count=req.num_prompts,
            seed=req.seed,
            categories=req.categories,
            max_seq_len=req.max_seq_len,
            layers=req.layers,
            model=req.model,
        )
    except Exception as exc:  # noqa: BLE001 -- surface backend error to UI
        raise HTTPException(status_code=400, detail=str(exc))
    return result


@router.get("/runs", response_model=List[dict])
def api_list_scan_runs(limit: int = 25):
    """Return recent adversarial scan runs."""
    return adversarial_scan.list_scan_runs(limit=limit)


@router.get("/runs/{run_id}", response_model=List[dict])
def api_scan_run_measurements(run_id: int, limit: int = 200):
    """Return activation measurements for one scan run."""
    return adversarial_scan.measurements_for_run(run_id, limit=limit)


class PipelineScanRequest(BaseModel):
    model: str = "tiny"
    num_prompts: int = 8
    max_seq_len: int = 16
    categories: Optional[List[str]] = None
    seed: int = 42
    layers: int = 12
    max_new_tokens: int = 3


@router.post("/pipeline", response_model=dict)
def api_start_pipeline_scan(req: PipelineScanRequest,
                            background_tasks: BackgroundTasks):
    """
    Create a QUEUED pipeline scan and run it end-to-end in the background.

    Returns immediately with the initial state; progress is polled via
    GET /api/scan/pipeline/state/{scan_id}.
    """
    scan_id = pipeline_mod.create_scan({
        "model": req.model,
        "num_prompts": req.num_prompts,
        "max_seq_len": req.max_seq_len,
        "categories": req.categories,
        "seed": req.seed,
        "layers": req.layers,
        "max_new_tokens": req.max_new_tokens,
    })
    background_tasks.add_task(pipeline_mod.execute_scan, scan_id)
    return pipeline_mod.get_scan_state(scan_id)


@router.get("/pipeline/state/{scan_id}", response_model=dict)
def api_pipeline_state(scan_id: int):
    """Return the real, persisted progress for one pipeline scan."""
    state = pipeline_mod.get_scan_state(scan_id)
    if state is None:
        raise HTTPException(status_code=404,
                            detail=f"No pipeline scan {scan_id}")
    return state


@router.get("/pipeline/runs", response_model=List[dict])
def api_pipeline_runs(limit: int = 25):
    """Return recent pipeline scan runs."""
    return pipeline_mod.list_pipeline_runs(limit=limit)


@router.post("/pipeline/{scan_id}/cancel", response_model=dict)
def api_pipeline_cancel(scan_id: int):
    """Request graceful cancellation of a running pipeline scan."""
    if not pipeline_mod.cancel_scan(scan_id):
        raise HTTPException(status_code=404,
                            detail=f"No active pipeline scan {scan_id}")
    return pipeline_mod.get_scan_state(scan_id)

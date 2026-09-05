"""
Statistical Findings API routes.

Exposes the statistical anomaly detection engine so the desktop UI and any
external client can list real findings, inspect a single finding's evidence,
and trigger detection over a completed adversarial scan run.

GET /api/findings           -> list findings (filter by run/severity/layer)
GET /api/findings/{id}      -> single finding with evidence
POST /api/findings/detect   -> run detection over a scan run
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from src.anomaly_detection import statistical_engine

router = APIRouter()


class DetectRequest(BaseModel):
    run_id: Optional[int] = None     # None = latest completed scan run
    force: bool = True               # delete prior findings for the run first


@router.get("", response_model=dict)
def api_list_findings(
    limit: int = 500,
    run_id: Optional[int] = None,
    severity: Optional[str] = None,
    layer: Optional[str] = None,
):
    """List real statistical findings, most severe first."""
    if limit < 1 or limit > 100000:
        raise HTTPException(status_code=400, detail="limit out of range 1..100000")
    findings = statistical_engine.list_findings(
        limit=limit, run_id=run_id, severity=severity, layer=layer
    )
    summary = statistical_engine.findings_summary(run_id=run_id)
    return {"findings": findings, "summary": summary}


@router.get("/summary", response_model=dict)
def api_findings_summary(run_id: Optional[int] = None):
    """Severity distribution and aggregate numbers for the Findings page."""
    return statistical_engine.findings_summary(run_id=run_id)


@router.get("/runs", response_model=List[dict])
def api_finding_scan_runs(limit: int = 25):
    """Completed scan runs that can be analyzed (with their measurement counts)."""
    from src.fuzzer.adversarial_scan import list_scan_runs
    runs = list_scan_runs(limit=limit)
    return [r for r in runs if r["status"] == "completed"]


@router.get("/{finding_id}", response_model=dict)
def api_get_finding(finding_id: int):
    """Return one finding (including its evidence JSON)."""
    finding = statistical_engine.get_finding(finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")
    return finding


@router.post("/detect", response_model=dict)
def api_detect(req: DetectRequest):
    """Run statistical anomaly detection over a completed scan run."""
    try:
        result = statistical_engine.generate_statistical_findings(
            run_id=req.run_id, force=req.force
        )
    except Exception as exc:  # noqa: BLE001 -- surface backend error to UI
        raise HTTPException(status_code=400, detail=str(exc))
    if result["status"] == "no_run":
        raise HTTPException(status_code=404, detail="No completed scan run to analyze")
    return result
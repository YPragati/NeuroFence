"""
Forensic report generation + download API routes.

    POST /api/investigations/{scan_id}/report   generate a PDF for a scan
    GET  /api/reports/{report_id}/download      download the generated file

Both endpoints are backed by the real forensic report engine and the
persisted reports table. The download endpoint resolves paths inside the
reports directory only (path-traversal safe) and streams the file with a
Content-Disposition attachment header.
"""

import os
from typing import Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from src.reporting import forensic_report
from src.reporting.forensic_report import _reports_dir

investigations_router = APIRouter()
reports_router = APIRouter()


class ReportRequest(BaseModel):
    format: str = "pdf"


def _safe_report_path(file_path) -> str:
    """Resolve a stored report path and reject traversal outside the dir."""
    if not file_path:
        return None
    reports_dir = os.path.abspath(_reports_dir())
    resolved = os.path.normpath(os.path.join(reports_dir, os.path.basename(file_path)))
    if not resolved.startswith(reports_dir + os.sep):
        return None
    return resolved


@investigations_router.post("/{scan_id}/report", response_model=dict)
def api_generate_report(scan_id: int, req: Optional[ReportRequest] = None):
    """Generate a real forensic PDF for the pipeline scan {scan_id}."""
    fmt = "pdf" if (req is None or req.format == "pdf") else req.format
    try:
        path = forensic_report.generate_forensic_report(scan_id=int(scan_id))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:  # noqa: BLE001 -- surface real engine errors
        raise HTTPException(status_code=400, detail=str(exc))
    newest = forensic_report.list_reports(limit=1)
    report = newest[0] if newest else None
    return {
        "status": "success",
        "format": fmt,
        "scan_id": int(scan_id),
        "file_path": path,
        "report_id": (report or {}).get("report_id"),
        "download_url": (
            f"/api/reports/{report['report_id']}/download" if report else None
        ),
    }


@reports_router.get("/{report_id}/download")
def api_download_report(report_id: int):
    """Stream one generated report with a download disposition."""
    detail = forensic_report.report_detail(int(report_id))
    if detail is None:
        raise HTTPException(status_code=404,
                            detail=f"No report {report_id}")
    path = _safe_report_path(detail.get("file_path"))
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404,
                            detail=f"Report file missing on disk for report {report_id}")
    return FileResponse(
        path,
        media_type="application/pdf",
        filename=os.path.basename(path),
    )
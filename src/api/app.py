"""
NeuroFence FastAPI application.

Offline-first REST API for the AI security forensic platform.
Run with: uvicorn src.api.app:app --reload
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes.models import router as models_router
from src.api.routes.scan import router as scan_router
from src.api.routes.findings import router as findings_router
from src.api.routes.reports import (
    investigations_router,
    reports_router,
)

app = FastAPI(
    title="NeuroFence API",
    description="Offline LLM Weight Poisoning & Backdoor Scanner",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(models_router, prefix="/api/models", tags=["models"])
app.include_router(scan_router, prefix="/api/scan", tags=["scan"])
app.include_router(findings_router, prefix="/api/findings", tags=["findings"])
app.include_router(
    investigations_router, prefix="/api/investigations", tags=["investigations"])
app.include_router(reports_router, prefix="/api/reports", tags=["reports"])


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "neurofence", "offline": True}

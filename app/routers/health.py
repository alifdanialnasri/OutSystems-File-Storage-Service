"""
routers/health.py
-----------------
Simple liveness probe — used by load balancers, monitoring, and OutSystems
to verify the service is up before starting an upload.
"""

from fastapi import APIRouter
from app.schemas import HealthResponse

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthResponse, summary="Service health check")
def health() -> HealthResponse:
    return HealthResponse(status="ok")

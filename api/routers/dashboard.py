"""Pre-built dashboard payloads (cached at startup via precompute.py)."""
from fastapi import APIRouter, HTTPException

from api.cache import get_cache
from api.models import DashboardTab

router = APIRouter()


@router.get("/api/dashboard")
def dashboard(tab: DashboardTab) -> dict:
    cache = get_cache()
    payload = cache.get_dashboard(tab.value)
    if payload is None:
        raise HTTPException(
            status_code=503,
            detail=f"Dashboard cache empty for tab '{tab.value}'. Run precompute.py.",
        )
    return payload

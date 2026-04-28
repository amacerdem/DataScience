"""Cached chip path — synchronous JSON response from in-memory cache."""
from fastapi import APIRouter, HTTPException

from api.cache import get_cache
from api.models import AskRequest

router = APIRouter()


@router.post("/api/ask")
def ask_cached(req: AskRequest) -> dict:
    cache = get_cache()
    payload = cache.get_ask(req.question)
    if payload is None:
        raise HTTPException(
            status_code=404,
            detail="No cached answer; use /api/ask/stream for live LLM",
        )
    return payload

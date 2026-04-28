"""FastAPI app entry point."""
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.cache import get_cache
from api.config import get_settings
from api.routers import ask as ask_router, dashboard as dashboard_router

ROOT = Path(__file__).resolve().parents[1]


def _load_cache_file() -> None:
    cache_path = Path(os.environ.get("CACHE_FILE", str(ROOT / "data" / "cache.json")))
    if not cache_path.exists():
        return
    payload = json.loads(cache_path.read_text())
    cache = get_cache()
    for q, p in payload.get("chips", {}).items():
        cache.set_ask(q, p)
    for tab, p in payload.get("dashboards", {}).items():
        cache.set_dashboard(tab, p)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_cache_file()
    yield


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Olist Analytics API", version="1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "olist-analytics-api", "status": "ok"}

    app.include_router(ask_router.router)
    app.include_router(dashboard_router.router)

    return app


app = create_app()

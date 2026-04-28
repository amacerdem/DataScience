"""FastAPI app entry point."""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.config import get_settings
from api.routers import ask as ask_router


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Olist Analytics API", version="1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.allowed_origins.split(",")],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(ask_router.router)

    @app.get("/")
    def root() -> dict[str, str]:
        return {"service": "olist-analytics-api", "status": "ok"}

    return app


app = create_app()

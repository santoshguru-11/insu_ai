"""Autonomous Maintenance Console — FastAPI application entry point.

Run locally from the `backend/` directory::

    uv run uvicorn app.main:app --reload
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import api_router
from app.core.config import settings
from app.core.exceptions import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.core.middleware import RequestContextMiddleware
from app.db.session import dispose_engine
from app.services.health import APP_VERSION

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    configure_logging()
    logger.info(
        "application_startup",
        app_name=settings.app_name,
        environment=settings.app_env,
        api_prefix=settings.api_prefix,
    )
    yield
    await dispose_engine()
    logger.info("application_shutdown")


def create_app() -> FastAPI:
    configure_logging()

    app = FastAPI(
        title=settings.app_name,
        version=APP_VERSION,
        description=(
            "Backend for the Autonomous Maintenance Console: machine anomalies, "
            "AI diagnosis, maintenance proposals, human approval and audit trail."
        ),
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )

    # Request id + structured access logging. Registered before CORS so the
    # id is bound for every response, including CORS preflights.
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    register_exception_handlers(app)

    # Versioned API, plus an unprefixed /health for probes that expect it there.
    app.include_router(api_router, prefix=settings.api_prefix)
    app.include_router(api_router)

    return app


app = create_app()

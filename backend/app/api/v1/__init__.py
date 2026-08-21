"""Version 1 of the HTTP API."""

from fastapi import APIRouter

from app.api.v1 import assets, health, incidents

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(assets.router)
api_router.include_router(incidents.router)

__all__ = ["api_router"]

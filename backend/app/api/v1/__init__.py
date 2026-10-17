"""API v1 (`/api/v1`)."""

from fastapi import APIRouter

from app.api.v1 import assets, catalog, costs, projects

router = APIRouter(prefix="/api/v1")
router.include_router(catalog.router)
router.include_router(projects.router)
router.include_router(assets.router)
router.include_router(costs.router)

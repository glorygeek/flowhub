from fastapi import APIRouter, Depends

from app.api import ai, planner, recipes, run_requests, skills, telemetry, workflows
from app.core.config import get_settings
from app.core.security import require_api_key

settings = get_settings()

api_router = APIRouter(
    prefix=settings.api_v1_prefix,
    dependencies=[Depends(require_api_key)],
)
api_router.include_router(skills.router)
api_router.include_router(recipes.router)
api_router.include_router(workflows.router)
api_router.include_router(ai.router)
api_router.include_router(planner.router)
api_router.include_router(run_requests.router)
api_router.include_router(telemetry.router)

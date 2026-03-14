from contextlib import asynccontextmanager

from fastapi import FastAPI, Response, status
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.core.database import migrate_db
from app.services.skill_sync_scheduler import (
    start_skill_sync_scheduler,
    stop_skill_sync_scheduler,
)

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    migrate_db()
    start_skill_sync_scheduler()
    try:
        yield
    finally:
        stop_skill_sync_scheduler()


app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_origin_regex=settings.cors_allow_origin_regex,
    allow_credentials=settings.cors_allow_credentials,
    allow_methods=settings.cors_allow_methods,
    allow_headers=settings.cors_allow_headers,
)


@app.get("/")
def root() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "health": "/health",
        "docs": "/docs",
    }


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok", "service": settings.app_name}


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.options("/{path:path}", include_in_schema=False)
def options_fallback(path: str) -> Response:
    _ = path
    return Response(status_code=status.HTTP_204_NO_CONTENT)


app.include_router(api_router)

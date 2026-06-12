"""
app/main.py
-----------
FastAPI application factory.

Startup sequence:
  1. Load settings from .env
  2. Configure logging (rotating file + console)
  3. Ensure storage directories exist
  4. Create database tables
  5. Register all routers

This file is the single entry point — `uvicorn app.main:app`
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import create_all_tables
from app.logging_config import setup_logging
from app.routers import files_router, health_router, upload_router
from app.utils.file_utils import ensure_directory

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan handler — runs once at startup before serving requests.
    """
    settings = get_settings()

    # 1. Initialise logging first so all subsequent messages are captured
    setup_logging(settings.log_dir, settings.log_level)

    # 2. Ensure all required directories exist
    for directory in [
        settings.temp_chunk_dir,
        settings.final_storage_dir,
        settings.log_dir,
    ]:
        ensure_directory(directory)

    # 3. Create DB tables (idempotent — safe on every restart)
    create_all_tables()

    logger.info("File Storage Service started | storage_root=%s", settings.storage_root)

    yield

    logger.info("File Storage Service shutting down.")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="OutSystems File Storage Service",
        description=(
            "On-premise large-file upload and storage service.\n\n"
            "Supports chunked uploads from OutSystems with full integrity checking."
        ),
        version="1.0.0",
        lifespan=lifespan,
        openapi_version="3.0.3",

    )

    # CORS — restrict origins in production to your OutSystems domain
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],   # TODO: tighten to specific OutSystems origins
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routers
    app.include_router(health_router)
    app.include_router(upload_router)
    app.include_router(files_router)

    return app


app = create_app()

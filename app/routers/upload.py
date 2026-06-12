"""
routers/upload.py
-----------------
Route handlers for the chunked upload flow:

  POST /upload/start       — begin a new upload session
  POST /upload/chunk       — receive a single chunk
  GET  /upload/status/{id} — query progress
  POST /upload/finalize    — assemble and save final file

Handlers are intentionally thin: validate input → delegate to
UploadService → serialise response.
"""

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.schemas import (
    ChunkUploadResponse,
    FinalizeUploadRequest,
    FinalizeUploadResponse,
    StartUploadRequest,
    StartUploadResponse,
    UploadStatusResponse,
)
from app.services.upload_service import UploadService

router = APIRouter(prefix="/upload", tags=["Upload"])
logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Start Upload
# ──────────────────────────────────────────────

@router.post(
    "/start",
    response_model=StartUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Start a new chunked upload session",
)
def start_upload(
    body: StartUploadRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> StartUploadResponse:
    """
    Initialise a new upload session.

    Returns an `upload_id` (UUID) that must be included in every
    subsequent chunk and finalize request.
    """
    service = UploadService(db, settings)
    upload_id = service.start_upload(
        filename=body.filename,
        total_chunks=body.total_chunks,
    )
    return StartUploadResponse(upload_id=upload_id)


# ──────────────────────────────────────────────
# Upload Chunk
# ──────────────────────────────────────────────

@router.post(
    "/chunk",
    response_model=ChunkUploadResponse,
    summary="Upload a single chunk",
)
async def upload_chunk(
    upload_id: str = Form(..., description="Session UUID returned by /upload/start"),
    chunk_number: int = Form(..., ge=1, description="1-based chunk index"),
    chunk_file: UploadFile = File(..., description="Binary chunk data"),
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> ChunkUploadResponse:
    """
    Upload one chunk of the file.

    - `chunk_number` must be between 1 and `total_chunks` (inclusive).
    - Duplicate chunk numbers are accepted and overwrite the previous data
      (allows safe retry on network error).
    - The chunk size limit is configured via `MAX_CHUNK_SIZE_MB` in .env.
    """
    # Enforce chunk size limit
    data = await chunk_file.read()
    max_bytes = settings.max_chunk_size_bytes
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Chunk exceeds maximum size of {settings.max_chunk_size_mb} MB.",
        )

    service = UploadService(db, settings)
    try:
        service.save_chunk(upload_id, chunk_number, data)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except OSError as exc:
        logger.exception("Disk error saving chunk upload_id=%s chunk=%d", upload_id, chunk_number)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to save chunk to disk.",
        )

    return ChunkUploadResponse(
        status="received",
        chunk_number=chunk_number,
        upload_id=upload_id,
    )


# ──────────────────────────────────────────────
# Upload Status
# ──────────────────────────────────────────────

@router.get(
    "/status/{upload_id}",
    response_model=UploadStatusResponse,
    summary="Query upload progress",
)
def get_upload_status(
    upload_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> UploadStatusResponse:
    """Return current progress for a running or completed upload session."""
    service = UploadService(db, settings)
    try:
        session = service.get_status(upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    pct = (
        round(session.uploaded_chunks / session.total_chunks * 100, 1)
        if session.total_chunks > 0
        else 0.0
    )

    return UploadStatusResponse(
        upload_id=session.upload_id,
        uploaded_chunks=session.uploaded_chunks,
        total_chunks=session.total_chunks,
        percentage=pct,
        status=session.status.value,
    )


# ──────────────────────────────────────────────
# Finalize
# ──────────────────────────────────────────────

@router.post(
    "/finalize",
    response_model=FinalizeUploadResponse,
    summary="Assemble chunks and finalise upload",
)
def finalize_upload(
    body: FinalizeUploadRequest,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> FinalizeUploadResponse:
    """
    Verify all chunks are present, reassemble the original file,
    calculate SHA-256, persist metadata, and remove temp files.

    This is a synchronous operation — for very large files (10+ GB)
    a background task / Celery worker may be preferred in a future phase.
    """
    service = UploadService(db, settings)
    try:
        metadata = service.finalize_upload(body.upload_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except (OSError, IOError) as exc:
        logger.exception("Finalize failed for upload_id=%s", body.upload_id)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="File assembly failed.",
        )

    return FinalizeUploadResponse(
        status="completed",
        file_path=metadata.file_path,
        sha256=metadata.sha256_hash,
        file_size=metadata.file_size,
        original_filename=metadata.original_filename,
    )

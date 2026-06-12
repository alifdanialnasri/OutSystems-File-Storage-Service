"""
schemas/__init__.py
-------------------
Pydantic v2 models used for:
  - request body validation
  - response serialisation
  - OpenAPI documentation generation

Kept intentionally separate from ORM models (clean architecture).
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, ConfigDict


# ──────────────────────────────────────────────
# Upload Session
# ──────────────────────────────────────────────

class StartUploadRequest(BaseModel):
    """Body for POST /upload/start"""
    filename: str = Field(..., examples=["video.mp4"], max_length=512)
    total_chunks: int = Field(..., ge=1, examples=[250])


class StartUploadResponse(BaseModel):
    """Response for POST /upload/start"""
    upload_id: str


class UploadStatusResponse(BaseModel):
    """Response for GET /upload/status/{upload_id}"""
    upload_id: str
    uploaded_chunks: int
    total_chunks: int
    percentage: float
    status: str


# ──────────────────────────────────────────────
# Chunk Upload
# ──────────────────────────────────────────────

class ChunkUploadResponse(BaseModel):
    """Response for POST /upload/chunk"""
    status: str
    chunk_number: int
    upload_id: str


# ──────────────────────────────────────────────
# Finalize
# ──────────────────────────────────────────────

class FinalizeUploadRequest(BaseModel):
    """Body for POST /upload/finalize"""
    upload_id: str


class FinalizeUploadResponse(BaseModel):
    """Response for POST /upload/finalize"""
    status: str
    file_path: str
    sha256: str
    file_size: int
    original_filename: str


# ──────────────────────────────────────────────
# File Metadata
# ──────────────────────────────────────────────

class FileMetadataResponse(BaseModel):
    """Response for GET /files and GET /files/{file_id}"""
    model_config = ConfigDict(from_attributes=True)  # enables ORM → schema conversion

    id: int
    upload_id: str
    original_filename: str
    stored_filename: str
    file_path: str
    file_size: int
    sha256_hash: str
    upload_date: datetime
    upload_status: str
    total_chunks: int


# ──────────────────────────────────────────────
# Health
# ──────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str = "ok"


# ──────────────────────────────────────────────
# Error
# ──────────────────────────────────────────────

class ErrorResponse(BaseModel):
    detail: str

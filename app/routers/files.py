"""
routers/files.py
----------------
Route handlers for file access:

  GET /files              — list all uploaded files
  GET /files/{file_id}    — metadata for a single file
  GET /files/download/{file_id} — stream file to client
"""

import logging
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.schemas import FileMetadataResponse
from app.services.file_service import FileService

router = APIRouter(prefix="/files", tags=["Files"])
logger = logging.getLogger(__name__)


@router.get(
    "",
    response_model=list[FileMetadataResponse],
    summary="List all uploaded files",
)
def list_files(db: Session = Depends(get_db)) -> list[FileMetadataResponse]:
    """Return metadata for every successfully uploaded file, newest first."""
    service = FileService(db)
    return service.list_files()


@router.get(
    "/download/{file_id}",
    summary="Stream download a file",
    response_class=StreamingResponse,
)
def download_file(file_id: int, db: Session = Depends(get_db)) -> StreamingResponse:
    """
    Stream the file directly to the client.

    - Uses chunked transfer encoding — the entire file is never loaded into memory.
    - Supports files larger than 10 GB.
    - Sets `Content-Disposition` so browsers trigger a Save-As dialogue.
    """
    service = FileService(db)
    try:
        metadata, byte_stream = service.stream_file(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

    # RFC 5987 encoding for non-ASCII filenames
    encoded_name = quote(metadata.original_filename)
    content_disposition = (
        f"attachment; filename=\"{metadata.original_filename}\"; "
        f"filename*=UTF-8''{encoded_name}"
    )

    return StreamingResponse(
        byte_stream,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": content_disposition,
            "Content-Length": str(metadata.file_size),
            "X-SHA256": metadata.sha256_hash,
        },
    )


@router.get(
    "/{file_id}",
    response_model=FileMetadataResponse,
    summary="Get file metadata",
)
def get_file_metadata(file_id: int, db: Session = Depends(get_db)) -> FileMetadataResponse:
    """Return stored metadata for a single file."""
    service = FileService(db)
    try:
        return service.get_file(file_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))

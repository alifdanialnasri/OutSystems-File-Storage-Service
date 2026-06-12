"""
services/file_service.py
------------------------
Business logic for file retrieval (downloads and metadata queries).

Streaming is used throughout — files larger than 10 GB are fully supported.
"""

import logging
from pathlib import Path
from typing import Generator

from sqlalchemy.orm import Session

from app.models import FileMetadata

logger = logging.getLogger(__name__)

_STREAM_BUFFER = 8 * 1024 * 1024  # 8 MB read buffer


class FileService:
    """Handles download and metadata lookup operations."""

    def __init__(self, db: Session):
        self.db = db

    # ──────────────────────────────────────────────
    # Metadata
    # ──────────────────────────────────────────────

    def list_files(self) -> list[FileMetadata]:
        """Return all successfully uploaded file records."""
        return self.db.query(FileMetadata).order_by(FileMetadata.upload_date.desc()).all()

    def get_file(self, file_id: int) -> FileMetadata:
        """
        Fetch a single file record by primary key.

        Raises:
            ValueError: File not found.
        """
        record = self.db.get(FileMetadata, file_id)
        if not record:
            raise ValueError(f"File with id={file_id} not found.")
        return record

    # ──────────────────────────────────────────────
    # Download
    # ──────────────────────────────────────────────

    def stream_file(self, file_id: int) -> tuple[FileMetadata, Generator]:
        """
        Return (metadata, byte_generator) for a file.

        The generator yields fixed-size chunks so the entire file
        is never loaded into memory.

        Usage in route:
            meta, gen = file_service.stream_file(file_id)
            return StreamingResponse(gen, media_type="application/octet-stream")
        """
        record = self.get_file(file_id)
        file_path = Path(record.file_path)

        if not file_path.exists():
            logger.error("File missing on disk | file_id=%d | path=%s", file_id, file_path)
            raise FileNotFoundError(f"File not found on disk: {file_path}")

        logger.info("Download started | file_id=%d | file=%s", file_id, record.original_filename)

        def _byte_generator() -> Generator[bytes, None, None]:
            with open(file_path, "rb") as f:
                while buf := f.read(_STREAM_BUFFER):
                    yield buf

        return record, _byte_generator()

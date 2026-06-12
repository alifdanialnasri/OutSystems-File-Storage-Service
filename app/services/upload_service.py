"""
services/upload_service.py
--------------------------
All upload-related business logic lives here.

Route handlers are intentionally thin — they delegate everything
to this service and return the result.

Responsibilities:
  - Create / query upload sessions
  - Persist incoming chunks
  - Assemble chunks into the final file
  - Generate checksums
  - Write FileMetadata records
  - Clean up temp files

Future phases can extend this with:
  - Resume support (skip already-received chunks)
  - Virus scanning before finalising
  - Compression during assembly
"""

import logging
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.config import Settings
from app.models import FileMetadata, UploadSession, UploadStatus
from app.utils.file_utils import (
    build_final_file_path,
    calculate_sha256,
    ensure_directory,
    get_chunk_path,
    get_upload_temp_dir,
)

logger = logging.getLogger(__name__)

# Buffer size for chunk assembly — 8 MB keeps memory usage flat regardless of file size
_ASSEMBLY_BUFFER = 8 * 1024 * 1024


class UploadService:
    """
    Encapsulates all upload business logic.
    Instantiated per-request via FastAPI's dependency injection.
    """

    def __init__(self, db: Session, settings: Settings):
        self.db = db
        self.settings = settings

    # ──────────────────────────────────────────────
    # Start session
    # ──────────────────────────────────────────────

    def start_upload(self, filename: str, total_chunks: int) -> str:
        """
        Create a new upload session and prepare the temp directory.

        Returns:
            upload_id  (UUID v4 string)
        """
        upload_id = str(uuid.uuid4())
        logger.info("Upload started | upload_id=%s | file=%s | chunks=%d",
                    upload_id, filename, total_chunks)

        # Persist session record
        session = UploadSession(
            upload_id=upload_id,
            total_chunks=total_chunks,
            uploaded_chunks=0,
            status=UploadStatus.IN_PROGRESS,
        )
        self.db.add(session)
        self.db.commit()

        # Create the temp chunk directory
        temp_dir = get_upload_temp_dir(self.settings.temp_chunk_dir, upload_id)
        ensure_directory(temp_dir)

        # Store the original filename in a sidecar file so finalize can read it
        # without an extra DB query (avoids passing it through every chunk call)
        (temp_dir / ".original_filename").write_text(filename, encoding="utf-8")

        return upload_id

    # ──────────────────────────────────────────────
    # Receive chunk
    # ──────────────────────────────────────────────

    def save_chunk(self, upload_id: str, chunk_number: int, data: bytes) -> None:
        """
        Persist a single chunk and increment the session counter.

        Args:
            upload_id:    Session identifier.
            chunk_number: 1-based chunk index.
            data:         Raw bytes of the chunk.

        Raises:
            ValueError:  Unknown upload_id or session already completed.
            IOError:     Disk write failure.
        """
        session = self._get_active_session(upload_id)

        chunk_path = get_chunk_path(
            self.settings.temp_chunk_dir, upload_id, chunk_number
        )

        if chunk_path.exists():
            logger.warning("Duplicate chunk | upload_id=%s | chunk=%d", upload_id, chunk_number)
            # Overwrite is safe — idempotent behaviour enables retry from OutSystems
            # without corrupting the upload.

        # Write chunk atomically via a temp file to avoid partial writes
        tmp_path = chunk_path.with_suffix(".tmp")
        try:
            tmp_path.write_bytes(data)
            tmp_path.replace(chunk_path)
        except OSError as exc:
            logger.error("Chunk write failed | upload_id=%s | chunk=%d | error=%s",
                         upload_id, chunk_number, exc)
            raise

        session.uploaded_chunks += 1
        self.db.commit()

        logger.info("Chunk received | upload_id=%s | chunk=%d | size=%d bytes",
                    upload_id, chunk_number, len(data))

    # ──────────────────────────────────────────────
    # Status
    # ──────────────────────────────────────────────

    def get_status(self, upload_id: str) -> UploadSession:
        """Fetch session; raises ValueError if not found."""
        session = self.db.get(UploadSession, upload_id)
        if not session:
            raise ValueError(f"Unknown upload_id: {upload_id}")
        return session

    # ──────────────────────────────────────────────
    # Finalize
    # ──────────────────────────────────────────────

    def finalize_upload(self, upload_id: str) -> FileMetadata:
        """
        Assemble all chunks into the final file, generate SHA-256,
        store metadata, and clean up temp files.

        Returns:
            FileMetadata ORM record.

        Raises:
            ValueError:  Missing chunks or unknown session.
            IOError:     Assembly or cleanup failure.
        """
        session = self._get_active_session(upload_id)

        logger.info("Finalize started | upload_id=%s | total_chunks=%d",
                    upload_id, session.total_chunks)

        # Read original filename from sidecar
        temp_dir = get_upload_temp_dir(self.settings.temp_chunk_dir, upload_id)
        original_filename = (temp_dir / ".original_filename").read_text(encoding="utf-8").strip()

        # 1. Verify all chunks are present
        missing = self._find_missing_chunks(upload_id, session.total_chunks)
        if missing:
            raise ValueError(f"Missing chunks for upload {upload_id}: {missing}")

        # 2. Determine final path
        final_path = build_final_file_path(
            self.settings.final_storage_dir, original_filename, upload_id
        )

        # 3. Assemble chunks → final file (streaming, no full-file in memory)
        file_size = self._assemble_chunks(upload_id, session.total_chunks, final_path)

        # 4. Calculate SHA-256 (streaming)
        sha256 = calculate_sha256(final_path)
        logger.info("Finalize complete | upload_id=%s | sha256=%s | size=%d",
                    upload_id, sha256, file_size)

        # 5. Persist FileMetadata
        metadata = FileMetadata(
            upload_id=upload_id,
            original_filename=original_filename,
            stored_filename=final_path.name,
            file_path=str(final_path),
            file_size=file_size,
            sha256_hash=sha256,
            upload_status=UploadStatus.COMPLETED,
            total_chunks=session.total_chunks,
        )
        self.db.add(metadata)

        # 6. Mark session complete
        session.status = UploadStatus.COMPLETED
        session.completed_at = datetime.now(timezone.utc)
        self.db.commit()
        self.db.refresh(metadata)

        # 7. Delete temp directory
        self._cleanup_temp(upload_id)

        return metadata

    # ──────────────────────────────────────────────
    # Private helpers
    # ──────────────────────────────────────────────

    def _get_active_session(self, upload_id: str) -> UploadSession:
        session = self.db.get(UploadSession, upload_id)
        if not session:
            raise ValueError(f"Unknown upload_id: {upload_id}")
        if session.status == UploadStatus.COMPLETED:
            raise ValueError(f"Upload {upload_id} is already completed.")
        return session

    def _find_missing_chunks(self, upload_id: str, total_chunks: int) -> list[int]:
        """Return a list of 1-based chunk numbers that are absent from disk."""
        missing = []
        for n in range(1, total_chunks + 1):
            path = get_chunk_path(self.settings.temp_chunk_dir, upload_id, n)
            if not path.exists():
                missing.append(n)
        return missing

    def _assemble_chunks(self, upload_id: str, total_chunks: int, output_path: Path) -> int:
        """
        Concatenate chunk files into output_path using buffered I/O.
        Returns total bytes written.
        """
        total_bytes = 0
        with open(output_path, "wb") as out_file:
            for n in range(1, total_chunks + 1):
                chunk_path = get_chunk_path(self.settings.temp_chunk_dir, upload_id, n)
                with open(chunk_path, "rb") as chunk_file:
                    while buf := chunk_file.read(_ASSEMBLY_BUFFER):
                        out_file.write(buf)
                        total_bytes += len(buf)
        return total_bytes

    def _cleanup_temp(self, upload_id: str) -> None:
        temp_dir = get_upload_temp_dir(self.settings.temp_chunk_dir, upload_id)
        try:
            shutil.rmtree(temp_dir)
            logger.info("Temp directory removed | upload_id=%s", upload_id)
        except OSError as exc:
            # Non-fatal: log and continue — metadata is already saved
            logger.warning("Could not remove temp dir | upload_id=%s | error=%s",
                           upload_id, exc)

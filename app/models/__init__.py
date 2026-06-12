"""
models/__init__.py
------------------
ORM models for the file storage service.

Two tables:
  UploadSession  — tracks the lifecycle of a chunked upload
  FileMetadata   — stores final file info after successful assembly

Future phases can add:
  User, Role, FileVersion, AuditLog, ...
"""

from datetime import datetime
from enum import Enum as PyEnum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Enum, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class UploadStatus(str, PyEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


class UploadSession(Base):
    """
    Represents one chunked upload session.
    Created when the client calls POST /upload/start.
    """

    __tablename__ = "upload_sessions"

    upload_id: Mapped[str] = mapped_column(String(36), primary_key=True, index=True)
    status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus), default=UploadStatus.IN_PROGRESS, nullable=False
    )
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_chunks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    # Relationship — one session produces one file record
    file_metadata: Mapped["FileMetadata | None"] = relationship(
        back_populates="session", uselist=False
    )

    def __repr__(self) -> str:
        return f"<UploadSession id={self.upload_id} status={self.status}>"


class FileMetadata(Base):
    """
    Persisted after a successful finalize.
    Stores enough metadata to serve, identify, and audit the file.
    """

    __tablename__ = "file_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upload_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("upload_sessions.upload_id"), unique=True, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    stored_filename: Mapped[str] = mapped_column(String(512), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)  # bytes
    sha256_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    upload_date: Mapped[datetime] = mapped_column(
        DateTime, default=func.now(), nullable=False
    )
    upload_status: Mapped[UploadStatus] = mapped_column(
        Enum(UploadStatus), default=UploadStatus.COMPLETED, nullable=False
    )
    total_chunks: Mapped[int] = mapped_column(Integer, nullable=False)

    # Back-reference to session
    session: Mapped["UploadSession"] = relationship(back_populates="file_metadata")

    def __repr__(self) -> str:
        return f"<FileMetadata id={self.id} file={self.original_filename}>"

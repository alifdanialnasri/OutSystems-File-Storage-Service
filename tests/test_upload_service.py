"""
tests/test_upload_service.py
----------------------------
Unit tests for UploadService.
Uses an in-memory SQLite database and a temp directory — no real disk paths needed.
"""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base
from app.models import UploadSession, UploadStatus
from app.services.upload_service import UploadService


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture
def tmp_dir(tmp_path):
    return tmp_path


@pytest.fixture
def settings(tmp_dir):
    s = MagicMock(spec=Settings)
    s.temp_chunk_dir = tmp_dir / "TempChunks"
    s.final_storage_dir = tmp_dir / "Files"
    s.max_chunk_size_bytes = 50 * 1024 * 1024
    return s


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture
def service(db_session, settings):
    return UploadService(db_session, settings)


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

def test_start_upload_creates_session(service, db_session):
    upload_id = service.start_upload("test.mp4", total_chunks=5)
    assert upload_id is not None
    session = db_session.get(UploadSession, upload_id)
    assert session is not None
    assert session.total_chunks == 5
    assert session.status == UploadStatus.IN_PROGRESS


def test_start_upload_creates_temp_dir(service, settings):
    upload_id = service.start_upload("test.mp4", total_chunks=3)
    temp_dir = settings.temp_chunk_dir / upload_id
    assert temp_dir.exists()


def test_save_chunk_writes_file(service, settings):
    upload_id = service.start_upload("test.mp4", total_chunks=3)
    service.save_chunk(upload_id, chunk_number=1, data=b"hello world")
    chunk_path = settings.temp_chunk_dir / upload_id / "chunk_00001.part"
    assert chunk_path.exists()
    assert chunk_path.read_bytes() == b"hello world"


def test_save_chunk_increments_counter(service, db_session, settings):
    upload_id = service.start_upload("test.mp4", total_chunks=3)
    service.save_chunk(upload_id, 1, b"chunk1")
    service.save_chunk(upload_id, 2, b"chunk2")
    session = db_session.get(UploadSession, upload_id)
    assert session.uploaded_chunks == 2


def test_save_chunk_unknown_upload_raises(service):
    with pytest.raises(ValueError, match="Unknown upload_id"):
        service.save_chunk("nonexistent-id", 1, b"data")


def test_finalize_assembles_file(service, settings, tmp_path):
    # Prepare a 3-chunk upload
    upload_id = service.start_upload("output.bin", total_chunks=3)
    service.save_chunk(upload_id, 1, b"aaa")
    service.save_chunk(upload_id, 2, b"bbb")
    service.save_chunk(upload_id, 3, b"ccc")

    metadata = service.finalize_upload(upload_id)

    final = Path(metadata.file_path)
    assert final.exists()
    assert final.read_bytes() == b"aaabbbccc"
    assert metadata.file_size == 9
    assert len(metadata.sha256_hash) == 64


def test_finalize_missing_chunk_raises(service, settings):
    upload_id = service.start_upload("test.mp4", total_chunks=3)
    service.save_chunk(upload_id, 1, b"chunk1")
    # chunk 2 deliberately missing
    service.save_chunk(upload_id, 3, b"chunk3")

    with pytest.raises(ValueError, match="Missing chunks"):
        service.finalize_upload(upload_id)


def test_finalize_cleans_temp_dir(service, settings):
    upload_id = service.start_upload("clean.mp4", total_chunks=1)
    service.save_chunk(upload_id, 1, b"data")
    service.finalize_upload(upload_id)

    temp_dir = settings.temp_chunk_dir / upload_id
    assert not temp_dir.exists()

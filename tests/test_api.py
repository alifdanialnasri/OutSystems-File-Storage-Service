"""
tests/test_api.py
-----------------
Integration tests using FastAPI's TestClient.
All storage is redirected to a temporary directory — no real paths needed.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import Settings
from app.database import Base, get_db
from app.main import create_app
from app.utils.file_utils import ensure_directory


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

@pytest.fixture(scope="session")
def tmp_storage(tmp_path_factory):
    base = tmp_path_factory.mktemp("storage")
    return base


@pytest.fixture(scope="session")
def test_settings(tmp_storage):
    s = Settings(
        storage_root=str(tmp_storage),
        temp_chunk_path=str(tmp_storage / "TempChunks"),
        final_storage_path=str(tmp_storage / "Files"),
        log_path=str(tmp_storage / "Logs"),
        database_url="sqlite:///:memory:",
        max_chunk_size_mb=50,
    )
    return s


@pytest.fixture(scope="session")
def client(test_settings, tmp_storage):
    engine = create_engine(
        "sqlite:///file::memory:?cache=shared",
        connect_args={"check_same_thread": False, "uri": True},
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)

    def override_db():
        db = TestSession()
        try:
            yield db
        finally:
            db.close()

    def override_settings():
        return test_settings

    app = create_app()
    app.dependency_overrides[get_db] = override_db

    from app.config import get_settings
    app.dependency_overrides[get_settings] = override_settings

    # Ensure directories exist
    ensure_directory(test_settings.temp_chunk_dir)
    ensure_directory(test_settings.final_storage_dir)
    ensure_directory(test_settings.log_dir)

    with TestClient(app) as c:
        yield c


# ──────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_full_upload_flow(client):
    # 1. Start session
    r = client.post("/upload/start", json={"filename": "test.txt", "total_chunks": 3})
    assert r.status_code == 201
    upload_id = r.json()["upload_id"]
    assert upload_id

    # 2. Upload chunks
    for i in range(1, 4):
        r = client.post(
            "/upload/chunk",
            data={"upload_id": upload_id, "chunk_number": str(i)},
            files={"chunk_file": (f"chunk_{i}", f"data_{i}".encode(), "application/octet-stream")},
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "received"

    # 3. Check status
    r = client.get(f"/upload/status/{upload_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["uploaded_chunks"] == 3
    assert body["total_chunks"] == 3
    assert body["percentage"] == 100.0

    # 4. Finalize
    r = client.post("/upload/finalize", json={"upload_id": upload_id})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "completed"
    assert len(body["sha256"]) == 64

    file_id = None

    # 5. List files
    r = client.get("/files")
    assert r.status_code == 200
    files = r.json()
    assert len(files) >= 1
    file_id = files[0]["id"]

    # 6. Get metadata
    r = client.get(f"/files/{file_id}")
    assert r.status_code == 200
    assert r.json()["original_filename"] == "test.txt"

    # 7. Download
    r = client.get(f"/files/download/{file_id}")
    assert r.status_code == 200
    assert b"data_1data_2data_3" == r.content


def test_unknown_upload_status(client):
    r = client.get("/upload/status/does-not-exist")
    assert r.status_code == 404


def test_unknown_file_metadata(client):
    r = client.get("/files/99999")
    assert r.status_code == 404

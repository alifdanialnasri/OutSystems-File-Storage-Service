# OutSystems File Storage Service

A production-ready, on-premise file storage service built with FastAPI.  
Designed to accept large file uploads from OutSystems via chunked transfer and store them on a Windows Server — no cloud required.

---

## Architecture Overview

```
OutSystems (frontend)
        │
        │  HTTP  (chunked multipart)
        ▼
┌───────────────────────────┐
│   FastAPI  (this service) │
│                           │
│  Routers  →  Services     │
│               │      │    │
│          Database  Disk   │
│          (SQLite/  (Files,│
│          SQL Srv)  Chunks)│
└───────────────────────────┘
        │
        ▼
  D:\Storage\
    Files\YYYY\MM\     ← final assembled files
    TempChunks\<id>\   ← in-progress chunks
    Logs\              ← rotating log files
    storage.db         ← SQLite database
```

### Design Principles

- **Business logic in services, not routes** — routes are thin adapters.
- **Streaming everywhere** — SHA-256, assembly, and downloads never load a whole file into memory.
- **Idempotent chunk upload** — retrying a chunk is safe (overwrites previous).
- **Atomic writes** — chunks are written to `.tmp` then renamed to avoid partial files.

---

## Project Structure

```
file-storage-service/
├── app/
│   ├── main.py              # App factory, lifespan startup
│   ├── config.py            # Settings loaded from .env
│   ├── database.py          # SQLAlchemy engine + session factory
│   ├── logging_config.py    # Rotating file + console logging
│   ├── models/
│   │   └── __init__.py      # UploadSession, FileMetadata ORM models
│   ├── schemas/
│   │   └── __init__.py      # Pydantic request/response schemas
│   ├── services/
│   │   ├── upload_service.py # Chunk receipt, assembly, finalization
│   │   └── file_service.py   # Download streaming, metadata queries
│   ├── routers/
│   │   ├── health.py         # GET /health
│   │   ├── upload.py         # POST /upload/start|chunk|finalize, GET /upload/status
│   │   └── files.py          # GET /files, /files/{id}, /files/download/{id}
│   └── utils/
│       └── file_utils.py     # SHA-256, path helpers, directory creation
├── tests/
│   ├── test_upload_service.py
│   └── test_api.py
├── .env                     # Configuration (edit before first run)
├── requirements.txt
└── run.py                   # Development server entry point
```

---

## Quick Start

### 1. Prerequisites

- Python 3.11+
- Windows Server (or Windows 10/11 for development)
- `D:\Storage` directory writable by the service account (or change paths in `.env`)

### 2. Install

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 3. Configure

Edit `.env`:

```env
STORAGE_ROOT=D:\Storage
TEMP_CHUNK_PATH=D:\Storage\TempChunks
FINAL_STORAGE_PATH=D:\Storage\Files
LOG_PATH=D:\Storage\Logs
DATABASE_URL=sqlite:///D:\Storage\storage.db
MAX_CHUNK_SIZE_MB=50
APP_HOST=0.0.0.0
APP_PORT=8000
```

### 4. Run

```powershell
python run.py
```

Or directly with uvicorn:

```powershell
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Visit `http://localhost:8000/docs` for the interactive Swagger UI.

---

## API Reference

### Health Check

```http
GET /health
```
```json
{ "status": "ok" }
```

---

### Start Upload Session

```http
POST /upload/start
Content-Type: application/json

{
  "filename": "video.mp4",
  "total_chunks": 250
}
```
```json
{ "upload_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6" }
```

---

### Upload Chunk

```http
POST /upload/chunk
Content-Type: multipart/form-data

upload_id=3fa85f64-...
chunk_number=1
chunk_file=<binary>
```
```json
{ "status": "received", "chunk_number": 1, "upload_id": "3fa85f64-..." }
```

> **Retry-safe**: re-uploading the same chunk number is accepted and overwrites the previous data.

---

### Get Upload Status

```http
GET /upload/status/3fa85f64-...
```
```json
{
  "upload_id": "3fa85f64-...",
  "uploaded_chunks": 120,
  "total_chunks": 250,
  "percentage": 48.0,
  "status": "in_progress"
}
```

---

### Finalize Upload

```http
POST /upload/finalize
Content-Type: application/json

{ "upload_id": "3fa85f64-..." }
```
```json
{
  "status": "completed",
  "file_path": "D:\\Storage\\Files\\2025\\01\\3fa85f64-..._video.mp4",
  "sha256": "e3b0c44298fc1c149afb...",
  "file_size": 1073741824,
  "original_filename": "video.mp4"
}
```

---

### Download File

```http
GET /files/download/1
```
Returns the file as a binary stream with `Content-Disposition: attachment`.

---

### List All Files

```http
GET /files
```
Returns an array of file metadata objects.

---

### Get File Metadata

```http
GET /files/42
```
Returns metadata for file id=42.

---

## OutSystems Integration Guide

### Recommended Chunk Size

Set `MAX_CHUNK_SIZE_MB=50` and split files into 50 MB chunks on the OutSystems side.  
For a 1 GB file: `total_chunks = ceil(1024 / 50) = 21`.

### OutSystems Upload Flow

1. **Calculate chunks**: `CEIL(FileSize / ChunkSizeBytes)`
2. **Start session**: `POST /upload/start` → store `upload_id`
3. **Loop**: for each chunk, read bytes and `POST /upload/chunk`
4. **Poll** (optional): `GET /upload/status/{upload_id}` to show a progress bar
5. **Finalize**: `POST /upload/finalize` → store `file_path` and `sha256`

---

## Running Tests

```powershell
pip install pytest
pytest tests/ -v
```

---

## Migrating to SQL Server

1. Install the ODBC driver and pyodbc:
   ```powershell
   pip install pyodbc
   ```
2. Update `.env`:
   ```env
   DATABASE_URL=mssql+pyodbc://user:password@server/dbname?driver=ODBC+Driver+17+for+SQL+Server
   ```
3. Restart the service. SQLAlchemy handles the rest — no code changes needed.

---

## Future Phases (not yet implemented)

| Feature | Notes |
|---|---|
| **Resume upload** | Track received chunks in DB; skip on retry |
| **User authentication** | JWT middleware; user_id FK on FileMetadata |
| **File versioning** | Version counter on FileMetadata |
| **Role-based permissions** | Role model; permission check in FileService |
| **Compression** | Compress during assembly (zlib/lz4) |
| **Virus scanning** | ClamAV hook in finalize_upload before saving |
| **SQL Server** | Change DATABASE_URL only |
| **Background finalization** | Celery worker for 10 GB+ files |

---

## Logging

Logs are written to `D:\Storage\Logs\app.log`.  
Files rotate at **10 MB**, keeping **7 backups**.

Key log events:
- `Upload started` — new session created
- `Chunk received` — chunk saved successfully
- `Finalize started / complete` — assembly lifecycle
- `Download started` — file served
- Errors at WARNING/ERROR level with full context

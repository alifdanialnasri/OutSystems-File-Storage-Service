"""
utils/file_utils.py
-------------------
Pure utility functions with no business logic or database access.
All functions stream data to support files larger than 10 GB.
"""

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Read buffer: 8 MB — large enough to minimise syscalls, small enough to stay
# well within RAM even on a loaded server.
_BUFFER_SIZE = 8 * 1024 * 1024


def calculate_sha256(file_path: Path) -> str:
    """
    Stream-calculate the SHA-256 checksum of a file.

    Never loads the entire file into memory — safe for files > 10 GB.

    Args:
        file_path: Absolute path to the file.

    Returns:
        Lowercase hex digest string (64 characters).

    Raises:
        FileNotFoundError: If the file does not exist.
        OSError: On any read error.
    """
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(_BUFFER_SIZE):
            sha256.update(chunk)
    return sha256.hexdigest()


def ensure_directory(path: Path) -> None:
    """
    Create a directory (and all parents) if it does not exist.
    Safe to call even if the directory already exists.
    """
    path.mkdir(parents=True, exist_ok=True)


def get_chunk_path(temp_dir: Path, upload_id: str, chunk_number: int) -> Path:
    """
    Return the canonical path for a single chunk file.

    Example:  .../TempChunks/<upload_id>/chunk_001.part
    Zero-padded to 5 digits to allow correct lexicographic sorting up to 99,999 chunks.
    """
    return temp_dir / upload_id / f"chunk_{chunk_number:05d}.part"


def get_upload_temp_dir(temp_base: Path, upload_id: str) -> Path:
    """Return the temp directory path for a given upload session."""
    return temp_base / upload_id


def build_final_file_path(storage_root: Path, original_filename: str, upload_id: str) -> Path:
    """
    Build a date-partitioned storage path for the assembled file.

    Structure: <storage_root>/YYYY/MM/<upload_id>_<original_filename>

    The upload_id prefix prevents collisions when two uploads share
    the same original filename in the same month.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)
    year_month_dir = storage_root / str(now.year) / f"{now.month:02d}"
    ensure_directory(year_month_dir)

    # Sanitise the filename to remove path traversal characters
    safe_name = Path(original_filename).name
    stored_name = f"{upload_id}_{safe_name}"
    return year_month_dir / stored_name

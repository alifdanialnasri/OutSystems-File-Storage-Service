"""
config.py
---------
Centralised configuration loaded from the .env file.
All paths and tunables are defined here — never hardcoded elsewhere.

Future phases can extend Settings with auth tokens, compression flags, etc.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Storage paths
    storage_root: str = r"D:\Storage"
    temp_chunk_path: str = r"D:\Storage\TempChunks"
    final_storage_path: str = r"D:\Storage\Files"
    log_path: str = r"D:\Storage\Logs"

    # Database
    database_url: str = r"sqlite:///D:\Storage\storage.db"

    # Limits
    max_chunk_size_mb: int = 50

    # Server
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_workers: int = 4

    # Logging
    log_level: str = "INFO"

    # ---------- Derived helpers ----------

    @property
    def temp_chunk_dir(self) -> Path:
        return Path(self.temp_chunk_path)

    @property
    def final_storage_dir(self) -> Path:
        return Path(self.final_storage_path)

    @property
    def log_dir(self) -> Path:
        return Path(self.log_path)

    @property
    def max_chunk_size_bytes(self) -> int:
        return self.max_chunk_size_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    """
    Return a cached Settings singleton.
    Use FastAPI's Depends(get_settings) to inject into routes.
    """
    return Settings()

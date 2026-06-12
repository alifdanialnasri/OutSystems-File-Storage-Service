"""
run.py
------
Convenience script to start the server directly via `python run.py`.
Useful during development and for Windows Service wrappers.

For production, prefer:
    uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
"""

import uvicorn
from app.config import get_settings

if __name__ == "__main__":
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        workers=settings.app_workers,
        reload=False,           # Set True only for local development
        log_level=settings.log_level.lower(),
    )

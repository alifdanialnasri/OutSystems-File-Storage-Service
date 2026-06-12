from app.routers.upload import router as upload_router
from app.routers.files import router as files_router
from app.routers.health import router as health_router

__all__ = ["upload_router", "files_router", "health_router"]

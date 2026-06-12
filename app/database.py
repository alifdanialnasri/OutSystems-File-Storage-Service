"""
database.py
-----------
SQLAlchemy engine, session factory, and Base metadata.

The engine is created from DATABASE_URL in .env.
For SQLite, check_same_thread=False is required because FastAPI
can serve requests from multiple threads.

Migration to SQL Server only requires changing DATABASE_URL in .env
and installing the pyodbc driver — no code changes needed here.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import get_settings

settings = get_settings()

# SQLite needs the connect_args workaround; other drivers don't.
connect_args = (
    {"check_same_thread": False}
    if settings.database_url.startswith("sqlite")
    else {}
)

engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    echo=False,          # Set True to log all SQL (useful for debugging)
    pool_pre_ping=True,  # Reconnect on stale connections (important for SQL Server)
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    """All ORM models inherit from this base."""
    pass


def get_db():
    """
    FastAPI dependency that yields a DB session and guarantees cleanup.

    Usage:
        @router.get("/example")
        def example(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """Called once at startup to create tables if they don't exist."""
    # Import models so SQLAlchemy registers them before create_all()
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

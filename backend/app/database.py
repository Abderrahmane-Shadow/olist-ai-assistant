from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from app.config import get_settings

settings = get_settings()

# SQLAlchemy Engine for PostgreSQL with psycopg 3
engine = create_engine(
    settings.sqlalchemy_database_url,
    pool_pre_ping=True,
    connect_args={"connect_timeout": 2},
    echo=settings.APP_ENV == "development",
)

# Session factory for database operations
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Read-only engine for safe dynamic SQL execution (Phase 4)
readonly_engine = create_engine(
    settings.readonly_database_url,
    pool_pre_ping=True,
    connect_args={
        "connect_timeout": 3,
        "options": "-c default_transaction_read_only=on -c statement_timeout=5000",
    },
    echo=settings.APP_ENV == "development",
)
SessionReadOnly = sessionmaker(autocommit=False, autoflush=False, bind=readonly_engine)

# Declarative base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a SQLAlchemy database session and ensures it closes."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_readonly_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a dedicated read-only database session."""
    db = SessionReadOnly()
    try:
        yield db
    finally:
        db.close()


def check_database_connection() -> dict:
    """Safely check PostgreSQL connectivity without raising unhandled exceptions."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "connected": True,
            "message": "Successfully connected to PostgreSQL database.",
            "database": settings.DB_NAME,
            "host": f"{settings.DB_HOST}:{settings.DB_PORT}",
        }
    except Exception as exc:
        return {
            "connected": False,
            "message": f"PostgreSQL database not reachable: {str(exc)}",
            "database": settings.DB_NAME,
            "host": f"{settings.DB_HOST}:{settings.DB_PORT}",
        }

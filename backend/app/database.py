import os
import logging
from typing import Generator
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker, Session
from sqlalchemy.pool import NullPool
from app.config import get_settings

logger = logging.getLogger("olist.database")
settings = get_settings()

# Detect serverless execution environment (Vercel Functions, AWS Lambda)
is_serverless = bool(
    os.environ.get("VERCEL")
    or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    or settings.APP_ENV != "development"
)

# Common connection arguments: generous 15s timeout for cloud/serverless SSL negotiation
base_connect_args = {"connect_timeout": 15}

# Primary Engine: In serverless, NullPool prevents stale/broken socket connections
# across frozen Lambda executions and avoids exhausting database connection limits.
primary_engine_kwargs = {
    "echo": settings.APP_ENV == "development",
    "connect_args": base_connect_args,
}
if is_serverless:
    primary_engine_kwargs["poolclass"] = NullPool
else:
    primary_engine_kwargs["pool_pre_ping"] = True
    primary_engine_kwargs["pool_recycle"] = 300

engine = create_engine(
    settings.sqlalchemy_database_url,
    **primary_engine_kwargs,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Read-only Engine: Used for executing dynamic Text-to-SQL analytics.
# Note: Custom "-c" startup options are avoided in connect_args because PgBouncer/Supavisor
# connection poolers in transaction mode reject custom startup parameters.
# Read-only transaction enforcement is handled safely per connection.
readonly_engine_kwargs = {
    "echo": settings.APP_ENV == "development",
    "connect_args": base_connect_args,
}
if is_serverless:
    readonly_engine_kwargs["poolclass"] = NullPool
else:
    readonly_engine_kwargs["pool_pre_ping"] = True
    readonly_engine_kwargs["pool_recycle"] = 300

readonly_engine = create_engine(
    settings.readonly_database_url,
    **readonly_engine_kwargs,
)
SessionReadOnly = sessionmaker(autocommit=False, autoflush=False, bind=readonly_engine)

Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a SQLAlchemy session and ensuring rollback on error."""
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_readonly_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a dedicated read-only database session."""
    db = SessionReadOnly()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def check_database_connection() -> dict:
    """Safely check PostgreSQL connectivity without raising unhandled exceptions or leaking secrets."""
    db_host = engine.url.host or settings.effective_db_host
    db_port = engine.url.port or settings.effective_db_port
    db_name = engine.url.database or settings.effective_db_name
    host_display = f"{db_host}:{db_port}" if db_port else str(db_host)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {
            "connected": True,
            "message": "Successfully connected to PostgreSQL database.",
            "database": db_name,
            "host": host_display,
        }
    except Exception as exc:
        err_msg = str(exc)
        # Redact any passwords or internal URLs if present in the exception message
        if "password" in err_msg.lower() or "@" in err_msg:
            err_msg = "Authentication failed or remote database is unreachable."
        return {
            "connected": False,
            "message": f"PostgreSQL database not reachable: {err_msg}",
            "database": db_name,
            "host": host_display,
        }


def init_application_tables() -> None:
    """Idempotently ensure required application tables exist in PostgreSQL.
    Safe for both local PostgreSQL and hosted Supabase databases.
    """
    ddl = """
    CREATE EXTENSION IF NOT EXISTS "pgcrypto";

    DO $$
    BEGIN
        IF NOT EXISTS (SELECT 1 FROM information_schema.schemata WHERE schema_name = 'auth') THEN
            CREATE SCHEMA auth;
            CREATE TABLE auth.users (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                email VARCHAR(255) UNIQUE NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
        END IF;
    END $$;

    CREATE TABLE IF NOT EXISTS public.profiles (
        id UUID PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        display_name VARCHAR(255),
        role VARCHAR(50) NOT NULL DEFAULT 'user',
        daily_question_limit INT NOT NULL DEFAULT 15,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.conversations (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID NOT NULL,
        title VARCHAR(255) NOT NULL DEFAULT 'New Conversation',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.messages (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        conversation_id UUID NOT NULL,
        role VARCHAR(50) NOT NULL,
        content TEXT NOT NULL,
        metadata JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

    CREATE TABLE IF NOT EXISTS public.user_daily_usage (
        user_id UUID NOT NULL,
        usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
        question_count INT NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, usage_date)
    );
    """
    try:
        with engine.begin() as conn:
            conn.execute(text(ddl))
        logger.info("Application management tables verified successfully.")
    except Exception as exc:
        logger.warning("Could not auto-verify application management tables: %s", exc)

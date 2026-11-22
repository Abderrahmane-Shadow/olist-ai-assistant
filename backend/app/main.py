import logging
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, OperationalError, DatabaseError
from app.config import get_settings
from app.database import check_database_connection, init_application_tables
from app.routers.chat import router as chat_router
from app.routers.conversations import router as conversations_router

logger = logging.getLogger("olist.main")
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan context for safe startup initialization."""
    # Attempt idempotent table verification on startup without failing if DB is offline
    try:
        init_application_tables()
    except Exception as exc:
        logger.warning("Startup table verification skipped or failed: %s", exc)
    yield


app = FastAPI(
    title="Olist AI Assistant API",
    description="Backend API service for Olist E-Commerce Analytics Assistant",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
    lifespan=lifespan,
)


@app.exception_handler(OperationalError)
@app.exception_handler(DatabaseError)
async def database_operational_exception_handler(request: Request, exc: Exception):
    """Catch unhandled database connectivity exceptions and return safe HTTP 503."""
    logger.error("Database connection failure on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=503,
        content={
            "detail": "The analytical database is currently unreachable. Please check database connectivity.",
            "error_type": "DatabaseConnectionError",
        },
    )


@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_generic_exception_handler(request: Request, exc: SQLAlchemyError):
    """Catch unhandled SQLAlchemy execution errors and return safe HTTP 500."""
    logger.error("SQLAlchemy query error on %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "A database error occurred while executing the query.",
            "error_type": "DatabaseExecutionError",
        },
    )

# Configure CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routers
app.include_router(chat_router, prefix="/api", tags=["Chat"])
app.include_router(conversations_router)



@app.get("/", tags=["Root"])
@app.get("/api", tags=["Root"])
def read_root():
    """Root endpoint welcoming clients and directing to API documentation."""
    return {
        "service": "Olist AI Assistant Backend",
        "status": "online",
        "docs_url": "/api/docs",
        "environment": settings.APP_ENV,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/health", tags=["Health"])
@app.get("/api/health", tags=["Health"])
def health_check():
    """Health check endpoint reporting API and database connectivity status."""
    db_status = check_database_connection()
    is_healthy = db_status.get("connected", False)

    return {
        "status": "healthy" if is_healthy else "degraded",
        "service": "olist-ai-assistant-api",
        "environment": settings.APP_ENV,
        "version": "0.1.0",
        "database": db_status,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


if __name__ == "__main__":
    import os
    import uvicorn

    server_port = int(os.environ.get("PORT", settings.APP_PORT))
    uvicorn.run(
        "app.main:app",
        host=settings.APP_HOST,
        port=server_port,
        reload=(settings.APP_ENV == "development"),
    )

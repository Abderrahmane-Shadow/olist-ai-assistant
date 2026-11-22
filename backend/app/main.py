from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import get_settings
from app.database import check_database_connection
from app.routers.chat import router as chat_router
from app.routers.conversations import router as conversations_router

settings = get_settings()

app = FastAPI(
    title="Olist AI Assistant API",
    description="Backend API service for Olist E-Commerce Analytics Assistant",
    version="0.1.0",
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
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

    return {
        "status": "healthy",
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

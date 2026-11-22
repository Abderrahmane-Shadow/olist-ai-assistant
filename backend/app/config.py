from functools import lru_cache
from pathlib import Path
from typing import List
from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Base directory for backend
BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file."""

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Application settings
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # CORS settings (comma-separated string or list)
    CORS_ORIGINS: str = "http://localhost:3000"

    # PostgreSQL Database settings
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "olist_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_SCHEMA: str = "public"

    # Dedicated PostgreSQL read-only credentials for safe dynamic SQL
    DB_READONLY_USER: str = "olist_readonly"
    DB_READONLY_PASSWORD: str = "olist_readonly_2026"

    # Direct database URL overrides (optional, auto-normalized to postgresql+psycopg://)
    DATABASE_URL: str | None = None
    DATABASE_RO_URL: str | None = None

    # Google Gemini API configuration
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_REQUEST_TIMEOUT: int = 10000

    # Supabase Authentication & Multi-User Configuration (Phase 6)
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_JWT_SECRET: str | None = "olist_super_secret_jwt_2026_dev_key_secure_32b"
    SUPABASE_JWT_PUBLIC_KEY: str | None = None
    SUPABASE_JWT_ALGORITHMS: str = "HS256,RS256,ES256"
    REQUIRE_AUTH: bool = True
    # Concurrency and Quota Settings (Local Deployment: Unlimited daily questions, generous local concurrency)
    MAX_DAILY_QUESTIONS_PER_USER: int = 999999
    MAX_CONCURRENT_REQUESTS_PER_USER: int = 5

    @computed_field
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS_ORIGINS string into a list of trimmed origins."""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return ["http://localhost:3000"]

    @computed_field
    @property
    def sqlalchemy_database_url(self) -> str:
        """Construct PostgreSQL SQLAlchemy database URL using psycopg driver."""
        url = self.DATABASE_URL
        if url:
            if url.startswith("postgres://"):
                url = "postgresql+psycopg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://"):]
            # Safely encode literal '@' or special characters in password if unencoded
            if url.count("@") > 1:
                prefix, rest = url.split("://", 1)
                auth_part, host_part = rest.rsplit("@", 1)
                if ":" in auth_part:
                    user_part, pw_part = auth_part.split(":", 1)
                    from urllib.parse import quote_plus, unquote
                    encoded_pw = quote_plus(unquote(pw_part))
                    url = f"{prefix}://{user_part}:{encoded_pw}@{host_part}"
            return url
        return (
            f"postgresql+psycopg://{self.DB_USER}:{self.DB_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )

    @computed_field
    @property
    def readonly_database_url(self) -> str:
        """Construct read-only database URL for safe dynamic SQL execution."""
        url = self.DATABASE_RO_URL
        if url:
            if url.startswith("postgres://"):
                url = "postgresql+psycopg://" + url[len("postgres://"):]
            elif url.startswith("postgresql://"):
                url = "postgresql+psycopg://" + url[len("postgresql://"):]
            # Safely encode literal '@' or special characters in password if unencoded
            if url.count("@") > 1:
                prefix, rest = url.split("://", 1)
                auth_part, host_part = rest.rsplit("@", 1)
                if ":" in auth_part:
                    user_part, pw_part = auth_part.split(":", 1)
                    from urllib.parse import quote_plus, unquote
                    encoded_pw = quote_plus(unquote(pw_part))
                    url = f"{prefix}://{user_part}:{encoded_pw}@{host_part}"
            return url
        return (
            f"postgresql+psycopg://{self.DB_READONLY_USER}:{self.DB_READONLY_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()

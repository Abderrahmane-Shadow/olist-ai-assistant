import os
from functools import lru_cache
from pathlib import Path
from typing import List
from urllib.parse import parse_qsl, quote_plus, unquote, urlencode, urlsplit, urlunsplit
from pydantic import computed_field, model_validator
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
    APP_ENV: str | None = None
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000

    # Vercel platform environment variables
    VERCEL: str | None = None
    VERCEL_ENV: str | None = None

    # CORS settings (comma-separated string or list)
    CORS_ORIGINS: str = "http://localhost:3000"

    # PostgreSQL Database settings (standard / local development)
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432
    DB_NAME: str = "olist_db"
    DB_USER: str = "postgres"
    DB_PASSWORD: str = "postgres"
    DB_SCHEMA: str = "public"

    # Discrete Vercel / Cloud PostgreSQL environment variables
    POSTGRES_HOST: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DATABASE: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None

    # Dedicated PostgreSQL read-only credentials for safe dynamic SQL
    DB_READONLY_USER: str = "olist_readonly"
    DB_READONLY_PASSWORD: str = "olist_readonly_2026"

    # Direct database URL overrides (auto-normalized to postgresql+psycopg://)
    DATABASE_URL: str | None = None
    DATABASE_URL_UNPOOLED: str | None = None
    DATABASE_RO_URL: str | None = None
    POSTGRES_URL: str | None = None
    POSTGRES_URL_NON_POOLING: str | None = None
    POSTGRES_PRISMA_URL: str | None = None

    # Google Gemini API configuration
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_FALLBACK_MODEL: str = "gemini-3.5-flash-lite"
    GEMINI_REQUEST_TIMEOUT: int = 10000

    # Supabase Authentication & Multi-User Configuration
    SUPABASE_URL: str | None = None
    SUPABASE_ANON_KEY: str | None = None
    SUPABASE_SERVICE_ROLE_KEY: str | None = None
    SUPABASE_JWT_SECRET: str | None = "olist_super_secret_jwt_2026_dev_key_secure_32b"
    SUPABASE_JWT_PUBLIC_KEY: str | None = None
    SUPABASE_JWT_ALGORITHMS: str = "HS256,RS256,ES256"
    REQUIRE_AUTH: bool = True
    # Concurrency and Quota Settings
    MAX_DAILY_QUESTIONS_PER_USER: int = 999999
    MAX_CONCURRENT_REQUESTS_PER_USER: int = 5

    @model_validator(mode="after")
    def resolve_environment(self) -> "Settings":
        """Accurately determine runtime environment (Vercel production/preview vs local dev)."""
        if self.VERCEL_ENV:
            self.APP_ENV = self.VERCEL_ENV
        elif self.VERCEL:
            self.APP_ENV = self.APP_ENV if (self.APP_ENV and self.APP_ENV != "development") else "production"
        elif not self.APP_ENV:
            self.APP_ENV = "development"
        return self

    @property
    def effective_db_host(self) -> str:
        return self.POSTGRES_HOST or self.DB_HOST

    @property
    def effective_db_port(self) -> int:
        return self.POSTGRES_PORT or self.DB_PORT

    @property
    def effective_db_name(self) -> str:
        return self.POSTGRES_DATABASE or self.DB_NAME

    @property
    def effective_db_user(self) -> str:
        return self.POSTGRES_USER or self.DB_USER

    @property
    def effective_db_password(self) -> str:
        return self.POSTGRES_PASSWORD or self.DB_PASSWORD

    @computed_field
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse comma-separated CORS_ORIGINS string into a list of trimmed origins."""
        if isinstance(self.CORS_ORIGINS, str):
            return [origin.strip() for origin in self.CORS_ORIGINS.split(",") if origin.strip()]
        return ["http://localhost:3000"]

    def _normalize_pg_url(self, raw_url: str) -> str:
        """Normalize PostgreSQL connection string to postgresql+psycopg:// with safe SSL handling and query filtering."""
        url = raw_url.strip()
        if url.startswith("postgres://"):
            url = "postgresql+psycopg://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]

        parsed = urlsplit(url)
        scheme = parsed.scheme
        netloc = parsed.netloc

        # Safely handle literal '@' or special characters in user password
        if netloc.count("@") > 1:
            auth_part, host_part = netloc.rsplit("@", 1)
            if ":" in auth_part:
                user_part, pw_part = auth_part.split(":", 1)
                netloc = f"{user_part}:{quote_plus(unquote(pw_part))}@{host_part}"

        # Filter out parameters that psycopg v3 rejects (e.g., pgbouncer, schema)
        drop_params = {"pgbouncer", "schema"}
        q_pairs = parse_qsl(parsed.query, keep_blank_values=True)
        filtered_query = [(k, v) for k, v in q_pairs if k.lower() not in drop_params]

        # Ensure sslmode=require for remote cloud databases if not already present
        hostname = parsed.hostname or ""
        is_local = hostname.lower() in ("localhost", "127.0.0.1", "db") or not hostname
        has_ssl = any(k.lower() == "sslmode" for k, _ in filtered_query)
        if not is_local and not has_ssl:
            filtered_query.append(("sslmode", "require"))

        new_query = urlencode(filtered_query)
        return urlunsplit((scheme, netloc, parsed.path, new_query, parsed.fragment))

    @computed_field
    @property
    def sqlalchemy_database_url(self) -> str:
        """Construct PostgreSQL SQLAlchemy database URL using psycopg driver.
        Prioritizes non-pooling connection URLs for serverless execution.
        """
        # Check cloud/Vercel Postgres URL overrides first
        raw_url = (
            self.POSTGRES_URL_NON_POOLING
            or self.DATABASE_URL_UNPOOLED
            or self.POSTGRES_URL
            or self.POSTGRES_PRISMA_URL
        )
        if raw_url and raw_url.strip():
            return self._normalize_pg_url(raw_url)

        # Check discrete POSTGRES_HOST if configured for cloud/Vercel
        if self.POSTGRES_HOST and self.POSTGRES_HOST not in ("localhost", "127.0.0.1"):
            user = quote_plus(self.effective_db_user) if self.effective_db_user else ""
            password = quote_plus(self.effective_db_password) if self.effective_db_password else ""
            auth = f"{user}:{password}@" if (user or password) else ""
            return f"postgresql+psycopg://{auth}{self.POSTGRES_HOST}:{self.effective_db_port}/{self.effective_db_name}?sslmode=require"

        # Check general DATABASE_URL (e.g. from local .env)
        if self.DATABASE_URL and self.DATABASE_URL.strip():
            return self._normalize_pg_url(self.DATABASE_URL)

        # Construct from discrete environment variables
        user = quote_plus(self.effective_db_user) if self.effective_db_user else ""
        password = quote_plus(self.effective_db_password) if self.effective_db_password else ""
        auth = f"{user}:{password}@" if (user or password) else ""
        base_url = (
            f"postgresql+psycopg://{auth}"
            f"{self.effective_db_host}:{self.effective_db_port}/{self.effective_db_name}"
        )
        if self.effective_db_host not in ("localhost", "127.0.0.1", "db"):
            base_url += "?sslmode=require"
        return base_url

    @computed_field
    @property
    def readonly_database_url(self) -> str:
        """Construct read-only database URL for safe dynamic SQL execution."""
        # In cloud environments where a separate read-only URL is not configured,
        # fall back to the primary cloud database URL.
        if (
            self.POSTGRES_URL_NON_POOLING
            or self.DATABASE_URL_UNPOOLED
            or self.POSTGRES_URL
            or self.POSTGRES_PRISMA_URL
            or (self.POSTGRES_HOST and self.POSTGRES_HOST not in ("localhost", "127.0.0.1"))
        ):
            return self.sqlalchemy_database_url

        raw_url = self.DATABASE_RO_URL
        if raw_url and raw_url.strip():
            return self._normalize_pg_url(raw_url)

        # Fallback to local read-only credentials for local development
        return (
            f"postgresql+psycopg://{self.DB_READONLY_USER}:{self.DB_READONLY_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings instance."""
    return Settings()

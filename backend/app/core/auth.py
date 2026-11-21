import asyncio
import logging
import threading
from datetime import date, datetime, timezone
from typing import Optional, Tuple, Dict
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database import get_db

logger = logging.getLogger("olist.auth")

# Bearer token extractor
security = HTTPBearer(auto_error=False)

# In-memory concurrent request tracker per user UUID
_active_user_requests: Dict[str, int] = {}
_lock = threading.Lock()


class AuthenticatedUser(BaseModel):
    """Represent an authenticated Supabase user in FastAPI backend."""
    id: str = Field(..., description="User unique UUID from auth.users")
    email: str
    display_name: Optional[str] = None
    role: str = Field(default="user", description="'user' or 'admin'")
    daily_question_limit: int = 15


def create_test_token(user_id: str, email: str, role: str = "user", secret: Optional[str] = None, expires_in_seconds: int = 3600) -> str:
    """Helper utility for generating cryptographically signed test tokens."""
    settings = get_settings()
    jwt_secret = secret or settings.SUPABASE_JWT_SECRET or "olist_super_secret_jwt_2026_dev_key_secure_32b"
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "email": email,
        "role": "authenticated",
        "app_metadata": {"role": role},
        "user_metadata": {"display_name": email.split("@")[0]},
        "iat": int(now.timestamp()),
        "exp": int(now.timestamp()) + expires_in_seconds,
        "iss": settings.SUPABASE_URL or "supabase-demo",
        "aud": "authenticated",
    }
    return jwt.encode(payload, jwt_secret, algorithm="HS256")


def verify_supabase_jwt(token: str) -> dict:
    """Verify Supabase JWT token signature and claims.
    Rejects unsigned tokens, unsupported algorithms, expired, or forged tokens.
    Supports both symmetric HS256 and asymmetric RS256/ES256 keys.
    """
    if not token or not isinstance(token, str) or not token.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token is empty or missing.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()

    # 1. Inspect unverified JWT header to enforce algorithm security
    try:
        header = jwt.get_unverified_header(token)
    except Exception as header_err:
        logger.warning("Rejected unparseable JWT header: %s", header_err)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed JWT header: {header_err}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg")
    if not alg or alg.lower() == "none":
        logger.warning("Rejected unsigned JWT token ('none' algorithm attempted)")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unsigned JWT tokens ('none' algorithm) are strictly prohibited.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    allowed_algs = [a.strip() for a in settings.SUPABASE_JWT_ALGORITHMS.split(",") if a.strip()]
    if alg not in allowed_algs:
        logger.warning("Rejected token with disallowed algorithm: %s", alg)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Unsupported signing algorithm '{alg}'. Allowed algorithms: {allowed_algs}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 2. Select cryptographic key according to algorithm
    if alg in ("RS256", "ES256"):
        key = settings.SUPABASE_JWT_PUBLIC_KEY
        if not key:
            logger.error("Received asymmetric JWT (%s) but SUPABASE_JWT_PUBLIC_KEY is not configured.", alg)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Asymmetric token ({alg}) cannot be verified: SUPABASE_JWT_PUBLIC_KEY is not configured.",
            )
    else:
        key = settings.SUPABASE_JWT_SECRET or "olist_super_secret_jwt_2026_dev_key_secure_32b"

    # 3. Cryptographically decode and verify signature & claims
    try:
        payload = jwt.decode(
            token,
            key,
            algorithms=[alg],
            options={"verify_signature": True, "verify_exp": True},
            audience=["authenticated", "supabase", "olist-ai-assistant"],
        )
    except jwt.ExpiredSignatureError:
        logger.warning("Rejected expired JWT token")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidSignatureError:
        logger.warning("Rejected JWT with invalid cryptographic signature")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token signature. Signature verification failed.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidAudienceError as aud_err:
        logger.warning("Rejected JWT with invalid audience: %s", aud_err)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token audience. Token must have audience 'authenticated'.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError as exc:
        logger.warning("Rejected invalid JWT token: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 4. Enforce required claims & Issuer validation
    sub = payload.get("sub")
    if not sub or not str(sub).strip():
        logger.warning("Rejected JWT missing 'sub' claim")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="JWT token is missing a valid subject ('sub') claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Validate issuer when SUPABASE_URL is configured
    if settings.SUPABASE_URL:
        expected_base = settings.SUPABASE_URL.rstrip("/")
        token_iss = str(payload.get("iss", "")).rstrip("/")
        valid_issuers = [expected_base, f"{expected_base}/auth/v1"]
        if not token_iss or token_iss not in valid_issuers:
            logger.warning("Rejected JWT invalid issuer: '%s'. Expected: %s", token_iss, valid_issuers)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token issuer: '{token_iss}'. Token was not issued by the configured Supabase project.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    return payload


def get_or_create_profile(user_id: str, email: str, display_name: Optional[str], role: str, db: Session) -> AuthenticatedUser:
    """Ensure user profile exists in database and fetch role & quota limit."""
    sql_select = text("SELECT id, email, display_name, role, daily_question_limit FROM public.profiles WHERE id = :id")
    row = db.execute(sql_select, {"id": user_id}).mappings().first()

    if row:
        if role and row["role"] != role:
            db.execute(text("UPDATE public.profiles SET role = :role WHERE id = :id"), {"role": role, "id": user_id})
            db.commit()
            return AuthenticatedUser(
                id=str(row["id"]),
                email=row["email"],
                display_name=row["display_name"],
                role=role,
                daily_question_limit=int(row["daily_question_limit"]),
            )
        return AuthenticatedUser(
            id=str(row["id"]),
            email=row["email"],
            display_name=row["display_name"],
            role=row["role"],
            daily_question_limit=int(row["daily_question_limit"]),
        )

    # Ensure user exists in auth.users if auth schema is present
    try:
        db.execute(
            text("INSERT INTO auth.users (id, email) VALUES (:id, :email) ON CONFLICT (id) DO NOTHING;"),
            {"id": user_id, "email": email},
        )
    except Exception as auth_err:
        logger.debug("Could not insert into auth.users (may be on hosted Supabase without direct auth writes): %s", auth_err)

    # Insert new profile
    clean_display = display_name or email.split("@")[0]
    sql_insert = text("""
        INSERT INTO public.profiles (id, email, display_name, role, daily_question_limit)
        VALUES (:id, :email, :display_name, :role, :daily_limit)
        ON CONFLICT (id) DO UPDATE SET email = EXCLUDED.email
        RETURNING id, email, display_name, role, daily_question_limit
    """)
    settings = get_settings()
    inserted = db.execute(sql_insert, {
        "id": user_id,
        "email": email,
        "display_name": clean_display,
        "role": role if role in ("user", "admin") else "user",
        "daily_limit": settings.MAX_DAILY_QUESTIONS_PER_USER,
    }).mappings().first()
    db.commit()

    return AuthenticatedUser(
        id=str(inserted["id"]),
        email=inserted["email"],
        display_name=inserted["display_name"],
        role=inserted["role"],
        daily_question_limit=int(inserted["daily_question_limit"]),
    )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db),
) -> AuthenticatedUser:
    """FastAPI dependency: extract and authenticate the current user from Bearer JWT."""
    settings = get_settings()

    if not credentials or not credentials.credentials:
        # If authentication is strictly required
        if settings.REQUIRE_AUTH:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated. Bearer token in Authorization header is required.",
                headers={"WWW-Authenticate": "Bearer"},
            )
        # Default anonymous test user when REQUIRE_AUTH is explicitly disabled
        return get_or_create_profile(
            user_id="00000000-0000-0000-0000-000000000001",
            email="demo@olist-assistant.internal",
            display_name="Demo User",
            role="admin",
            db=db,
        )

    token = credentials.credentials.strip()
    payload = verify_supabase_jwt(token)

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing subject identifier (sub claim).",
            headers={"WWW-Authenticate": "Bearer"},
        )

    email = payload.get("email", f"{user_id}@user.supabase.internal")
    app_meta = payload.get("app_metadata", {})
    user_meta = payload.get("user_metadata", {})
    role = app_meta.get("role", "user")
    display_name = user_meta.get("display_name") or user_meta.get("full_name") or email.split("@")[0]

    return get_or_create_profile(
        user_id=user_id,
        email=email,
        display_name=display_name,
        role=role,
        db=db,
    )


def check_and_increment_daily_usage(user: AuthenticatedUser, db: Session) -> Tuple[int, int]:
    """Check daily question quota for user.
    Admins are exempt from daily question quotas.
    Returns (used_count, limit).
    Raises HTTP 429 if quota exceeded.
    """
    if user.role == "admin":
        return 0, 999999  # Unlimited for admins

    today = date.today()
    sql_check = text("""
        SELECT question_count FROM public.user_daily_usage
        WHERE user_id = :user_id AND usage_date = :today
    """)
    row = db.execute(sql_check, {"user_id": user.id, "today": today}).first()
    current_count = row[0] if row else 0

    limit = user.daily_question_limit
    if current_count >= limit:
        logger.warning("User %s exceeded daily question limit (%d/%d)", user.email, current_count, limit)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Daily question limit reached ({current_count}/{limit} questions used today). Please try again tomorrow or contact an administrator for higher quotas.",
        )

    # Upsert increment
    sql_upsert = text("""
        INSERT INTO public.user_daily_usage (user_id, usage_date, question_count, updated_at)
        VALUES (:user_id, :today, 1, NOW())
        ON CONFLICT (user_id, usage_date)
        DO UPDATE SET question_count = public.user_daily_usage.question_count + 1, updated_at = NOW()
        RETURNING question_count;
    """)
    new_count = db.execute(sql_upsert, {"user_id": user.id, "today": today}).scalar()
    db.commit()

    return new_count or (current_count + 1), limit


class ConcurrentRequestGuard:
    """Process-local context manager enforcing maximum concurrent AI requests per user on a single backend instance.
    
    ARCHITECTURE NOTE:
    This guard uses a process-level threading lock and dictionary (`_active_user_requests`).
    It strictly protects against concurrent request floods on a single FastAPI instance.
    It is NOT a distributed limiter: if horizontally scaled across multiple Render instances or workers,
    requests hitting separate worker processes are tracked independently unless backed by a distributed
    store (e.g., Redis semaphore or PostgreSQL advisory locks).
    """
    def __init__(self, user_id: str, max_concurrent: int = 2):
        self.user_id = user_id
        self.max_concurrent = max_concurrent

    def __enter__(self):
        with _lock:
            active = _active_user_requests.get(self.user_id, 0)
            if active >= self.max_concurrent:
                logger.warning("User %s exceeded max concurrent AI requests (%d active)", self.user_id, active)
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Too many concurrent requests ({active} in progress). Please wait for your previous query to complete before asking another.",
                )
            _active_user_requests[self.user_id] = active + 1

    def __exit__(self, exc_type, exc_val, exc_tb):
        with _lock:
            active = _active_user_requests.get(self.user_id, 1)
            if active <= 1:
                _active_user_requests.pop(self.user_id, None)
            else:
                _active_user_requests[self.user_id] = active - 1

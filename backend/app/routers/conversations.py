import logging
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.auth import AuthenticatedUser, get_current_user
from app.database import get_db
from app.services.conversation_service import ConversationService

logger = logging.getLogger("olist.routers.conversations")

router = APIRouter(prefix="/api", tags=["conversations", "auth"])


class ConversationCreateRequest(BaseModel):
    title: Optional[str] = Field("New Conversation", description="Initial conversation title")


class ConversationUpdateRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=100, description="Updated conversation title")


class UserProfile(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    role: str
    daily_question_limit: int


class DailyUsage(BaseModel):
    used: int
    limit: int
    remaining: int


class UserProfileResponse(BaseModel):
    id: str
    email: str
    display_name: Optional[str]
    role: str
    daily_question_limit: int
    daily_questions_used: int
    daily_questions_remaining: int
    profile: Optional[UserProfile] = None
    daily_usage: Optional[DailyUsage] = None


@router.get("/auth/me", response_model=UserProfileResponse)
def get_user_me(
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Return the authenticated user's profile and remaining question quota."""
    used = 0
    try:
        today = date.today()
        sql_check = text("SELECT question_count FROM public.user_daily_usage WHERE user_id = :user_id AND usage_date = :today")
        row = db.execute(sql_check, {"user_id": user.id, "today": today}).first()
        used = row[0] if row else 0
    except Exception as exc:
        logger.warning("Could not read daily usage from DB, defaulting to 0: %s", exc)

    remaining = 999999
    unlimited_limit = 999999

    prof = UserProfile(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        daily_question_limit=unlimited_limit,
    )
    usage = DailyUsage(
        used=used,
        limit=unlimited_limit,
        remaining=remaining,
    )

    return UserProfileResponse(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        role=user.role,
        daily_question_limit=user.daily_question_limit,
        daily_questions_used=used,
        daily_questions_remaining=remaining,
        profile=prof,
        daily_usage=usage,
    )


@router.get("/conversations")
def get_conversations(
    limit: int = 50,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve all conversations belonging to the authenticated user."""
    return ConversationService.list_conversations(user_id=user.id, db=db, limit=limit)


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
def create_conversation(
    payload: ConversationCreateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Create a new conversation for the authenticated user."""
    return ConversationService.create_conversation(user_id=user.id, title=payload.title or "New Conversation", db=db)


@router.get("/conversations/{conversation_id}")
def get_conversation_detail(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Retrieve conversation details and messages, verifying ownership."""
    return ConversationService.get_conversation_with_messages(
        conversation_id=conversation_id,
        user_id=user.id,
        db=db,
    )


@router.patch("/conversations/{conversation_id}")
def update_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Rename a conversation title, verifying ownership."""
    return ConversationService.update_conversation_title(
        conversation_id=conversation_id,
        user_id=user.id,
        title=payload.title,
        db=db,
    )


class AccountDeleteRequest(BaseModel):
    confirmation: str = Field(..., description="Must be exactly 'DELETE' to confirm irreversible account deletion")


@router.delete("/auth/account", status_code=status.HTTP_200_OK)
@router.delete("/account", status_code=status.HTTP_200_OK)
def delete_user_account(
    payload: AccountDeleteRequest,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Irreversibly delete the authenticated user's account and personal analytical data.
    
    Security guardrails:
    - Verifies authenticated user identity (self-deletion only; cannot delete another user).
    - Requires exact confirmation string 'DELETE'.
    - Cascades cleanly through user messages, conversations, daily usage tracking, and profile.
    - Shared analytical tables (orders, order_items, customers, sellers, etc.) are strictly untouched.
    """
    if not user or user.email == "demo@olist-assistant.internal":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Unauthenticated or demo users cannot delete accounts.",
        )

    if not payload.confirmation or payload.confirmation.strip() != "DELETE":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Confirmation keyword mismatch. You must provide exactly 'DELETE' to confirm account deletion.",
        )

    user_id = str(user.id)
    user_email = user.email
    logger.info("Initiating secure account deletion for user: %s (id: %s)", user_email, user_id)

    try:
        # 1. Delete all messages in conversations belonging to this user
        db.execute(
            text("""
                DELETE FROM public.messages
                WHERE conversation_id IN (
                    SELECT id FROM public.conversations WHERE user_id = :uid
                );
            """),
            {"uid": user_id},
        )

        # 2. Delete all conversations belonging to this user
        db.execute(
            text("DELETE FROM public.conversations WHERE user_id = :uid;"),
            {"uid": user_id},
        )

        # 3. Delete user daily usage records
        db.execute(
            text("DELETE FROM public.user_daily_usage WHERE user_id = :uid;"),
            {"uid": user_id},
        )

        # 4. Delete profile
        db.execute(
            text("DELETE FROM public.profiles WHERE id = :uid;"),
            {"uid": user_id},
        )

        # 5. Optionally remove from auth.users mock/local table if present
        try:
            db.execute(
                text("DELETE FROM auth.users WHERE id = :uid;"),
                {"uid": user_id},
            )
        except Exception as auth_err:
            logger.debug("Local auth.users deletion skipped or unavailable: %s", auth_err)

        db.commit()
        logger.info("Successfully deleted all account data for user: %s (id: %s)", user_email, user_id)
        return {
            "success": True,
            "message": f"Account for {user_email} and all associated conversation history have been permanently deleted.",
        }

    except Exception as exc:
        db.rollback()
        logger.error("Failed to delete account for user %s: %s", user_id, exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete account due to an internal database error.",
        )


@router.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation(
    conversation_id: str,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Delete a conversation and all its messages, verifying ownership."""
    ConversationService.delete_conversation(
        conversation_id=conversation_id,
        user_id=user.id,
        db=db,
    )
    return None

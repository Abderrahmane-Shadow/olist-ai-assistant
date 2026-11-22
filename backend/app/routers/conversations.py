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
    today = date.today()
    sql_check = text("SELECT question_count FROM public.user_daily_usage WHERE user_id = :user_id AND usage_date = :today")
    row = db.execute(sql_check, {"user_id": user.id, "today": today}).first()
    used = row[0] if row else 0

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

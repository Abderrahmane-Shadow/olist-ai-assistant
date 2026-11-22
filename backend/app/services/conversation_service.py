import json
import logging
import uuid
from typing import List, Optional, Dict, Any
from datetime import datetime, timezone
from fastapi import HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger("olist.conversations")


def _normalize_uuid(val: str) -> str:
    """Safely convert any conversation identifier into a valid UUID format."""
    try:
        uuid.UUID(str(val))
        return str(val)
    except (ValueError, TypeError, AttributeError):
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, str(val)))


class ConversationService:
    """Service managing user conversations and message history with strict ownership isolation."""

    @staticmethod
    def list_conversations(user_id: str, db: Session, limit: int = 50) -> List[Dict[str, Any]]:
        """List conversations belonging exclusively to the authenticated user."""
        sql = text("""
            SELECT id, user_id, title, created_at, updated_at
            FROM public.conversations
            WHERE user_id = :user_id
            ORDER BY updated_at DESC
            LIMIT :limit;
        """)
        rows = db.execute(sql, {"user_id": user_id, "limit": limit}).mappings().fetchall()
        return [
            {
                "id": str(r["id"]),
                "user_id": str(r["user_id"]),
                "title": r["title"],
                "created_at": r["created_at"].isoformat() if r["created_at"] else None,
                "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            }
            for r in rows
        ]

    @staticmethod
    def create_conversation(user_id: str, title: str, db: Session) -> Dict[str, Any]:
        """Create a new conversation for the authenticated user."""
        clean_title = (title or "New Conversation").strip()[:100]
        sql = text("""
            INSERT INTO public.conversations (user_id, title)
            VALUES (:user_id, :title)
            RETURNING id, user_id, title, created_at, updated_at;
        """)
        row = db.execute(sql, {"user_id": user_id, "title": clean_title}).mappings().first()
        db.commit()
        return {
            "id": str(row["id"]),
            "user_id": str(row["user_id"]),
            "title": row["title"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else None,
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
        }

    @staticmethod
    def get_conversation_with_messages(conversation_id: str, user_id: str, db: Session) -> Dict[str, Any]:
        """Fetch conversation and all associated messages.
        Enforces strict ownership check: raises 404/403 if conversation belongs to another user.
        """
        conversation_id = _normalize_uuid(conversation_id)
        # 1. Verify conversation exists and belongs to user
        sql_conv = text("""
            SELECT id, user_id, title, created_at, updated_at
            FROM public.conversations
            WHERE id = :id;
        """)
        conv = db.execute(sql_conv, {"id": conversation_id}).mappings().first()
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Conversation not found.",
            )

        if str(conv["user_id"]) != str(user_id):
            logger.warning("Access denied: User %s attempted to read conversation %s owned by %s", user_id, conversation_id, conv["user_id"])
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not own this conversation.",
            )

        # 2. Fetch messages in chronological order
        sql_msg = text("""
            SELECT id, conversation_id, role, content, metadata, created_at
            FROM public.messages
            WHERE conversation_id = :id
            ORDER BY created_at ASC;
        """)
        msg_rows = db.execute(sql_msg, {"id": conversation_id}).mappings().fetchall()
        messages = [
            {
                "id": str(m["id"]),
                "role": m["role"],
                "content": m["content"],
                "metadata": m["metadata"] if isinstance(m["metadata"], dict) else (json.loads(m["metadata"]) if m["metadata"] else None),
                "created_at": m["created_at"].isoformat() if m["created_at"] else None,
            }
            for m in msg_rows
        ]

        return {
            "id": str(conv["id"]),
            "user_id": str(conv["user_id"]),
            "title": conv["title"],
            "created_at": conv["created_at"].isoformat() if conv["created_at"] else None,
            "updated_at": conv["updated_at"].isoformat() if conv["updated_at"] else None,
            "messages": messages,
        }

    @staticmethod
    def update_conversation_title(conversation_id: str, user_id: str, title: str, db: Session) -> Dict[str, Any]:
        """Update conversation title, enforcing ownership."""
        conversation_id = _normalize_uuid(conversation_id)
        clean_title = (title or "New Conversation").strip()[:100]
        # Verify ownership first
        sql_check = text("SELECT user_id FROM public.conversations WHERE id = :id;")
        row = db.execute(sql_check, {"id": conversation_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
        if str(row["user_id"]) != str(user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. You do not own this conversation.")

        sql_update = text("""
            UPDATE public.conversations
            SET title = :title, updated_at = NOW()
            WHERE id = :id AND user_id = :user_id
            RETURNING id, user_id, title, created_at, updated_at;
        """)
        updated = db.execute(sql_update, {"id": conversation_id, "user_id": user_id, "title": clean_title}).mappings().first()
        db.commit()
        return {
            "id": str(updated["id"]),
            "user_id": str(updated["user_id"]),
            "title": updated["title"],
            "created_at": updated["created_at"].isoformat() if updated["created_at"] else None,
            "updated_at": updated["updated_at"].isoformat() if updated["updated_at"] else None,
        }

    @staticmethod
    def delete_conversation(conversation_id: str, user_id: str, db: Session) -> bool:
        """Delete conversation and cascade delete its messages. Enforces ownership."""
        conversation_id = _normalize_uuid(conversation_id)
        sql_check = text("SELECT user_id FROM public.conversations WHERE id = :id;")
        row = db.execute(sql_check, {"id": conversation_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
        if str(row["user_id"]) != str(user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. You do not own this conversation.")

        sql_delete = text("DELETE FROM public.conversations WHERE id = :id AND user_id = :user_id;")
        db.execute(sql_delete, {"id": conversation_id, "user_id": user_id})
        db.commit()
        return True

    @staticmethod
    def save_message(
        conversation_id: str,
        user_id: str,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]],
        db: Session,
    ) -> Dict[str, Any]:
        """Save a message to a conversation. Enforces ownership and updates conversation updated_at."""
        conversation_id = _normalize_uuid(conversation_id)
        # 1. Verify ownership of the target conversation
        sql_check = text("SELECT user_id FROM public.conversations WHERE id = :id;")
        row = db.execute(sql_check, {"id": conversation_id}).mappings().first()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found.")
        if str(row["user_id"]) != str(user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied. You do not own this conversation.")

        # 2. Insert message
        sql_insert = text("""
            INSERT INTO public.messages (conversation_id, role, content, metadata)
            VALUES (:conv_id, :role, :content, :metadata)
            RETURNING id, conversation_id, role, content, metadata, created_at;
        """)
        meta_json = json.dumps(metadata, default=str) if metadata else None
        msg_row = db.execute(sql_insert, {
            "conv_id": conversation_id,
            "role": role,
            "content": content,
            "metadata": meta_json,
        }).mappings().first()

        # 3. Touch updated_at on conversation
        sql_touch = text("UPDATE public.conversations SET updated_at = NOW() WHERE id = :id;")
        db.execute(sql_touch, {"id": conversation_id})
        db.commit()

        return {
            "id": str(msg_row["id"]),
            "conversation_id": str(msg_row["conversation_id"]),
            "role": msg_row["role"],
            "content": msg_row["content"],
            "metadata": metadata,
            "created_at": msg_row["created_at"].isoformat() if msg_row["created_at"] else None,
        }

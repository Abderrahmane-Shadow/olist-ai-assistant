import pytest
import uuid
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.database import SessionLocal
from app.core.auth import get_current_user, AuthenticatedUser, get_or_create_profile

client = TestClient(app)


def test_delete_account_unauthenticated():
    """Verify that unauthenticated / demo requests to delete account are rejected."""
    app.dependency_overrides.pop(get_current_user, None)
    response = client.request("DELETE", "/api/auth/account", json={"confirmation": "DELETE"})
    assert response.status_code in (401, 403)


def test_delete_account_invalid_confirmation():
    """Verify that account deletion requires exact 'DELETE' keyword."""
    fake_user_id = str(uuid.uuid4())
    fake_user = AuthenticatedUser(
        id=fake_user_id,
        email="test_delete_invalid@olist-assistant.test",
        display_name="Test User",
        role="user",
        daily_question_limit=15,
    )
    app.dependency_overrides[get_current_user] = lambda: fake_user

    try:
        # Lowercase 'delete' must fail
        resp = client.request("DELETE", "/api/auth/account", json={"confirmation": "delete"})
        assert resp.status_code == 400
        assert "DELETE" in resp.json()["detail"]

        # Empty confirmation must fail
        resp = client.request("DELETE", "/api/auth/account", json={"confirmation": ""})
        assert resp.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_delete_account_cascade_and_isolation():
    """Verify secure cascading self-deletion:
    - User's profile, conversations, messages, and daily usage are deleted.
    - Other users' data remains completely untouched.
    - Shared analytical tables (orders, order_items, etc.) are untouched.
    """
    db = SessionLocal()
    user_to_delete_id = str(uuid.uuid4())
    user_to_keep_id = str(uuid.uuid4())
    conv_id_1 = str(uuid.uuid4())
    conv_id_2 = str(uuid.uuid4())

    try:
        # Create user 1 (to delete) via get_or_create_profile
        user_1_prof = get_or_create_profile(
            user_id=user_to_delete_id,
            email="user_to_delete@olist-assistant.test",
            display_name="To Delete",
            role="user",
            db=db,
        )
        # Create user 2 (to keep) via get_or_create_profile
        user_2_prof = get_or_create_profile(
            user_id=user_to_keep_id,
            email="user_to_keep@olist-assistant.test",
            display_name="To Keep",
            role="user",
            db=db,
        )

        # Create conversations and messages for both
        db.execute(
            text("""
                INSERT INTO public.conversations (id, user_id, title)
                VALUES (:cid, :uid, 'Conv 1');
            """),
            {"cid": conv_id_1, "uid": user_to_delete_id},
        )
        db.execute(
            text("""
                INSERT INTO public.messages (conversation_id, role, content)
                VALUES (:cid, 'user', 'What is total revenue?');
            """),
            {"cid": conv_id_1},
        )
        db.execute(
            text("""
                INSERT INTO public.conversations (id, user_id, title)
                VALUES (:cid, :uid, 'Conv 2');
            """),
            {"cid": conv_id_2, "uid": user_to_keep_id},
        )
        db.execute(
            text("""
                INSERT INTO public.messages (conversation_id, role, content)
                VALUES (:cid, 'user', 'Average item price?');
            """),
            {"cid": conv_id_2},
        )
        # Daily usage for both
        db.execute(
            text("""
                INSERT INTO public.user_daily_usage (user_id, usage_date, question_count)
                VALUES (:uid, :today, 3)
                ON CONFLICT (user_id, usage_date) DO NOTHING;
            """),
            {"uid": user_to_delete_id, "today": date.today()},
        )
        db.execute(
            text("""
                INSERT INTO public.user_daily_usage (user_id, usage_date, question_count)
                VALUES (:uid, :today, 5)
                ON CONFLICT (user_id, usage_date) DO NOTHING;
            """),
            {"uid": user_to_keep_id, "today": date.today()},
        )
        db.commit()

        # Count total orders in shared database before deletion
        orders_count_before = db.execute(text("SELECT count(*) FROM orders;")).scalar()

        # Authenticate as user 1 and perform self-deletion
        app.dependency_overrides[get_current_user] = lambda: user_1_prof

        resp = client.request("DELETE", "/api/auth/account", json={"confirmation": "DELETE"})
        assert resp.status_code == 200
        assert resp.json()["success"] is True

        # Verify user 1 data is completely gone
        p1 = db.execute(text("SELECT id FROM public.profiles WHERE id = :uid;"), {"uid": user_to_delete_id}).first()
        assert p1 is None
        c1 = db.execute(text("SELECT id FROM public.conversations WHERE user_id = :uid;"), {"uid": user_to_delete_id}).fetchall()
        assert len(c1) == 0
        m1 = db.execute(text("SELECT id FROM public.messages WHERE conversation_id = :cid;"), {"cid": conv_id_1}).fetchall()
        assert len(m1) == 0
        u1 = db.execute(text("SELECT question_count FROM public.user_daily_usage WHERE user_id = :uid;"), {"uid": user_to_delete_id}).fetchall()
        assert len(u1) == 0

        # Verify user 2 data is intact
        p2 = db.execute(text("SELECT id FROM public.profiles WHERE id = :uid;"), {"uid": user_to_keep_id}).first()
        assert p2 is not None
        c2 = db.execute(text("SELECT id FROM public.conversations WHERE user_id = :uid;"), {"uid": user_to_keep_id}).fetchall()
        assert len(c2) == 1
        m2 = db.execute(text("SELECT id FROM public.messages WHERE conversation_id = :cid;"), {"cid": conv_id_2}).fetchall()
        assert len(m2) == 1

        # Verify shared analytical orders table is untouched
        orders_count_after = db.execute(text("SELECT count(*) FROM orders;")).scalar()
        assert orders_count_before == orders_count_after

    finally:
        app.dependency_overrides.pop(get_current_user, None)
        # Cleanup user 2
        try:
            db.execute(text("DELETE FROM public.messages WHERE conversation_id = :cid;"), {"cid": conv_id_2})
            db.execute(text("DELETE FROM public.conversations WHERE user_id = :uid;"), {"uid": user_to_keep_id})
            db.execute(text("DELETE FROM public.user_daily_usage WHERE user_id = :uid;"), {"uid": user_to_keep_id})
            db.execute(text("DELETE FROM public.profiles WHERE id = :uid;"), {"uid": user_to_keep_id})
            db.execute(text("DELETE FROM auth.users WHERE id = :uid;"), {"uid": user_to_keep_id})
            db.commit()
        except Exception:
            db.rollback()
        db.close()

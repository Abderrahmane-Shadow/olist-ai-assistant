import pytest
import uuid
from app.database import SessionLocal
from app.core.auth import get_or_create_profile, AuthenticatedUser
from app.routers.chat import process_chat_message
from app.schemas.chat import ChatRequest, MessageHistoryItem
from app.services.conversation_service import ConversationService


@pytest.fixture(scope="module")
def db_session():
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def account_a(db_session):
    return get_or_create_profile(
        user_id="9f082356-932d-40d1-ac78-7a8f6978bbfa",
        email="elharaabderrahman2@gmail.com",
        display_name="Abderrahman",
        role="user",
        db=db_session,
    )


@pytest.fixture(scope="module")
def account_b(db_session):
    return get_or_create_profile(
        user_id="88888888-8888-8888-8888-888888888888",
        email="harakani2002@gmail.com",
        display_name="Harakani",
        role="user",
        db=db_session,
    )


ACCEPTANCE_QUERIES = [
    "What is the average product price?",
    "What is the total revenue?",
    "Which state has the highest revenue?",
    "What is the average order value?",
    "What is the percentage of late deliveries?",
]


@pytest.mark.parametrize("query", ACCEPTANCE_QUERIES)
def test_account_a_dynamic_text_to_sql_execution(db_session, account_a, query):
    """Verify Account A (elharaabderrahman2@gmail.com, role=user) executes dynamic SQL without fallback."""
    req = ChatRequest(message=query, conversation_id=None, history=[])
    resp = process_chat_message(request=req, db=db_session, user=account_a)
    assert resp is not None
    assert resp.source == "postgresql"
    assert resp.intent in ("dynamic_sql", "average_item_price", "total_revenue", "revenue_by_state", "logistics_delayed_orders")
    assert resp.sql_query is not None
    assert "not yet covered by our safe PostgreSQL analytics registry" not in resp.text


@pytest.mark.parametrize("query", ACCEPTANCE_QUERIES)
def test_account_b_dynamic_text_to_sql_execution(db_session, account_b, query):
    """Verify Account B (harakani2002@gmail.com, role=user) executes dynamic SQL without fallback."""
    req = ChatRequest(message=query, conversation_id=None, history=[])
    resp = process_chat_message(request=req, db=db_session, user=account_b)
    assert resp is not None
    assert resp.source == "postgresql"
    assert resp.intent in ("dynamic_sql", "average_item_price", "total_revenue", "revenue_by_state", "logistics_delayed_orders")
    assert resp.sql_query is not None
    assert "not yet covered by our safe PostgreSQL analytics registry" not in resp.text


def test_history_sanitization_does_not_poison_sql_generation(db_session, account_a):
    """Verify that if recent conversation history contains a previous refusal/fallback message,
    it does NOT cause dynamic Text-to-SQL to refuse the next question.
    """
    poisoned_history = [
        MessageHistoryItem(
            role="user",
            text="Can you predict crypto prices next year?",
        ),
        MessageHistoryItem(
            role="assistant",
            text="This question is not yet covered by our safe PostgreSQL analytics registry or schema explorer.",
        ),
    ]

    req = ChatRequest(
        message="What is the average product price?",
        conversation_id=None,
        history=poisoned_history,
    )
    resp = process_chat_message(request=req, db=db_session, user=account_a)
    assert resp.source == "postgresql"
    assert resp.sql_query is not None
    assert "not yet covered by our safe PostgreSQL analytics registry" not in resp.text


def test_multi_user_conversation_isolation(db_session, account_a, account_b):
    """Verify strict data isolation: Account A cannot access or mutate Account B's conversations."""
    # Account A creates a conversation
    conv_a = ConversationService.create_conversation(
        user_id=account_a.id,
        title="Private Account A Conversation",
        db=db_session,
    )
    conv_a_id = conv_a["id"]

    # Account B attempts to read Account A's conversation
    with pytest.raises(Exception) as excinfo:
        ConversationService.get_conversation_with_messages(
            conversation_id=conv_a_id,
            user_id=account_b.id,
            db=db_session,
        )
    assert "Access denied" in str(excinfo.value) or "403" in str(excinfo.value)

    # Account B attempts to post to Account A's conversation
    req = ChatRequest(
        message="What is total revenue?",
        conversation_id=conv_a_id,
        history=[],
    )
    with pytest.raises(Exception) as excinfo:
        process_chat_message(request=req, db=db_session, user=account_b)
    assert "Access denied" in str(excinfo.value) or "403" in str(excinfo.value)

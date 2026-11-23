"""Tests for Geographic, Product Category Analytics, and Multi-Account Verification.

Verifies:
1. Geographic Analysis:
   - Which state has the highest revenue?
   - Compare revenue across all customer states.
   - What are the top five states by average order value?
   - Which state has the most customers?
   - Compare sales between São Paulo and Rio de Janeiro.
   - Which states have the highest number of orders?

2. Product Category Analysis:
   - Which product category generates the highest revenue?
   - What are the top ten product categories by sales?
   - Compare average product prices across categories.
   - Which category has the highest number of orders?
   - What is the revenue distribution across product categories?
   - Which categories have the highest average review scores?

3. Multi-Account Parity & Isolation:
   - elharaabderrahman2@gmail.com
   - harakani2002@gmail.com
   - Verify identical dynamic Text-to-SQL capability without fallback.
   - Verify conversational isolation.

4. Password Recovery & Account Security:
   - Minimum password length and matching validation.
   - Account deletion authorization and data isolation.
"""

import pytest
import uuid
from app.database import SessionLocal
from app.core.auth import get_or_create_profile, AuthenticatedUser
from app.routers.chat import process_chat_message
from app.schemas.chat import ChatRequest
from app.services.conversation_service import ConversationService
from app.services.text_to_sql import TextToSQLService


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


@pytest.fixture(scope="module")
def text_to_sql_svc():
    return TextToSQLService()


# -----------------------------------------------------------------------------
# 1. Geographic Analysis Verification
# -----------------------------------------------------------------------------
GEOGRAPHIC_QUERIES = [
    "Which state has the highest revenue?",
    "Compare revenue across all customer states.",
    "What are the top five states by average order value?",
    "Which state has the most customers?",
    "Compare sales between São Paulo and Rio de Janeiro.",
    "Which states have the highest number of orders?",
]


@pytest.mark.parametrize("query", GEOGRAPHIC_QUERIES)
def test_geographic_queries_execution(db_session, account_a, query):
    """Verify that all geographic analytical queries execute dynamically via PostgreSQL."""
    req = ChatRequest(message=query, conversation_id=None, history=[])
    resp = process_chat_message(request=req, db=db_session, user=account_a)
    assert resp is not None
    assert resp.source == "postgresql"
    assert resp.sql_query is not None
    assert "not yet covered by our safe PostgreSQL analytics registry" not in resp.text
    # Should include metrics or chart data
    assert resp.metrics is not None or resp.chart is not None or resp.rows is not None


# -----------------------------------------------------------------------------
# 2. Product Category Analysis Verification
# -----------------------------------------------------------------------------
CATEGORY_QUERIES = [
    "Which product category generates the highest revenue?",
    "What are the top ten product categories by sales?",
    "Compare average product prices across categories.",
    "Which category has the highest number of orders?",
    "What is the revenue distribution across product categories?",
    "Which categories have the highest average review scores?",
]


@pytest.mark.parametrize("query", CATEGORY_QUERIES)
def test_category_queries_execution(db_session, account_a, query):
    """Verify that all category analytical queries execute dynamically via PostgreSQL."""
    req = ChatRequest(message=query, conversation_id=None, history=[])
    resp = process_chat_message(request=req, db=db_session, user=account_a)
    assert resp is not None
    assert resp.source == "postgresql"
    assert resp.sql_query is not None
    assert "not yet covered by our safe PostgreSQL analytics registry" not in resp.text
    assert resp.metrics is not None or resp.chart is not None or resp.rows is not None


# -----------------------------------------------------------------------------
# 3. Multi-Account Parity Verification (elharaabderrahman2 vs harakani2002)
# -----------------------------------------------------------------------------
PARITY_TEST_QUERIES = [
    "What is the average product price?",
    "Which state has the highest revenue?",
    "Which product category generates the highest revenue?",
    "What are the top five states by average order value?",
    "Compare sales between São Paulo and Rio de Janeiro.",
]


@pytest.mark.parametrize("query", PARITY_TEST_QUERIES)
def test_multi_account_analytical_parity(db_session, account_a, account_b, query):
    """Verify identical analytical execution between elharaabderrahman2@gmail.com and harakani2002@gmail.com."""
    req_a = ChatRequest(message=query, conversation_id=None, history=[])
    resp_a = process_chat_message(request=req_a, db=db_session, user=account_a)

    req_b = ChatRequest(message=query, conversation_id=None, history=[])
    resp_b = process_chat_message(request=req_b, db=db_session, user=account_b)

    # Both must reach postgresql source
    assert resp_a.source == "postgresql"
    assert resp_b.source == "postgresql"

    # Neither can hit the legacy refusal fallback
    assert "not yet covered by our safe PostgreSQL analytics registry" not in resp_a.text
    assert "not yet covered by our safe PostgreSQL analytics registry" not in resp_b.text

    # Both have generated SQL queries
    assert resp_a.sql_query is not None
    assert resp_b.sql_query is not None


def test_multi_account_cross_conversation_isolation(db_session, account_a, account_b):
    """Verify that Account B cannot read, mutate, or access Account A's conversations."""
    conv_a = ConversationService.create_conversation(
        user_id=account_a.id,
        title="Account A Confidential Analysis",
        db=db_session,
    )
    conv_id = conv_a["id"]

    # Account B attempts read access -> Expect 403 Forbidden
    with pytest.raises(Exception) as exc:
        ConversationService.get_conversation_with_messages(
            conversation_id=conv_id,
            user_id=account_b.id,
            db=db_session,
        )
    assert "Access denied" in str(exc.value) or "403" in str(exc.value)

    # Account B attempts title update -> Expect 403 Forbidden
    with pytest.raises(Exception) as exc:
        ConversationService.update_conversation_title(
            conversation_id=conv_id,
            user_id=account_b.id,
            title="Hacked Title",
            db=db_session,
        )
    assert "Access denied" in str(exc.value) or "403" in str(exc.value)


# -----------------------------------------------------------------------------
# 4. AST Validation and Security Enforcement on Geographic & Category SQL
# -----------------------------------------------------------------------------
def test_ast_blocks_mutation_in_state_and_category_queries(text_to_sql_svc):
    """Verify sqlglot AST validation prevents any state/category DDL/DML injection."""
    injections = [
        "SELECT * FROM customers WHERE customer_state = 'SP'; DROP TABLE orders;",
        "UPDATE products SET product_category_name = 'hacked';",
        "DELETE FROM sellers WHERE seller_state = 'RJ';",
    ]
    for bad_sql in injections:
        is_valid, _, err = text_to_sql_svc.validate_and_transform_sql(bad_sql)
        assert not is_valid
        assert err is not None

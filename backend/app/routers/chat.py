import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session
from app.config import get_settings
from app.core.auth import (
    AuthenticatedUser,
    get_current_user,
    check_and_increment_daily_usage,
    ConcurrentRequestGuard,
    get_or_create_profile,
)
from app.database import get_db
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.analytics import get_analytics_service
from app.services.conversation_service import ConversationService
from app.services.llm import get_llm_service
from app.services.review_service import get_review_service
from app.services.schema_service import get_schema_service
from app.services.text_to_sql import get_text_to_sql_service

logger = logging.getLogger("olist.api.chat")

router = APIRouter()


def _finalize_response(
    response: ChatResponse,
    conv_id: str,
    user_id: str,
    daily_used: int,
    daily_limit: int,
    is_admin: bool,
    db: Session,
) -> ChatResponse:
    """Attach conversation and usage metadata and persist message to database."""
    response.conversation_id = conv_id
    response.daily_usage = {
        "used": daily_used,
        "limit": daily_limit,
        "remaining": max(0, daily_limit - daily_used) if not is_admin else 999999,
    }
    meta = {
        "metrics": [m.model_dump() for m in response.metrics] if response.metrics else None,
        "breakdown": response.breakdown.model_dump() if response.breakdown else None,
        "chart": response.chart.model_dump() if response.chart else None,
        "columns": response.columns,
        "rows": response.rows,
        "review_citations": [c.model_dump() for c in response.review_citations] if response.review_citations else None,
        "sentiment_summary": response.sentiment_summary.model_dump() if response.sentiment_summary else None,
        "sql_query": response.sql_query,
        "intent": response.intent,
        "source": response.source,
    }
    try:
        ConversationService.save_message(
            conversation_id=conv_id,
            user_id=user_id,
            role="assistant",
            content=response.text,
            metadata=meta,
            db=db,
        )
    except Exception as save_err:
        logger.warning("Could not persist assistant response message: %s", save_err)
    return response


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Process user query and return analytical response",
    description="Processes natural language queries against PostgreSQL Olist dataset with Gemini Text-to-SQL, AST security validation, and safe read-only execution.",
)
def process_chat_message(
    request: ChatRequest,
    db: Session = Depends(get_db),
    user: Optional[AuthenticatedUser] = Depends(get_current_user),
) -> ChatResponse:
    request_start = time.perf_counter()
    iso_start = datetime.now(timezone.utc).isoformat()
    user_query = request.message.strip()
    settings = get_settings()

    # Fallback to test/anonymous user for direct unit test invocations
    if user is None or not isinstance(user, AuthenticatedUser):
        user = get_or_create_profile(
            user_id="00000000-0000-0000-0000-000000000001",
            email="developer@olist-assistant.internal",
            display_name="Developer",
            role="admin",
            db=db,
        )

    # 1. Enforce Daily Question Quota
    daily_used, daily_limit = check_and_increment_daily_usage(user, db)

    # 2. Manage Persistent Conversation
    conv_id = request.conversation_id
    if conv_id:
        try:
            uuid.UUID(str(conv_id))
        except (ValueError, TypeError, AttributeError):
            conv_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, str(conv_id)))
            request.conversation_id = conv_id

    if not conv_id:
        title_snippet = user_query[:50] + ("..." if len(user_query) > 50 else "")
        new_conv = ConversationService.create_conversation(user_id=user.id, title=title_snippet, db=db)
        conv_id = new_conv["id"]
        request.conversation_id = conv_id
    else:
        # Check if conversation exists; if not, auto-create it with this ID
        sql_exists = text("SELECT user_id FROM public.conversations WHERE id = :id;")
        existing = db.execute(sql_exists, {"id": conv_id}).mappings().first()
        if not existing:
            title_snippet = user_query[:50] + ("..." if len(user_query) > 50 else "")
            db.execute(
                text("INSERT INTO public.conversations (id, user_id, title) VALUES (:id, :user_id, :title);"),
                {"id": conv_id, "user_id": user.id, "title": title_snippet},
            )
            db.commit()
        elif str(existing["user_id"]) != str(user.id):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied. You do not own this conversation.",
            )

    # Save User message to persistent history
    ConversationService.save_message(
        conversation_id=conv_id,
        user_id=user.id,
        role="user",
        content=user_query,
        metadata=None,
        db=db,
    )

    # Cap history for safety/token limits (last 6 items)
    safe_history = request.history[-6:] if request.history else []

    logger.info(
        "[%s] [REQUEST RECEIVED] User: %s | Query: '%s' | ConvID: %s | History: %d items",
        iso_start,
        user.email,
        user_query,
        conv_id,
        len(safe_history),
    )

    # 3. Guard against excessive concurrent AI requests per user
    guard = ConcurrentRequestGuard(user.id, max_concurrent=settings.MAX_CONCURRENT_REQUESTS_PER_USER)
    guard.__enter__()
    try:
        schema_service = get_schema_service(db)
        text_to_sql_service = get_text_to_sql_service(db)
        analytics_service = get_analytics_service(db)
        llm_service = get_llm_service()

        # Step 1: Language Detection (English / French) with history context for follow-ups
        detected_language = "fr" if schema_service.is_french(user_query) else "en"
        if detected_language == "en" and safe_history:
            words = user_query.strip().split()
            if len(words) <= 6:
                last_user_turns = [h for h in safe_history if h.role == "user"]
                if last_user_turns and schema_service.is_french(last_user_turns[-1].text):
                    detected_language = "fr"
        logger.info(
            "[%s] [LANGUAGE DETECTED] Query: '%s' -> Detected: '%s'",
            datetime.now(timezone.utc).isoformat(),
            user_query,
            detected_language,
        )

        # Step 2: Safe Database Schema Explorer
        # Handles questions about database metadata, table schemas, columns, PKs, relationships
        t_schema = time.perf_counter()
        schema_intent, schema_table = schema_service.classify_intent(user_query)
        if schema_intent:
            schema_response = schema_service.execute_intent(
                schema_intent,
                table_name=schema_table,
                language=detected_language,
            )
            if schema_response:
                schema_elapsed_ms = (time.perf_counter() - t_schema) * 1000
                total_elapsed_ms = (time.perf_counter() - request_start) * 1000
                schema_response.timestamp = datetime.now(timezone.utc).isoformat()
                schema_response.language = detected_language
                schema_response.metadata = {
                    "service": "schema_service",
                    "execution_time_ms": round(total_elapsed_ms, 2),
                }
                logger.info(
                    "[%s] [SCHEMA MATCH] Intent '%s' (table: %s) served in %.2f ms (Total: %.2f ms)",
                    datetime.now(timezone.utc).isoformat(),
                    schema_intent,
                    schema_table,
                    schema_elapsed_ms,
                    total_elapsed_ms,
                )
                return _finalize_response(schema_response, conv_id, user.id, daily_used, daily_limit, user.role == "admin", db)

        # Step 3: Customer Reviews Intelligence (RAG + Sentiment Analysis + Review Citations)
        # Handles complaints, customer feedback, sentiment analysis, delivery/product reviews
        review_service = get_review_service(db)
        if review_service.is_review_query(user_query):
            t_rev = time.perf_counter()
            logger.info(
                "[%s] [REVIEWS INTELLIGENCE] Routing query '%s' to ReviewService...",
                datetime.now(timezone.utc).isoformat(),
                user_query,
            )
            review_response = review_service.answer_query(
                user_query=user_query,
                language=detected_language,
                history=safe_history,
            )
            if review_response:
                total_elapsed_ms = (time.perf_counter() - request_start) * 1000
                review_response.timestamp = datetime.now(timezone.utc).isoformat()
                review_response.language = detected_language
                if review_response.metadata is None:
                    review_response.metadata = {}
                review_response.metadata["total_pipeline_ms"] = round(total_elapsed_ms, 2)
                logger.info(
                    "[%s] [REVIEWS MATCH] Query '%s' served via ReviewService in %.2f ms",
                    datetime.now(timezone.utc).isoformat(),
                    user_query,
                    total_elapsed_ms,
                )
                return _finalize_response(review_response, conv_id, user.id, daily_used, daily_limit, user.role == "admin", db)

        # Step 4: PRIMARY MECHANISM -> Safe Dynamic Text-to-SQL Analytics
        # Translates natural-language questions into safe PostgreSQL queries via Gemini,
        # validates AST with sqlglot, executes read-only, and synthesizes executive insights.
        if text_to_sql_service.is_configured:
            t_t2sql = time.perf_counter()
            logger.info(
                "[%s] [PRIMARY TEXT-TO-SQL] Routing query '%s' to Text-to-SQL engine...",
                datetime.now(timezone.utc).isoformat(),
                user_query,
            )
            dynamic_response = text_to_sql_service.answer_query(
                user_query=user_query,
                language=detected_language,
                history=safe_history,
            )
            t2sql_elapsed_ms = (time.perf_counter() - t_t2sql) * 1000
            if dynamic_response:
                total_elapsed_ms = (time.perf_counter() - request_start) * 1000
                dynamic_response.timestamp = datetime.now(timezone.utc).isoformat()
                if not dynamic_response.language:
                    dynamic_response.language = detected_language
                if dynamic_response.metadata is None:
                    dynamic_response.metadata = {}
                dynamic_response.metadata["total_pipeline_ms"] = round(total_elapsed_ms, 2)
                logger.info(
                    "[%s] [RESPONSE RETURNED] Query '%s' served via primary Text-to-SQL in %.2f ms (source: %s)",
                    datetime.now(timezone.utc).isoformat(),
                    user_query,
                    total_elapsed_ms,
                    dynamic_response.source,
                )
                return _finalize_response(dynamic_response, conv_id, user.id, daily_used, daily_limit, user.role == "admin", db)
            else:
                logger.info(
                    "[%s] [TEXT-TO-SQL PASSED] Engine returned None in %.2f ms. Falling back to analytics registry.",
                    datetime.now(timezone.utc).isoformat(),
                    t2sql_elapsed_ms,
                )
        else:
            logger.info(
                "[%s] [TEXT-TO-SQL SKIPPED] TextToSQLService is unconfigured. Falling back to analytics registry.",
                datetime.now(timezone.utc).isoformat(),
            )

        # Step 4: FALLBACK / OFFLINE MECHANISM -> Predefined Analytics Registry
        # Used when Gemini is unconfigured or dynamic Text-to-SQL could not generate valid SQL
        t_fallback = time.perf_counter()
        local_intent = analytics_service.classify_intent(user_query)
        if not local_intent and llm_service.is_configured:
            llm_intent, _ = llm_service.understand_intent(user_query, safe_history)
            if llm_intent and llm_intent != "unsupported":
                local_intent = llm_intent

        if local_intent and local_intent != "unsupported":
            postgres_response = analytics_service.execute_intent(local_intent)
            if postgres_response:
                if llm_service.is_configured:
                    try:
                        enhanced_text = llm_service.generate_explanation(
                            user_query=user_query,
                            intent=local_intent,
                            postgres_result=postgres_response,
                            language=detected_language,
                            history=safe_history,
                        )
                        postgres_response.text = enhanced_text
                        postgres_response.metadata = {"llm_enhanced": True, "engine": llm_service.model_name}
                    except Exception as llm_err:
                        logger.warning("LLM explanation synthesis skipped: %s", llm_err)
                        postgres_response.metadata = {"llm_enhanced": False, "error": str(llm_err)}
                else:
                    postgres_response.metadata = {"llm_enhanced": False}

                total_elapsed_ms = (time.perf_counter() - request_start) * 1000
                postgres_response.timestamp = datetime.now(timezone.utc).isoformat()
                postgres_response.language = detected_language
                postgres_response.metadata["total_pipeline_ms"] = round(total_elapsed_ms, 2)

                logger.info(
                    "[%s] [RESPONSE RETURNED] Query '%s' served via fallback registry intent '%s' in %.2f ms",
                    datetime.now(timezone.utc).isoformat(),
                    user_query,
                    local_intent,
                    total_elapsed_ms,
                )
                return _finalize_response(postgres_response, conv_id, user.id, daily_used, daily_limit, user.role == "admin", db)

        # Step 5: Handle Truly Unsupported / Out-of-Domain Queries
        total_elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.info(
            "[%s] [RESPONSE RETURNED] Query '%s' unsupported by schema, text-to-sql, and analytics (took %.2f ms). Generating explanation.",
            datetime.now(timezone.utc).isoformat(),
            user_query,
            total_elapsed_ms,
        )

        unsupported_text = llm_service.generate_unsupported_explanation(user_query, language=detected_language)

        unsupported_resp = ChatResponse(
            text=unsupported_text,
            source="unsupported",
            intent=None,
            language=detected_language,
            timestamp=datetime.now(timezone.utc).isoformat(),
            metadata={
                "llm_enhanced": llm_service.is_configured,
                "total_pipeline_ms": round(total_elapsed_ms, 2),
            },
        )
        return _finalize_response(unsupported_resp, conv_id, user.id, daily_used, daily_limit, user.role == "admin", db)

    except HTTPException:
        raise
    except Exception as exc:
        total_elapsed_ms = (time.perf_counter() - request_start) * 1000
        logger.error(
            "[%s] [REQUEST ERROR] Error processing chat query '%s' after %.2f ms: %s",
            datetime.now(timezone.utc).isoformat(),
            user_query,
            total_elapsed_ms,
            exc,
            exc_info=True,
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred while processing the analytics query. Please try again.",
        )
    finally:
        guard.__exit__(None, None, None)

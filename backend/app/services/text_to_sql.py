"""Phase 4: Safe Dynamic SQL Analytics Service for Olist AI Assistant.

Architecture:
User question -> Gemini generates SQL -> SQL validation (sqlglot AST) ->
PostgreSQL read-only execution -> Gemini explains results -> frontend displays answer.

Security Controls:
1. Strictly SELECT queries (no DML, DDL, or administrative commands).
2. AST validation using sqlglot for PostgreSQL dialect.
3. Whitelisted access restricted to approved public Olist tables and defined CTEs.
4. Single SQL statement enforcement (no stacked queries or semicolon chaining).
5. Mandatory LIMIT enforcement (injected or clamped to <= 50).
6. PostgreSQL execution timeout (5000ms) and transaction read-only mode.
7. Dedicated PostgreSQL read-only database role (olist_readonly).
8. Dangerous functions and system catalog access blocked.
9. Credential and internal database error redaction.
10. Explicit HTTP timeouts and resilient model cascade (no indefinite hanging).
"""

import json
import logging
import re
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError
from sqlalchemy import text
from sqlalchemy.orm import Session
import sqlglot
from sqlglot import exp

from app.config import get_settings
from app.database import SessionReadOnly, readonly_engine
from app.schemas.chat import ChatResponse, MetricCard, Breakdown, BreakdownItem, MessageHistoryItem, ChartConfig
from app.services.chart_service import detect_and_build_chart

logger = logging.getLogger("olist.services.text_to_sql")

# Whitelist of approved public Olist tables
APPROVED_TABLES = {
    "customers",
    "geolocation",
    "order_items",
    "order_payments",
    "order_reviews",
    "orders",
    "product_category_name_translation",
    "products",
    "sellers",
}

# Dangerous / administrative PostgreSQL functions that must be blocked
DANGEROUS_FUNCTIONS = {
    "pg_sleep",
    "pg_read_file",
    "pg_read_binary_file",
    "pg_ls_dir",
    "pg_stat_file",
    "dblink",
    "dblink_exec",
    "query_to_xml",
    "query_to_xml_and_xmlschema",
    "pg_terminate_backend",
    "pg_cancel_backend",
    "set_config",
    "current_setting",
}

# Comprehensive database schema prompt given to Gemini for accurate SQL generation
OLIST_SCHEMA_CONTEXT = """
Database: PostgreSQL
Schema: public

TABLES AND COLUMNS:
1. orders (
    order_id VARCHAR PRIMARY KEY,
    customer_id VARCHAR REFERENCES customers(customer_id),
    order_status VARCHAR, -- 'delivered', 'shipped', 'canceled', 'invoiced', 'processing', 'created', 'approved', 'unavailable'
    order_purchase_timestamp TIMESTAMP,
    order_approved_at TIMESTAMP,
    order_delivered_carrier_date TIMESTAMP,
    order_delivered_customer_date TIMESTAMP,
    order_estimated_delivery_date TIMESTAMP
)
2. order_items (
    order_id VARCHAR REFERENCES orders(order_id),
    order_item_id INT, -- sequence number of item within order (1, 2, 3...)
    product_id VARCHAR REFERENCES products(product_id),
    seller_id VARCHAR REFERENCES sellers(seller_id),
    shipping_limit_date TIMESTAMP,
    price DOUBLE PRECISION, -- item price in Brazilian Reais (BRL)
    freight_value DOUBLE PRECISION, -- shipping freight cost in BRL
    PRIMARY KEY (order_id, order_item_id)
)
3. customers (
    customer_id VARCHAR PRIMARY KEY, -- per-order customer token
    customer_unique_id VARCHAR, -- unique person/entity across multiple orders
    customer_zip_code_prefix INT,
    customer_city VARCHAR,
    customer_state VARCHAR -- 2-letter Brazilian state code, e.g. 'SP', 'RJ', 'MG'
)
4. products (
    product_id VARCHAR PRIMARY KEY,
    product_category_name VARCHAR, -- Portuguese category name
    product_name_lenght DOUBLE PRECISION,
    product_description_lenght DOUBLE PRECISION,
    product_photos_qty DOUBLE PRECISION,
    product_weight_g DOUBLE PRECISION, -- weight in grams
    product_length_cm DOUBLE PRECISION,
    product_height_cm DOUBLE PRECISION,
    product_width_cm DOUBLE PRECISION
)
5. sellers (
    seller_id VARCHAR PRIMARY KEY,
    seller_zip_code_prefix INT,
    seller_city VARCHAR,
    seller_state VARCHAR -- 2-letter Brazilian state code
)
6. order_payments (
    order_id VARCHAR REFERENCES orders(order_id),
    payment_sequential INT,
    payment_type VARCHAR, -- 'credit_card', 'boleto', 'voucher', 'debit_card', 'not_defined'
    payment_installments INT,
    payment_value DOUBLE PRECISION,
    PRIMARY KEY (order_id, payment_sequential)
)
7. order_reviews (
    review_id VARCHAR,
    order_id VARCHAR REFERENCES orders(order_id),
    review_score INT, -- rating from 1 (lowest) to 5 (highest)
    review_comment_title VARCHAR,
    review_comment_message TEXT,
    review_creation_date TIMESTAMP,
    review_answer_timestamp TIMESTAMP
)
8. product_category_name_translation (
    product_category_name VARCHAR PRIMARY KEY, -- Portuguese category name
    product_category_name_english VARCHAR -- English translation
)
9. geolocation (
    geolocation_zip_code_prefix INT,
    geolocation_lat DOUBLE PRECISION,
    geolocation_lng DOUBLE PRECISION,
    geolocation_city VARCHAR,
    geolocation_state VARCHAR
)

COMMON BUSINESS METRICS & SQL RECIPES:
- Total Revenue / GMV: SUM(order_items.price)
- Total Freight: SUM(order_items.freight_value)
- Total Orders: COUNT(DISTINCT orders.order_id)
- Unique Customers: COUNT(DISTINCT customers.customer_unique_id)
- Average Order Value (AOV): SUM(order_items.price) / NULLIF(COUNT(DISTINCT orders.order_id), 0)
- Average Item Price: AVG(order_items.price)
- Delivery Delay (days): EXTRACT(epoch FROM (orders.order_delivered_customer_date - orders.order_estimated_delivery_date)) / 86400.0
- Delivery Duration (days): EXTRACT(epoch FROM (orders.order_delivered_customer_date - orders.order_purchase_timestamp)) / 86400.0
- Late Orders Condition: orders.order_delivered_customer_date > orders.order_estimated_delivery_date
- Delay Impact on Reviews: GROUP BY (CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 'Delayed' ELSE 'On-Time' END) with AVG(r.review_score)
- High Revenue / Low Satisfaction Categories: JOIN order_items oi JOIN products p JOIN product_category_name_translation t JOIN order_reviews r; SELECT COALESCE(t.product_category_name_english, p.product_category_name) AS category, ROUND(SUM(oi.price)::numeric, 2) AS revenue, ROUND(AVG(r.review_score)::numeric, 2) AS avg_rating GROUP BY category HAVING SUM(oi.price) > 100000 ORDER BY avg_rating ASC
- Seller Performance & Risk: SELECT oi.seller_id, COUNT(DISTINCT oi.order_id) AS order_cnt, ROUND(AVG(r.review_score)::numeric, 2) AS avg_rating, ROUND(COUNT(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0), 1) AS late_pct FROM order_items oi JOIN orders o ON oi.order_id = o.order_id LEFT JOIN order_reviews r ON o.order_id = r.order_id GROUP BY oi.seller_id HAVING COUNT(DISTINCT oi.order_id) >= 30 ORDER BY avg_rating ASC
- English Categories: JOIN product_category_name_translation ON products.product_category_name = product_category_name_translation.product_category_name
- Correlation: CORR(order_items.price, order_items.freight_value)
- Monthly Aggregation: TO_CHAR(orders.order_purchase_timestamp, 'YYYY-MM')
- Rounding in Postgres: ROUND(CAST(val AS numeric), 2)
"""


class SQLValidationError(Exception):
    """Raised when generated SQL violates safety constraints or AST rules."""
    pass


class TextToSQLService:
    """Safe Dynamic SQL Analytics generator and executor with resilient model cascade and strict timeouts."""

    def __init__(self, db: Optional[Session] = None):
        self.settings = get_settings()
        self.db = db
        self.client: Optional[genai.Client] = None
        self.model_name = self.settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        self.fallback_model = getattr(self.settings, "GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite") or "gemini-3.5-flash-lite"
        self.timeout_ms = getattr(self.settings, "GEMINI_REQUEST_TIMEOUT", 10000) or 10000

        if self.settings.GEMINI_API_KEY and self.settings.GEMINI_API_KEY.strip():
            try:
                # Explicit HTTP timeout (10000ms minimum supported by Google Gemini SDK)
                http_opts = types.HttpOptions(timeout=self.timeout_ms)
                self.client = genai.Client(
                    api_key=self.settings.GEMINI_API_KEY.strip(),
                    http_options=http_opts,
                )
                logger.info(
                    "Initialized Gemini Client for Text-to-SQL (primary: '%s', fallback: '%s', timeout: %d ms)",
                    self.model_name,
                    self.fallback_model,
                    self.timeout_ms,
                )
            except Exception as exc:
                logger.warning("Failed to initialize Gemini Client for Text-to-SQL: %s", exc)
                self.client = None

    @property
    def is_configured(self) -> bool:
        """Whether Gemini LLM client is ready."""
        return bool(self.client and self.settings.GEMINI_API_KEY and self.settings.GEMINI_API_KEY.strip())

    def _call_gemini_with_fallback(
        self,
        prompt: str,
        response_mime_type: Optional[str] = None,
        temperature: float = 0.0,
        max_output_tokens: int = 400,
    ) -> Tuple[Optional[str], Optional[str]]:
        """Call Gemini model with automatic cascade to fallback model if primary fails or times out.
        Returns: (response_text, error_message)
        """
        if not self.is_configured:
            return None, "Gemini client is not configured."

        config_args = {
            "temperature": temperature,
            "max_output_tokens": max_output_tokens,
        }
        if response_mime_type:
            config_args["response_mime_type"] = response_mime_type

        config = types.GenerateContentConfig(**config_args)

        # Try primary model first, followed by valid active Google AI models
        models_to_try = [self.model_name]
        for candidate in [self.fallback_model, "gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"]:
            if candidate and candidate not in models_to_try:
                models_to_try.append(candidate)

        last_error = None
        for m in models_to_try:
            t0 = time.perf_counter()
            try:
                logger.info("Calling Gemini model '%s' (timeout: %d ms)...", m, self.timeout_ms)
                resp = self.client.models.generate_content(
                    model=m,
                    contents=prompt,
                    config=config,
                )
                elapsed_ms = (time.perf_counter() - t0) * 1000
                logger.info("Gemini model '%s' returned response in %.2f ms", m, elapsed_ms)
                if resp.text and resp.text.strip():
                    return resp.text.strip(), None
                last_error = f"Empty response text from model '{m}'"
            except Exception as exc:
                elapsed_ms = (time.perf_counter() - t0) * 1000
                err_msg = str(exc)
                # Clean and sanitize error message
                if "API key not valid" in err_msg:
                    err_msg = "Invalid Gemini API Key."
                elif "DEADLINE_EXCEEDED" in err_msg or "timed out" in err_msg.lower():
                    err_msg = f"Gemini API timeout after {elapsed_ms:.1f}ms on model '{m}'."
                elif "UNAVAILABLE" in err_msg or "503" in err_msg:
                    err_msg = f"Gemini model '{m}' is experiencing high demand (503)."
                    time.sleep(1.0)  # Brief backoff before fallback candidate
                elif "RESOURCE_EXHAUSTED" in err_msg or "429" in err_msg:
                    err_msg = f"Gemini quota limit on '{m}' (429)."
                    time.sleep(1.0)
                else:
                    err_msg = f"Model '{m}' error after {elapsed_ms:.1f}ms: {err_msg[:120]}"

                logger.warning("Gemini call to '%s' failed in %.2f ms: %s", m, elapsed_ms, err_msg)
                last_error = err_msg

        return None, last_error

    # -------------------------------------------------------------
    # 1. SQL Generation & Ambiguity Handling with Gemini
    # -------------------------------------------------------------
    def generate_sql(
        self,
        user_query: str,
        language: str = "en",
        history: Optional[List[MessageHistoryItem]] = None,
    ) -> Dict[str, Any]:
        """Ask Gemini to generate a safe read-only PostgreSQL SELECT query or request clarification.
        Returns a dict:
        {
            "type": "sql" | "clarification" | "unsupported",
            "sql": "SELECT ...",
            "message": "...",
            "error": "..."
        }
        """
        start_stage = time.perf_counter()
        logger.info(
            "[%s] [STAGE 1/4: SQL GENERATION] Started for query: '%s' (lang: %s)",
            datetime.now(timezone.utc).isoformat(),
            user_query,
            language,
        )

        if not self.is_configured:
            logger.warning("[STAGE 1/4: SQL GENERATION] Aborted: Gemini client not configured.")
            return {
                "type": "unsupported",
                "error": "Gemini LLM is not configured for dynamic SQL generation.",
            }

        history_context = ""
        if history:
            turns = []
            for h in history[-6:]:
                turn_str = f"{h.role.capitalize()}: {h.text}"
                if getattr(h, "sql_query", None):
                    turn_str += f"\n  [Executed SQL]: {h.sql_query}"
                turns.append(turn_str)
            history_context = "RECENT CONVERSATION HISTORY:\n" + "\n".join(turns) + "\n\n"

        lang_instruction = (
            "The user question is in French. If clarification is needed, write the clarification message in natural French."
            if language == "fr"
            else "The user question is in English. If clarification is needed, write the clarification message in clear English."
        )

        prompt = (
            "You are an expert PostgreSQL analytics AI for the Brazilian Olist e-commerce database.\n"
            f"{lang_instruction}\n\n"
            f"{history_context}"
            "DATABASE SCHEMA & RECIPES:\n"
            f"{OLIST_SCHEMA_CONTEXT}\n\n"
            "CONVERSATIONAL MEMORY & FOLLOW-UP INSTRUCTIONS:\n"
            "When RECENT CONVERSATION HISTORY is present above, the user's latest question may be an elliptical follow-up that references entities, filters, categories, sellers, or states from previous turns.\n"
            "- Resolve anaphoric references:\n"
            "  * 'their', 'them', 'those', 'these' -> refers to the entities/categories/sellers/states discussed in the previous turn.\n"
            "  * 'its', 'it' -> refers to the primary subject of the previous turn (e.g. state 'SP', category 'health_beauty', seller X).\n"
            "- Inherit context & filters:\n"
            "  * If the previous turn discussed a specific state (e.g. 'São Paulo' / 'SP') or seller or category, and the follow-up asks 'And its delivery performance?' or 'What about delivery time?', analyze delivery performance specifically for that state (e.g. WHERE customers.customer_state = 'SP').\n"
            "  * If the previous turn asked 'What are the top product categories by revenue?' and the follow-up asks 'What about their order counts?', generate a query computing order counts for those categories (e.g. SELECT p.product_category_name, COUNT(DISTINCT oi.order_id) AS order_count FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY order_count DESC LIMIT 10).\n"
            "- Ambiguous follow-ups:\n"
            "  * If a follow-up is too vague, elliptical, or ambiguous to understand what metric is requested (e.g. 'And then?', 'More?', 'What else?'), return:\n"
            "    {\"type\": \"clarification\", \"message\": \"<Polite clarification in the user's language asking which metric or dimension they want>\"}.\n\n"
            "GENERAL INSTRUCTIONS:\n"
            "1. If the user asks an analytical or data question about Olist (orders, products, revenue, customers, sellers, freight, reviews, payments, dates, correlations, distributions):\n"
            "   - Generate a single read-only PostgreSQL SELECT query.\n"
            "   - Return JSON with {\"type\": \"sql\", \"sql\": \"<SELECT query>\"}.\n"
            "   - Always alias calculated columns clearly (e.g. total_revenue, avg_price, order_count).\n"
            "   - Always include a reasonable LIMIT (e.g. LIMIT 10 or LIMIT 20 for rankings/breakdowns; omit or LIMIT 1 for single scalars).\n"
            "   - Use proper JOIN keys as defined in the schema.\n"
            "   - Only query the 9 approved public tables. Never use DDL or DML.\n"
            "2. If the user question is analytical but heavily ambiguous or missing required parameters (e.g. 'compare revenue' without specifying by what dimension, or 'show me orders' without any criteria):\n"
            "   - Return JSON with {\"type\": \"clarification\", \"message\": \"<Polite clarification question suggesting options>\"}.\n"
            "3. If the query is completely outside the domain of Olist e-commerce analytics:\n"
            "   - Return JSON with {\"type\": \"unsupported\", \"message\": \"<Polite explanation of what Olist analytics capabilities are supported>\"}.\n\n"
            f"User Question: \"{user_query}\"\n\n"
            "Return valid JSON matching one of the 3 formats above."
        )

        resp_text, call_err = self._call_gemini_with_fallback(
            prompt=prompt,
            response_mime_type="application/json",
            temperature=0.0,
            max_output_tokens=400,
        )

        elapsed_ms = (time.perf_counter() - start_stage) * 1000

        if not resp_text or call_err:
            logger.error(
                "[%s] [STAGE 1/4: SQL GENERATION] Failed in %.2f ms: %s",
                datetime.now(timezone.utc).isoformat(),
                elapsed_ms,
                call_err,
            )
            return {"type": "unsupported", "error": call_err}

        try:
            data = json.loads(resp_text)
            resp_type = data.get("type", "sql").lower()

            if resp_type == "clarification":
                msg = data.get("message", "Could you please specify more details for this query?")
                logger.info(
                    "[%s] [STAGE 1/4: SQL GENERATION] Completed in %.2f ms -> Clarification required: '%s'",
                    datetime.now(timezone.utc).isoformat(),
                    elapsed_ms,
                    msg,
                )
                return {"type": "clarification", "message": msg}

            if resp_type == "unsupported":
                msg = data.get("message", "This request is outside the scope of Olist e-commerce analytics.")
                logger.info(
                    "[%s] [STAGE 1/4: SQL GENERATION] Completed in %.2f ms -> Unsupported scope: '%s'",
                    datetime.now(timezone.utc).isoformat(),
                    elapsed_ms,
                    msg,
                )
                return {"type": "unsupported", "message": msg}

            sql = data.get("sql", "").strip()
            # Clean markdown code blocks if present
            sql = re.sub(r"^```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
            sql = re.sub(r"\s*```$", "", sql)
            sql = sql.strip().rstrip(";")

            if not sql:
                logger.warning(
                    "[%s] [STAGE 1/4: SQL GENERATION] Completed in %.2f ms but generated SQL was empty",
                    datetime.now(timezone.utc).isoformat(),
                    elapsed_ms,
                )
                return {"type": "unsupported", "error": "Generated SQL statement was empty."}

            logger.info(
                "[%s] [STAGE 1/4: SQL GENERATION] Completed in %.2f ms -> Generated SQL: %s",
                datetime.now(timezone.utc).isoformat(),
                elapsed_ms,
                sql,
            )
            return {"type": "sql", "sql": sql}

        except Exception as exc:
            logger.warning(
                "[%s] [STAGE 1/4: SQL GENERATION] Failed to parse JSON response in %.2f ms: %s (Raw: %s)",
                datetime.now(timezone.utc).isoformat(),
                elapsed_ms,
                exc,
                resp_text[:100],
            )
            return {"type": "unsupported", "error": f"Failed to parse model response: {exc}"}

    # -------------------------------------------------------------
    # 2. Strict AST Validation & Transformation (sqlglot)
    # -------------------------------------------------------------
    def validate_and_transform_sql(self, sql_str: str) -> Tuple[bool, str, str]:
        """Validate SQL query using sqlglot AST and enforce safety guardrails:
        - Only SELECT queries
        - Single statement
        - Approved tables only (plus defined CTE aliases)
        - Public schema only
        - Dangerous functions blocked
        - Mandatory LIMIT (injected or clamped to <= 50)
        
        Returns: (is_valid, transformed_sql, error_message)
        """
        start_stage = time.perf_counter()
        logger.info(
            "[%s] [STAGE 2/4: SQL VALIDATION] Started for input: %s",
            datetime.now(timezone.utc).isoformat(),
            sql_str,
        )

        if not sql_str or not sql_str.strip():
            return False, "", "Empty SQL query."

        clean_sql = sql_str.strip().rstrip(";")

        try:
            statements = sqlglot.parse(clean_sql, read="postgres")
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_stage) * 1000
            logger.warning("[STAGE 2/4: SQL VALIDATION] Parse error in %.2f ms: %s", elapsed_ms, exc)
            return False, "", f"SQL Syntax Error: {str(exc)}"

        if not statements:
            return False, "", "No valid SQL statements found."

        if len(statements) > 1:
            return False, "", "Multiple SQL statements are strictly prohibited."

        expression = statements[0]

        # 1. Must be a SELECT expression (or Union of Selects)
        if not isinstance(expression, (exp.Select, exp.Union)):
            return False, "", f"Only SELECT queries are permitted (got {type(expression).__name__})."

        # 2. Collect CTE aliases (Common Table Expressions defined in WITH clauses)
        cte_aliases = {cte.alias.lower() for cte in expression.find_all(exp.CTE) if cte.alias}
        allowed_tables = APPROVED_TABLES | cte_aliases

        # 3. Check for prohibited AST nodes
        disallowed_nodes = (
            exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Alter,
            exp.Create, exp.Command, exp.Set, exp.Copy, exp.Into
        )
        for node in expression.walk():
            if isinstance(node, disallowed_nodes):
                return False, "", f"Prohibited SQL operation: {type(node).__name__}"

            # Check functions against dangerous functions
            if isinstance(node, exp.Anonymous):
                func_name = node.name.lower()
                if func_name in DANGEROUS_FUNCTIONS or func_name.startswith("pg_"):
                    return False, "", f"Prohibited function access: {func_name}"

            # Check tables against approved tables whitelist and defined CTEs
            if isinstance(node, exp.Table):
                tbl_name = node.name.lower()
                if node.db and node.db.lower() != "public":
                    return False, "", f"Access to schema '{node.db}' is prohibited."
                if tbl_name not in allowed_tables:
                    return False, "", f"Access to table '{tbl_name}' is not allowed."

        # 4. Enforce or clamp LIMIT (max 50 rows)
        limit_node = expression.args.get("limit")
        if not limit_node:
            expression = expression.limit(50)
        else:
            try:
                val_node = limit_node.expression
                val = int(val_node.this if hasattr(val_node, "this") else str(val_node))
                if val > 50 or val <= 0:
                    limit_node.set("expression", exp.Literal.number(50))
            except Exception:
                limit_node.set("expression", exp.Literal.number(50))

        transformed_sql = expression.sql(dialect="postgres")
        elapsed_ms = (time.perf_counter() - start_stage) * 1000
        logger.info(
            "[%s] [STAGE 2/4: SQL VALIDATION] Passed in %.2f ms -> Transformed: %s",
            datetime.now(timezone.utc).isoformat(),
            elapsed_ms,
            transformed_sql,
        )
        return True, transformed_sql, ""

    # -------------------------------------------------------------
    # 3. Safe Database Execution
    # -------------------------------------------------------------
    def execute_sql(self, safe_sql: str) -> Tuple[Optional[List[str]], Optional[List[Dict[str, Any]]], Optional[str]]:
        """Execute validated read-only SQL query in PostgreSQL with strict timeout.
        Returns: (column_names, rows_as_dicts, error_message)
        """
        start_stage = time.perf_counter()
        logger.info(
            "[%s] [STAGE 3/4: POSTGRESQL EXECUTION] Started for SQL: %s",
            datetime.now(timezone.utc).isoformat(),
            safe_sql,
        )
        try:
            with readonly_engine.connect() as conn:
                # Execute in read-only transaction with 5s statement timeout
                conn.execute(text("SET statement_timeout = 5000;"))
                result = conn.execute(text(safe_sql))
                columns = list(result.keys())
                raw_rows = result.fetchall()
                rows = [dict(zip(columns, row)) for row in raw_rows]

                elapsed_ms = (time.perf_counter() - start_stage) * 1000
                logger.info(
                    "[%s] [STAGE 3/4: POSTGRESQL EXECUTION] Completed in %.2f ms (%d rows, %d cols)",
                    datetime.now(timezone.utc).isoformat(),
                    elapsed_ms,
                    len(rows),
                    len(columns),
                )
                return columns, rows, None

        except Exception as exc:
            elapsed_ms = (time.perf_counter() - start_stage) * 1000
            err_msg = str(exc)
            logger.warning(
                "[%s] [STAGE 3/4: POSTGRESQL EXECUTION] Failed in %.2f ms: %s",
                datetime.now(timezone.utc).isoformat(),
                elapsed_ms,
                err_msg,
            )
            # Redact database credentials or internal connection details
            if "password" in err_msg.lower() or "@" in err_msg:
                err_msg = "Database execution error occurred."
            elif "canceling statement due to statement timeout" in err_msg.lower():
                err_msg = "Query execution timed out (maximum 5 seconds allowed)."
            return None, None, err_msg

    # -------------------------------------------------------------
    # 4. Result Explanation & Executive Synthesis
    # -------------------------------------------------------------
    def explain_results(
        self,
        user_query: str,
        sql_query: str,
        columns: List[str],
        rows: List[Dict[str, Any]],
        language: str = "en",
    ) -> str:
        """Synthesize natural-language analytical explanation of verified PostgreSQL results."""
        start_stage = time.perf_counter()
        logger.info(
            "[%s] [STAGE 4/4: EXPLANATION SYNTHESIS] Started for query: '%s' (%d rows)",
            datetime.now(timezone.utc).isoformat(),
            user_query,
            len(rows),
        )
        is_fr = language == "fr"

        # If LLM is available, synthesize executive summary
        if self.is_configured:
            lang_instruction = (
                "Respond entirely in French (français professionnel, concis et soigné)."
                if is_fr
                else "Respond entirely in clear, professional executive English."
            )
            # Format preview of rows for prompt (first 10 rows)
            data_preview = json.dumps(rows[:10], default=str)
            prompt = (
                "You are Olist AI Assistant, an expert analytics AI for Brazilian e-commerce.\n"
                f"{lang_instruction}\n\n"
                "The following SQL query was executed safely against the verified PostgreSQL database:\n"
                f"SQL: {sql_query}\n\n"
                f"Columns: {columns}\n"
                f"Data (up to 10 rows): {data_preview}\n"
                f"Total Rows: {len(rows)}\n\n"
                f"User Question: \"{user_query}\"\n\n"
                "CRITICAL BUSINESS ANALYTICS RULES:\n"
                "1. Exact Numbers & Grounding: State the exact figures directly from the query data. Never alter, round inappropriately, or invent metrics, rankings, or percentages.\n"
                "2. Executive Interpretation: Provide clear business meaning behind the data. Highlight top drivers, outliers, and key operational takeaways.\n"
                "3. Correlation vs. Causation: Strictly distinguish statistical correlation from causal links (e.g. between freight cost and product price, or delivery delays and ratings). Do not claim causation without direct evidence.\n"
                "4. Data Limitations: If the returned data only partially addresses the user's broader 'why' question, honestly state the dataset's scope limitations.\n"
                "5. Actionable Recommendations: Offer realistic, data-backed operational actions where relevant.\n"
                "6. Format: Structure cleanly with GitHub Markdown (headings ###, bold key metrics, bulleted lists)."
            )
            resp_text, call_err = self._call_gemini_with_fallback(
                prompt=prompt,
                temperature=0.2,
                max_output_tokens=350,
            )
            elapsed_ms = (time.perf_counter() - start_stage) * 1000
            if resp_text and resp_text.strip():
                logger.info(
                    "[%s] [STAGE 4/4: EXPLANATION SYNTHESIS] Completed via Gemini in %.2f ms",
                    datetime.now(timezone.utc).isoformat(),
                    elapsed_ms,
                )
                return resp_text.strip()

            logger.warning(
                "[%s] [STAGE 4/4: EXPLANATION SYNTHESIS] Gemini synthesis unavailable in %.2f ms (%s). Using local fallback.",
                datetime.now(timezone.utc).isoformat(),
                elapsed_ms,
                call_err,
            )

        # Local deterministic fallback explanation
        fallback_res = self._format_local_fallback(user_query, columns, rows, language=language)
        elapsed_ms = (time.perf_counter() - start_stage) * 1000
        logger.info(
            "[%s] [STAGE 4/4: EXPLANATION SYNTHESIS] Completed via local template in %.2f ms",
            datetime.now(timezone.utc).isoformat(),
            elapsed_ms,
        )
        return fallback_res

    def _format_local_fallback(
        self,
        user_query: str,
        columns: List[str],
        rows: List[Dict[str, Any]],
        language: str = "en",
    ) -> str:
        """Deterministic markdown formatter when Gemini is offline."""
        is_fr = language == "fr"

        if not rows:
            if is_fr:
                return "La requête exécutée dans PostgreSQL n'a renvoyé aucun résultat correspondant aux critères."
            return "The query executed in PostgreSQL returned no matching records for the specified criteria."

        # If single scalar result (1 row, 1 column)
        if len(rows) == 1 and len(columns) == 1:
            val = rows[0][columns[0]]
            formatted_val = f"{val:,.2f}" if isinstance(val, (int, float)) else str(val)
            if is_fr:
                return (
                    f"### Résultat Analytique (PostgreSQL dynamique) :\n\n"
                    f"D'après les calculs réels de la base de données :\n\n"
                    f"- **{columns[0].replace('_', ' ').title()} :** **{formatted_val}**\n\n"
                    "> Calculé en direct via PostgreSQL avec validation AST et exécution en lecture seule."
                )
            return (
                f"### Analytical Result (PostgreSQL Dynamic SQL):\n\n"
                f"According to real-time database calculations:\n\n"
                f"- **{columns[0].replace('_', ' ').title()}:** **{formatted_val}**\n\n"
                "> Calculated live via PostgreSQL with AST validation and read-only execution."
            )

        # Tabular output
        header = "### Résultat de la requête dynamique (PostgreSQL) :\n" if is_fr else "### Dynamic Query Results (PostgreSQL):\n"
        lines = [header]

        # Build Markdown table
        header_row = "| " + " | ".join(columns) + " |"
        sep_row = "| " + " | ".join(["---"] * len(columns)) + " |"
        lines.append(header_row)
        lines.append(sep_row)

        for r in rows[:15]:
            row_vals = []
            for col in columns:
                v = r.get(col)
                if isinstance(v, float):
                    row_vals.append(f"{v:,.2f}")
                elif isinstance(v, int):
                    row_vals.append(f"{v:,}")
                else:
                    row_vals.append(str(v) if v is not None else "-")
            lines.append("| " + " | ".join(row_vals) + " |")

        if len(rows) > 15:
            lines.append(f"\n*(Affichage limité aux 15 premières lignes sur {len(rows)})*" if is_fr else f"\n*(Showing top 15 of {len(rows)} returned rows)*")

        return "\n".join(lines)

    # -------------------------------------------------------------
    # 5. End-to-End Dynamic SQL Processing
    # -------------------------------------------------------------
    def answer_query(
        self,
        user_query: str,
        language: str = "en",
        history: Optional[List[MessageHistoryItem]] = None,
    ) -> Optional[ChatResponse]:
        """Orchestrate full Text-to-SQL pipeline:
        Generate SQL / Detect Ambiguity -> Validate AST -> Execute in DB -> Explain -> Return ChatResponse.
        Returns ChatResponse or None if query cannot be handled.
        """
        pipeline_start = time.perf_counter()

        # Step 1: Generate SQL or Detect Ambiguity / Scope
        gen_res = self.generate_sql(user_query, language=language, history=history)
        res_type = gen_res.get("type", "sql")

        # Ambiguous query needing user clarification
        if res_type == "clarification":
            return ChatResponse(
                text=gen_res.get("message", "Could you please clarify your question?"),
                source="clarification",
                intent="clarification_needed",
                language=language,
                metadata={"requires_clarification": True},
            )

        # Query outside Olist scope
        if res_type == "unsupported":
            return None

        sql = gen_res.get("sql")
        if not sql:
            return None

        # Step 2: Validate and Transform SQL AST
        is_valid, safe_sql, val_err = self.validate_and_transform_sql(sql)
        if not is_valid or val_err:
            logger.warning("Generated SQL failed safety validation: %s (SQL: %s)", val_err, sql)
            return None

        # Step 3: Execute in PostgreSQL
        columns, rows, exec_err = self.execute_sql(safe_sql)
        if exec_err or columns is None or rows is None:
            logger.warning("Dynamic SQL execution failed: %s (SQL: %s)", exec_err, safe_sql)
            return None

        # Step 4: Synthesize Explanation
        explanation = self.explain_results(
            user_query=user_query,
            sql_query=safe_sql,
            columns=columns,
            rows=rows,
            language=language,
        )

        # Step 5: Construct Metric Cards
        metrics = []
        if len(rows) == 1 and len(columns) <= 3:
            for col in columns:
                val = rows[0][col]
                formatted_val = f"{val:,.2f}" if isinstance(val, float) else (f"{val:,}" if isinstance(val, int) else str(val))
                metrics.append(MetricCard(
                    label=col.replace("_", " ").title(),
                    value=formatted_val,
                    subtext="Dynamic SQL Query",
                ))
        elif len(rows) > 1 and len(columns) >= 2:
            col0 = columns[0]
            col1 = columns[1]
            top_val = rows[0].get(col1)
            formatted_val = f"{top_val:,.2f}" if isinstance(top_val, float) else str(top_val)
            metrics.append(MetricCard(
                label=f"Top {col0.replace('_', ' ').title()}",
                value=str(rows[0].get(col0, "")),
                subtext=f"{col1.replace('_', ' ').title()}: {formatted_val}",
            ))
            metrics.append(MetricCard(
                label="Total Rows Returned",
                value=str(len(rows)),
                subtext="Enforced Limit <= 50",
            ))

        # Pass columns and rows for multi-row results or multi-column scalars
        pass_columns = columns if (len(rows) > 1 or (len(rows) == 1 and len(columns) > 1)) else None
        pass_rows = rows if (len(rows) > 1 or (len(rows) == 1 and len(columns) > 1)) else None

        # Step 6: Automatic Chart Visualization Generation
        chart_config = detect_and_build_chart(
            columns=columns,
            rows=rows,
            user_query=user_query,
            sql_query=safe_sql,
            intent="dynamic_sql",
        )

        total_elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
        logger.info(
            "[%s] [TEXT-TO-SQL PIPELINE] Completed successfully in %.2f ms for query: '%s' (chart: %s)",
            datetime.now(timezone.utc).isoformat(),
            total_elapsed_ms,
            user_query,
            chart_config.type if chart_config else "None",
        )

        return ChatResponse(
            text=explanation,
            source="postgresql",
            intent="dynamic_sql",
            metrics=metrics if metrics else None,
            chart=chart_config,
            columns=pass_columns,
            rows=pass_rows,
            sql_query=safe_sql,
            language=language,
            metadata={
                "dynamic_sql": True,
                "rows_returned": len(rows),
                "columns": columns,
                "role": "olist_readonly",
                "execution_time_ms": round(total_elapsed_ms, 2),
            },
        )


_global_text_to_sql_service: Optional[TextToSQLService] = None


def get_text_to_sql_service(db: Optional[Session] = None) -> TextToSQLService:
    """Dependency helper for TextToSQLService."""
    global _global_text_to_sql_service
    if _global_text_to_sql_service is None:
        _global_text_to_sql_service = TextToSQLService(db)
    return _global_text_to_sql_service

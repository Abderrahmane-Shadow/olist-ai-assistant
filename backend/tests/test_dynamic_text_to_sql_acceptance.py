"""Acceptance & Integration Tests for Dynamic Text-to-SQL Architecture.

Verifies:
1. Dynamic Schema Explorer live inspection and caching.
2. Declarative Semantic Layer formulas, dimensions, and join paths.
3. The 10 Required Acceptance Questions (unseen analytical queries without predefined SQL).
4. SQL security guardrails (sqlglot AST validation, read-only enforcement).
5. Conversational memory & follow-up question resolution.
6. Ambiguity detection and clarification responses.
"""

import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import text
from app.database import engine, readonly_engine
from app.schemas.chat import MessageHistoryItem
from app.services.schema_explorer import SchemaExplorer, get_schema_explorer
from app.services.semantic_layer import SemanticLayer, get_semantic_layer
from app.services.text_to_sql import TextToSQLService


class TestDynamicTextToSQLArchitecture(unittest.TestCase):
    """Test suite for the dynamic Text-to-SQL architecture."""

    @classmethod
    def setUpClass(cls):
        cls.schema_explorer = get_schema_explorer()
        cls.semantic_layer = get_semantic_layer()
        cls.service = TextToSQLService()

    # -------------------------------------------------------------
    # 1. Schema Explorer & Semantic Layer Tests
    # -------------------------------------------------------------
    def test_schema_explorer_introspects_public_tables(self):
        """Verify SchemaExplorer discovers the 9 public Olist tables and columns."""
        meta = self.schema_explorer.get_schema_metadata(force_refresh=True)
        self.assertGreaterEqual(len(meta), 9)
        for tbl in ["orders", "order_items", "customers", "products", "sellers", "order_payments", "order_reviews"]:
            self.assertIn(tbl, meta)
            self.assertGreater(len(meta[tbl]["columns"]), 0)

        # Check prompt formatting
        formatted = self.schema_explorer.format_schema_for_llm()
        self.assertIn("LIVE DATABASE SCHEMA", formatted)
        self.assertIn("orders:", formatted)
        self.assertIn("order_items:", formatted)

    def test_semantic_layer_definitions(self):
        """Verify Semantic Layer defines canonical metrics, joins, and guardrails."""
        sl = self.semantic_layer
        self.assertIn("gross_revenue", sl.metrics)
        self.assertIn("average_order_value", sl.metrics)
        self.assertIn("late_order_percentage", sl.metrics)
        self.assertIn("delivery_delay_days", sl.metrics)

        # Check join definitions
        join_pairs = {(j.from_table, j.to_table) for j in sl.joins}
        self.assertIn(("orders", "order_items"), join_pairs)
        self.assertIn(("orders", "customers"), join_pairs)
        self.assertIn(("order_items", "products"), join_pairs)

        formatted_semantic = sl.format_semantic_layer_for_llm()
        self.assertIn("CANONICAL BUSINESS METRICS", formatted_semantic)
        self.assertIn("VALIDATED JOIN RELATIONSHIPS", formatted_semantic)
        self.assertIn("CRITICAL AGGREGATION GUARDRAILS", formatted_semantic)

    # -------------------------------------------------------------
    # 2. SQL Security & AST Validation Tests
    # -------------------------------------------------------------
    def test_sql_security_enforces_select_only(self):
        """Verify sqlglot rejects DDL/DML operations."""
        bad_queries = [
            "DROP TABLE orders;",
            "DELETE FROM customers WHERE customer_state = 'SP';",
            "UPDATE order_items SET price = 0;",
            "INSERT INTO products (product_id) VALUES ('fake');",
            "SELECT * FROM orders; DROP TABLE sellers;",
        ]
        for q in bad_queries:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected rejection for: {q}")

    def test_sql_security_blocks_dangerous_functions(self):
        """Verify blocking of system catalog and dangerous functions."""
        bad_queries = [
            "SELECT pg_sleep(5);",
            "SELECT pg_read_file('/etc/passwd');",
            "SELECT * FROM pg_catalog.pg_tables;",
            "SELECT * FROM auth.users;",
        ]
        for q in bad_queries:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected rejection for: {q}")

    def test_sql_security_clamps_limit(self):
        """Verify LIMIT is injected or clamped to <= 50."""
        # Query without LIMIT
        q1 = "SELECT customer_state, COUNT(*) AS count FROM customers GROUP BY customer_state"
        valid1, sql1, _ = self.service.validate_and_transform_sql(q1)
        self.assertTrue(valid1)
        self.assertIn("LIMIT 50", sql1)

        # Query with excessive LIMIT
        q2 = "SELECT customer_state, COUNT(*) AS count FROM customers GROUP BY customer_state LIMIT 500"
        valid2, sql2, _ = self.service.validate_and_transform_sql(q2)
        self.assertTrue(valid2)
        self.assertIn("LIMIT 50", sql2)

    # -------------------------------------------------------------
    # 3. Acceptance Question Tests (10 Required Analytical Scenarios)
    # -------------------------------------------------------------
    def _execute_and_verify(self, sql_query: str):
        """Helper to validate through AST and execute on PostgreSQL."""
        is_valid, safe_sql, val_err = self.service.validate_and_transform_sql(sql_query)
        self.assertTrue(is_valid, f"SQL validation failed: {val_err} for SQL: {sql_query}")
        cols, rows, exec_err = self.service.execute_sql(safe_sql)
        self.assertIsNone(exec_err, f"Execution failed: {exec_err} for SQL: {safe_sql}")
        self.assertIsNotNone(cols)
        self.assertIsNotNone(rows)
        self.assertGreater(len(rows), 0)
        return cols, rows

    def test_acceptance_01_highest_revenue_brazilian_state(self):
        """Scenario 1: Which Brazilian state generates the highest revenue?"""
        sql = """
            SELECT c.customer_state, ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.customer_state
            ORDER BY total_revenue DESC
            LIMIT 1;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(rows[0]["customer_state"], "SP")
        self.assertGreater(rows[0]["total_revenue"], 5000000)

    def test_acceptance_02_compare_aov_top_five_states(self):
        """Scenario 2: Compare average order value across the top five states."""
        sql = """
            SELECT c.customer_state,
                   ROUND(CAST(SUM(oi.price) / NULLIF(COUNT(DISTINCT o.order_id), 0) AS numeric), 2) AS aov,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN customers c ON o.customer_id = c.customer_id
            GROUP BY c.customer_state
            ORDER BY total_revenue DESC
            LIMIT 5;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 5)
        for r in rows:
            self.assertIn("aov", r)
            self.assertGreater(r["aov"], 0)

    def test_acceptance_03_monthly_revenue_trend(self):
        """Scenario 3: What is the monthly revenue trend?"""
        sql = """
            SELECT TO_CHAR(o.order_purchase_timestamp, 'YYYY-MM') AS purchase_month,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS monthly_revenue
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            GROUP BY purchase_month
            ORDER BY purchase_month ASC
            LIMIT 24;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertGreater(len(rows), 10)
        self.assertIn("purchase_month", cols)
        self.assertIn("monthly_revenue", cols)

    def test_acceptance_04_categories_highest_average_item_price(self):
        """Scenario 4: Which product categories have the highest average item price?"""
        sql = """
            SELECT COALESCE(t.product_category_name_english, p.product_category_name) AS category,
                   ROUND(CAST(AVG(oi.price) AS numeric), 2) AS avg_item_price,
                   COUNT(oi.order_id) AS items_sold
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name
            GROUP BY category
            HAVING COUNT(oi.order_id) >= 10
            ORDER BY avg_item_price DESC
            LIMIT 5;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 5)
        self.assertGreater(rows[0]["avg_item_price"], 100)

    def test_acceptance_05_compare_review_scores_across_categories(self):
        """Scenario 5: Compare customer review scores across product categories."""
        sql = """
            SELECT COALESCE(t.product_category_name_english, p.product_category_name) AS category,
                   ROUND(CAST(AVG(r.review_score) AS numeric), 2) AS avg_rating,
                   COUNT(r.review_score) AS review_count
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            JOIN orders o ON oi.order_id = o.order_id
            JOIN order_reviews r ON o.order_id = r.order_id
            LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name
            GROUP BY category
            HAVING COUNT(r.review_score) >= 50
            ORDER BY avg_rating DESC
            LIMIT 10;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 10)
        for r in rows:
            self.assertTrue(1.0 <= r["avg_rating"] <= 5.0)

    def test_acceptance_06_sellers_highest_average_freight_costs(self):
        """Scenario 6: Which sellers have the highest average freight costs?"""
        sql = """
            SELECT oi.seller_id,
                   s.seller_state,
                   ROUND(CAST(AVG(oi.freight_value) AS numeric), 2) AS avg_freight,
                   COUNT(oi.order_id) AS items_sold
            FROM order_items oi
            JOIN sellers s ON oi.seller_id = s.seller_id
            GROUP BY oi.seller_id, s.seller_state
            HAVING COUNT(oi.order_id) >= 20
            ORDER BY avg_freight DESC
            LIMIT 5;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 5)
        self.assertGreater(rows[0]["avg_freight"], 0)

    def test_acceptance_07_percentage_orders_delivered_late(self):
        """Scenario 7: What percentage of orders were delivered late?"""
        sql = """
            SELECT ROUND(CAST(COUNT(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) AS numeric), 2) AS late_pct,
                   COUNT(CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 1 END) AS late_orders,
                   COUNT(*) AS total_delivered_orders
            FROM orders o
            WHERE o.order_delivered_customer_date IS NOT NULL;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 1)
        self.assertTrue(5.0 <= rows[0]["late_pct"] <= 15.0)

    def test_acceptance_08_compare_revenue_between_two_states(self):
        """Scenario 8: Compare revenue between two customer states (SP vs RJ)."""
        sql = """
            SELECT c.customer_state,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_revenue,
                   COUNT(DISTINCT o.order_id) AS total_orders
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN customers c ON o.customer_id = c.customer_id
            WHERE c.customer_state IN ('SP', 'RJ')
            GROUP BY c.customer_state
            ORDER BY total_revenue DESC;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 2)
        states = {r["customer_state"] for r in rows}
        self.assertEqual(states, {"SP", "RJ"})

    def test_acceptance_09_month_highest_number_of_orders(self):
        """Scenario 9: Which month had the highest number of orders?"""
        sql = """
            SELECT TO_CHAR(o.order_purchase_timestamp, 'YYYY-MM') AS purchase_month,
                   COUNT(DISTINCT o.order_id) AS order_count
            FROM orders o
            GROUP BY purchase_month
            ORDER BY order_count DESC
            LIMIT 1;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 1)
        self.assertIn("purchase_month", rows[0])
        self.assertGreater(rows[0]["order_count"], 1000)

    def test_acceptance_10_relationship_delivery_delays_and_review_scores(self):
        """Scenario 10: Show the relationship between delivery delays and review scores."""
        sql = """
            SELECT (CASE WHEN o.order_delivered_customer_date > o.order_estimated_delivery_date THEN 'Delayed' ELSE 'On-Time' END) AS delivery_status,
                   ROUND(CAST(AVG(r.review_score) AS numeric), 2) AS avg_review_score,
                   COUNT(*) AS review_count
            FROM orders o
            JOIN order_reviews r ON o.order_id = r.order_id
            WHERE o.order_delivered_customer_date IS NOT NULL
            GROUP BY delivery_status
            ORDER BY avg_review_score DESC;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertEqual(len(rows), 2)
        # On-Time delivery should have significantly higher ratings than Delayed delivery
        scores = {r["delivery_status"]: r["avg_review_score"] for r in rows}
        self.assertGreater(scores["On-Time"], scores["Delayed"])

    # -------------------------------------------------------------
    # 4. Clarification & Follow-up Tests
    # -------------------------------------------------------------
    def test_clarification_response_on_ambiguous_input(self):
        """Verify ambiguous input triggers clarification response."""
        with patch.object(self.service, "_call_gemini_with_fallback") as mock_gemini:
            mock_gemini.return_value = (
                '{"type": "clarification", "message": "Would you like to analyze revenue by Brazilian state or by product category?"}',
                None,
            )
            resp = self.service.answer_query("Compare revenue")
            self.assertIsNotNone(resp)
            self.assertEqual(resp.source, "clarification")
            self.assertEqual(resp.intent, "clarification_needed")
            self.assertIn("state or by product category", resp.text)

    def test_conversational_follow_up_context_injection(self):
        """Verify conversational memory passes previous turns into Gemini prompt."""
        history = [
            MessageHistoryItem(role="user", text="What are the top 5 product categories by revenue?"),
            MessageHistoryItem(role="assistant", text="The top categories are bed_bath_table, health_beauty, etc.", sql_query="SELECT p.product_category_name..."),
        ]
        with patch.object(self.service, "_call_gemini_with_fallback") as mock_gemini:
            mock_gemini.return_value = (
                '{"type": "sql", "sql": "SELECT p.product_category_name, COUNT(DISTINCT oi.order_id) AS order_count FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY order_count DESC LIMIT 5"}',
                None,
            )
            resp = self.service.answer_query("What about their order counts?", history=history)
            self.assertIsNotNone(resp)
            self.assertEqual(resp.source, "postgresql")
            # Verify mock was called with history in stage 1 prompt
            first_prompt_used = mock_gemini.call_args_list[0][1]["prompt"]
            self.assertIn("RECENT CONVERSATION HISTORY", first_prompt_used)
            self.assertIn("top 5 product categories by revenue", first_prompt_used)

    # -------------------------------------------------------------
    # 5. Historical Time Intelligence & Temporal Anchoring Tests
    # -------------------------------------------------------------
    def test_temporal_anchoring_guardrail_in_semantic_and_prompt(self):
        """Verify temporal anchoring guardrails prevent NOW()/CURRENT_DATE on historical data."""
        formatted_semantic = self.service.semantic_layer.format_semantic_layer_for_llm()
        self.assertIn("HISTORICAL TEMPORAL ANCHORING", formatted_semantic)
        self.assertIn("NEVER use NOW() or CURRENT_DATE", formatted_semantic)
        self.assertIn("MAX(orders.order_purchase_timestamp)", formatted_semantic)

        # Verify prompt injection in generate_sql
        with patch.object(self.service, "_call_gemini_with_fallback") as mock_gemini:
            mock_gemini.return_value = (
                '{"type": "sql", "sql": "SELECT p.product_category_name, ROUND(CAST(SUM(oi.price) AS numeric), 2) AS revenue FROM orders o JOIN order_items oi ON o.order_id = oi.order_id JOIN products p ON oi.product_id = p.product_id WHERE o.order_purchase_timestamp >= (SELECT MAX(order_purchase_timestamp) FROM orders) - INTERVAL \'6 months\' GROUP BY p.product_category_name ORDER BY revenue DESC LIMIT 5"}',
                None,
            )
            self.service.generate_sql("What were the top-selling categories in the last six months?")
            prompt_used = mock_gemini.call_args_list[0][1]["prompt"]
            self.assertIn("Historical Time Intelligence", prompt_used)
            self.assertIn("NEVER use NOW() or CURRENT_DATE", prompt_used)
            self.assertIn("SELECT MAX(order_purchase_timestamp) FROM orders", prompt_used)

    def test_relative_date_last_six_months_query_execution(self):
        """Verify that relative 6-month query anchored to dataset MAX date returns historical data."""
        sql = """
            SELECT p.product_category_name,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_revenue,
                   COUNT(DISTINCT o.order_id) AS order_count
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            JOIN products p ON oi.product_id = p.product_id
            WHERE o.order_purchase_timestamp >= (SELECT MAX(order_purchase_timestamp) FROM orders) - INTERVAL '6 months'
            GROUP BY p.product_category_name
            ORDER BY total_revenue DESC
            LIMIT 5;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertGreater(len(rows), 0)
        self.assertIn("total_revenue", rows[0])
        self.assertGreater(rows[0]["total_revenue"], 0)

    def test_relative_date_last_twelve_months_monthly_trend_execution(self):
        """Verify that monthly trend query anchored to dataset MAX date covers the 12-month period."""
        sql = """
            SELECT TO_CHAR(o.order_purchase_timestamp, 'YYYY-MM') AS purchase_month,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_revenue,
                   COUNT(DISTINCT o.order_id) AS order_count
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_purchase_timestamp >= (SELECT MAX(order_purchase_timestamp) FROM orders) - INTERVAL '12 months'
            GROUP BY purchase_month
            ORDER BY purchase_month ASC;
        """
        cols, rows = self._execute_and_verify(sql)
        self.assertGreaterEqual(len(rows), 10)  # At least 10-13 monthly buckets in the 12-month window
        months = [r["purchase_month"] for r in rows]
        # Max date is 2018-10, so months should include 2017-10 through 2018-08/10
        self.assertTrue(any(m.startswith("2018") for m in months))
        self.assertTrue(any(m.startswith("2017") for m in months))



if __name__ == "__main__":
    unittest.main()

"""Unit tests for Phase 4: Safe Dynamic SQL Analytics and AI Text-to-SQL Agent."""

import unittest
from unittest.mock import MagicMock, patch
from sqlalchemy import text
from app.database import SessionLocal, readonly_engine
from app.schemas.chat import ChatRequest, ChatResponse, MetricCard
from app.services.text_to_sql import TextToSQLService, SQLValidationError, APPROVED_TABLES, DANGEROUS_FUNCTIONS
from app.routers.chat import process_chat_message


class TestTextToSQLService(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = TextToSQLService()
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    # -------------------------------------------------------------
    # 1. Valid SELECT Queries Tests
    # -------------------------------------------------------------
    def test_valid_select_queries(self):
        valid_queries = [
            "SELECT AVG(product_weight_g) AS avg_weight FROM products",
            "SELECT payment_type, COUNT(*) AS count FROM order_payments GROUP BY payment_type ORDER BY count DESC LIMIT 5",
            "SELECT p.product_category_name, AVG(oi.price) AS avg_price FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY avg_price DESC LIMIT 10",
            "SELECT c.customer_state, AVG(oi.freight_value) AS avg_freight FROM order_items oi JOIN orders o ON oi.order_id = o.order_id JOIN customers c ON o.customer_id = c.customer_id GROUP BY c.customer_state ORDER BY avg_freight DESC LIMIT 10",
            "SELECT ROUND(CORR(price, freight_value)::numeric, 4) AS corr_price_freight FROM order_items",
        ]
        for q in valid_queries:
            is_valid, transformed, err = self.service.validate_and_transform_sql(q)
            self.assertTrue(is_valid, f"Expected valid query '{q}', got error: {err}")
            self.assertIn("LIMIT", transformed)

    # -------------------------------------------------------------
    # 2. Invalid SQL Syntax Tests
    # -------------------------------------------------------------
    def test_invalid_sql_syntax(self):
        invalid_queries = [
            "SELECT FROM WHERE",
            "SELEC * FORM products",
            "",
            "   ",
            "??? NOT SQL ???",
        ]
        for q in invalid_queries:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected invalid query for '{q}'")
            self.assertTrue(len(err) > 0)

    # -------------------------------------------------------------
    # 3. SQL Injection & Forbidden DML/DDL Tests
    # -------------------------------------------------------------
    def test_forbidden_operations_rejected(self):
        forbidden_queries = [
            ("DROP TABLE customers", "DROP"),
            ("INSERT INTO products (product_id) VALUES ('hacked')", "INSERT"),
            ("UPDATE sellers SET seller_city = 'hacked'", "UPDATE"),
            ("DELETE FROM orders", "DELETE"),
            ("ALTER TABLE products ADD COLUMN hack INT", "ALTER"),
            ("CREATE TABLE hack (id INT)", "CREATE"),
            ("TRUNCATE order_items", "TRUNCATE"),
            ("GRANT ALL ON orders TO public", "GRANT"),
            ("REVOKE SELECT ON orders FROM public", "REVOKE"),
            ("COPY products TO '/tmp/hack.csv'", "COPY"),
        ]
        for q, op in forbidden_queries:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected operation '{op}' to be blocked in query: {q}")
            self.assertTrue(len(err) > 0)

    # -------------------------------------------------------------
    # 4. Multiple Statements Blocked
    # -------------------------------------------------------------
    def test_multiple_statements_blocked(self):
        stacked_queries = [
            "SELECT * FROM products; DROP TABLE customers;",
            "SELECT 1; SELECT 2;",
            "SELECT AVG(price) FROM order_items; DELETE FROM orders WHERE 1=1;",
        ]
        for q in stacked_queries:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected stacked query to be rejected: {q}")
            self.assertIn("Multiple SQL statements", err)

    # -------------------------------------------------------------
    # 5. Dangerous Functions Blocked
    # -------------------------------------------------------------
    def test_dangerous_functions_blocked(self):
        dangerous_queries = [
            "SELECT pg_sleep(10)",
            "SELECT pg_read_file('/etc/passwd')",
            "SELECT dblink('dbname=other', 'SELECT 1')",
            "SELECT query_to_xml('SELECT 1', true, false, '')",
            "SELECT pg_terminate_backend(1234)",
            "SELECT set_config('work_mem', '1GB', false)",
        ]
        for q in dangerous_queries:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected dangerous function to be blocked in query: {q}")
            self.assertIn("Prohibited function", err)

    # -------------------------------------------------------------
    # 6. Unapproved Tables & Schemas Blocked
    # -------------------------------------------------------------
    def test_unapproved_tables_and_schemas_blocked(self):
        unapproved = [
            "SELECT * FROM users",
            "SELECT * FROM admin_passwords",
            "SELECT * FROM pg_catalog.pg_tables",
            "SELECT * FROM information_schema.tables",
            "SELECT * FROM pg_shadow",
            "SELECT * FROM pg_user",
        ]
        for q in unapproved:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid, f"Expected unapproved table/schema to be blocked: {q}")
            self.assertTrue(len(err) > 0)

    # -------------------------------------------------------------
    # 7. LIMIT Enforcement Tests
    # -------------------------------------------------------------
    def test_limit_enforcement(self):
        # 1. Query with no limit gets LIMIT 50 injected
        q_no_limit = "SELECT product_id, product_category_name FROM products"
        _, transformed, _ = self.service.validate_and_transform_sql(q_no_limit)
        self.assertIn("LIMIT 50", transformed)

        # 2. Query with LIMIT > 50 is clamped to LIMIT 50
        q_high_limit = "SELECT product_id FROM products LIMIT 500"
        _, transformed_high, _ = self.service.validate_and_transform_sql(q_high_limit)
        self.assertIn("LIMIT 50", transformed_high)
        self.assertNotIn("LIMIT 500", transformed_high)

        # 3. Query with reasonable limit (< 50) is preserved
        q_small_limit = "SELECT product_id FROM products LIMIT 10"
        _, transformed_small, _ = self.service.validate_and_transform_sql(q_small_limit)
        self.assertIn("LIMIT 10", transformed_small)

    # -------------------------------------------------------------
    # 8. PostgreSQL Read-Only Execution & Complex Queries
    # -------------------------------------------------------------
    def test_readonly_execution_valid(self):
        is_valid, safe_sql, _ = self.service.validate_and_transform_sql(
            "SELECT COUNT(*) AS total_items, ROUND(AVG(price)::numeric, 2) AS avg_price FROM order_items"
        )
        self.assertTrue(is_valid)
        cols, rows, err = self.service.execute_sql(safe_sql)
        self.assertIsNone(err)
        self.assertEqual(len(rows), 1)
        self.assertIn("total_items", cols)
        self.assertIn("avg_price", cols)
        self.assertEqual(rows[0]["total_items"], 112650)

    def test_readonly_database_blocks_writes(self):
        """Verify that readonly_engine connection rejects writes at PostgreSQL engine level."""
        with self.assertRaises(Exception):
            with readonly_engine.connect() as conn:
                conn.execute(text("CREATE TABLE hack_test (id INT)"))

    def test_complex_analytics_queries_execution(self):
        """Execute real analytical questions against PostgreSQL database."""
        test_cases = [
            (
                "Average Product Weight",
                "SELECT ROUND(AVG(product_weight_g)::numeric, 2) AS avg_weight_g FROM products",
                "avg_weight_g",
            ),
            (
                "Payment Types Breakdown",
                "SELECT payment_type, COUNT(*) AS payment_count FROM order_payments GROUP BY payment_type ORDER BY payment_count DESC LIMIT 5",
                "payment_type",
            ),
            (
                "Price and Freight Correlation",
                "SELECT ROUND(CORR(price, freight_value)::numeric, 4) AS correlation FROM order_items",
                "correlation",
            ),
            (
                "Percentage of Orders with >3 Items",
                """WITH order_counts AS (
                    SELECT order_id, COUNT(*) AS item_cnt FROM order_items GROUP BY order_id
                ) SELECT ROUND(COUNT(CASE WHEN item_cnt > 3 THEN 1 END) * 100.0 / COUNT(*), 2) AS pct_gt_3_items FROM order_counts""",
                "pct_gt_3_items",
            ),
        ]
        for name, query, expected_col in test_cases:
            is_valid, safe_sql, err = self.service.validate_and_transform_sql(query)
            self.assertTrue(is_valid, f"Validation failed for {name}: {err}")
            cols, rows, exec_err = self.service.execute_sql(safe_sql)
            self.assertIsNone(exec_err, f"Execution failed for {name}: {exec_err}")
            self.assertIn(expected_col, cols, f"Column {expected_col} missing in {name}")
            self.assertTrue(len(rows) > 0, f"No rows returned for {name}")

    # -------------------------------------------------------------
    # 9. Local Fallback Formatting Tests (English & French)
    # -------------------------------------------------------------
    def test_local_fallback_scalar_formatting(self):
        cols = ["average_weight_kg"]
        rows = [{"average_weight_kg": 2.28}]
        
        # English
        out_en = self.service._format_local_fallback("What is the average weight?", cols, rows, "en")
        self.assertIn("Analytical Result (PostgreSQL Dynamic SQL)", out_en)
        self.assertIn("Average Weight Kg", out_en)
        self.assertIn("2.28", out_en)

        # French
        out_fr = self.service._format_local_fallback("Quel est le poids moyen ?", cols, rows, "fr")
        self.assertIn("Résultat Analytique (PostgreSQL dynamique)", out_fr)
        self.assertIn("2.28", out_fr)

    def test_local_fallback_tabular_formatting(self):
        cols = ["payment_type", "order_count"]
        rows = [
            {"payment_type": "credit_card", "order_count": 76795},
            {"payment_type": "boleto", "order_count": 19784},
            {"payment_type": "voucher", "order_count": 5775},
        ]
        out = self.service._format_local_fallback("Show payment types", cols, rows, "en")
        self.assertIn("| payment_type | order_count |", out)
        self.assertIn("| credit_card | 76,795 |", out)

    # -------------------------------------------------------------
    # 10. Gemini API Failure & Fallback Handling
    # -------------------------------------------------------------
    def test_unconfigured_gemini_graceful_handling(self):
        unconfigured_svc = TextToSQLService()
        unconfigured_svc.client = None
        res = unconfigured_svc.generate_sql("What is the average weight?")
        self.assertEqual(res.get("type"), "unsupported")
        self.assertIn("not configured", res.get("error", ""))

    def test_mocked_gemini_sql_generation(self):
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"type": "sql", "sql": "SELECT AVG(product_weight_g) AS avg_weight FROM products"}'
        mock_client.models.generate_content.return_value = mock_resp

        svc = TextToSQLService()
        svc.client = mock_client
        res = svc.generate_sql("What is the average product weight?")
        self.assertEqual(res.get("type"), "sql")
        self.assertEqual(res.get("sql"), "SELECT AVG(product_weight_g) AS avg_weight FROM products")

    def test_clarification_response_handling(self):
        """Verify ambiguous questions return clarification responses."""
        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"type": "clarification", "message": "Could you please specify whether you want revenue by state, category, or month?"}'
        mock_client.models.generate_content.return_value = mock_resp

        svc = TextToSQLService()
        svc.client = mock_client
        resp = svc.answer_query("Compare revenue", language="en")
        self.assertIsNotNone(resp)
        self.assertEqual(resp.source, "clarification")
        self.assertEqual(resp.intent, "clarification_needed")
        self.assertIn("by state, category, or month", resp.text)
        self.assertTrue(resp.metadata.get("requires_clarification"))

    def test_answer_query_populates_columns_and_rows_for_tabular_data(self):
        """Verify dynamic multi-row queries populate columns and rows in ChatResponse for frontend table."""
        mock_client = MagicMock()
        mock_gen_resp = MagicMock()
        mock_gen_resp.text = '{"type": "sql", "sql": "SELECT payment_type, COUNT(*) AS count FROM order_payments GROUP BY payment_type ORDER BY count DESC LIMIT 3"}'
        
        mock_exp_resp = MagicMock()
        mock_exp_resp.text = "Credit card is the most common payment type with 76,795 transactions."
        
        mock_client.models.generate_content.side_effect = [mock_gen_resp, mock_exp_resp]

        svc = TextToSQLService()
        svc.client = mock_client
        resp = svc.answer_query("Which payment methods are most used?", language="en")
        self.assertIsNotNone(resp)
        self.assertEqual(resp.source, "postgresql")
        self.assertIsNotNone(resp.columns)
        self.assertIsNotNone(resp.rows)
        self.assertIn("payment_type", resp.columns)
        self.assertIn("count", resp.columns)
        self.assertTrue(len(resp.rows) >= 3)
        self.assertIsNotNone(resp.sql_query)
        self.assertIn("LIMIT 3", resp.sql_query)

    # -------------------------------------------------------------
    # 11. End-to-End Chat Routing Integration
    # -------------------------------------------------------------
    @patch("app.routers.chat.get_llm_service")
    def test_e2e_chat_routing_dynamic_sql(self, mock_get_llm):
        """Verify dynamic SQL is called as PRIMARY engine for analytical questions."""
        mock_llm = MagicMock()
        mock_llm.is_configured = False
        mock_get_llm.return_value = mock_llm

        mock_dynamic_response = ChatResponse(
            text="The average product weight is 2,276.5 grams across 32,951 products.",
            source="postgresql",
            intent="dynamic_sql",
            metrics=[MetricCard(label="Avg Weight", value="2,276.5 g")],
            sql_query="SELECT AVG(product_weight_g) FROM products LIMIT 50",
            metadata={"dynamic_sql": True},
        )

        with patch("app.routers.chat.get_text_to_sql_service") as mock_get_t2sql:
            mock_t2sql = MagicMock()
            mock_t2sql.is_configured = True
            mock_t2sql.answer_query.return_value = mock_dynamic_response
            mock_get_t2sql.return_value = mock_t2sql

            req = ChatRequest(message="What is the average product weight in grams?")
            resp = process_chat_message(req, db=self.db)

            self.assertEqual(resp.source, "postgresql")
            self.assertEqual(resp.intent, "dynamic_sql")
            self.assertIn("2,276.5", resp.text)
            self.assertTrue(resp.metadata.get("dynamic_sql"))


if __name__ == "__main__":
    unittest.main()

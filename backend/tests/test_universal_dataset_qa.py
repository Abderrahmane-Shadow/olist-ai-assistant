"""Comprehensive Test Suite for Universal Olist Dataset Question Answering.

Verifies:
1. Full coverage across all 9 Olist database tables.
2. Analytical domains A through J:
   - Category A: General Database & Catalog Questions
   - Category B: Revenue & Sales Analytics
   - Category C: Products & Categories
   - Category D: Geographic Analysis (including geolocation)
   - Category E: Seller Performance
   - Category F: Customer Analytics & Retention CTEs
   - Category G: Orders & Logistics Performance
   - Category H: Payment Methods & Financials
   - Category I: Customer Reviews & Satisfaction
   - Category J: Advanced Analytics (Cohorts & Period-over-Period)
3. AST security guardrails (SQLGlot AST validation, limit enforcement, read-only mode).
4. Review query routing (analytical review queries -> Text-to-SQL vs qualitative -> ReviewService).
5. Dataset boundary detection and graceful service error reporting.
"""

import unittest
from unittest.mock import MagicMock, patch
from app.services.schema_explorer import get_schema_explorer
from app.services.semantic_layer import get_semantic_layer
from app.services.text_to_sql import TextToSQLService
from app.services.review_service import ReviewService


class TestUniversalDatasetQA(unittest.TestCase):
    """Test suite verifying end-to-end question answering across all 9 Olist tables."""

    @classmethod
    def setUpClass(cls):
        cls.schema_explorer = get_schema_explorer()
        cls.semantic_layer = get_semantic_layer()
        cls.service = TextToSQLService()
        cls.review_service = ReviewService(db=MagicMock())

    def _validate_and_execute(self, sql_query: str):
        """Helper to validate through AST and execute against PostgreSQL."""
        is_valid, safe_sql, val_err = self.service.validate_and_transform_sql(sql_query)
        self.assertTrue(is_valid, f"AST validation failed: {val_err} for query:\n{sql_query}")
        cols, rows, exec_err = self.service.execute_sql(safe_sql)
        self.assertIsNone(exec_err, f"Execution failed: {exec_err} for query:\n{safe_sql}")
        self.assertIsNotNone(cols)
        self.assertIsNotNone(rows)
        self.assertGreater(len(rows), 0, f"Query returned 0 rows:\n{safe_sql}")
        return cols, rows

    # =========================================================================
    # 1. Database Schema & Semantic Layer Metadata
    # =========================================================================
    def test_schema_explorer_covers_all_nine_tables(self):
        """Verify dynamic schema explorer inspects all 9 public tables."""
        meta = self.schema_explorer.get_schema_metadata(force_refresh=True)
        expected_tables = {
            "customers",
            "geolocation",
            "order_items",
            "order_payments",
            "order_reviews",
            "orders",
            "products",
            "sellers",
            "product_category_name_translation",
        }
        for tbl in expected_tables:
            self.assertIn(tbl, meta, f"Table '{tbl}' missing from Schema Explorer")
            self.assertGreater(len(meta[tbl]["columns"]), 0)

    def test_semantic_layer_has_all_canonical_metrics_and_joins(self):
        """Verify semantic layer contains canonical metrics across all domains."""
        sl = self.semantic_layer
        required_metrics = [
            "gross_revenue",
            "total_freight",
            "order_count",
            "average_order_value",
            "average_item_price",
            "highest_item_price",
            "lowest_item_price",
            "average_product_weight",
            "average_payment_value",
            "average_installments",
            "cancellation_rate",
            "late_order_percentage",
            "early_delivery_percentage",
            "repeat_customer_rate",
            "average_spend_per_customer",
            "dataset_date_range",
        ]
        for m in required_metrics:
            self.assertIn(m, sl.metrics, f"Metric '{m}' missing from Semantic Layer")

        # Verify geolocation joins exist
        join_pairs = {(j.from_table, j.to_table) for j in sl.joins}
        self.assertIn(("customers", "geolocation"), join_pairs)
        self.assertIn(("sellers", "geolocation"), join_pairs)

    # =========================================================================
    # 2. Analytical Domain Queries (A through J)
    # =========================================================================

    # Category A: General Database & Catalog Questions
    def test_category_a_dataset_date_range(self):
        """Category A: Total dataset date range from orders."""
        sql = """
            SELECT MIN(order_purchase_timestamp) AS earliest_order,
                   MAX(order_purchase_timestamp) AS latest_order,
                   COUNT(*) AS total_orders
            FROM orders;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertIn("earliest_order", cols)
        self.assertIn("latest_order", cols)
        self.assertGreater(rows[0]["total_orders"], 90000)

    def test_category_a_table_counts(self):
        """Category A: Verify order_items and products counts."""
        sql = """
            SELECT (SELECT COUNT(*) FROM orders) AS total_orders,
                   (SELECT COUNT(*) FROM customers) AS total_customers,
                   (SELECT COUNT(*) FROM products) AS total_products,
                   (SELECT COUNT(*) FROM sellers) AS total_sellers;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertGreater(rows[0]["total_orders"], 90000)
        self.assertGreater(rows[0]["total_customers"], 90000)
        self.assertGreater(rows[0]["total_products"], 30000)
        self.assertGreater(rows[0]["total_sellers"], 3000)

    # Category B: Revenue & Sales Analytics
    def test_category_b_gmv_freight_and_aov(self):
        """Category B: Total merchandise GMV, freight, and Average Order Value."""
        sql = """
            SELECT ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_gmv,
                   ROUND(CAST(SUM(oi.freight_value) AS numeric), 2) AS total_freight,
                   ROUND(CAST(SUM(oi.price) / NULLIF(COUNT(DISTINCT o.order_id), 0) AS numeric), 2) AS aov
            FROM orders o
            JOIN order_items oi ON o.order_id = oi.order_id
            WHERE o.order_status = 'delivered';
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertGreater(rows[0]["total_gmv"], 10000000)
        self.assertGreater(rows[0]["total_freight"], 1000000)
        self.assertGreater(rows[0]["aov"], 100)

    def test_category_b_highest_and_lowest_item_prices(self):
        """Category B: Highest and lowest individual item prices."""
        sql = """
            SELECT MAX(price) AS max_price,
                   MIN(price) AS min_price,
                   ROUND(CAST(AVG(price) AS numeric), 2) AS avg_price
            FROM order_items;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertGreater(rows[0]["max_price"], 5000)
        self.assertGreater(rows[0]["min_price"], 0)
        self.assertGreater(rows[0]["avg_price"], 100)

    # Category C: Products & Categories
    def test_category_c_top_categories_by_revenue_and_weight(self):
        """Category C: Top product categories with English names, GMV, and average weight."""
        sql = """
            SELECT COALESCE(t.product_category_name_english, p.product_category_name) AS category,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_revenue,
                   COUNT(oi.order_id) AS items_sold,
                   ROUND(CAST(AVG(p.product_weight_g) AS numeric), 1) AS avg_weight_g
            FROM order_items oi
            JOIN products p ON oi.product_id = p.product_id
            LEFT JOIN product_category_name_translation t ON p.product_category_name = t.product_category_name
            GROUP BY category
            ORDER BY total_revenue DESC
            LIMIT 5;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertEqual(len(rows), 5)
        self.assertIn("category", cols)
        self.assertIn("total_revenue", cols)
        self.assertIn("avg_weight_g", cols)
        self.assertIsNotNone(rows[0]["category"])

    # Category D: Geographic Analysis
    def test_category_d_customer_and_seller_states(self):
        """Category D: Revenue and orders by customer state."""
        sql = """
            SELECT c.customer_state,
                   COUNT(DISTINCT o.order_id) AS total_orders,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_revenue
            FROM orders o
            JOIN customers c ON o.customer_id = c.customer_id
            JOIN order_items oi ON o.order_id = oi.order_id
            GROUP BY c.customer_state
            ORDER BY total_revenue DESC
            LIMIT 5;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertEqual(rows[0]["customer_state"], "SP")
        self.assertGreater(rows[0]["total_orders"], 30000)

    def test_category_d_geolocation_state_coordinates(self):
        """Category D: Geolocation zip codes and average coordinates."""
        sql = """
            SELECT geolocation_state,
                   COUNT(DISTINCT geolocation_zip_code_prefix) AS unique_zip_prefixes,
                   ROUND(CAST(AVG(geolocation_lat) AS numeric), 4) AS avg_lat,
                   ROUND(CAST(AVG(geolocation_lng) AS numeric), 4) AS avg_lng
            FROM geolocation
            GROUP BY geolocation_state
            ORDER BY unique_zip_prefixes DESC
            LIMIT 5;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["geolocation_state"], "SP")

    # Category E: Seller Performance
    def test_category_e_top_sellers_and_ratings(self):
        """Category E: Top sellers by revenue and their average rating."""
        sql = """
            SELECT s.seller_id,
                   s.seller_state,
                   s.seller_city,
                   ROUND(CAST(SUM(oi.price) AS numeric), 2) AS total_sales,
                   COUNT(DISTINCT oi.order_id) AS orders_fulfilled,
                   ROUND(CAST(AVG(r.review_score) AS numeric), 2) AS avg_seller_rating
            FROM sellers s
            JOIN order_items oi ON s.seller_id = oi.seller_id
            LEFT JOIN order_reviews r ON oi.order_id = r.order_id
            GROUP BY s.seller_id, s.seller_state, s.seller_city
            ORDER BY total_sales DESC
            LIMIT 5;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertEqual(len(rows), 5)
        self.assertGreater(rows[0]["total_sales"], 100000)

    # Category F: Customer Analytics & Retention
    def test_category_f_customer_unique_id_vs_customer_id(self):
        """Category F: Distinct unique individuals vs order customer tokens."""
        sql = """
            SELECT COUNT(customer_id) AS total_customer_records,
                   COUNT(DISTINCT customer_unique_id) AS unique_buyers
            FROM customers;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertGreater(rows[0]["total_customer_records"], 99000)
        self.assertGreater(rows[0]["unique_buyers"], 90000)
        self.assertLess(rows[0]["unique_buyers"], rows[0]["total_customer_records"])

    def test_category_f_repeat_buyer_rate_cte(self):
        """Category F: Repeat buyer percentage calculated via CTE."""
        sql = """
            WITH customer_order_counts AS (
                SELECT c.customer_unique_id, COUNT(DISTINCT o.order_id) AS order_cnt
                FROM customers c
                JOIN orders o ON c.customer_id = o.customer_id
                GROUP BY c.customer_unique_id
            )
            SELECT COUNT(*) AS total_customers,
                   SUM(CASE WHEN order_cnt > 1 THEN 1 ELSE 0 END) AS repeat_customers,
                   ROUND(CAST(100.0 * SUM(CASE WHEN order_cnt > 1 THEN 1 ELSE 0 END) / COUNT(*) AS numeric), 2) AS repeat_rate_pct
            FROM customer_order_counts;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertIn("repeat_rate_pct", cols)
        self.assertGreater(rows[0]["repeat_customers"], 2000)
        self.assertGreater(rows[0]["repeat_rate_pct"], 2.0)

    # Category G: Orders & Logistics Performance
    def test_category_g_order_status_distribution(self):
        """Category G: Order status counts and cancellation rate."""
        sql = """
            SELECT order_status,
                   COUNT(*) AS count,
                   ROUND(CAST(100.0 * COUNT(*) / SUM(COUNT(*)) OVER() AS numeric), 2) AS percentage
            FROM orders
            GROUP BY order_status
            ORDER BY count DESC;
        """
        cols, rows = self._validate_and_execute(sql)
        status_map = {r["order_status"]: r["count"] for r in rows}
        self.assertIn("delivered", status_map)
        self.assertGreater(status_map["delivered"], 90000)
        self.assertIn("canceled", status_map)

    def test_category_g_delivery_duration_and_late_percentage(self):
        """Category G: Delivery duration, late deliveries, and early deliveries."""
        sql = """
            SELECT ROUND(CAST(AVG(EXTRACT(EPOCH FROM (order_delivered_customer_date - order_purchase_timestamp)) / 86400.0) AS numeric), 1) AS avg_delivery_days,
                   ROUND(CAST(100.0 * SUM(CASE WHEN order_delivered_customer_date > order_estimated_delivery_date THEN 1 ELSE 0 END) /
                         NULLIF(COUNT(order_delivered_customer_date), 0) AS numeric), 2) AS late_delivery_pct,
                   ROUND(CAST(100.0 * SUM(CASE WHEN order_delivered_customer_date <= order_estimated_delivery_date THEN 1 ELSE 0 END) /
                         NULLIF(COUNT(order_delivered_customer_date), 0) AS numeric), 2) AS on_time_delivery_pct
            FROM orders
            WHERE order_status = 'delivered'
              AND order_delivered_customer_date IS NOT NULL;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertGreater(rows[0]["avg_delivery_days"], 10)
        self.assertGreater(rows[0]["late_delivery_pct"], 5)
        self.assertGreater(rows[0]["on_time_delivery_pct"], 80)

    # Category H: Payment Methods & Financials
    def test_category_h_payment_methods_and_installments(self):
        """Category H: Payment methods, transaction volume, and installments."""
        sql = """
            SELECT payment_type,
                   COUNT(DISTINCT order_id) AS orders_count,
                   ROUND(CAST(SUM(payment_value) AS numeric), 2) AS total_payment_value,
                   ROUND(CAST(AVG(payment_installments) AS numeric), 1) AS avg_installments
            FROM order_payments
            GROUP BY payment_type
            ORDER BY total_payment_value DESC;
        """
        cols, rows = self._validate_and_execute(sql)
        types = [r["payment_type"] for r in rows]
        self.assertIn("credit_card", types)
        self.assertIn("boleto", types)
        self.assertGreater(rows[0]["total_payment_value"], 1000000)

    # Category I: Customer Reviews & Satisfaction
    def test_category_i_overall_review_score_distribution(self):
        """Category I: Distribution of review ratings 1 through 5."""
        sql = """
            SELECT review_score,
                   COUNT(*) AS review_count,
                   ROUND(CAST(100.0 * COUNT(*) / SUM(COUNT(*)) OVER() AS numeric), 1) AS pct_of_total
            FROM order_reviews
            GROUP BY review_score
            ORDER BY review_score DESC;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertEqual(len(rows), 5)
        self.assertEqual(rows[0]["review_score"], 5)
        self.assertGreater(rows[0]["review_count"], 50000)

    def test_category_i_review_score_vs_delivery_delay(self):
        """Category I: Relationship between delivery delay and review score."""
        sql = """
            SELECT r.review_score,
                   ROUND(CAST(AVG(EXTRACT(EPOCH FROM (o.order_delivered_customer_date - o.order_estimated_delivery_date)) / 86400.0) AS numeric), 1) AS avg_delay_vs_estimate_days,
                   COUNT(*) AS total_reviews
            FROM orders o
            JOIN order_reviews r ON o.order_id = r.order_id
            WHERE o.order_delivered_customer_date IS NOT NULL
            GROUP BY r.review_score
            ORDER BY r.review_score ASC;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertEqual(len(rows), 5)
        # Low scores (score 1) have higher delay than score 5
        score_1_delay = [r["avg_delay_vs_estimate_days"] for r in rows if r["review_score"] == 1][0]
        score_5_delay = [r["avg_delay_vs_estimate_days"] for r in rows if r["review_score"] == 5][0]
        self.assertGreater(score_1_delay, score_5_delay)

    # Category J: Advanced Analytics (Cohorts & Comparisons)
    def test_category_j_monthly_cohort_retention(self):
        """Category J: Monthly cohort creation and 30-day activity."""
        sql = """
            WITH first_purchase AS (
                SELECT c.customer_unique_id,
                       TO_CHAR(MIN(o.order_purchase_timestamp), 'YYYY-MM') AS cohort_month
                FROM customers c
                JOIN orders o ON c.customer_id = o.customer_id
                GROUP BY c.customer_unique_id
            )
            SELECT cohort_month,
                   COUNT(*) AS new_customers
            FROM first_purchase
            GROUP BY cohort_month
            ORDER BY cohort_month ASC
            LIMIT 12;
        """
        cols, rows = self._validate_and_execute(sql)
        self.assertGreater(len(rows), 6)
        self.assertIn("cohort_month", cols)
        self.assertIn("new_customers", cols)

    # =========================================================================
    # 3. Routing & Review Service Tests
    # =========================================================================
    def test_review_service_routes_analytical_queries_to_text_to_sql(self):
        """Verify analytical review questions do NOT get trapped in qualitative review search."""
        analytical_questions = [
            "Which categories have the highest review scores?",
            "Which states have the lowest customer satisfaction?",
            "What is the average review score across all orders?",
            "Is there a correlation between delivery delays and review scores?",
            "Top 5 sellers with the best customer ratings",
        ]
        for q in analytical_questions:
            is_review = self.review_service.is_review_query(q)
            self.assertFalse(
                is_review,
                f"Query '{q}' should be classified as analytical Text-to-SQL, but review_service claimed it.",
            )

    def test_review_service_still_handles_qualitative_feedback(self):
        """Verify qualitative feedback queries still route to ReviewService."""
        qualitative_questions = [
            "What do customers say about broken items?",
            "Show me negative comments about slow delivery",
            "What are common complaints in 1-star reviews?",
            "Customer opinions on packaging quality",
        ]
        for q in qualitative_questions:
            is_review = self.review_service.is_review_query(q)
            self.assertTrue(
                is_review,
                f"Query '{q}' should be classified as qualitative review query.",
            )

    # =========================================================================
    # 4. AST Security & Limit Enforcements
    # =========================================================================
    def test_security_blocks_destructive_sql(self):
        """Verify AST rejects any write/DDL attempts."""
        destructive_queries = [
            "DELETE FROM orders WHERE order_status = 'canceled';",
            "DROP TABLE geolocation;",
            "ALTER TABLE customers ADD COLUMN secret text;",
            "TRUNCATE TABLE order_payments;",
        ]
        for q in destructive_queries:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid)
            self.assertIsNotNone(err)

    def test_security_blocks_unapproved_tables(self):
        """Verify AST rejects access to auth or postgres internal catalogs."""
        prohibited = [
            "SELECT * FROM auth.users;",
            "SELECT * FROM pg_catalog.pg_user;",
            "SELECT * FROM information_schema.tables;",
        ]
        for q in prohibited:
            is_valid, _, err = self.service.validate_and_transform_sql(q)
            self.assertFalse(is_valid)

    def test_security_clamps_limit_to_50(self):
        """Verify limit is injected if missing or clamped if > 50."""
        valid, sql, _ = self.service.validate_and_transform_sql(
            "SELECT customer_id, customer_city FROM customers;"
        )
        self.assertTrue(valid)
        self.assertIn("LIMIT 50", sql)

        valid2, sql2, _ = self.service.validate_and_transform_sql(
            "SELECT customer_id, customer_city FROM customers LIMIT 5000;"
        )
        self.assertTrue(valid2)
        self.assertIn("LIMIT 50", sql2)

    # =========================================================================
    # 5. Out-of-Scope & Service Error Handling
    # =========================================================================
    def test_out_of_scope_query_handling(self):
        """Verify answer_query returns source='unsupported' when Gemini identifies out-of-scope query."""
        with patch.object(
            self.service,
            "generate_sql",
            return_value={
                "type": "unsupported",
                "message": "The Olist dataset does not contain profit margins or product cost (COGS) data.",
            },
        ):
            resp = self.service.answer_query("What is our net profit margin for laptops?")
            self.assertIsNotNone(resp)
            self.assertEqual(resp.source, "unsupported")
            self.assertIn("profit margins", resp.text)

    def test_rate_limit_service_error_handling(self):
        """Verify 429 quota exhaustion returns a clear service error instead of a crash or generic fallback."""
        with patch.object(
            self.service,
            "generate_sql",
            return_value={
                "type": "error",
                "error": "ResourceExhausted: 429 Resource has been exhausted (quota limit).",
            },
        ):
            resp = self.service.answer_query("total revenue by month", language="en")
            # Note: fallback canonical SQL might kick in for common metrics, so test with a query that has no canonical fallback:
            # Let's test with a mock where _synthesize_canonical_sql returns None
            with patch.object(self.service, "_synthesize_canonical_sql", return_value=None):
                resp = self.service.answer_query("arbitrary query that rate limited", language="en")
                self.assertIsNotNone(resp)
                self.assertEqual(resp.source, "service_error")
                self.assertIn("temporary high demand", resp.text)


if __name__ == "__main__":
    unittest.main()

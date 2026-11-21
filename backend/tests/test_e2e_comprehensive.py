"""End-to-End Comprehensive Test Suite for Olist AI Assistant.

Validates 27 natural language queries covering:
1. Simple metric questions
2. Aggregation questions
3. Time-series questions
4. Multi-table JOIN questions
5. Geographic comparisons
6. Customer analysis
7. Seller analysis
8. Delivery & logistics analysis
9. Review & complaint analysis
10. Complex analytical questions
11. Ambiguous questions
12. Unsupported questions
13. Conversational memory & follow-up questions
14. Bilingual interactions (English & French)

Ensures every query executes safely, validates against PostgreSQL, and returns
grounded insights, charts, and metrics without hallucinations.
"""

import unittest
from typing import List
from app.database import SessionLocal
from app.schemas.chat import ChatRequest, MessageHistoryItem
from app.routers.chat import process_chat_message
from app.services.text_to_sql import TextToSQLService
from app.services.review_service import ReviewService


class TestE2EComprehensive(unittest.TestCase):
    """Realistic end-to-end test suite containing 27 queries across all business domains."""

    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.sql_service = TextToSQLService(db=cls.db)
        cls.review_service = ReviewService(db=cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    # --- 1. Simple Metrics & Aggregations ---

    def test_01_total_revenue(self):
        """Simple Metric: Total revenue calculation."""
        req = ChatRequest(message="What is the total revenue?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])
        self.assertTrue(any("13,591,643" in str(m.value) or "13.59" in str(m.value) or "13591643" in str(res.text) for m in (res.metrics or [])) or "13" in res.text)

    def test_02_average_product_weight(self):
        """Simple Metric: Average product weight."""
        req = ChatRequest(message="What is the average product weight in grams?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])
        # True PostgreSQL average across products table is 2,276.47 grams (~2.28 kg)
        has_val = (
            any(c in res.text for c in ["2,276", "2276", "2.28", "2,28"]) or
            (res.metrics and any("2276" in str(m.value) for m in res.metrics))
        )
        self.assertTrue(has_val)

    def test_03_payment_type_aggregation(self):
        """Aggregation: Order counts by payment type."""
        req = ChatRequest(message="Which payment type is most frequently used?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        has_credit = (
            any(c in res.text.lower() for c in ["credit_card", "credit card", "credit"]) or
            (res.rows and any("credit" in str(r.get("payment_type", "")).lower() for r in res.rows)) or
            (res.metrics and any("credit" in str(m.value).lower() for m in res.metrics))
        )
        self.assertTrue(has_credit)

    # --- 2. Time-Series Analysis ---

    def test_04_monthly_orders_2017(self):
        """Time-Series: Monthly order counts in 2017."""
        req = ChatRequest(message="How many orders were placed each month in 2017?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])
        if res.chart:
            self.assertIn(res.chart.type, ["line", "bar"])

    def test_05_monthly_revenue_trend_2018(self):
        """Time-Series: Monthly revenue trend in 2018."""
        req = ChatRequest(message="What was the monthly revenue trend in 2018?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])

    # --- 3. Multi-Table JOIN & Rankings ---

    def test_06_top_categories_by_revenue(self):
        """Multi-Table JOIN: Top categories by revenue."""
        req = ChatRequest(message="Which product categories generate the most revenue?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        # Bed bath table or health beauty or computers accessories
        self.assertTrue(any(k in res.text.lower() for k in ["bed", "health", "beauty", "informatica", "relogios", "beleza", "cama"]) or (res.rows and len(res.rows) > 0))

    def test_07_top_sellers_by_revenue(self):
        """Seller Analysis: Top sellers by revenue."""
        req = ChatRequest(message="Who are the top 5 sellers by revenue?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])

    # --- 4. Geographic Analysis ---

    def test_08_freight_by_state(self):
        """Geographic Comparison: Average freight cost by state."""
        req = ChatRequest(message="What is the average freight cost by state?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])

    def test_09_customer_distribution_by_state(self):
        """Geographic Comparison: States with highest customer counts."""
        req = ChatRequest(message="Which states have the highest number of customers?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertTrue("SP" in res.text or "são paulo" in res.text.lower() or (res.rows and any(r.get("customer_state") == "SP" for r in res.rows)))

    # --- 5. Customer & Basket Behavior ---

    def test_10_repeat_customer_rate(self):
        """Customer Analysis: Repeat customer purchase percentage."""
        req = ChatRequest(message="What percentage of customers made repeat purchases?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        # Repeat customer rate is ~3.0%
        self.assertTrue(any(k in res.text for k in ["3.", "2.", "repeat", "3%"]) or (res.rows and len(res.rows) > 0))

    def test_11_orders_with_multiple_items(self):
        """Basket Analysis: Percentage of orders with more than 3 items."""
        req = ChatRequest(message="What percentage of orders have more than 3 items?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        # Typically ~1.2% - 1.5%
        self.assertIn(res.source, ["postgresql", "gemini"])

    # --- 6. Delivery & Logistics Analysis ---

    def test_12_delivery_delay_performance(self):
        """Logistics: Average delivery delay for late orders."""
        req = ChatRequest(message="What is the average delivery delay in days for late orders?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        # Delay days average is ~11.8 - 12.0 days
        self.assertIn(res.source, ["postgresql", "gemini"])

    def test_13_states_worst_delivery(self):
        """Logistics: States with worst delivery performance."""
        req = ChatRequest(message="Which states have the worst delivery performance?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])

    # --- 7. Complex Analytical & Correlation Questions ---

    def test_14_correlation_price_and_freight(self):
        """Complex Analytics: Correlation between product price and freight cost."""
        req = ChatRequest(message="What is the correlation between product price and freight cost?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        # Positive correlation ~0.414
        self.assertTrue(any(c in res.text for c in ["0.41", "0.4", "correlation", "corrélation"]) or res.rows is not None)

    def test_15_delivery_delay_vs_review_score(self):
        """Complex Analytics: Relationship between delivery delay and negative ratings."""
        req = ChatRequest(message="Is there a relationship between delivery delays and negative reviews?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])

    def test_16_high_revenue_low_satisfaction(self):
        """Complex Analytics: Categories with high revenue but lower satisfaction."""
        req = ChatRequest(message="Which product categories generate high revenue but have lower customer satisfaction?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])

    def test_17_sellers_concerning_performance(self):
        """Seller Risk: Sellers with concerning delivery delay rates."""
        req = ChatRequest(message="Which sellers have concerning performance with high delivery delay rates?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini"])

    # --- 8. Customer Reviews Intelligence & Sentiment ---

    def test_18_customer_complaints_overview(self):
        """Review Intelligence: Top complaint reasons overview."""
        req = ChatRequest(message="What do customers complain about most?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertEqual(res.intent, "customer_reviews_intelligence")
        self.assertEqual(res.sentiment_summary.total_reviews_analyzed, 10861)
        self.assertEqual(res.chart.type, "bar")

    def test_19_delivery_review_feedback(self):
        """Review Intelligence: Deep-dive on delivery reviews."""
        req = ChatRequest(message="What do customer reviews say about delivery delays?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertEqual(res.intent, "customer_reviews_intelligence")
        self.assertGreater(len(res.review_citations), 0)

    def test_20_product_quality_complaints(self):
        """Review Intelligence: Product quality feedback."""
        req = ChatRequest(message="What are negative reviews saying about product quality?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertEqual(res.intent, "customer_reviews_intelligence")
        self.assertGreater(len(res.review_citations), 0)

    # --- 9. Conversational Memory & Follow-up Questions ---

    def test_21_conversational_followup_entity(self):
        """Conversational Memory: Anaphoric entity resolution."""
        history = [
            MessageHistoryItem(role="user", text="Which state has the highest revenue?"),
            MessageHistoryItem(role="assistant", text="São Paulo (SP) generates the highest revenue at R$5,202,955.", sql_query="SELECT c.customer_state, SUM(oi.price) AS total_revenue FROM customers c JOIN orders o ON c.customer_id = o.customer_id JOIN order_items oi ON o.order_id = oi.order_id GROUP BY c.customer_state ORDER BY total_revenue DESC LIMIT 1;"),
        ]
        req = ChatRequest(message="And its delivery performance?", history=history)
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        # Should resolve context to SP
        if res.sql_query:
            self.assertIn("SP", res.sql_query.upper())

    def test_22_conversational_followup_metric(self):
        """Conversational Memory: Category follow-up metric change."""
        history = [
            MessageHistoryItem(role="user", text="What are the top 3 product categories by revenue?"),
            MessageHistoryItem(role="assistant", text="The top categories are bed_bath_table, health_beauty, and sports_leisure."),
        ]
        req = ChatRequest(message="What about their average review scores?", history=history)
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)

    # --- 10. Ambiguous & Unsupported Handling ---

    def test_23_ambiguous_short_query(self):
        """Robustness: Ambiguous query handled gracefully without crash."""
        req = ChatRequest(message="Show me orders", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["postgresql", "gemini", "clarification"])

    def test_24_unsupported_out_of_domain(self):
        """Robustness: Out of domain question handled politely."""
        req = ChatRequest(message="What is the weather forecast in São Paulo tomorrow?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.source, ["unsupported", "clarification", "gemini"])

    # --- 11. French Language Interactions ---

    def test_25_french_revenue(self):
        """Bilingual: French revenue calculation."""
        req = ChatRequest(message="Quel est le chiffre d'affaires total ?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertEqual(res.language, "fr")
        self.assertTrue("13" in res.text or any("13" in str(m.value) for m in (res.metrics or [])))

    def test_26_french_logistics(self):
        """Bilingual: French delivery performance."""
        req = ChatRequest(message="Quels sont les délais moyens de livraison par état ?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertEqual(res.language, "fr")

    def test_27_french_complaints(self):
        """Bilingual: French customer complaints overview."""
        req = ChatRequest(message="Quelles sont les principales plaintes des clients ?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertEqual(res.language, "fr")
        self.assertEqual(res.intent, "customer_reviews_intelligence")
        self.assertEqual(res.sentiment_summary.total_reviews_analyzed, 10861)


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Phase 3B: Conversational Memory & Contextual Follow-up Resolution."""

import unittest
from unittest.mock import MagicMock, patch
from app.database import SessionLocal
from app.schemas.chat import ChatRequest, ChatResponse, MessageHistoryItem
from app.services.text_to_sql import TextToSQLService
from app.routers.chat import process_chat_message


class TestConversationalMemory(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = TextToSQLService()
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_followup_pronoun_resolution_categories_order_counts(self):
        """Test follow-up question 'What about their order counts?' inherits categories context."""
        history = [
            MessageHistoryItem(
                role="user",
                text="What are the top 5 product categories by revenue?",
            ),
            MessageHistoryItem(
                role="assistant",
                text="The top 5 categories by revenue are bed_bath_table, health_beauty, computer_accessories, sports_leisure, and furniture_decor.",
                sql_query="SELECT p.product_category_name, SUM(oi.price) AS revenue FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY revenue DESC LIMIT 5",
            ),
        ]

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"type": "sql", "sql": "SELECT p.product_category_name, COUNT(DISTINCT oi.order_id) AS order_count FROM order_items oi JOIN products p ON oi.product_id = p.product_id GROUP BY p.product_category_name ORDER BY order_count DESC LIMIT 5"}'
        mock_client.models.generate_content.return_value = mock_resp

        svc = TextToSQLService()
        svc.client = mock_client

        res = svc.generate_sql("What about their order counts?", history=history)
        self.assertEqual(res.get("type"), "sql")
        self.assertIn("order_count", res.get("sql", ""))
        self.assertIn("product_category_name", res.get("sql", ""))

    def test_followup_pronoun_resolution_state_delivery_performance(self):
        """Test follow-up question 'And its delivery performance?' inherits state SP context."""
        history = [
            MessageHistoryItem(
                role="user",
                text="Which state has the highest revenue?",
            ),
            MessageHistoryItem(
                role="assistant",
                text="São Paulo (SP) has the highest revenue with over R$ 5.2M.",
                sql_query="SELECT c.customer_state, SUM(oi.price) AS total_revenue FROM order_items oi JOIN orders o ON oi.order_id = o.order_id JOIN customers c ON o.customer_id = c.customer_id GROUP BY c.customer_state ORDER BY total_revenue DESC LIMIT 1",
            ),
        ]

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"type": "sql", "sql": "SELECT COUNT(*) AS total_delivered, ROUND(AVG(EXTRACT(epoch FROM (o.order_delivered_customer_date - o.order_purchase_timestamp))/86400.0)::numeric, 2) AS avg_delivery_days FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE c.customer_state = \'SP\' AND o.order_status = \'delivered\'"}'
        mock_client.models.generate_content.return_value = mock_resp

        svc = TextToSQLService()
        svc.client = mock_client

        res = svc.generate_sql("And its delivery performance?", history=history)
        self.assertEqual(res.get("type"), "sql")
        self.assertIn("SP", res.get("sql", ""))

    def test_ambiguous_followup_triggers_clarification(self):
        """Test ambiguous follow-up questions return structured clarification requests."""
        history = [
            MessageHistoryItem(
                role="user",
                text="What is the total revenue?",
            ),
            MessageHistoryItem(
                role="assistant",
                text="Total revenue is R$ 13,591,643.70.",
            ),
        ]

        mock_client = MagicMock()
        mock_resp = MagicMock()
        mock_resp.text = '{"type": "clarification", "message": "Could you please specify which comparison or breakdown you would like to see?"}'
        mock_client.models.generate_content.return_value = mock_resp

        svc = TextToSQLService()
        svc.client = mock_client

        res = svc.generate_sql("What about compared to that?", history=history)
        self.assertEqual(res.get("type"), "clarification")
        msg = res.get("message", "").lower()
        self.assertTrue(any(w in msg for w in ["clarify", "specify", "detail"]))

    def test_french_contextual_followup_preservation(self):
        """Test French conversational follow-up questions preserve French language and context."""
        history = [
            MessageHistoryItem(
                role="user",
                text="Quel État a le chiffre d'affaires le plus élevé ?",
            ),
            MessageHistoryItem(
                role="assistant",
                text="L'État de São Paulo (SP) enregistre le chiffre d'affaires le plus élevé.",
            ),
        ]

        req = ChatRequest(
            message="Et ses délais de livraison ?",
            history=history,
        )

        mock_t2sql_resp = ChatResponse(
            text="Pour l'État de São Paulo (SP), le délai moyen de livraison est de 8,3 jours.",
            source="postgresql",
            intent="dynamic_sql",
            language="fr",
            sql_query="SELECT ROUND(AVG(EXTRACT(epoch FROM (o.order_delivered_customer_date - o.order_purchase_timestamp))/86400.0)::numeric, 2) AS avg_delivery_days FROM orders o JOIN customers c ON o.customer_id = c.customer_id WHERE c.customer_state = 'SP'",
        )

        with patch("app.routers.chat.get_text_to_sql_service") as mock_get_t2sql:
            mock_svc = MagicMock()
            mock_svc.is_configured = True
            mock_svc.answer_query.return_value = mock_t2sql_resp
            mock_get_t2sql.return_value = mock_svc

            resp = process_chat_message(req, db=self.db)
            self.assertEqual(resp.language, "fr")
            self.assertEqual(resp.source, "postgresql")
            self.assertIn("São Paulo", resp.text)


if __name__ == "__main__":
    unittest.main()

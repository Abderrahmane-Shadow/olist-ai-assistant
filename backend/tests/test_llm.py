import unittest
from unittest.mock import MagicMock, patch
from app.database import SessionLocal
from app.schemas.chat import ChatResponse, MetricCard, Breakdown, BreakdownItem, MessageHistoryItem, ChatRequest
from app.services.analytics import AnalyticsService
from app.services.llm import LLMService, _detect_language_heuristic
from app.routers.chat import process_chat_message


class TestLLMService(unittest.TestCase):
    def setUp(self):
        self.db = SessionLocal()
        self.analytics_service = AnalyticsService(self.db)
        self.llm_service = LLMService(api_key="")

    def tearDown(self):
        self.db.close()

    def test_language_detection(self):
        # French questions
        self.assertEqual(_detect_language_heuristic("Quel est le chiffre d'affaires total ?"), "fr")
        self.assertEqual(_detect_language_heuristic("Combien de commandes ont été livrées en retard ?"), "fr")
        self.assertEqual(_detect_language_heuristic("Quelles sont les meilleures catégories de produits ?"), "fr")
        self.assertEqual(_detect_language_heuristic("Quel est le délai moyen de livraison ?"), "fr")

        # English questions
        self.assertEqual(_detect_language_heuristic("What is the total revenue?"), "en")
        self.assertEqual(_detect_language_heuristic("How many orders were delayed?"), "en")
        self.assertEqual(_detect_language_heuristic("Top 10 sellers by revenue"), "en")

    def test_unconfigured_graceful_fallback(self):
        """When GEMINI_API_KEY is not set, service must gracefully fallback to deterministic templates."""
        self.assertFalse(self.llm_service.is_configured)

        # Understand intent returns None for intent so local regex or fallback takes over
        intent, lang = self.llm_service.understand_intent("What is the total revenue?")
        self.assertIsNone(intent)
        self.assertEqual(lang, "en")

        # In French
        intent_fr, lang_fr = self.llm_service.understand_intent("Quel est le chiffre d'affaires ?")
        self.assertIsNone(intent_fr)
        self.assertEqual(lang_fr, "fr")

    def test_explanation_generation_preserves_numbers(self):
        """Explanation must preserve the exact PostgreSQL metrics numbers."""
        postgres_res = self.analytics_service._handle_total_revenue()
        explanation = self.llm_service.generate_explanation(
            user_query="What is the total revenue?",
            intent="total_revenue",
            postgres_result=postgres_res,
            language="en",
        )
        # Check that key numbers from PostgreSQL are present
        self.assertIn("13,591,643.70", explanation)
        self.assertIn("98,666", explanation)

    def test_french_explanation_fallback(self):
        """French queries without active Gemini key return French template."""
        postgres_res = self.analytics_service._handle_total_revenue()
        explanation = self.llm_service.generate_explanation(
            user_query="Quel est le chiffre d'affaires total ?",
            intent="total_revenue",
            postgres_result=postgres_res,
            language="fr",
        )
        self.assertIn("chiffre d'affaires", explanation.lower())

    def test_unsupported_explanation_bilingual(self):
        """Unsupported questions receive clear, honest guidance in user language."""
        en_text = self.llm_service.generate_unsupported_explanation("Can you predict stock prices?", language="en")
        self.assertIn("safe PostgreSQL analytics registry", en_text)

        fr_text = self.llm_service.generate_unsupported_explanation("Pouvez-vous prédire les actions ?", language="fr")
        self.assertIn("chiffre d'affaires total", fr_text)

    @patch("app.routers.chat.get_llm_service")
    def test_chat_router_integration(self, mock_get_llm):
        """Test process_chat_message with history and language parameters."""
        mock_get_llm.return_value = self.llm_service
        req = ChatRequest(
            message="What is the total revenue?",
            conversation_id="conv-123",
            history=[
                MessageHistoryItem(role="user", text="Hello"),
                MessageHistoryItem(role="assistant", text="Welcome to Olist AI Assistant."),
            ]
        )
        resp = process_chat_message(req, db=self.db)
        self.assertEqual(resp.source, "postgresql")
        self.assertIn(resp.intent, ["total_revenue", "dynamic_sql"])
        self.assertEqual(resp.language, "en")
        self.assertIsNotNone(resp.metrics)
        self.assertIn("Revenue", resp.metrics[0].label)

    def test_mock_gemini_api_call(self):
        """Verify behavior with mocked Gemini GenAI client."""
        mock_client = MagicMock()
        mock_response = MagicMock()
        mock_response.text = '{"intent": "total_revenue", "language": "fr"}'
        mock_client.models.generate_content.return_value = mock_response

        service = LLMService(api_key="test_dummy_key")
        service.client = mock_client

        intent, lang = service.understand_intent("Combien avons-nous gagné au total ?")
        self.assertEqual(intent, "total_revenue")
        self.assertEqual(lang, "fr")


if __name__ == "__main__":
    unittest.main()

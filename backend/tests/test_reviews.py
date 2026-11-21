import unittest
from unittest.mock import MagicMock, patch
from app.database import SessionLocal
from app.schemas.chat import ChatRequest, MessageHistoryItem
from app.services.review_service import ReviewService, get_review_service
from app.routers.chat import process_chat_message


class TestReviewService(unittest.TestCase):
    """Unit and integration tests for Customer Reviews Intelligence (RAG + Sentiment Analysis)."""

    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.service = ReviewService(db=cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_is_review_query_detection(self):
        """Test accurate classification of review, feedback, sentiment, and complaint questions."""
        positive_samples = [
            "What do customers complain about most?",
            "What are the main customer reviews regarding delivery delays?",
            "Show me negative reviews for watches",
            "What is the overall sentiment of customer reviews?",
            "What do customers say about product quality?",
            "Why are customers giving 1-star reviews?",
            "Quels sont les avis clients sur la livraison ?",
            "Pourquoi les clients se plaignent ?",
            "Donne-moi les avis négatifs sur le service",
            "Analyse des sentiments des clients",
        ]
        for query in positive_samples:
            self.assertTrue(
                self.service.is_review_query(query),
                f"Failed to identify review query: '{query}'",
            )

        # Pure count or unrelated queries should NOT be classified as review RAG queries
        negative_samples = [
            "Total reviews",
            "How many reviews are there?",
            "total of reviews",
            "What is the total revenue?",
            "Top 5 sellers by revenue",
            "Describe the products table",
        ]
        for query in negative_samples:
            self.assertFalse(
                self.service.is_review_query(query),
                f"Incorrectly classified scalar/unrelated query as review RAG: '{query}'",
            )

    def test_extract_search_parameters(self):
        """Test extraction of sentiment filter, topic, state, and Portuguese search terms."""
        # 1. Delivery complaints
        p1 = self.service.extract_search_parameters("What do customers complain about regarding delivery?")
        self.assertEqual(p1["sentiment_filter"], "negative")
        self.assertEqual(p1["topic"], "delivery")
        self.assertIn("entrega", p1["pt_terms"])
        self.assertIn("atraso", p1["pt_terms"])

        # 2. Positive quality praise
        p2 = self.service.extract_search_parameters("What are the best positive reviews for product quality?")
        self.assertEqual(p2["sentiment_filter"], "positive")
        self.assertEqual(p2["topic"], "quality")
        self.assertIn("qualidade", p2["pt_terms"])

        # 3. Contextual state filter inheritance from history
        history = [
            MessageHistoryItem(role="user", text="Which state has the highest revenue?"),
            MessageHistoryItem(role="assistant", text="São Paulo (SP) leads with the highest revenue."),
        ]
        p3 = self.service.extract_search_parameters("What do customers complain about in this state?", history=history)
        self.assertEqual(p3["state_filter"], "SP")

    def test_compute_sentiment_summary_real_db(self):
        """Test real PostgreSQL calculation of customer sentiment metrics and percentages."""
        sentiment = self.service.compute_sentiment_summary()
        self.assertIsNotNone(sentiment)
        self.assertGreater(sentiment.total_reviews_analyzed, 90000)
        self.assertGreaterEqual(sentiment.average_score, 1.0)
        self.assertLessEqual(sentiment.average_score, 5.0)

        # Validate distribution sums to ~100%
        total_pct = sentiment.positive_percentage + sentiment.neutral_percentage + sentiment.negative_percentage
        self.assertAlmostEqual(total_pct, 100.0, delta=1.5)
        self.assertIn(sentiment.sentiment_label, ["predominantly_positive", "mixed", "predominantly_negative"])

    def test_retrieve_reviews_real_db(self):
        """Test PostgreSQL full-text retrieval returns real review citations with text."""
        # Retrieve negative delivery reviews
        citations = self.service.retrieve_reviews(
            sentiment_filter="negative",
            topic_terms=["atraso", "demora", "prazo", "entrega"],
            limit=4,
        )
        self.assertIsInstance(citations, list)
        self.assertGreater(len(citations), 0)

        for c in citations:
            self.assertIsNotNone(c.review_id)
            self.assertLessEqual(c.score, 2)  # Negative
            self.assertGreater(len(c.comment), 3)
            self.assertEqual(c.sentiment, "negative")

    def test_local_rag_fallback_generation(self):
        """Test deterministic local RAG explanation generation in both English and French."""
        sentiment = self.service.compute_sentiment_summary()
        citations = self.service.retrieve_reviews(sentiment_filter="negative", limit=3)

        # English
        text_en = self.service._generate_local_rag_fallback(
            "What do customers complain about?", citations, sentiment, language="en"
        )
        self.assertIn("Customer Reviews & Sentiment Analysis", text_en)
        self.assertIn("Average Rating", text_en)
        self.assertIn("Review #1", text_en)

        # French
        text_fr = self.service._generate_local_rag_fallback(
            "Quels sont les avis des clients ?", citations, sentiment, language="fr"
        )
        self.assertIn("Analyse des Avis Clients & Sentiments", text_fr)
        self.assertIn("Note moyenne", text_fr)
        self.assertIn("Avis #1", text_fr)

    def test_full_answer_query_pipeline(self):
        """Test full answer_query end-to-end: metrics, breakdown, chart, citations, and text."""
        res = self.service.answer_query("What do customers complain about most regarding delivery?", language="en")
        self.assertIsNotNone(res)
        self.assertEqual(res.intent, "customer_reviews_intelligence")
        self.assertIsNotNone(res.metrics)
        self.assertGreaterEqual(len(res.metrics), 2)
        self.assertIsNotNone(res.breakdown)
        self.assertIsNotNone(res.chart)
        self.assertEqual(res.chart.type, "pie")
        self.assertIsNotNone(res.review_citations)
        self.assertGreater(len(res.review_citations), 0)
        self.assertIsNotNone(res.sentiment_summary)
        self.assertIn("review", res.text.lower())

    def test_chat_router_integration_for_reviews(self):
        """Test POST /chat routing dynamically hands review queries to ReviewService."""
        req = ChatRequest(message="What do customers complain about most?", history=[])
        res = process_chat_message(req, db=self.db)
        self.assertIsNotNone(res)
        self.assertIn(res.intent, ["customer_reviews_intelligence"])
        self.assertIsNotNone(res.review_citations)
        self.assertIsNotNone(res.chart)


    def test_complaint_topic_classification_real_db(self):
        """Test PostgreSQL complaint topic classification across the 8 categories with accurate metrics."""
        result = self.service.classify_complaint_topics()
        self.assertIsNotNone(result)
        self.assertEqual(result["total_negative_reviews"], 10861)
        self.assertEqual(result["total_written_reviews"], 42687)
        self.assertEqual(result["total_platform_reviews"], 99224)
        self.assertAlmostEqual(result["platform_average_score"], 4.09, delta=0.05)
        self.assertEqual(result["total_classified_sum"], 10861)
        self.assertAlmostEqual(result["percentage_sum"], 100.0, delta=0.5)

        categories = result["categories"]
        self.assertEqual(len(categories), 8)
        category_keys = [c["id"] for c in categories]
        expected_keys = [
            "delivery_delays",
            "wrong_missing",
            "damaged_defective",
            "product_quality",
            "seller_communication",
            "refund_payment",
            "packaging_problems",
            "other_complaints",
        ]
        for ek in expected_keys:
            self.assertIn(ek, category_keys)

        # Mutually exclusive sum check: categories must sum to exactly 10,861
        total_primary = sum(c["primary_reviews"] for c in categories)
        self.assertEqual(total_primary, 10861)
        total_pct = sum(c["percentage_of_complaints"] for c in categories)
        self.assertAlmostEqual(total_pct, 100.0, delta=0.5)

        # Check delivery delays is top complaint
        delivery_cat = next(c for c in categories if c["id"] == "delivery_delays")
        self.assertEqual(delivery_cat["primary_reviews"], 3013)
        self.assertAlmostEqual(delivery_cat["percentage_of_complaints"], 27.74, delta=0.1)
        self.assertIsNotNone(delivery_cat["sample_citation"])

        # Check other complaints category exists for unclassified negatives (4,834 with strict Portuguese config)
        other_cat = next(c for c in categories if c["id"] == "other_complaints")
        self.assertEqual(other_cat["primary_reviews"], 4834)
        self.assertAlmostEqual(other_cat["percentage_of_complaints"], 44.51, delta=0.1)

    def test_complaint_overlap_and_multi_label_consistency(self):
        """Test detection and documentation of cross-category multi-label review overlap."""
        result = self.service.classify_complaint_topics()
        categories = result["categories"]

        # Multi-label mentions must be >= primary mutually exclusive counts
        for c in categories:
            self.assertGreaterEqual(c["mention_reviews"], c["primary_reviews"])
            self.assertEqual(c["overlap_count"], c["mention_reviews"] - c["primary_reviews"])

        # Specifically verify wrong_missing has co-occurring mentions with delivery delays
        wm = next(c for c in categories if c["id"] == "wrong_missing")
        self.assertEqual(wm["primary_reviews"], 1643)
        self.assertEqual(wm["mention_reviews"], 2036)
        self.assertEqual(wm["overlap_count"], 393)

        # Verify damaged_defective co-mentions
        dd = next(c for c in categories if c["id"] == "damaged_defective")
        self.assertEqual(dd["primary_reviews"], 327)
        self.assertEqual(dd["mention_reviews"], 751)
        self.assertEqual(dd["overlap_count"], 424)

        # Verify refund_payment with Portuguese phrase queries
        rp = next(c for c in categories if c["id"] == "refund_payment")
        self.assertEqual(rp["primary_reviews"], 221)
        self.assertEqual(rp["mention_reviews"], 415)
        self.assertEqual(rp["overlap_count"], 194)

    def test_percentage_denominators_and_scope_consistency(self):
        """Test that every percentage strictly uses dynamic denominator and uncategorized covers the remainder."""
        result = self.service.classify_complaint_topics()
        categories = result["categories"]
        total_cohort = result["total_negative_reviews"]
        self.assertEqual(total_cohort, 10861)
        self.assertEqual(result["dynamic_denominator"], 10861)

        # Check that individual percentages match primary_reviews / total_cohort
        for c in categories:
            expected_pct = round(c["primary_reviews"] * 100.0 / total_cohort, 2)
            self.assertEqual(c["percentage_of_complaints"], expected_pct)

        # Check that sum of 7 specific categories + other equals total cohort
        specific_categories_sum = sum(c["primary_reviews"] for c in categories if c["id"] != "other_complaints")
        other_cat = next(c for c in categories if c["id"] == "other_complaints")
        self.assertEqual(specific_categories_sum + other_cat["primary_reviews"], total_cohort)
        self.assertEqual(specific_categories_sum, 10861 - 4834)  # 6,027 distinct categorized reviews

    def test_tsquery_phrase_preservation_and_stopword_removal(self):
        """Test _build_tsquery preserves multi-word phrases with <-> and removes isolated Portuguese stopwords."""
        # Multi-word phrase + single keyword + standalone stopword
        query = self.service._build_tsquery(["não recomendo", "defeito", "não", "com"])
        self.assertIn("('não' <-> 'recomendo')", query)
        self.assertIn("defeito", query)
        # Standalone "não" or "com" should not appear as bare unphrased tokens
        self.assertNotIn("| não |", query)
        self.assertFalse(query.endswith("| não"))
        self.assertFalse(query.startswith("não |"))

        # Empty or stopwords only
        empty_query = self.service._build_tsquery(["de", "em", "para"])
        self.assertEqual(empty_query, "")

    def test_is_complaint_overview_detection(self):
        """Test detection of broad complaint questions vs specific topic queries."""
        overview_queries = [
            "What do customers complain about most?",
            "What are the main customer complaints?",
            "Why are customers giving 1-star reviews?",
            "What is the breakdown of customer complaints?",
            "Pourquoi les clients se plaignent ?",
            "Quelles sont les plaintes les plus fréquentes ?",
        ]
        for q in overview_queries:
            params = self.service.extract_search_parameters(q)
            self.assertTrue(params["is_complaint_overview"], f"Failed to mark overview for: {q}")

        specific_queries = [
            "What do customers complain about regarding delivery?",
            "Show me reviews about product quality",
            "Positive reviews about watches",
        ]
        for q in specific_queries:
            params = self.service.extract_search_parameters(q)
            self.assertFalse(params["is_complaint_overview"], f"Incorrectly marked as overview: {q}")

    def test_complaint_overview_answer_query(self):
        """Test answer_query returns structured complaint topic metrics, bar chart, and citations."""
        res = self.service.answer_query("What do customers complain about most?", language="en")
        self.assertIsNotNone(res)
        self.assertEqual(res.intent, "customer_reviews_intelligence")
        # Check chart is a Bar chart showing complaint categories
        self.assertIsNotNone(res.chart)
        self.assertEqual(res.chart.type, "bar")
        self.assertGreaterEqual(len(res.chart.data), 5)
        # Check sentiment summary has transparent cohort scope and platform averages
        self.assertIsNotNone(res.sentiment_summary)
        self.assertIn("Complaints Cohort", res.sentiment_summary.cohort_name)
        self.assertEqual(res.sentiment_summary.platform_average_score, 4.09)
        self.assertEqual(res.sentiment_summary.platform_total_reviews, 99224)
        self.assertEqual(res.sentiment_summary.platform_text_reviews, 42687)
        # Check citations
        self.assertGreater(len(res.review_citations), 0)
        # Check text mentions delivery delays and category percentages
        self.assertIn("Delivery Delays", res.text)
        self.assertIn("4.09", res.text)


if __name__ == "__main__":
    unittest.main()

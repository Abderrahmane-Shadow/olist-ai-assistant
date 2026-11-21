import unittest
from app.database import SessionLocal
from app.services.analytics import AnalyticsService, _format_category_name


class TestOlistAnalytics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.service = AnalyticsService(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    # -------------------------------------------------------------
    # 1. Product Categories Tests
    # -------------------------------------------------------------
    def test_top_categories_revenue(self):
        resp = self.service._handle_top_categories_revenue()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "top_categories_revenue")
        self.assertIsNotNone(resp.metrics)
        self.assertIsNotNone(resp.breakdown)
        self.assertGreater(len(resp.breakdown.items), 0)
        # Verify #1 category is Health & Beauty
        top1 = resp.breakdown.items[0]
        self.assertEqual(top1.label, "Health & Beauty")
        self.assertIn("R$", top1.value)

    def test_top_categories_orders(self):
        resp = self.service._handle_top_categories_orders()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "top_categories_orders")
        # Verify #1 order volume category is Bed, Bath & Table
        top1 = resp.breakdown.items[0]
        self.assertEqual(top1.label, "Bed, Bath & Table")
        self.assertIn("orders", top1.value)

    # -------------------------------------------------------------
    # 2. Sellers Tests
    # -------------------------------------------------------------
    def test_top_sellers_revenue(self):
        resp = self.service._handle_top_sellers_revenue()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "top_sellers_revenue")
        self.assertEqual(len(resp.breakdown.items), 10)
        self.assertIn("Guariba", resp.breakdown.items[0].label)

    def test_top_sellers_orders(self):
        resp = self.service._handle_top_sellers_orders()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "top_sellers_orders")
        self.assertEqual(len(resp.breakdown.items), 10)
        self.assertIn("orders", resp.breakdown.items[0].value)

    def test_seller_avg_price(self):
        resp = self.service._handle_seller_avg_price()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "seller_avg_price")
        self.assertGreater(len(resp.metrics), 0)

    # -------------------------------------------------------------
    # 3. Geography Tests
    # -------------------------------------------------------------
    def test_revenue_by_state(self):
        resp = self.service._handle_revenue_by_state()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "revenue_by_state")
        # São Paulo (SP) must lead revenue
        self.assertEqual(resp.breakdown.items[0].label, "SP")
        self.assertGreater(resp.breakdown.items[0].percentage, 30.0)

    def test_top_cities_revenue(self):
        resp = self.service._handle_top_cities_revenue()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "top_cities_revenue")
        self.assertEqual(len(resp.breakdown.items), 10)
        self.assertIn("Sao Paulo", resp.breakdown.items[0].label)

    def test_customers_by_state(self):
        resp = self.service._handle_customers_by_state()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "customers_by_state")
        self.assertEqual(resp.breakdown.items[0].label, "SP")
        self.assertGreater(resp.breakdown.items[0].percentage, 40.0)

    # -------------------------------------------------------------
    # 4. Logistics Tests
    # -------------------------------------------------------------
    def test_logistics_delivery_time(self):
        resp = self.service._handle_logistics_delivery_time()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "logistics_delivery_time")
        self.assertIn("12.", resp.metrics[0].value)

    def test_logistics_delayed_orders(self):
        resp = self.service._handle_logistics_delayed_orders()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "logistics_delayed_orders")
        self.assertIn("8.1%", resp.metrics[0].value)

    # -------------------------------------------------------------
    # 5. Customers Tests
    # -------------------------------------------------------------
    def test_customers_analysis(self):
        resp = self.service._handle_customers_analysis()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "customers_analysis")
        # 96,096 unique customers
        self.assertEqual(resp.metrics[0].value, "96,096")
        self.assertIn("3.1%", resp.metrics[2].value)

    # -------------------------------------------------------------
    # 6. Time Series Tests
    # -------------------------------------------------------------
    def test_monthly_time_series(self):
        resp = self.service._handle_monthly_time_series()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "monthly_time_series")
        self.assertIn("2017-11", resp.metrics[0].subtext)

    # -------------------------------------------------------------
    # 7. Basic Counts Metrics Tests (Phase 3 Extension)
    # -------------------------------------------------------------
    def test_total_products(self):
        resp = self.service._handle_total_products()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "total_products")
        self.assertEqual(resp.metrics[0].value, "32,951")
        self.assertEqual(resp.metrics[1].value, "73")

    def test_total_sellers(self):
        resp = self.service._handle_total_sellers()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "total_sellers")
        self.assertEqual(resp.metrics[0].value, "3,095")
        self.assertEqual(resp.metrics[1].value, "23")

    def test_total_customers(self):
        resp = self.service._handle_total_customers()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "total_customers")
        self.assertEqual(resp.metrics[0].value, "96,096")
        self.assertEqual(resp.metrics[2].value, "27 States")

    def test_total_categories(self):
        resp = self.service._handle_total_categories()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "total_categories")
        self.assertEqual(resp.metrics[0].value, "73")
        self.assertIn("Health & Beauty", resp.metrics[1].value)

    def test_total_reviews(self):
        resp = self.service._handle_total_reviews()
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "total_reviews")
        self.assertEqual(resp.metrics[0].value, "99,224")
        self.assertEqual(resp.metrics[1].value, "77.1%")

    # -------------------------------------------------------------
    # 8. Intent Classification Tests
    # -------------------------------------------------------------
    def test_intent_classification(self):
        queries = {
            "What is the total revenue?": "total_revenue",
            "Which product category performs best?": "top_categories_revenue",
            "Top categories by number of orders": "top_categories_orders",
            "Who are the top 10 sellers by revenue?": "top_sellers_revenue",
            "Top sellers by order count": "top_sellers_orders",
            "What is the average item price per seller?": "seller_avg_price",
            "Revenue by Brazilian state": "revenue_by_state",
            "Top 10 customer cities by revenue": "top_cities_revenue",
            "How many customers per state?": "customers_by_state",
            "What is the average delivery time in days?": "logistics_delivery_time",
            "How many orders were delayed?": "logistics_delayed_orders",
            "Number of unique customers and repeat customer rate": "customers_analysis",
            "Show me monthly revenue and growth": "monthly_time_series",
            # Basic Counts Tests
            "How many products are there?": "total_products",
            "Total products": "total_products",
            "Total of products": "total_products",
            "How many sellers?": "total_sellers",
            "Number of customers": "total_customers",
            "How many product categories?": "total_categories",
            "Total reviews": "total_reviews",
            # French Variants
            "Combien de produits ?": "total_products",
            "Combien de vendeurs ?": "total_sellers",
            "Nombre de clients": "total_customers",
            "Combien de catégories ?": "total_categories",
            "Total des avis": "total_reviews",
        }
        for q, expected_intent in queries.items():
            intent = self.service.classify_intent(q)
            self.assertEqual(intent, expected_intent, f"Query '{q}' classified as '{intent}', expected '{expected_intent}'")


if __name__ == "__main__":
    unittest.main()

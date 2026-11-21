"""Unit tests for automatic chart detection and formatting service."""

import unittest
from app.services.chart_service import detect_and_build_chart
from app.schemas.chat import ChartConfig, Breakdown, BreakdownItem
from app.services.analytics import AnalyticsService
from app.database import SessionLocal


class TestChartService(unittest.TestCase):
    def test_scalar_result_returns_no_chart(self):
        """Single row / scalar metrics should not generate a chart."""
        columns = ["total_revenue"]
        rows = [{"total_revenue": 13591643.70}]
        chart = detect_and_build_chart(columns, rows, "What is the total revenue?")
        self.assertIsNone(chart)

    def test_single_row_multi_column_returns_no_chart(self):
        """Single row with multiple columns is not suitable for a chart."""
        columns = ["min_price", "avg_price", "max_price"]
        rows = [{"min_price": 0.85, "avg_price": 120.65, "max_price": 6735.00}]
        chart = detect_and_build_chart(columns, rows, "Show price summary")
        self.assertIsNone(chart)

    def test_bar_chart_for_categories(self):
        """Multi-row categories ranking generates a Bar chart."""
        columns = ["product_category_name", "total_revenue"]
        rows = [
            {"product_category_name": "bed_bath_table", "total_revenue": 1045000.50},
            {"product_category_name": "health_beauty", "total_revenue": 1260000.75},
            {"product_category_name": "sports_leisure", "total_revenue": 980000.00},
            {"product_category_name": "furniture_decor", "total_revenue": 730000.25},
        ]
        chart = detect_and_build_chart(columns, rows, "Top product categories by revenue")
        self.assertIsNotNone(chart)
        self.assertIsInstance(chart, ChartConfig)
        self.assertEqual(chart.type, "bar")
        self.assertEqual(chart.x_key, "product_category_name")
        self.assertEqual(chart.y_keys, ["total_revenue"])
        self.assertEqual(chart.unit, "R$")
        self.assertEqual(len(chart.data), 4)
        self.assertEqual(chart.data[0]["product_category_name"], "Bed Bath Table")

    def test_line_chart_for_monthly_time_series(self):
        """Monthly time series generates a Line chart with sorted timeline."""
        columns = ["month_key", "revenue"]
        rows = [
            {"month_key": "2017-03", "revenue": 450000.00},
            {"month_key": "2017-01", "revenue": 120000.00},
            {"month_key": "2017-02", "revenue": 280000.00},
        ]
        chart = detect_and_build_chart(columns, rows, "Monthly revenue in 2017")
        self.assertIsNotNone(chart)
        self.assertEqual(chart.type, "line")
        self.assertEqual(chart.x_key, "month_key")
        self.assertEqual(chart.y_keys, ["revenue"])
        self.assertEqual(chart.unit, "R$")
        # Verify chronological sorting
        self.assertEqual(chart.data[0]["month_key"], "2017-01")
        self.assertEqual(chart.data[1]["month_key"], "2017-02")
        self.assertEqual(chart.data[2]["month_key"], "2017-03")

    def test_pie_chart_for_payment_types_distribution(self):
        """Payment types (small cardinality closed distribution) generates a Pie chart."""
        columns = ["payment_type", "payment_count"]
        rows = [
            {"payment_type": "credit_card", "payment_count": 76795},
            {"payment_type": "boleto", "payment_count": 19784},
            {"payment_type": "voucher", "payment_count": 5775},
            {"payment_type": "debit_card", "payment_count": 1529},
        ]
        chart = detect_and_build_chart(columns, rows, "Which payment methods are most used?")
        self.assertIsNotNone(chart)
        self.assertEqual(chart.type, "pie")
        self.assertEqual(chart.x_key, "payment_type")
        self.assertEqual(chart.y_keys, ["payment_count"])
        self.assertEqual(len(chart.data), 4)

    def test_bar_chart_for_states_revenue(self):
        """Geographic state revenue generates a Bar chart."""
        columns = ["customer_state", "total_revenue"]
        rows = [
            {"customer_state": "SP", "total_revenue": 5200000.00},
            {"customer_state": "RJ", "total_revenue": 1800000.00},
            {"customer_state": "MG", "total_revenue": 1500000.00},
        ]
        chart = detect_and_build_chart(columns, rows, "Revenue by state")
        self.assertIsNotNone(chart)
        self.assertEqual(chart.type, "bar")
        self.assertEqual(chart.x_key, "customer_state")
        self.assertEqual(chart.unit, "R$")

    def test_analytics_service_breakdown_charts(self):
        """Predefined analytics breakdown queries attach charts automatically."""
        db = SessionLocal()
        try:
            svc = AnalyticsService(db)
            
            # Orders by status -> Pie chart
            resp_status = svc.execute_intent("orders_by_status")
            self.assertIsNotNone(resp_status)
            self.assertIsNotNone(resp_status.chart)
            self.assertEqual(resp_status.chart.type, "pie")
            
            # Top categories by revenue -> Bar chart
            resp_cat = svc.execute_intent("top_categories_revenue")
            self.assertIsNotNone(resp_cat)
            self.assertIsNotNone(resp_cat.chart)
            self.assertEqual(resp_cat.chart.type, "bar")

            # Monthly time series -> Line chart
            resp_month = svc.execute_intent("monthly_time_series")
            self.assertIsNotNone(resp_month)
            self.assertIsNotNone(resp_month.chart)
            self.assertEqual(resp_month.chart.type, "line")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()

"""Unit tests for Phase 3B: Safe Database Schema Explorer."""

import unittest
from app.database import SessionLocal
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.schema_service import SchemaService, APPROVED_TABLES
from app.routers.chat import process_chat_message


class TestSchemaExplorer(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        cls.service = SchemaService(cls.db)

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    # -------------------------------------------------------------
    # 1. Database Overview Tests
    # -------------------------------------------------------------
    def test_database_overview_en(self):
        resp = self.service.get_database_overview(language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_overview")
        self.assertIsNotNone(resp.metrics)
        self.assertEqual(resp.metrics[0].value, "9")
        self.assertIn("1.55M", resp.metrics[1].value)
        self.assertIsNotNone(resp.breakdown)
        self.assertEqual(len(resp.breakdown.items), 9)
        # Check all approved tables are mentioned
        for tbl in APPROVED_TABLES:
            self.assertIn(f"`{tbl}`", resp.text)

    def test_database_overview_fr(self):
        resp = self.service.get_database_overview(language="fr")
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_overview")
        self.assertIn("Vue d'ensemble", resp.text)
        self.assertEqual(resp.metrics[0].label, "Tables accessibles")

    # -------------------------------------------------------------
    # 2. Table Structure & Columns Tests
    # -------------------------------------------------------------
    def test_table_structure_orders(self):
        resp = self.service.get_table_structure("orders", language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_table_structure")
        self.assertEqual(resp.metrics[0].value, "public.orders")
        self.assertEqual(resp.metrics[1].value, "8")
        self.assertEqual(resp.metrics[2].value, "order_id")
        self.assertIn("order_status", resp.text)
        self.assertIn("customer_id", resp.text)
        self.assertIn("fk_orders_customers", resp.text)

    def test_table_structure_order_items_composite_pk(self):
        resp = self.service.get_table_structure("order_items", language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertIn("order_id, order_item_id", resp.metrics[2].value)
        self.assertIn("fk_order_items_orders", resp.text)
        self.assertIn("fk_order_items_products", resp.text)
        self.assertIn("fk_order_items_sellers", resp.text)

    def test_table_structure_products(self):
        resp = self.service.get_table_structure("products", language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertIn("product_id", resp.metrics[2].value)
        self.assertIn("product_category_name", resp.text)
        self.assertIn("product_weight_g", resp.text)

    def test_table_structure_customers(self):
        resp = self.service.get_table_structure("customers", language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertIn("customer_id", resp.metrics[2].value)
        self.assertIn("customer_unique_id", resp.text)
        self.assertIn("customer_state", resp.text)

    def test_table_structure_french(self):
        resp = self.service.get_table_structure("commandes", language="fr")
        self.assertEqual(resp.source, "postgresql")
        self.assertIn("Structure de la table `public.orders`", resp.text)
        self.assertEqual(resp.metrics[0].label, "Nom de la table")

    # -------------------------------------------------------------
    # 3. Primary Keys Tests
    # -------------------------------------------------------------
    def test_primary_keys_order_items(self):
        resp = self.service.get_primary_keys("order_items", language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_primary_keys")
        self.assertEqual(resp.metrics[1].value, "order_id, order_item_id")
        self.assertEqual(resp.metrics[1].subtext, "Composite")
        self.assertIn("Composite primary key", resp.text)

    def test_all_primary_keys(self):
        resp = self.service.get_primary_keys(None, language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_primary_keys")
        self.assertIn("**`orders`**: `(order_id)`", resp.text)
        self.assertIn("**`order_items`**: `(order_id, order_item_id)`", resp.text)
        self.assertIn("**`customers`**: `(customer_id)`", resp.text)
        self.assertIn("**`products`**: `(product_id)`", resp.text)
        self.assertIn("**`sellers`**: `(seller_id)`", resp.text)

    # -------------------------------------------------------------
    # 4. Database Relationships Tests
    # -------------------------------------------------------------
    def test_database_relationships_en(self):
        resp = self.service.get_database_relationships(language="en")
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_relationships")
        self.assertIn("5 Active Constraints", resp.metrics[0].value)
        self.assertIn("fk_orders_customers", resp.text)
        self.assertIn("fk_order_items_orders", resp.text)
        self.assertIn("fk_order_items_products", resp.text)
        self.assertIn("fk_order_items_sellers", resp.text)
        self.assertIn("fk_order_payments_orders", resp.text)
        self.assertIn("Customers to Orders", resp.text)
        self.assertIn("Orders to Order Items", resp.text)

    def test_database_relationships_fr(self):
        resp = self.service.get_database_relationships(language="fr")
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_relationships")
        self.assertIn("Relations et Contraintes", resp.text)
        self.assertIn("Clients ➔ Commandes", resp.text)

    # -------------------------------------------------------------
    # 5. Unsupported Table Safe Rejection
    # -------------------------------------------------------------
    def test_unsupported_table_rejection(self):
        resp = self.service.get_table_structure("users", language="en")
        self.assertEqual(resp.source, "unsupported")
        self.assertIn("The table **`users`** does not exist", resp.text)
        self.assertIn("customers", resp.text)

        resp_fr = self.service.get_table_structure("utilisateurs", language="fr")
        self.assertEqual(resp_fr.source, "unsupported")
        self.assertIn("n'existe pas dans le schéma public", resp_fr.text)

    # -------------------------------------------------------------
    # 6. Intent Classification Tests
    # -------------------------------------------------------------
    def test_schema_intent_classification(self):
        test_cases = [
            ("What tables exist in the database?", "schema_overview", None),
            ("Show me the database schema.", "schema_overview", None),
            ("What columns are in the orders table?", "schema_table_structure", "orders"),
            ("Describe the products table.", "schema_table_structure", "products"),
            ("What is the structure of customers?", "schema_table_structure", "customers"),
            ("What are the primary keys of order_items?", "schema_primary_keys", "order_items"),
            ("Primary keys in the database", "schema_primary_keys", None),
            ("Explain relationships between orders, customers, sellers, products, and order_items.", "schema_relationships", None),
            ("What are the relationships between tables?", "schema_relationships", None),
            # French Queries
            ("Quelles tables existent dans la base de données ?", "schema_overview", None),
            ("Montre-moi le schéma de la base de données", "schema_overview", None),
            ("Quelles sont les colonnes de la table des commandes ?", "schema_table_structure", "orders"),
            ("Décris la table des produits.", "schema_table_structure", "products"),
            ("Quelle est la structure des clients ?", "schema_table_structure", "customers"),
            ("Quelles sont les clés primaires de order_items ?", "schema_primary_keys", "order_items"),
            ("Quelles sont les relations entre les tables ?", "schema_relationships", None),
        ]
        for query, expected_intent, expected_table in test_cases:
            intent, tbl = self.service.classify_intent(query)
            self.assertEqual(intent, expected_intent, f"Query '{query}' classified as intent '{intent}', expected '{expected_intent}'")
            if expected_table:
                self.assertEqual(tbl, expected_table, f"Query '{query}' extracted table '{tbl}', expected '{expected_table}'")

    # -------------------------------------------------------------
    # 7. End-to-End Chat Router Integration Tests
    # -------------------------------------------------------------
    def test_e2e_schema_overview(self):
        req = ChatRequest(message="What tables exist in the database?")
        resp = process_chat_message(req, self.db)
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_overview")
        self.assertIsNotNone(resp.metrics)
        self.assertEqual(resp.metrics[0].value, "9")

    def test_e2e_table_structure(self):
        req = ChatRequest(message="What columns are in the orders table?")
        resp = process_chat_message(req, self.db)
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_table_structure")
        self.assertIn("order_id", resp.text)

    def test_e2e_primary_keys(self):
        req = ChatRequest(message="What are the primary keys of order_items?")
        resp = process_chat_message(req, self.db)
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_primary_keys")
        self.assertIn("order_id, order_item_id", resp.metrics[1].value)

    def test_e2e_relationships(self):
        req = ChatRequest(message="Explain relationships between orders, customers, sellers, products, and order_items.")
        resp = process_chat_message(req, self.db)
        self.assertEqual(resp.source, "postgresql")
        self.assertEqual(resp.intent, "schema_relationships")
        self.assertIn("5 Active Constraints", resp.metrics[0].value)


if __name__ == "__main__":
    unittest.main()

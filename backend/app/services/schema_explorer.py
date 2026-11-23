"""Dynamic PostgreSQL Schema Explorer for Olist AI Assistant.

Automatically inspects the live PostgreSQL database catalog:
- Discovers public tables, column names, data types, and nullability
- Identifies primary keys (single and composite)
- Discovers foreign key relationships and canonical join constraints
- Caches discovered schema in-memory with a configurable TTL
- Formats discovered schema metadata for LLM Text-to-SQL prompt injection
"""

import logging
import time
from typing import Any, Dict, List, Optional
from sqlalchemy import text
from sqlalchemy.engine import Engine
from app.database import readonly_engine, engine

logger = logging.getLogger("olist.services.schema_explorer")

# Approved public analytical tables for Olist
APPROVED_ANALYTICAL_TABLES = [
    "customers",
    "geolocation",
    "order_items",
    "order_payments",
    "order_reviews",
    "orders",
    "product_category_name_translation",
    "products",
    "sellers",
]

# Baseline fallback schema if PostgreSQL is completely unreachable during initialization
FALLBACK_SCHEMA_METADATA: Dict[str, Dict[str, Any]] = {
    "orders": {
        "columns": [
            ("order_id", "varchar", False),
            ("customer_id", "varchar", False),
            ("order_status", "varchar", True),
            ("order_purchase_timestamp", "timestamp", True),
            ("order_approved_at", "timestamp", True),
            ("order_delivered_carrier_date", "timestamp", True),
            ("order_delivered_customer_date", "timestamp", True),
            ("order_estimated_delivery_date", "timestamp", True),
        ],
        "primary_keys": ["order_id"],
        "foreign_keys": [("customer_id", "customers", "customer_id")],
    },
    "order_items": {
        "columns": [
            ("order_id", "varchar", False),
            ("order_item_id", "integer", False),
            ("product_id", "varchar", False),
            ("seller_id", "varchar", False),
            ("shipping_limit_date", "timestamp", True),
            ("price", "double precision", False),
            ("freight_value", "double precision", False),
        ],
        "primary_keys": ["order_id", "order_item_id"],
        "foreign_keys": [
            ("order_id", "orders", "order_id"),
            ("product_id", "products", "product_id"),
            ("seller_id", "sellers", "seller_id"),
        ],
    },
    "customers": {
        "columns": [
            ("customer_id", "varchar", False),
            ("customer_unique_id", "varchar", False),
            ("customer_zip_code_prefix", "integer", True),
            ("customer_city", "varchar", True),
            ("customer_state", "varchar", True),
        ],
        "primary_keys": ["customer_id"],
        "foreign_keys": [],
    },
    "products": {
        "columns": [
            ("product_id", "varchar", False),
            ("product_category_name", "varchar", True),
            ("product_name_lenght", "double precision", True),
            ("product_description_lenght", "double precision", True),
            ("product_photos_qty", "double precision", True),
            ("product_weight_g", "double precision", True),
            ("product_length_cm", "double precision", True),
            ("product_height_cm", "double precision", True),
            ("product_width_cm", "double precision", True),
        ],
        "primary_keys": ["product_id"],
        "foreign_keys": [],
    },
    "sellers": {
        "columns": [
            ("seller_id", "varchar", False),
            ("seller_zip_code_prefix", "integer", True),
            ("seller_city", "varchar", True),
            ("seller_state", "varchar", True),
        ],
        "primary_keys": ["seller_id"],
        "foreign_keys": [],
    },
    "order_payments": {
        "columns": [
            ("order_id", "varchar", False),
            ("payment_sequential", "integer", False),
            ("payment_type", "varchar", True),
            ("payment_installments", "integer", True),
            ("payment_value", "double precision", False),
        ],
        "primary_keys": ["order_id", "payment_sequential"],
        "foreign_keys": [("order_id", "orders", "order_id")],
    },
    "order_reviews": {
        "columns": [
            ("review_id", "varchar", True),
            ("order_id", "varchar", False),
            ("review_score", "integer", False),
            ("review_comment_title", "varchar", True),
            ("review_comment_message", "text", True),
            ("review_creation_date", "timestamp", True),
            ("review_answer_timestamp", "timestamp", True),
        ],
        "primary_keys": ["review_id"],
        "foreign_keys": [("order_id", "orders", "order_id")],
    },
    "product_category_name_translation": {
        "columns": [
            ("product_category_name", "varchar", False),
            ("product_category_name_english", "varchar", True),
        ],
        "primary_keys": ["product_category_name"],
        "foreign_keys": [],
    },
    "geolocation": {
        "columns": [
            ("geolocation_zip_code_prefix", "integer", True),
            ("geolocation_lat", "double precision", True),
            ("geolocation_lng", "double precision", True),
            ("geolocation_city", "varchar", True),
            ("geolocation_state", "varchar", True),
        ],
        "primary_keys": [],
        "foreign_keys": [],
    },
}


class SchemaExplorer:
    """Introspects and caches live PostgreSQL database schema metadata for dynamic SQL generation."""

    def __init__(self, db_engine: Optional[Engine] = None, ttl_seconds: int = 3600):
        self.engine = db_engine or readonly_engine or engine
        self.ttl_seconds = ttl_seconds
        self._cached_schema: Optional[Dict[str, Any]] = None
        self._last_refresh: float = 0.0

    def get_schema_metadata(self, force_refresh: bool = False) -> Dict[str, Any]:
        """Fetch discovered PostgreSQL schema metadata, leveraging in-memory TTL caching."""
        now = time.time()
        if not force_refresh and self._cached_schema and (now - self._last_refresh < self.ttl_seconds):
            return self._cached_schema

        try:
            discovered = self._inspect_live_schema()
            if discovered:
                self._cached_schema = discovered
                self._last_refresh = now
                logger.info("Successfully refreshed dynamic schema metadata for %d tables", len(discovered))
                return self._cached_schema
        except Exception as exc:
            logger.warning("Failed to inspect live PostgreSQL schema: %s. Using cached or fallback schema.", exc)

        if self._cached_schema:
            return self._cached_schema

        logger.info("Using baseline fallback schema metadata")
        self._cached_schema = FALLBACK_SCHEMA_METADATA
        self._last_refresh = now
        return self._cached_schema

    def _inspect_live_schema(self) -> Dict[str, Dict[str, Any]]:
        """Query information_schema and pg_catalog to introspect tables, columns, PKs, and FKs."""
        schema_dict: Dict[str, Dict[str, Any]] = {}

        # 1. Inspect Columns
        cols_query = """
            SELECT table_name, column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public'
            ORDER BY table_name, ordinal_position;
        """

        # 2. Inspect Primary Keys
        pks_query = """
            SELECT tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema = 'public'
            ORDER BY tc.table_name, kcu.ordinal_position;
        """

        # 3. Inspect Foreign Keys
        fks_query = """
            SELECT
                kcu.table_name AS foreign_table,
                kcu.column_name AS foreign_column,
                ccu.table_name AS primary_table,
                ccu.column_name AS primary_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
              AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON ccu.constraint_name = tc.constraint_name
              AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'public';
        """

        with self.engine.connect() as conn:
            # Columns
            col_res = conn.execute(text(cols_query)).fetchall()
            for t_name, c_name, d_type, is_null in col_res:
                if t_name in APPROVED_ANALYTICAL_TABLES:
                    if t_name not in schema_dict:
                        schema_dict[t_name] = {
                            "columns": [],
                            "primary_keys": [],
                            "foreign_keys": [],
                        }
                    schema_dict[t_name]["columns"].append((c_name, d_type, is_null == "YES"))

            # Primary Keys
            try:
                pk_res = conn.execute(text(pks_query)).fetchall()
                for t_name, pk_col in pk_res:
                    if t_name in schema_dict:
                        schema_dict[t_name]["primary_keys"].append(pk_col)
            except Exception as pk_err:
                logger.warning("Could not introspect primary keys: %s", pk_err)

            # Foreign Keys
            try:
                fk_res = conn.execute(text(fks_query)).fetchall()
                for f_tbl, f_col, p_tbl, p_col in fk_res:
                    if f_tbl in schema_dict and p_tbl in APPROVED_ANALYTICAL_TABLES:
                        schema_dict[f_tbl]["foreign_keys"].append((f_col, p_tbl, p_col))
            except Exception as fk_err:
                logger.warning("Could not introspect foreign keys: %s", fk_err)

        return schema_dict

    def format_schema_for_llm(self) -> str:
        """Render discovered schema into a token-efficient, unambiguous prompt block for LLMs."""
        schema_data = self.get_schema_metadata()
        lines = ["LIVE DATABASE SCHEMA (PostgreSQL / public):"]

        for tbl_name in sorted(schema_data.keys()):
            tbl_info = schema_data[tbl_name]
            cols_def = []
            pks = set(tbl_info.get("primary_keys", []))
            
            for col_name, data_type, is_null in tbl_info.get("columns", []):
                pk_marker = " [PK]" if col_name in pks else ""
                cols_def.append(f"{col_name} ({data_type}{pk_marker})")
            
            fks = tbl_info.get("foreign_keys", [])
            fk_notes = [f"{f_col} -> {p_tbl}.{p_col}" for f_col, p_tbl, p_col in fks]
            fk_str = f" | FKs: {', '.join(fk_notes)}" if fk_notes else ""

            lines.append(f"- {tbl_name}: {', '.join(cols_def)}{fk_str}")

        return "\n".join(lines)


_global_schema_explorer: Optional[SchemaExplorer] = None


def get_schema_explorer() -> SchemaExplorer:
    """Dependency helper for singleton SchemaExplorer."""
    global _global_schema_explorer
    if _global_schema_explorer is None:
        _global_schema_explorer = SchemaExplorer()
    return _global_schema_explorer

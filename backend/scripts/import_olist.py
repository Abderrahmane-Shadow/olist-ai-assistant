"""Olist E-Commerce Dataset Importer for PostgreSQL.

Loads raw Olist Brazilian E-Commerce CSV files into PostgreSQL database `olist_db`
under schema `public` with detailed transactional fidelity, appropriate data types,
explicit transaction commits, and memory-efficient chunked streaming.
"""

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
from sqlalchemy import (
    DateTime,
    Float,
    Integer,
    Numeric,
    String,
    Text,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.types import TypeEngine

# Add backend directory to sys.path to load configuration
BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.config import get_settings

    settings = get_settings()
    DEFAULT_DATABASE_URL = settings.sqlalchemy_database_url
except Exception:
    DEFAULT_DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/olist_db",
    )

# Candidate directories for raw CSV files
DEFAULT_RAW_DIR_CANDIDATES = [
    Path(BACKEND_DIR).parent / "data" / "raw",
    Path(r"D:\data analyst projects\Olist_Analytics\data\raw"),
    Path(BACKEND_DIR) / "data" / "raw",
]


def resolve_data_directory(custom_path: Optional[str] = None) -> Path:
    """Resolve and validate the directory containing raw Olist CSV files."""
    if custom_path:
        p = Path(custom_path).resolve()
        if p.exists() and p.is_dir():
            return p
        raise FileNotFoundError(f"Specified data directory does not exist: {custom_path}")

    # Check candidates
    for candidate in DEFAULT_RAW_DIR_CANDIDATES:
        if candidate.exists() and candidate.is_dir():
            csv_count = len(list(candidate.glob("*.csv")))
            if csv_count > 0:
                return candidate.resolve()

    raise FileNotFoundError(
        "Could not automatically locate raw Olist CSV directory. "
        "Please provide --data-dir argument pointing to data/raw/."
    )


# Definition of all 9 canonical Olist tables, files, date columns, and SQL types
TABLE_CONFIGS: List[Dict] = [
    {
        "table_name": "customers",
        "csv_filename": "olist_customers_dataset.csv",
        "date_columns": [],
        "dtypes": {
            "customer_id": String(32),
            "customer_unique_id": String(32),
            "customer_zip_code_prefix": Integer(),
            "customer_city": String(100),
            "customer_state": String(5),
        },
    },
    {
        "table_name": "sellers",
        "csv_filename": "olist_sellers_dataset.csv",
        "date_columns": [],
        "dtypes": {
            "seller_id": String(32),
            "seller_zip_code_prefix": Integer(),
            "seller_city": String(100),
            "seller_state": String(5),
        },
    },
    {
        "table_name": "product_category_name_translation",
        "csv_filename": "product_category_name_translation.csv",
        "date_columns": [],
        "dtypes": {
            "product_category_name": String(100),
            "product_category_name_english": String(100),
        },
    },
    {
        "table_name": "products",
        "csv_filename": "olist_products_dataset.csv",
        "date_columns": [],
        "dtypes": {
            "product_id": String(32),
            "product_category_name": String(100),
            "product_name_lenght": Float(),
            "product_description_lenght": Float(),
            "product_photos_qty": Float(),
            "product_weight_g": Float(),
            "product_length_cm": Float(),
            "product_height_cm": Float(),
            "product_width_cm": Float(),
        },
    },
    {
        "table_name": "orders",
        "csv_filename": "olist_orders_dataset.csv",
        "date_columns": [
            "order_purchase_timestamp",
            "order_approved_at",
            "order_delivered_carrier_date",
            "order_delivered_customer_date",
            "order_estimated_delivery_date",
        ],
        "dtypes": {
            "order_id": String(32),
            "customer_id": String(32),
            "order_status": String(30),
            "order_purchase_timestamp": DateTime(),
            "order_approved_at": DateTime(),
            "order_delivered_carrier_date": DateTime(),
            "order_delivered_customer_date": DateTime(),
            "order_estimated_delivery_date": DateTime(),
        },
    },
    {
        "table_name": "order_items",
        "csv_filename": "olist_order_items_dataset.csv",
        "date_columns": ["shipping_limit_date"],
        "dtypes": {
            "order_id": String(32),
            "order_item_id": Integer(),
            "product_id": String(32),
            "seller_id": String(32),
            "shipping_limit_date": DateTime(),
            "price": Numeric(10, 2),
            "freight_value": Numeric(10, 2),
        },
    },
    {
        "table_name": "order_payments",
        "csv_filename": "olist_order_payments_dataset.csv",
        "date_columns": [],
        "dtypes": {
            "order_id": String(32),
            "payment_sequential": Integer(),
            "payment_type": String(30),
            "payment_installments": Integer(),
            "payment_value": Numeric(10, 2),
        },
    },
    {
        "table_name": "order_reviews",
        "csv_filename": "olist_order_reviews_dataset.csv",
        "date_columns": ["review_creation_date", "review_answer_timestamp"],
        "dtypes": {
            "review_id": String(32),
            "order_id": String(32),
            "review_score": Integer(),
            "review_comment_title": String(255),
            "review_comment_message": Text(),
            "review_creation_date": DateTime(),
            "review_answer_timestamp": DateTime(),
        },
    },
    {
        "table_name": "geolocation",
        "csv_filename": "olist_geolocation_dataset.csv",
        "date_columns": [],
        "dtypes": {
            "geolocation_zip_code_prefix": Integer(),
            "geolocation_lat": Float(),
            "geolocation_lng": Float(),
            "geolocation_city": String(100),
            "geolocation_state": String(5),
        },
    },
]


def test_connection(engine: Engine) -> bool:
    """Verify database connection before starting import."""
    try:
        with engine.connect() as conn:
            res = conn.execute(text("SELECT current_database(), current_user;")).fetchone()
            print(f"[OK] Database connection verified: database='{res[0]}', user='{res[1]}'")
        return True
    except Exception as exc:
        print(f"\n[ERROR] Database connection failed: {exc}")
        return False


def import_dataset_table(
    engine: Engine,
    csv_path: Path,
    config: Dict,
    chunksize: int = 25000,
    if_exists: str = "replace",
) -> Tuple[int, int]:
    """Read CSV in chunks and stream into PostgreSQL with explicit transaction commits."""
    table_name = config["table_name"]
    date_cols = config.get("date_columns", [])
    dtypes: Dict[str, TypeEngine] = config.get("dtypes", {})

    print(f"\n" + "-" * 75)
    print(f"-> TABLE: 'public.{table_name}'")
    print(f"   CSV File   : {csv_path.name}")
    print(f"   Chunk Size : {chunksize:,} rows")
    print(f"   Mode       : {if_exists}")

    total_rows_read = 0
    total_rows_inserted = 0
    start_time = time.time()
    first_chunk = True

    # Read CSV in chunks for memory safety
    reader = pd.read_csv(
        csv_path,
        chunksize=chunksize,
        encoding="utf-8",
        low_memory=False,
    )

    for i, chunk in enumerate(reader, start=1):
        chunk_read_count = len(chunk)
        total_rows_read += chunk_read_count

        # Convert date columns with coerce to handle missing or irregular timestamps
        for col in date_cols:
            if col in chunk.columns:
                chunk[col] = pd.to_datetime(chunk[col], errors="coerce")

        # Strip whitespace from text/object columns and restore genuine None/NaN
        text_cols = chunk.select_dtypes(include=["object", "string"]).columns
        for col in text_cols:
            chunk[col] = chunk[col].astype(str).str.strip()
            chunk[col] = chunk[col].replace({"nan": None, "None": None, "": None})

        # Insert mode: first chunk applies if_exists ('replace' or 'append'), subsequent chunks append
        current_mode = if_exists if first_chunk else "append"

        # Use an explicit transaction block with engine.begin() to guarantee commits
        with engine.begin() as connection:
            chunk.to_sql(
                name=table_name,
                con=connection,
                schema="public",
                if_exists=current_mode,
                index=False,
                dtype=dtypes,
                method=None,  # Standard parameterized executemany avoids parameter limit
            )

        first_chunk = False
        total_rows_inserted += chunk_read_count
        elapsed = time.time() - start_time
        rate = total_rows_inserted / elapsed if elapsed > 0 else 0
        print(
            f"   Chunk {i}: read {chunk_read_count:,} | inserted {total_rows_inserted:,} | "
            f"{rate:,.0f} rows/s",
            end="\r",
        )

    elapsed = time.time() - start_time
    print(
        f"\n   [SUCCESS] '{table_name}': {total_rows_read:,} rows read, "
        f"{total_rows_inserted:,} rows inserted in {elapsed:.2f}s"
    )
    return total_rows_read, total_rows_inserted


def create_indexes(engine: Engine):
    """Create essential performance indexes for relational joins and analytical queries."""
    index_queries = [
        "CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON public.orders(customer_id);",
        "CREATE INDEX IF NOT EXISTS idx_orders_purchase_timestamp ON public.orders(order_purchase_timestamp);",
        "CREATE INDEX IF NOT EXISTS idx_order_items_order_id ON public.order_items(order_id);",
        "CREATE INDEX IF NOT EXISTS idx_order_items_product_id ON public.order_items(product_id);",
        "CREATE INDEX IF NOT EXISTS idx_order_items_seller_id ON public.order_items(seller_id);",
        "CREATE INDEX IF NOT EXISTS idx_order_payments_order_id ON public.order_payments(order_id);",
        "CREATE INDEX IF NOT EXISTS idx_order_reviews_order_id ON public.order_reviews(order_id);",
        "CREATE INDEX IF NOT EXISTS idx_products_category ON public.products(product_category_name);",
        "CREATE INDEX IF NOT EXISTS idx_customers_state ON public.customers(customer_state);",
        "CREATE INDEX IF NOT EXISTS idx_sellers_state ON public.sellers(seller_state);",
    ]

    print("\n-> Creating performance indexes...")
    with engine.begin() as conn:
        for q in index_queries:
            try:
                conn.execute(text(q))
            except Exception as e:
                print(f"   [NOTICE] Index creation warning: {e}")
    print("   [OK] Performance indexes established.")


def verify_database_counts(engine: Engine, expected_counts: Dict[str, int]):
    """Query PostgreSQL using SQLAlchemy to verify actual row counts against CSV records."""
    print("\n" + "=" * 80)
    print("POST-IMPORT DATABASE VERIFICATION")
    print("=" * 80)
    print(f"{'Table Name':<35} | {'CSV Rows':<12} | {'DB Rows':<12} | {'Status'}")
    print("-" * 75)

    all_matched = True
    with engine.connect() as conn:
        for table_name, expected_row_count in expected_counts.items():
            try:
                db_count = conn.execute(text(f'SELECT count(*) FROM public."{table_name}";')).scalar()
                if db_count == expected_row_count:
                    status = "[MATCHED]"
                else:
                    status = f"[MISMATCH (diff: {db_count - expected_row_count:+})]"
                    all_matched = False
                print(f"{table_name:<35} | {expected_row_count:<12,} | {db_count:<12,} | {status}")
            except Exception as e:
                all_matched = False
                print(f"{table_name:<35} | {expected_row_count:<12,} | {'ERROR':<12} | [FAILED: {e}]")

    print("-" * 75)
    if all_matched:
        print("[VERIFICATION PASSED] All tables match exact CSV row counts!")
    else:
        print("[VERIFICATION WARNING] One or more tables had row count discrepancies.")


def run_import(
    database_url: str,
    data_dir: Path,
    chunksize: int = 25000,
    if_exists: str = "replace",
):
    """Main orchestrator for importing all Olist datasets."""
    print("=" * 80)
    print("OLIST E-COMMERCE DATASET IMPORTER")
    print(f"Source Directory : {data_dir}")
    print(f"Target Database  : {database_url.split('@')[-1] if '@' in database_url else database_url}")
    print(f"Target Schema    : public")
    print(f"Mode             : {if_exists}")
    print("=" * 80)

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    if not test_connection(engine):
        print("\n[ABORTED] Please ensure PostgreSQL is running and credentials in .env are correct.")
        sys.exit(1)

    total_read_all = 0
    total_inserted_all = 0
    expected_counts: Dict[str, int] = {}
    start_total_time = time.time()

    for config in TABLE_CONFIGS:
        table_name = config["table_name"]
        csv_file = data_dir / config["csv_filename"]

        if not csv_file.exists():
            print(f"\n[WARNING] Missing file: {csv_file.name}. Skipping table '{table_name}'.")
            continue

        try:
            read_cnt, inserted_cnt = import_dataset_table(
                engine=engine,
                csv_path=csv_file,
                config=config,
                chunksize=chunksize,
                if_exists=if_exists,
            )
            total_read_all += read_cnt
            total_inserted_all += inserted_cnt
            expected_counts[table_name] = read_cnt
        except Exception as err:
            print(f"\n[ERROR] Failed to import '{table_name}': {err}")
            raise err

    # Apply database indexes
    create_indexes(engine)

    # Post-import verification
    verify_database_counts(engine, expected_counts)

    total_elapsed = time.time() - start_total_time
    print("\n" + "=" * 80)
    print(
        f"IMPORT SUMMARY: {total_read_all:,} rows read | "
        f"{total_inserted_all:,} rows inserted across {len(expected_counts)} tables in {total_elapsed:.1f}s"
    )
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(
        description="Import Olist E-Commerce dataset into PostgreSQL."
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default=None,
        help="Directory containing the raw Olist CSV files.",
    )
    parser.add_argument(
        "--database-url",
        type=str,
        default=DEFAULT_DATABASE_URL,
        help="SQLAlchemy PostgreSQL database connection URL.",
    )
    parser.add_argument(
        "--chunksize",
        type=int,
        default=25000,
        help="Number of rows per chunk (default: 25000).",
    )
    parser.add_argument(
        "--if-exists",
        choices=["replace", "append", "fail"],
        default="replace",
        help="Action if table already exists (default: replace).",
    )

    args = parser.parse_args()

    try:
        resolved_data_dir = resolve_data_directory(args.data_dir)
    except FileNotFoundError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)

    run_import(
        database_url=args.database_url,
        data_dir=resolved_data_dir,
        chunksize=args.chunksize,
        if_exists=args.if_exists,
    )


if __name__ == "__main__":
    main()

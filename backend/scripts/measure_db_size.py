"""
Comprehensive Olist Dataset and Multi-User Persistence Sizing Audit
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlalchemy
from sqlalchemy import text
from app.database import SessionLocal

def measure():
    db = SessionLocal()
    tables = [
        "geolocation",
        "order_items",
        "order_payments",
        "orders",
        "order_reviews",
        "customers",
        "products",
        "sellers",
        "product_category_name_translation",
    ]

    print("=================================================================")
    print("           OLIST DATASET ROW COUNT AND SIZE AUDIT               ")
    print("=================================================================")
    total_rows = 0
    for tbl in tables:
        count = db.execute(text(f"SELECT COUNT(*) FROM public.{tbl}")).scalar()
        size_pretty = db.execute(text(f"SELECT pg_size_pretty(pg_total_relation_size('public.{tbl}'))")).scalar()
        bytes_size = db.execute(text(f"SELECT pg_total_relation_size('public.{tbl}')")).scalar()
        total_rows += count
        print(f" - {tbl:<35}: {count:>10,} rows | {size_pretty:>10} ({bytes_size:>12,} bytes)")

    print("-----------------------------------------------------------------")
    print(f" TOTAL ROWS ACROSS 9 APPROVED TABLES : {total_rows:>10,} rows")
    
    total_db_size = db.execute(text("SELECT pg_size_pretty(pg_database_size(current_database()))")).scalar()
    total_bytes = db.execute(text("SELECT pg_database_size(current_database())")).scalar()
    print(f" DATABASE TOTAL PHYSICAL SIZE       : {total_db_size} ({total_bytes:,} bytes)")
    print("=================================================================")
    db.close()

if __name__ == "__main__":
    measure()

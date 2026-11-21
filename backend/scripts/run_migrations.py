import logging
import traceback
from pathlib import Path
from sqlalchemy import text
from app.database import engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("olist.migrations")

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


def run_migrations():
    logger.info("Starting database migrations...")
    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not sql_files:
        logger.warning("No migration files found in %s", MIGRATIONS_DIR)
        return

    with engine.connect() as conn:
        raw_conn = conn.connection
        for sql_file in sql_files:
            logger.info("Executing migration: %s", sql_file.name)
            sql_content = sql_file.read_text(encoding="utf-8")
            try:
                # Use raw psycopg cursor for multi-statement DDL scripts
                with raw_conn.cursor() as cur:
                    cur.execute(sql_content)
                raw_conn.commit()
                logger.info("Successfully applied %s", sql_file.name)
            except Exception as e:
                raw_conn.rollback()
                logger.error("Migration %s failed: %s", sql_file.name, e)
                traceback.print_exc()
                raise

    logger.info("All database migrations applied successfully!")


if __name__ == "__main__":
    run_migrations()

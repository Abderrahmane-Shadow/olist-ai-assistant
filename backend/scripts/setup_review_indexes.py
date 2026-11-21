import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import engine
from sqlalchemy import text

def create_review_search_index():
    print("Creating GIN index for Portuguese full-text search on order_reviews...")
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_order_reviews_fts_pt 
            ON order_reviews 
            USING gin (to_tsvector('portuguese', COALESCE(review_comment_title, '') || ' ' || COALESCE(review_comment_message, '')));
        """))
        conn.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_order_reviews_score 
            ON order_reviews (review_score);
        """))
    print("Review indexes created successfully.")

if __name__ == "__main__":
    create_review_search_index()

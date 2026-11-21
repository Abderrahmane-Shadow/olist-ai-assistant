import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()

print("--- ORDER REVIEWS OVERVIEW ---")
stats = db.execute(text("""
    SELECT 
        COUNT(*) as total_reviews,
        COUNT(review_comment_message) as with_message,
        COUNT(review_comment_title) as with_title,
        COUNT(CASE WHEN review_comment_message IS NOT NULL OR review_comment_title IS NOT NULL THEN 1 END) as with_text,
        ROUND(AVG(review_score)::numeric, 2) as avg_score,
        COUNT(CASE WHEN review_score <= 2 THEN 1 END) as negative_reviews,
        COUNT(CASE WHEN review_score = 3 THEN 1 END) as neutral_reviews,
        COUNT(CASE WHEN review_score >= 4 THEN 1 END) as positive_reviews
    FROM order_reviews;
""")).mappings().first()

for k, v in stats.items():
    print(f"  {k}: {v}")

print("\n--- COLUMNS ---")
cols = db.execute(text("""
    SELECT column_name, data_type 
    FROM information_schema.columns 
    WHERE table_name = 'order_reviews'
    ORDER BY ordinal_position;
""")).fetchall()
for col in cols:
    print(f"  {col[0]} ({col[1]})")

print("\n--- SAMPLE REVIEWS WITH MESSAGES ---")
samples = db.execute(text("""
    SELECT r.review_id, r.order_id, r.review_score, r.review_comment_title, r.review_comment_message,
           c.customer_state, p.product_category_name
    FROM order_reviews r
    LEFT JOIN orders o ON r.order_id = o.order_id
    LEFT JOIN customers c ON o.customer_id = c.customer_id
    LEFT JOIN order_items oi ON o.order_id = oi.order_id
    LEFT JOIN products p ON oi.product_id = p.product_id
    WHERE r.review_comment_message IS NOT NULL
    LIMIT 3;
""")).mappings().fetchall()
for s in samples:
    print(f"  Score: {s['review_score']} | Cat: {s['product_category_name']} | State: {s['customer_state']}")
    print(f"  Title: {s['review_comment_title']}")
    print(f"  Message: {s['review_comment_message'][:120]}...\n")

# Check if PostgreSQL has pg_trgm or full text search capabilities
print("\n--- EXTENSIONS & FULL TEXT SEARCH ---")
exts = db.execute(text("SELECT extname FROM pg_extension;")).fetchall()
print("Installed extensions:", [e[0] for e in exts])
cfg = db.execute(text("SELECT cfgname FROM pg_ts_config WHERE cfgname IN ('portuguese', 'simple', 'english');")).fetchall()
print("Available ts_configs:", [c[0] for c in cfg])

# Test Portuguese full-text search on reviews
test_fts = db.execute(text("""
    SELECT review_id, review_score, review_comment_message
    FROM order_reviews
    WHERE to_tsvector('portuguese', COALESCE(review_comment_message, '')) @@ plainto_tsquery('portuguese', 'demora entrega atraso')
    LIMIT 3;
""")).mappings().fetchall()
print("\n--- FTS MATCHES FOR 'demora entrega atraso' (delivery delay) ---")
for t in test_fts:
    print(f"  [{t['review_score']}*] {t['review_comment_message']}")

# Test Portuguese full-text search with OR
print("\n--- FTS MATCHES TEST ---")
ts_and = db.execute(text("SELECT count(*) FROM order_reviews WHERE to_tsvector('portuguese', COALESCE(review_comment_message, '')) @@ plainto_tsquery('portuguese', 'atraso demora prazo entrega');")).scalar()
ts_or = db.execute(text("SELECT count(*) FROM order_reviews WHERE to_tsvector('portuguese', COALESCE(review_comment_message, '')) @@ to_tsquery('portuguese', 'atraso | demora | prazo | entrega');")).scalar()
print(f"AND matches: {ts_and}, OR matches: {ts_or}")

# Check indexes
print("\n--- INDEXES ON order_reviews ---")
idxs = db.execute(text("SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'order_reviews';")).fetchall()
for i in idxs:
    print(f"  {i[0]}: {i[1]}")

db.close()

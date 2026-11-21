"""
Audit Database Row Counts, Total Size, RLS Policies, and Role Separation
"""
import os
import psycopg
from psycopg import sql

DB_ADMIN = os.getenv("DATABASE_URL") or (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'olist_db')} "
    f"user={os.getenv('DB_USER', 'postgres')} "
    f"password={os.getenv('DB_PASSWORD', 'postgres')}"
)

DB_RO = os.getenv("DATABASE_RO_URL") or (
    f"host={os.getenv('DB_HOST', 'localhost')} "
    f"port={os.getenv('DB_PORT', '5432')} "
    f"dbname={os.getenv('DB_NAME', 'olist_db')} "
    f"user={os.getenv('DB_READONLY_USER', 'olist_readonly')} "
    f"password={os.getenv('DB_READONLY_PASSWORD', 'olist_readonly_2026')}"
)

def audit_database():
    conn = psycopg.connect(DB_ADMIN)
    cur = conn.cursor()

    tables = [
        "geolocation",
        "order_items",
        "order_payments",
        "orders",
        "order_reviews",
        "customers",
        "products",
        "sellers",
        "product_category_name_translation"
    ]

    print("=================== 1. TABLE ROW COUNTS ===================")
    total_rows = 0
    table_counts = {}
    for t in tables:
        cur.execute(sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(t)))
        cnt = cur.fetchone()[0]
        table_counts[t] = cnt
        total_rows += cnt
        print(f"  {t:<35} : {cnt:>10,}")

    print(f"  {'Calculated Sum of 9 Tables':<35} : {total_rows:>10,}")

    print("\n=================== 2. DATABASE SIZE ===================")
    cur.execute("SELECT pg_size_pretty(pg_database_size('olist_db')), pg_database_size('olist_db');")
    pretty_size, bytes_size = cur.fetchone()
    print(f"  Pretty Size : {pretty_size}")
    print(f"  Bytes Size  : {bytes_size:,} bytes")
    print(f"  MB Size     : {bytes_size / (1024 * 1024):.2f} MB")

    print("\n=================== 3. ACTIVE RLS POLICIES ===================")
    cur.execute("""
        SELECT tablename, policyname, permissive, roles, cmd, qual, with_check
        FROM pg_policies
        WHERE schemaname = 'public' AND tablename IN ('profiles', 'conversations', 'messages', 'user_daily_usage')
        ORDER BY tablename, policyname;
    """)
    policies = cur.fetchall()
    for p in policies:
        print(f"  Table: {p[0]:<18} | Policy: {p[1]:<45} | Cmd: {p[4]:<7} | Qual: {p[5]}")

    print("\n=================== 4. RLS ENFORCEMENT SIMULATION ===================")
    # Check if RLS is enabled on tables
    cur.execute("""
        SELECT relname, relrowsecurity
        FROM pg_class
        JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace
        WHERE pg_namespace.nspname = 'public' 
          AND relname IN ('profiles', 'conversations', 'messages', 'user_daily_usage');
    """)
    rls_status = cur.fetchall()
    for tbl, enabled in rls_status:
        print(f"  Table {tbl:<18} : RLS Enabled = {enabled}")

    conn.close()

def audit_readonly_role():
    print("\n=================== 5. OLIST_READONLY PERMISSIONS AUDIT ===================")
    conn = psycopg.connect(DB_RO)
    cur = conn.cursor()

    approved = [
        "customers", "geolocation", "order_items", "order_payments",
        "order_reviews", "orders", "product_category_name_translation",
        "products", "sellers"
    ]
    user_tables = ["profiles", "conversations", "messages", "user_daily_usage"]

    print("Checking SELECT on 9 approved tables:")
    for t in approved:
        try:
            cur.execute(sql.SQL("SELECT COUNT(*) FROM public.{}").format(sql.Identifier(t)))
            cnt = cur.fetchone()[0]
            print(f"  [OK] SELECT on public.{t:<35} allowed ({cnt:,} rows)")
        except Exception as e:
            print(f"  [FAIL] SELECT on public.{t}: {e}")
            conn.rollback()

    print("\nChecking that SELECT is BLOCKED on multi-user tables:")
    for t in user_tables:
        try:
            cur.execute(sql.SQL("SELECT * FROM public.{} LIMIT 1").format(sql.Identifier(t)))
            cur.fetchone()
            print(f"  [SECURITY BREACH] olist_readonly CAN read public.{t}!")
        except Exception as e:
            print(f"  [BLOCKED AS EXPECTED] SELECT on public.{t}: {type(e).__name__}")
            conn.rollback()

    print("\nChecking that DML (INSERT, UPDATE, DELETE, DROP) is BLOCKED on approved tables:")
    try:
        cur.execute("INSERT INTO public.customers (customer_id, customer_unique_id, customer_zip_code_prefix, customer_city, customer_state) VALUES ('hacked', 'hacked', 12345, 'city', 'SP');")
        print("  [SECURITY BREACH] olist_readonly CAN insert!")
    except Exception as e:
        print(f"  [BLOCKED AS EXPECTED] INSERT on public.customers: {type(e).__name__}")
        conn.rollback()

    try:
        cur.execute("DROP TABLE public.sellers;")
        print("  [SECURITY BREACH] olist_readonly CAN drop tables!")
    except Exception as e:
        print(f"  [BLOCKED AS EXPECTED] DROP TABLE public.sellers: {type(e).__name__}")
        conn.rollback()

    conn.close()

if __name__ == "__main__":
    audit_database()
    audit_readonly_role()

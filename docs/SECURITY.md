# Olist AI Assistant - Security Architecture & Threat Model

This document specifies the security controls, validation boundaries, and attack mitigation strategies protecting the Olist AI Assistant from malicious inputs, prompt injection, and unauthorized data access.

---

## 1. Threat Model & Security Posture

Because the system translates open-ended user requests into executable database queries via Large Language Models (LLMs), malicious users might attempt:
1. **SQL Injection (SQLi)**: Injecting quotes, semicolons, stacked queries, or comment characters.
2. **Data Manipulation (DML)**: Attempting `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `UPSERT`.
3. **Data Definition (DDL)**: Attempting `DROP TABLE`, `ALTER TABLE`, `TRUNCATE`, `CREATE TABLE`.
4. **Data Exfiltration via Secondary Table Creation**: Attempting `SELECT ... INTO ...`.
5. **System Introspection**: Querying PostgreSQL internal catalogs (`pg_shadow`, `pg_authid`, `information_schema`).
6. **Denial of Service (DoS)**: Writing runaway queries or invoking sleep/loop functions (`pg_sleep`).
7. **Prompt Injection**: Prompting the LLM to output system secrets or bypass AST validation.

---

## 2. Multi-Layer Security Architecture

```
User Query
   │
   ▼
[1] Rate Limiter & Message Length Check (Capped length, no raw control chars)
   │
   ▼
[2] LLM SQL Generation Prompt (Enforces strict read-only SELECT rules)
   │
   ▼
[3] SQLGlot Abstract Syntax Tree (AST) Security Gate:
    ├── Statement Type Check: Must be exp.Select
    ├── Disallowed AST Nodes: exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.AlterTable, exp.Into, etc.
    ├── Table Whitelist Check: Only 9 sanctioned public tables
    ├── Forbidden Words Regex: Block pg_shadow, pg_authid, pg_sleep, dblink, copy, etc.
    └── Stacked Query Blocker: Exactly 1 statement permitted
   │
   ▼
[4] Execution Sandbox:
    ├── Dedicated PostgreSQL Role: olist_readonly (GRANT SELECT ONLY, NO DDL/DML)
    ├── Hard Statement Timeout: SET statement_timeout = 5000 (5 seconds)
    ├── Hard Row Limit: Automatically appends LIMIT 50 if missing or higher
    └── Transaction Rollback: Always rolls back transactions cleanly
   │
   ▼
Database Response
```

---

## 3. SQLGlot AST Validation Engine Details

Validation is performed in `backend/app/services/text_to_sql.py` via `validate_and_transform_sql`:

### 3.1 Disallowed AST Nodes
```python
disallowed_nodes = (
    exp.Insert, exp.Update, exp.Delete,
    exp.Drop, exp.AlterTable, exp.TruncateTable,
    exp.Create, exp.Command, exp.Transaction,
    exp.Into,  # Blocks SELECT ... INTO
)
```

### 3.2 Table Whitelist Enforcement
Every table referenced in `exp.Table` expressions is validated against the whitelist:
```python
ALLOWED_TABLES = {
    "orders", "order_items", "order_payments", "order_reviews",
    "customers", "sellers", "products", "geolocation",
    "product_category_name_translation",
}
```
Any reference to `pg_catalog`, `information_schema`, or non-existent tables triggers an immediate `ValueError: Table not in allowed schema`.

### 3.3 Statement Timeout & Connection Hardening
Every session begins with:
```sql
SET statement_timeout = 5000;
```
If any query takes longer than 5 seconds (e.g. unindexed full Cartesian product), PostgreSQL aborts execution and returns an error without stalling the application.

---

## 4. Dedicated Read-Only Database Role

In addition to software-level AST guards, the PostgreSQL connection uses a restricted database user:
```sql
CREATE ROLE olist_readonly WITH LOGIN PASSWORD 'olist_readonly_2026';
GRANT CONNECT ON DATABASE olist_db TO olist_readonly;
GRANT USAGE ON SCHEMA public TO olist_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO olist_readonly;
REVOKE ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public FROM olist_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE ALL ON TABLES FROM olist_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO olist_readonly;
```
Even if an attacker bypassed the AST validator, PostgreSQL's engine will reject any write, drop, or administrative action with `permission denied`.

---

## 5. Secrets Management & Privacy
- Zero credential logging: API keys and passwords are loaded strictly from environment variables (`.env`).
- Database credentials and Gemini keys are never logged in stack traces or transmitted to the client.
- `.gitignore` strictly protects `.env`, `.venv`, and temporary test artifacts from accidental commits.

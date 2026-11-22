# Supabase Setup Guide — Olist AI Assistant

This guide provides step-by-step instructions to configure **Supabase** as the hosted PostgreSQL database and authentication provider for the **Olist AI Assistant**.

---

## 1. Database Size & Free-Tier Suitability

An exact measurement of the Olist PostgreSQL database was conducted via `backend/scripts/measure_db_size.py`:

- **Total Olist Dataset Size:** **205 MB (215,430,835 bytes)**
- **Total Rows Across 9 Approved Olist Tables:** **1,550,922 rows**
  - `geolocation`: 1,000,163 rows
  - `order_items`: 112,650 rows
  - `order_payments`: 103,886 rows
  - `orders`: 99,441 rows
  - `order_reviews`: 99,224 rows
  - `customers`: 99,441 rows
  - `products`: 32,951 rows
  - `sellers`: 3,095 rows
  - `product_category_name_translation`: 71 rows

> **Free Tier Compatibility:** Supabase provides **500 MB** of free storage. The complete 204 MB Olist dataset and all user conversation tables consume **~41%** of the free tier capacity, leaving plenty of room for persistent chat histories.

---

## 2. Create Supabase Project

1. Go to [https://supabase.com](https://supabase.com) and create an account.
2. Click **New project**:
   - **Name:** `olist-ai-assistant`
   - **Database Password:** Choose a strong password and save it securely.
   - **Region:** Choose a region close to your users (e.g., `South America (São Paulo)` or `US East`).
   - **Pricing Plan:** Free ($0/month).
3. Wait 1–2 minutes for the database to provision.

---

## 3. Retrieve Project API Keys & JWT Secret

From your Supabase project dashboard:

1. Go to **Project Settings** > **API**:
   - **Project URL:** `https://<project-ref>.supabase.co`
     *(Set as `NEXT_PUBLIC_SUPABASE_URL` in frontend, and `SUPABASE_URL` in backend)*
   - **Publishable Key (or Anon Key):** `sb_publishable_...` or `ey...`
     *(Set as `NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY` in frontend)*
2. Go to **Project Settings** > **API** > **JWT Settings**:
   - **JWT Secret:** Copy the secret string.
     *(Set as `SUPABASE_JWT_SECRET` in backend)*
3. Go to **Project Settings** > **Database** > **Connection string**:
   - Copy the **URI** connection string:
     `postgresql://postgres:[YOUR-PASSWORD]@aws-0-[region].pooler.supabase.com:5432/postgres` (Pooler - Session Mode)
     *(Set as `DATABASE_URL` in backend; auto-normalized to `postgresql+psycopg://`)*

---

## 4. Run Multi-User Database Migrations

Open the **SQL Editor** in your Supabase dashboard and execute the migration file located at:

[`backend/migrations/001_multi_user_tables.sql`](file:///backend/migrations/001_multi_user_tables.sql)

This script creates:
1. `public.profiles` — user display name, role (`user` or `admin`), and custom daily limits.
2. `public.conversations` — user-isolated chat threads.
3. `public.messages` — individual user queries and assistant responses with metadata, metrics, and charts.
4. `public.user_daily_usage` — atomic tracking of queries per user per day.
5. **Row Level Security (RLS)** — strict policies preventing User A from reading or modifying User B's conversations.
6. **New User Trigger** — automatically populates `public.profiles` when a user signs up through Supabase Auth.

---

## 5. Import the Olist Dataset

Export your local Olist dataset and restore it into your Supabase database:

```bash
# 1. Dump local Olist tables
pg_dump -U postgres -h localhost -p 5432 -d olist_db -t customers -t geolocation -t order_items -t order_payments -t order_reviews -t orders -t product_category_name_translation -t products -t sellers --no-owner --no-privileges -F p -f olist_dump.sql

# 2. Restore directly to Supabase PostgreSQL
psql -h db.<project-ref>.supabase.co -U postgres -d postgres -p 5432 -f olist_dump.sql
```

---

## 6. Configure Read-Only Database User & Privilege Isolation

In Supabase **SQL Editor**, run:

```sql
-- 1. Create dedicated read-only role for safe Text-to-SQL analytics
CREATE USER olist_readonly WITH PASSWORD 'SecurePasswordHere123!';
GRANT CONNECT ON DATABASE postgres TO olist_readonly;
GRANT USAGE ON SCHEMA public TO olist_readonly;

-- 2. Explicitly grant SELECT ONLY on the 9 approved Olist analytics tables
GRANT SELECT ON TABLE public.customers TO olist_readonly;
GRANT SELECT ON TABLE public.geolocation TO olist_readonly;
GRANT SELECT ON TABLE public.orders TO olist_readonly;
GRANT SELECT ON TABLE public.order_items TO olist_readonly;
GRANT SELECT ON TABLE public.order_payments TO olist_readonly;
GRANT SELECT ON TABLE public.order_reviews TO olist_readonly;
GRANT SELECT ON TABLE public.products TO olist_readonly;
GRANT SELECT ON TABLE public.sellers TO olist_readonly;
GRANT SELECT ON TABLE public.product_category_name_translation TO olist_readonly;

-- 3. STRICT PRIVILEGE ISOLATION: Explicitly revoke access to user and conversation tables
REVOKE ALL ON TABLE public.profiles FROM olist_readonly;
REVOKE ALL ON TABLE public.conversations FROM olist_readonly;
REVOKE ALL ON TABLE public.messages FROM olist_readonly;
REVOKE ALL ON TABLE public.user_daily_usage FROM olist_readonly;
```

Set the read-only connection string in your backend environment:
`DATABASE_RO_URL=postgresql://olist_readonly:SecurePasswordHere123!@db.<project-ref>.supabase.co:5432/postgres`

---

## 7. Configure Supabase Authentication Settings

In the Supabase Dashboard:

1. Go to **Authentication** > **Providers** > **Email**:
   - Ensure **Email provider** is **Enabled**.
   - For demo or evaluation ease, you can disable **Confirm email** during testing, or keep it enabled for production security.
2. Go to **Authentication** > **URL Configuration**:
   - **Site URL:** `https://your-app.vercel.app` (or `http://localhost:3000` for local testing).
   - **Redirect URLs:** Add:
     - `https://your-app.vercel.app/auth/callback`
     - `https://your-app.vercel.app/reset-password`
     - `http://localhost:3000/auth/callback`
     - `http://localhost:3000/reset-password`

---

## 8. Configure Google OAuth Provider

The frontend UI supports **Google Sign-In** via `supabase.auth.signInWithOAuth({ provider: 'google' })`. To enable it in production:

### A. Google Cloud Console Setup
1. Open the [Google Cloud Console](https://console.cloud.google.com/).
2. Navigate to **APIs & Services** > **OAuth consent screen**:
   - User Type: **External**.
   - Fill in App Name: `Olist AI Assistant`, User support email, and Developer contact email.
3. Navigate to **APIs & Services** > **Credentials**:
   - Click **Create Credentials** > **OAuth Client ID**.
   - Application type: **Web application**.
   - Name: `Olist AI Assistant Supabase Auth`.
   - **Authorized redirect URIs:** Add your Supabase auth callback URL:
     `https://<project-ref>.supabase.co/auth/v1/callback`
   - Click **Create**.
   - Copy the generated **Client ID** and **Client Secret**.

### B. Supabase Dashboard Setup
1. In your Supabase Dashboard, go to **Authentication** > **Providers** > **Google**.
2. Toggle **Enable Sign in with Google** to **ON**.
3. Paste:
   - **Client ID** from Google Cloud Console.
   - **Client Secret** from Google Cloud Console.
4. Click **Save**.

Users can now sign in or register with one click using their Google accounts!

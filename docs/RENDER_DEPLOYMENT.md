# Render Deployment Guide — FastAPI Backend

This guide outlines how to deploy the **Olist AI Assistant FastAPI Backend** to [Render](https://render.com).

---

## 1. Prerequisites

- A GitHub repository containing this project.
- A Render account ([render.com](https://render.com)).
- Hosted PostgreSQL database (Supabase or Neon) configured with the Olist dataset.
- Google Gemini API key.

---

## 2. Deploy Using Blueprint (`render.yaml`)

The repository includes a ready-to-use `render.yaml` specification.

1. Log into your Render dashboard.
2. Click **Blueprints** > **New Blueprint Instance**.
3. Connect your GitHub repository.
4. Render will detect `render.yaml` and configure the web service automatically.
5. In the prompt for secret environment variables, supply:
   - `DATABASE_URL`: Connection string with write access (for conversation persistence and usage tracking).
   - `DATABASE_RO_URL`: Connection string with `olist_readonly` user (for analytical Text-to-SQL execution).
   - `SUPABASE_JWT_SECRET`: Supabase JWT Secret string.
   - `GEMINI_API_KEY`: Your Google AI Studio API key.
6. Click **Apply**.

---

## 3. Manual Deployment (Alternative)

If you prefer to configure the Web Service manually:

1. Click **New +** > **Web Service**.
2. Connect your GitHub repository.
3. Configure the service settings:
   - **Name:** `olist-ai-backend`
   - **Region:** Select the region closest to your PostgreSQL database.
   - **Root Directory:** `backend`
   - **Runtime:** `Python 3`
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - **Instance Type:** `Free` (or Starter for high availability)
4. Add the following **Environment Variables**:

| Variable | Value | Description |
|---|---|---|
| `APP_ENV` | `production` | Enables production security mode |
| `DATABASE_URL` | `postgresql://...` | Supabase main connection string |
| `DATABASE_RO_URL` | `postgresql://...` | Supabase read-only (`olist_readonly`) connection |
| `SUPABASE_JWT_SECRET` | `<secret>` | Supabase JWT Secret from dashboard |
| `GEMINI_API_KEY` | `<api-key>` | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Primary fast model |
| `GEMINI_FALLBACK_MODELS` | `gemini-3.5-flash,gemini-3.1-flash-lite,gemini-3.8-flash` | Automated fallback cascade |
| `CORS_ORIGINS` | `https://your-frontend.vercel.app,http://localhost:3000` | Allowed frontend origins |
| `REQUIRE_AUTH` | `true` | Requires valid Supabase Bearer token |
| `MAX_DAILY_QUESTIONS_PER_USER`| `15` | Anti-abuse limit for public demo |
| `MAX_CONCURRENT_PER_USER` | `2` | Prevents concurrent query floods |

5. Under **Health Check Path**, enter: `/api/health`.
6. Click **Create Web Service**.

---

## 4. Verification

Once deployed:

1. Open `https://your-render-service.onrender.com/api/health`.
2. Confirm the JSON response:
   ```json
   {
     "status": "healthy",
     "version": "1.0.0",
     "database": {
       "status": "healthy",
       "accessible_tables": 9
     },
     "ai_models": {
       "primary": "gemini-3.5-flash-lite",
       "fallbacks": ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-3.8-flash"],
       "status": "ready"
     }
   }
   ```

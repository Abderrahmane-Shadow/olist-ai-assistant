# Vercel Deployment Guide — Next.js Frontend

This guide outlines how to deploy the **Olist AI Assistant Next.js Frontend** to [Vercel](https://vercel.com).

---

## 1. Prerequisites

- A GitHub repository containing this project.
- A Vercel account ([vercel.com](https://vercel.com)).
- Deployed FastAPI backend URL (e.g. on Render: `https://olist-ai-backend.onrender.com`).
- Supabase Project URL and Public Anon Key.

---

## 2. Deploy to Vercel

1. Log into your Vercel dashboard.
2. Click **Add New...** > **Project**.
3. Import your GitHub repository.
4. In the **Configure Project** screen:
   - **Framework Preset:** `Next.js`
   - **Root Directory:** `./` (leave default)
   - **Build Command:** `npm run build`
   - **Output Directory:** `.next`
5. Expand the **Environment Variables** section and add:

| Variable | Value | Description |
|---|---|---|
| `NEXT_PUBLIC_API_URL` | `https://your-render-backend.onrender.com` | Live FastAPI backend URL |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<ref>.supabase.co` | Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | `ey...` | Supabase Public Anon Key |

6. Click **Deploy**.

---

## 3. Post-Deployment Configuration

1. After deployment finishes, copy your live Vercel URL (e.g., `https://olist-ai-assistant.vercel.app`).
2. Update **Backend CORS Origins** on Render:
   - Add `https://olist-ai-assistant.vercel.app` to `CORS_ORIGINS`.
3. Update **Supabase Auth Redirect URLs**:
   - In Supabase Dashboard > **Authentication** > **URL Configuration**, add:
     - `https://olist-ai-assistant.vercel.app/auth/callback`
     - `https://olist-ai-assistant.vercel.app/reset-password`
     - Site URL: `https://olist-ai-assistant.vercel.app`

---

## 4. Verification

1. Open your live Vercel URL in your browser.
2. Click **Register now** and create a new account.
3. Confirm that you can ask questions (e.g. `"What is the total revenue?"`).
4. Verify that:
   - Conversation title updates automatically.
   - Daily quota badge shows remaining count (e.g., `14/15 left`).
   - Refreshing the page preserves your chat history.
   - Clicking **New Chat** creates a fresh persistent thread.

# Olist AI Assistant - Deployment & Operations Guide

This guide covers deployment options for the Olist AI Assistant across local, containerized (Docker), and cloud environments.

---

## 1. Local Development Setup (Quickstart)

### Prerequisites
- Python 3.11+
- Node.js 18+ & npm
- PostgreSQL 14+ running locally with the Olist database loaded as `olist_db`
- Google AI Studio Gemini API Key

### Backend Setup
```bash
# 1. Navigate to backend directory
cd backend

# 2. Create and activate virtual environment
python -m venv .venv
# On Windows:
.\.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env and set GEMINI_API_KEY, DB credentials

# 5. Start development server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend Setup
```bash
# 1. In project root
npm install

# 2. Start Next.js development server
npm run dev
# Interface opens at http://localhost:3000
```

---

## 2. Docker Compose Deployment

The repository includes ready-to-use Docker configurations:
- `Dockerfile.backend` (Python 3.11-slim)
- `Dockerfile.frontend` (Node 20-alpine multi-stage build)
- `docker-compose.yml` (Orchestrates Database, Backend, and Frontend)

### Launching with Docker Compose
```bash
# 1. Populate root .env file from template
cp .env.example .env
# Edit .env with your GEMINI_API_KEY

# 2. Build and start containers in detached mode
docker-compose up --build -d

# 3. Check service health
docker-compose ps

# 4. View logs
docker-compose logs -f
```

---

## 3. Production Cloud Hosting Recommendations

### Architecture Overview
- **Database**: Managed PostgreSQL on **Supabase**, **Neon**, or **AWS RDS** (ensure pgvector or standard GIN text search is enabled).
- **Backend**: Containerized FastAPI service on **Render**, **Railway**, or **Google Cloud Run**.
- **Frontend**: Edge-optimized deployment on **Vercel** or **Netlify**.

### Cloud Configuration Checklist
1. **Database Role**: Create the `olist_readonly` user on your cloud PostgreSQL instance and grant `SELECT` on all tables in `public`.
2. **CORS Origins**: Set `CORS_ORIGINS` to your production frontend domain (e.g. `https://olist-analytics.vercel.app`).
3. **Environment Variables**:
   - Backend: Set `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `GEMINI_API_KEY`, `APP_ENV=production`.
   - Frontend: Set `NEXT_PUBLIC_API_URL=https://your-backend-api.onrender.com`.
4. **Statement Timeout**: Keep `statement_timeout = 5000` to prevent serverless connection exhaustion.

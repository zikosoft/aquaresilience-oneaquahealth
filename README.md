# AquaResilience

AI-assisted urban freshwater resilience intelligence platform — OneAquaHealth IEEE Global Hackathon 2026, Track 6 (Resilience Informatics). Demo geography: Toulouse / Toulouse Métropole.

This repository currently implements **P0 — Foundation & Platform Core**: a secure, navigable, configurable, internationalized platform skeleton (auth, RBAC, Settings, map/chart foundations, health checks). Environmental data ingestion, deterministic risk, early warning, AI intelligence and the Scenario Simulator are delivered in later priority blocks (see `AquaResilience_Development_Progress_Priority_Blocks.md`).

## Stack

- **Frontend:** Vue 3 + TypeScript + Vite + Vuetify, Pinia, Vue Router, vue-i18n (EN/FR/ES), MapLibre GL JS, Apache ECharts
- **Backend:** FastAPI, Pydantic, SQLAlchemy, Alembic
- **Data:** PostgreSQL + PostGIS, Redis
- **Runtime:** Docker Compose (single command startup)

## Quick start

```bash
cp .env.example .env
# Edit .env: set SECRET_KEY, SECRETS_ENCRYPTION_KEY, POSTGRES_PASSWORD, DEMO_ADMIN_PASSWORD.
docker compose up -d
```

- Frontend: http://localhost:8080
- Backend API docs: http://localhost:8000/docs
- Health: http://localhost:8000/health/live, http://localhost:8000/health/ready

Demo login (P0, admin-only account creation — see `.env`): `DEMO_ADMIN_EMAIL` / `DEMO_ADMIN_PASSWORD`. The demo account is seeded with the **Administrator** role so the full platform (including Settings and Users & Access) is reachable for evaluation.

## Repository layout

```text
backend/    FastAPI application, Alembic migrations, tests
frontend/   Vue 3 application (Vuetify UI, i18n, MapLibre, ECharts)
docs/       Architecture / data-source / responsible-AI documentation (P5)
```

## Development without Docker

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
python -m app.seed.seed_data
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

## Security notes (P0 baseline)

- Passwords hashed with bcrypt (via passlib).
- JWT access/refresh tokens; login endpoint rate-limited via Redis.
- AI provider API keys are encrypted at rest (Fernet) and are **write-only**: the API never returns a stored secret, only a configured/not-configured status.
- PostgreSQL and Redis are not published to the host; only the backend/frontend ports are exposed.
- `.env` is git-ignored; `.env.example` contains no real secrets.

## Roadmap

See `AquaResilience_Master_Spec_Priority_Blocks.md` (source of truth) and `AquaResilience_Development_Progress_Priority_Blocks.md` (live tracker) for the full functional priority block plan (P0–P5).

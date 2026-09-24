# AquaResilience — Architecture

OneAquaHealth IEEE Global Hackathon 2026 — **Track 6: Resilience Informatics**
("Enable early warning & resilience planning" / "predictive dashboards, alerts, and resilience tools").

This document explains *how* the platform is built and *why* the key
decisions were made. For *what* is built and its current completion state,
see `README.md` and `AquaResilience_Development_Progress_Priority_Blocks.md`.
For data sources and their licenses, see `docs/DATA_SOURCES.md`. For how the
AI layer is used responsibly, see `docs/RESPONSIBLE_AI.md`.

## 1. System overview

```text
                     ┌─────────────────────────────────────────────┐
                     │           External public APIs               │
                     │  Hub'Eau Hydrométrie (Garonne water height)   │
                     │  Open-Meteo (rain, soil moisture, weather)    │
                     └───────────────────┬───────────────────────────┘
                                          │ scheduled ingestion (APScheduler)
                                          ▼
                     ┌─────────────────────────────────────────────┐
                     │   Ingestion & normalization (FastAPI backend) │
                     │   idempotent upsert · provenance · freshness  │
                     └───────────────────┬───────────────────────────┘
                                          ▼
                     ┌─────────────────────────────────────────────┐
                     │      PostgreSQL + PostGIS  ·  Redis           │
                     └───────────────────┬───────────────────────────┘
                                          ▼
                     ┌─────────────────────────────────────────────┐
                     │            FastAPI REST API (/api/v1)         │
                     │  auth · RBAC · environmental · risk · alerts  │
                     │  intelligence · scenario · settings           │
                     └───────────────────┬───────────────────────────┘
                                          ▼
        ┌─────────────────────────────────────────────────────────────┐
        │                  Deterministic Risk Engine                    │
        │  rainfall + hydrology + environmental + trend  →  0-100        │
        │  (configurable weights/thresholds — the AI never touches this) │
        └───────────────────┬─────────────────────────┬───────────────┘
                             ▼                         ▼
              ┌───────────────────────┐   ┌─────────────────────────────┐
              │   Early Warning        │   │  AI Resilience Intelligence  │
              │ ACTIVE→ACK→RESOLVED    │   │  OpenAI/Anthropic, scheduled │
              │                         │   │  + event-triggered, graceful │
              │                         │   │  degradation on failure      │
              └───────────────────────┘   └─────────────────────────────┘
                             │                         │
                             └────────────┬────────────┘
                                          ▼
                     ┌─────────────────────────────────────────────┐
                     │        Vue 3 / Vuetify frontend (SPA)          │
                     │  Command Center · Resilience Map · Early       │
                     │  Warnings · AI Intelligence · Scenario         │
                     │  Simulator · Data Sources · Settings           │
                     └─────────────────────────────────────────────┘
```

## 2. Why a deterministic Risk Engine, separate from the AI

Track 6 asks for *predictive dashboards and alerts*, which must be
trustworthy and reproducible — a hackathon judge (or a real operator) must
be able to ask "why is risk 71/100?" and get the same, explainable answer
every time. An LLM is non-deterministic and can hallucinate, so it is
**never** used to compute the risk score itself.

Instead:

- **Risk Engine** (`backend/app/services/risk_engine.py`) is pure,
  deterministic Python: four normalized 0–1 factors — rainfall (24h
  cumulative ÷ 40mm reference), hydrology (current Garonne level placed on a
  0–1 scale via its own trailing 90-day observed min/max), environmental
  (soil moisture ratio, already 0–1), trend (rate of rise over 6h ÷
  50mm/h reference, clamped at 0 so a falling level never *adds* risk) —
  combined via configurable weights (default 0.3/0.3/0.2/0.2) into a 0–100
  score, bucketed into LOW/MODERATE/HIGH/CRITICAL by configurable
  thresholds. Same inputs always produce the same score. Every factor's
  individual contribution is stored, so the dashboard can answer "why" with
  real numbers, not a generated sentence.
- **AI layer** (`backend/app/services/intelligence_service.py`,
  `scenario_service.py`) only ever receives the *already-computed* risk
  score and factor breakdown as a structured snapshot, and is asked to
  *interpret and explain* it (situation summary, drivers, zones to watch,
  recommendations, confidence, limitations) — never to invent a number of
  its own. If the AI provider is unreachable, slow, or returns invalid
  output, the risk score, the map, the Early Warning and the Scenario
  Simulator all keep working exactly as before; only the AI panel shows a
  clear degraded-state message. This was verified live against a genuine
  provider outage (this sandbox's own network policy blocks both providers
  outright), not just unit-tested.

## 3. Data provenance and freshness — no "LIVE/CACHED/REPLAY" badges

Every ingested measurement keeps: provider, station, parameter, unit,
value, the provider's own acquisition timestamp, and the platform's
ingestion timestamp (`backend/app/models/environmental.py`). Ingestion is
idempotent (`ON CONFLICT DO NOTHING` on `(station_id, variable,
observed_at)` — verified with a real repeated-run test: the second run of
the same window inserts zero new rows).

Rather than exposing raw "live vs. cached vs. replay" modes to the user
(confusing, and not what an operator actually needs), each data source
computes a **fresh / stale / degraded** health status from its own
`expected_interval_seconds`/failure count, and the UI always shows *when*
data was last updated and from where — so a viewer can judge trust for
themselves without the platform ever silently presenting stale data as
current.

## 4. Scenario Simulator — the reuse decision

The Scenario Simulator (`backend/app/services/scenario_service.py`,
`frontend/src/views/scenarios/ScenarioSimulatorView.vue`) is the platform's
main differentiation feature: rainfall/river-level sliders drive a
**projected** risk score. Rather than building a second, separate
prediction model, it calls the *exact same* Risk Engine normalizers used
for real risk, fed hypothetically-scaled inputs (`rainfall_adjustment_pct`,
`river_level_adjustment_pct`). This guarantees the projected number is
reached by the same, already-explainable logic as the real one — a judge
who trusts the Current risk score has no separate model to also trust for
the Projected one. A simulation never persists a real `Warning` row (a
hypothetical scenario must never contaminate the real Early Warning
history) but does synchronize the Risk Gauge, the Resilience Map
(Current/Projected toggle on the same map component), the Risk Factor
Contribution breakdown and the water-level/precipitation charts together,
plus an optional AI explanation layered on top without blocking the
deterministic result if the AI is slow or unavailable.

## 5. RBAC

Relational and modular, not a bespoke identity product:
`users / roles / modules / permissions / user_roles / role_permissions`,
with compact permission types (`VIEW/CREATE/EDIT/DELETE/EXECUTE/ADMIN`)
across modules (`DASHBOARD/MAP/ALERTS/AI_INTELLIGENCE/SCENARIOS/
DATA_SOURCES/SETTINGS/ADMINISTRATION`). A per-user "Custom" permission
override clones the user's current role into a user-scoped role on first
edit (never duplicated on subsequent edits, verified by test) rather than
requiring a bespoke per-user override table — a deliberate cost/benefit
trade-off for a hackathon-scale platform.

## 6. Internationalization

`vue-i18n`, English/French/Spanish, zero hard-coded user-facing strings in
core screens. Backend values stay language-neutral (`LOW`, `MODERATE`,
`HIGH`, `CRITICAL`, `ACTIVE`, `ACKNOWLEDGED`, `RESOLVED`) and are translated
client-side, so language switching works at runtime with no
re-authentication and no server-side per-locale branching.

## 7. Deployment architecture

Two Docker Compose stacks from the same images:

- `docker-compose.yml` — development: hot-reload, ports exposed for
  convenience.
- `docker-compose.prod.yml` — production: nginx as the single public
  reverse proxy terminating HTTPS (Let's Encrypt via `certbot`, or a
  self-signed quick-start needing no domain), Postgres/Redis/backend/
  frontend all internal-only (no published host ports), backend running
  multi-worker behind `--proxy-headers`. See `DEPLOYMENT.md` for the full
  operational guide.

## 8. Scalability beyond Toulouse

Toulouse is the demonstration city, not a hard-coded architecture. A
`countries`/`cities` reference schema (iso codes, EN/FR/ES labels, default
lat/lon/zoom) already backs Settings → Map's city defaults. Each data
connector declares its own station identity (code, name, coordinates)
rather than assuming a single fixed location, and the Risk Engine's
weights/thresholds are configuration, not code. Adding a second city is
intended to mainly require new connector station mappings and a config
row, not rewriting the ingestion pipeline, the Risk Engine or the UI.

## 9. Testing

Backend: pytest against a real PostgreSQL test database (not mocked),
covering authentication/RBAC, environmental ingestion/idempotency, the Risk
Engine's determinism, the Early Warning lifecycle, AI Situation Brief
generation (including simulated provider failure), the Scenario Simulator,
event-triggered AI gating, and the maintenance-mode write-blocking gate —
88 tests, all passing. Frontend: `vue-tsc` (strict type-check), ESLint, and
a production `vite build`, all clean. Beyond automated tests, every
user-facing fix in this project has been **live-verified** with a real
running dev stack and, where visual, real screenshots — not just code
review — because a hackathon demo depends on what a judge actually sees
working, not on what the code claims to do.

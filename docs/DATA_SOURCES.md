# AquaResilience — Data Sources

Two real, free, key-less public data sources feed the platform — chosen
deliberately over integrating many partial ones (see the project's
decision log: "2-3 strong real sources, not six unfinished integrations").

## Hub'Eau Hydrométrie (hydrology)

- **Provider:** Hub'Eau / Eaufrance, French Ministry for Ecological
  Transition — https://hubeau.eaufrance.fr/page/api-hydrometrie
- **License:** Licence Ouverte / Open Licence 2.0 (Etalab)
- **Access:** public REST API, no key or registration required
- **What we ingest:** real-time Garonne water height (mm) for the Toulouse
  demo geography, station **O200004001** — "La Garonne à Toulouse
  [Pont-Neuf] - Quai de Tounis" (confirmed live during development;
  coordinates ~1.44°E / 43.60°N, on the city-centre stretch of the Garonne
  the platform's default map viewport is centered on)
- **Cadence:** published roughly every 5 minutes; the platform treats data
  older than 1 hour as stale
- **Connector:** `backend/app/services/connectors/hubeau.py`

## Open-Meteo (weather / environmental)

- **Provider:** Open-Meteo — https://open-meteo.com/
- **License:** free for non-commercial use (CC BY 4.0-compatible
  attribution); no API key required for this project's usage
- **Access:** public REST API
- **What we ingest, hourly, for the same Toulouse coordinates:**
  precipitation (mm), soil moisture ratio (m³/m³), temperature (°C),
  relative humidity (%), wind speed (km/h), wind direction (°), surface
  pressure (hPa), UV index — 8 variables from a single connector call, no
  additional source needed
- **Important boundary:** Open-Meteo's response blends observed and
  short-range forecast hours; the connector only ingests hours at-or-before
  "now" as real measurements. Forecast/future hours are never stored as if
  they were observations — the Scenario Simulator is the platform's
  deliberate, explicit place for projected/what-if values, kept clearly
  separate from measured history
- **Connector:** `backend/app/services/connectors/open_meteo.py`

## How ingestion works

A shared APScheduler background job (`backend/app/core/scheduler.py`)
ticks every 5 minutes and calls each connector only once its own
`expected_interval_seconds` has elapsed, so both sources share one
scheduler cleanly without over-polling either API. Every ingested
measurement keeps its provider, station, parameter, unit, value, the
provider's own acquisition timestamp and the platform's ingestion
timestamp (full provenance — see `docs/ARCHITECTURE.md` §3). Ingestion is
idempotent: re-ingesting an already-stored window inserts zero duplicate
rows (`ON CONFLICT DO NOTHING` on `(station_id, variable, observed_at)`,
verified with a real repeated-run test).

## If a source becomes unreachable

Each source's health is computed as **fresh / stale / degraded** from its
own expected interval and recent failure count — never a raw
"live/cached/replay" badge. The last successfully ingested values remain
visible and clearly marked with their real age; the platform never
silently presents stale data as current. This was verified against a real
outage, not just a simulated one: both providers are blocked outright by
this development sandbox's own network policy, and the pipeline handled
that exactly as designed (no crash, correct `consecutive_failures`/
`last_error_message`, both sources correctly shown "Degraded" with their
real HTTP error).

## Deterministic demo seed

Because a live demo or a judge's evaluation session must never depend on
an external API happening to respond correctly at the wrong moment, a
fixed-seed synthetic backfill (`backend/app/seed/seed_environmental.py`,
`random.Random(20260921)`) guarantees the Command Center and map are never
empty, covering a realistic rolling 5-day (120h) window for both stations.
It reuses each connector's own real station identity — a demo reset never
creates a duplicate "fake" station next to the real one — and is purely
internal bookkeeping (`is_backfill`), never surfaced to the user as a
special mode. `python -m app.seed.seed_environmental --reset` rebuilds it
byte-identically every time.

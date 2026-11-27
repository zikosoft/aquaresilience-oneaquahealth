# AquaResilience — historical backtest

Replays the deterministic Risk Engine on historical observations and scores
it against observed floods. The harness imports the engine's own factor
functions (`backend/app/services/risk_factors.py`), so the backtest and the
live platform always compute the same thing.

The method (event catalogue, causal replay, matched false-alarm budget,
paired comparison, robustness and Morris screening) is described in the
accompanying article.

## Step 1 — download and clean the data

```bash
cd research/backtest
cp .env.example .env          # paste your free NVE key
docker compose build
docker compose run --rm backtest python -m loaders
```

A single loader: `python -m loaders.load_toulouse` (or `load_oslo`, `load_weather`).
Downloads are cached in `data/raw/`; re-running only fetches what is missing.

## Step 2 — build the flood catalogue

```bash
docker compose run --rm backtest python events.py
```

Writes `data/events/events_<station>.csv` and `thresholds_<station>.json`
(S1, S2, S3 fitted on the calibration period only).

## Step 3 — replay the engine and score it

```bash
docker compose run --rm backtest python replay.py
```

Writes `results/metrics_*.csv` (detection, false alarms, lead time, bootstrap
intervals), `results/paired_*.csv` (per-flood lead-time difference against
the water-level baseline) and `results/signals_*.parquet`.

## Step 4 — robustness and sensitivity

```bash
docker compose run --rm backtest python robustness.py
```

Writes `results/robust_budget.csv`, `results/robust_rules.csv`,
`results/morris_v2c.csv` and `results/morris_runs.csv`.

## Step 5 — figures and main table

```bash
docker compose run --rm backtest python figures.py
```

Writes `figures/fig1_event_2022` to `figures/fig5_regimes` and
`results/table_main.csv`.

## Data

| File (data/clean/) | Source | Content |
| --- | --- | --- |
| `toulouse_pontneuf_H.parquet` | data.gouv.fr, station O200004001 | hourly water height (mm), 1983– |
| `oslo_akerselva_H.parquet` | NVE HydAPI, station 6.9.0 | hourly water level (mm), 2000– |
| `oslo_alna_H.parquet` | NVE HydAPI, station 6.12.0 | hourly water level (mm), 1998– |
| `weather_<city>_H.parquet` | Open-Meteo archive (ERA5) | hourly precipitation (mm), soil moisture 0–7 cm |

Each `.parquet` has a `.json` next to it with its span, completeness and
largest gap. `data/` is not versioned: everything is re-downloadable.

Data licences: Hub'Eau / data.gouv.fr — Licence Ouverte 2.0 (Etalab);
NVE — see the HydAPI terms of use (hydapi.nve.no); Open-Meteo — attribution under its own terms (see `docs/DATA_SOURCES.md`).

"""Oslo: hourly water level from NVE HydAPI (parameter 1000, stage).

Stations: 6.9.0 Akerselva below Maridalsvatn (main), 6.12.0 Alna at Vestli
(control). Fetched year by year at hourly resolution to stay under the API's
response size limit. NVE reports stage in metres; stored here in mm, the
unit the Risk Engine uses.

Output: data/clean/oslo_<station>_H.parquet, hourly index (UTC), column h_mm.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import pandas as pd

from loaders.common import RAW, get, log, write_clean

API = "https://hydapi.nve.no/api/v1/Observations"
STATIONS = {"6.9.0": ("akerselva", 2000), "6.12.0": ("alna", 1998)}
RAW_DIR = RAW / "oslo"


def _observations(payload) -> list[dict]:
    out = []
    for item in payload.get("data") or []:
        out.extend(item.get("observations") or [])
    return out


def _fetch_year(station: str, year: int, key: str) -> list[dict]:
    path = RAW_DIR / f"{station}_{year}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    r = get(API, headers={"X-API-Key": key, "accept": "application/json"}, params={
        "StationId": station, "Parameter": 1000, "ResolutionTime": 60,
        "ReferenceTime": f"{year}-01-01/{year + 1}-01-01"})
    obs = _observations(r.json())
    path.write_text(json.dumps(obs), encoding="utf-8")
    return obs


def run() -> None:
    key = os.getenv("NVE_API_KEY", "").strip()
    if not key:
        raise RuntimeError("NVE_API_KEY missing in research/backtest/.env")
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    this_year = datetime.now(timezone.utc).year
    for station, (name, first_year) in STATIONS.items():
        log(f"Oslo: {name} ({station})")
        rows = []
        for year in range(first_year, this_year + 1):
            rows.extend(_fetch_year(station, year, key))
        df = pd.DataFrame(rows)
        df["t"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
        df["h_mm"] = pd.to_numeric(df["value"], errors="coerce") * 1000.0
        df = df.dropna(subset=["t", "h_mm"]).drop_duplicates("t").sort_values("t").set_index("t")
        hourly = df[["h_mm"]].resample("h").last().dropna()
        write_clean(hourly, f"oslo_{name}_H", "h_mm", {"station": station, "unit": "mm"})


if __name__ == "__main__":
    run()

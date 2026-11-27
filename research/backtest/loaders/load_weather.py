"""Hourly ERA5 reanalysis from the Open-Meteo archive API.

Variables: precipitation (mm), soil_moisture_0_to_7cm (m3/m3), at the city
point the platform itself uses. Fetched year by year; the most recent week
is excluded because the reanalysis is published with a delay.

Also builds an upstream-basin precipitation series for the Garonne above
Toulouse: the hourly mean of six ERA5 points spread over the Pyrenean
headwaters (upper Garonne, Neste, Salat, Ariege) and the plain above the city.
This is a coarse areal average, not a hydrological catchment integral.

Output: data/clean/weather_<city>_H.parquet and
data/clean/weather_toulouse_basin_H.parquet, hourly index (UTC).
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pandas as pd

from loaders.common import RAW, get, log, write_clean

API = "https://archive-api.open-meteo.com/v1/archive"
VARIABLES = "precipitation,soil_moisture_0_to_7cm"
CITIES = {
    "toulouse": (43.600, 1.440, 1983),
    "oslo": (59.913, 10.752, 1998),
}
RAW_DIR = RAW / "weather"

TOULOUSE_BASIN = {
    "vielha": (42.70, 0.80),
    "saint_gaudens": (43.11, 0.72),
    "saint_girons": (42.98, 1.15),
    "ax_les_thermes": (42.72, 1.84),
    "foix": (42.97, 1.61),
    "muret": (43.46, 1.33),
}


def _fetch_year(city: str, lat: float, lon: float, year: int, last_day: date) -> dict:
    path = RAW_DIR / f"{city}_{year}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    end = min(date(year, 12, 31), last_day)
    r = get(API, params={"latitude": lat, "longitude": lon, "start_date": f"{year}-01-01",
                         "end_date": end.isoformat(), "hourly": VARIABLES, "timezone": "UTC"})
    hourly = r.json().get("hourly") or {}
    path.write_text(json.dumps(hourly), encoding="utf-8")
    return hourly


def run() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_day = date.today() - timedelta(days=7)
    for city, (lat, lon, first_year) in CITIES.items():
        log(f"Weather: {city}")
        frames = []
        for year in range(first_year, last_day.year + 1):
            frames.append(pd.DataFrame(_fetch_year(city, lat, lon, year, last_day)))
        df = pd.concat(frames, ignore_index=True)
        df["t"] = pd.to_datetime(df["time"], utc=True)
        df = df.drop(columns=["time"]).drop_duplicates("t").set_index("t").sort_index()
        df = df.rename(columns={"precipitation": "precip_mm",
                                "soil_moisture_0_to_7cm": "soil_moisture_ratio"})
        write_clean(df, f"weather_{city}_H", "precip_mm",
                    {"source": "Open-Meteo archive (ERA5)", "lat": lat, "lon": lon})


def _fetch_basin_year(year: int, last_day: date) -> list:
    path = RAW_DIR / f"toulouse_basin_{year}.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    end = min(date(year, 12, 31), last_day)
    lats = ",".join(str(v[0]) for v in TOULOUSE_BASIN.values())
    lons = ",".join(str(v[1]) for v in TOULOUSE_BASIN.values())
    r = get(API, params={"latitude": lats, "longitude": lons, "start_date": f"{year}-01-01",
                         "end_date": end.isoformat(), "hourly": "precipitation", "timezone": "UTC"})
    payload = r.json()
    payload = payload if isinstance(payload, list) else [payload]
    hourly = [p.get("hourly") or {} for p in payload]
    path.write_text(json.dumps(hourly), encoding="utf-8")
    return hourly


def run_basin() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    last_day = date.today() - timedelta(days=7)
    log("Weather: Toulouse upstream basin (6 points)")
    frames = []
    for year in range(CITIES["toulouse"][2], last_day.year + 1):
        points = _fetch_basin_year(year, last_day)
        cols = {}
        for name, h in zip(TOULOUSE_BASIN, points):
            cols[f"precip_{name}"] = pd.Series(h.get("precipitation"), index=pd.to_datetime(h.get("time"), utc=True))
        frames.append(pd.DataFrame(cols))
    df = pd.concat(frames).sort_index()
    df = df[~df.index.duplicated()]
    df["precip_mm"] = df[[c for c in df.columns if c.startswith("precip_")]].mean(axis=1)
    df.index.name = "t"
    write_clean(df, "weather_toulouse_basin_H", "precip_mm",
                {"source": "Open-Meteo archive (ERA5)", "points": TOULOUSE_BASIN})


if __name__ == "__main__":
    run()
    run_basin()

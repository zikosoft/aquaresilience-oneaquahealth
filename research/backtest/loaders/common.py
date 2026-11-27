"""Shared paths, HTTP and coverage helpers for the data loaders."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "raw"
CLEAN = ROOT / "data" / "clean"
RAW.mkdir(parents=True, exist_ok=True)
CLEAN.mkdir(parents=True, exist_ok=True)

SESSION = requests.Session()
SESSION.headers["User-Agent"] = "AquaResilience-backtest/1.0"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def get(url: str, *, params=None, headers=None, timeout=120, retries=4, stream=False):
    last = None
    for attempt in range(retries):
        try:
            r = SESSION.get(url, params=params, headers=headers, timeout=timeout, stream=stream)
            if r.status_code in (429, 500, 502, 503, 504):
                raise requests.HTTPError(f"HTTP {r.status_code}: {r.text[:200]}")
            r.raise_for_status()
            return r
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(5 * (attempt + 1))
    raise last


def coverage(df: pd.DataFrame, value_col: str) -> dict:
    """Summary written next to each clean file: span, completeness, largest gap."""
    s = df[value_col].dropna()
    if s.empty:
        return {"rows": 0}
    full = pd.date_range(s.index.min(), s.index.max(), freq="h")
    present = s.index.unique()
    gaps = full.difference(present)
    largest_gap_h = 0
    if len(gaps):
        runs = (pd.Series(gaps).diff() != pd.Timedelta(hours=1)).cumsum()
        largest_gap_h = int(pd.Series(gaps).groupby(runs).size().max())
    return {
        "rows": int(len(s)),
        "from": s.index.min().isoformat(),
        "to": s.index.max().isoformat(),
        "hours_expected": int(len(full)),
        "completeness_pct": round(100 * len(present) / len(full), 2),
        "largest_gap_hours": largest_gap_h,
        "min": float(s.min()),
        "max": float(s.max()),
    }


def write_clean(df: pd.DataFrame, name: str, value_col: str, extra: dict | None = None) -> None:
    path = CLEAN / f"{name}.parquet"
    df.to_parquet(path)
    meta = {"file": path.name, **coverage(df, value_col), **(extra or {})}
    (CLEAN / f"{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    log(f"    wrote {path.name}: {meta.get('rows')} rows, "
        f"{meta.get('completeness_pct')}% complete, largest gap {meta.get('largest_gap_hours')} h")

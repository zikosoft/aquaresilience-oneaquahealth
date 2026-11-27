"""Flood event catalogue (ground truth) for each station.

Thresholds are fitted on the calibration period only:
  S1 = median of annual maxima (about a 2-year flood)
  S2 = 5-year return level, S3 = 10-year return level (Gumbel, method of moments)
Years with less than 80 % of their hours present are left out of the fit.

An event is a run of hours above S1; runs less than 7 days apart are merged.
For each event the first hour above S1, S2 and S3 is recorded (empty when
that level was not reached): the backtest measures lead time against these.

Output in data/events/: events_<station>.csv and thresholds_<station>.json.
Run: python -m events
"""
from __future__ import annotations

import json
import math

import pandas as pd

from loaders.common import CLEAN, ROOT, log

OUT = ROOT / "data" / "events"
OUT.mkdir(parents=True, exist_ok=True)

MERGE_GAP = pd.Timedelta(days=7)
MIN_YEAR_COVERAGE = 0.8
EULER = 0.5772156649

STATIONS = {
    "toulouse_pontneuf": {"file": "toulouse_pontneuf_H", "col": "h_mm_max", "calibration": (1983, 2009)},
    "oslo_akerselva": {"file": "oslo_akerselva_H", "col": "h_mm", "calibration": (2000, 2012)},
    "oslo_alna": {"file": "oslo_alna_H", "col": "h_mm", "calibration": (2000, 2012)},
}

DOCUMENTED = {"toulouse_pontneuf": ["1993-09-24", "2000-06-11", "2014-01-25", "2022-01-11", "2026-02-11"]}


def annual_maxima(s: pd.Series, first: int, last: int) -> pd.Series:
    s = s[(s.index.year >= first) & (s.index.year <= last)]
    counts = s.groupby(s.index.year).count()
    hours = pd.Series({y: (8784 if y % 4 == 0 else 8760) for y in counts.index})
    good = counts.index[(counts / hours) >= MIN_YEAR_COVERAGE]
    return s.groupby(s.index.year).max().loc[good]


def gumbel_return_level(maxima: pd.Series, years: float) -> float:
    beta = maxima.std(ddof=1) * math.sqrt(6) / math.pi
    mu = maxima.mean() - EULER * beta
    return mu - beta * math.log(-math.log(1 - 1 / years))


def thresholds(maxima: pd.Series) -> dict:
    return {"S1": float(maxima.median()),
            "S2": float(gumbel_return_level(maxima, 5)),
            "S3": float(gumbel_return_level(maxima, 10))}


def catalogue(s: pd.Series, th: dict) -> pd.DataFrame:
    above = s[s > th["S1"]]
    if above.empty:
        return pd.DataFrame()
    starts = above.index.to_series().diff() > MERGE_GAP
    event_id = starts.cumsum()
    rows = []
    for _, block in above.groupby(event_id):
        span = s.loc[block.index.min(): block.index.max()]
        row = {"start": block.index.min(), "end": block.index.max(),
               "peak_time": span.idxmax(), "peak_mm": float(span.max())}
        for level in ("S1", "S2", "S3"):
            hit = span[span > th[level]]
            row[f"t_cross_{level}"] = hit.index.min() if not hit.empty else pd.NaT
        row["level"] = max((lvl for lvl in ("S1", "S2", "S3") if pd.notna(row[f"t_cross_{lvl}"])),
                           key=lambda x: int(x[1]))
        rows.append(row)
    return pd.DataFrame(rows)


def run() -> None:
    for name, cfg in STATIONS.items():
        s = pd.read_parquet(CLEAN / f"{cfg['file']}.parquet")[cfg["col"]].dropna()
        first, last = cfg["calibration"]
        maxima = annual_maxima(s, first, last)
        th = thresholds(maxima)
        ev = catalogue(s, th)
        ev["period"] = ev["t_cross_S1"].dt.year.map(lambda y: "calibration" if y <= last else "test")
        ev.to_csv(OUT / f"events_{name}.csv", index=False)
        counts = {p: {lvl: int(((ev["period"] == p) & ev[f"t_cross_{lvl}"].notna()).sum())
                      for lvl in ("S1", "S2", "S3")} for p in ("calibration", "test")}
        check = {}
        for day in DOCUMENTED.get(name, []):
            d = pd.Timestamp(day, tz="UTC")
            hit = ev[(ev["peak_time"] - d).abs() <= pd.Timedelta(days=2)]
            check[day] = hit["level"].iloc[0] if not hit.empty else "MISSING"
        meta = {"station": name, "calibration_years": [first, last],
                "annual_maxima_used": int(len(maxima)),
                "thresholds_mm": {k: round(v, 1) for k, v in th.items()},
                "events": counts, "documented_check": check}
        (OUT / f"thresholds_{name}.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
        log(f"{name}: S1={th['S1']:.0f} S2={th['S2']:.0f} S3={th['S3']:.0f} mm | "
            f"events calib {counts['calibration']} | test {counts['test']}")
        if check:
            log(f"    documented floods: {check}")


if __name__ == "__main__":
    run()

"""Robustness of the Toulouse result (V2c vs B1) and sensitivity of V2c.

A. False-alarm budget: thresholds re-selected on the calibration period for
   0.5, 1 and 2 false alarms per year (Toulouse and Oslo Alna).
B. Evaluation rules: detection window 48 / 72 / 96 h and alert merge gap
   12 / 24 / 48 h (Toulouse, S1, budget 1/yr).
C. Morris-style elementary effects on V2c (Toulouse, S1, budget 1/yr):
   4 weights (renormalised to sum 1), hydrology lower/upper quantiles, trend
   reference quantile, rainfall reference. Outputs: test POD, median lead,
   false alarms per year, events alerted earlier than B1.

Every threshold is chosen on the calibration period only; every metric is
computed on the test period. Paired comparisons use an exact two-sided sign
test on per-event lead differences against B1.

Output: results/robust_budget.csv, results/robust_rules.csv,
results/morris_v2c.csv, results/morris_runs.csv
Run: python -m robustness
"""
from __future__ import annotations

from math import comb

import numpy as np
import pandas as pd

import replay as R
from loaders.common import CLEAN, log

BUDGETS = (0.5, 1.0, 2.0)
WINDOWS_H = (48, 72, 96)
MERGES_H = (12, 24, 48)
MORRIS_R = 12
MORRIS_DELTA = 2 / 3
SEED = 20261127

PARAMS = {  # name: (low, high, base)
    "w_rainfall": (0.1, 0.5, 0.3),
    "w_hydrology": (0.1, 0.5, 0.3),
    "w_environmental": (0.0, 0.4, 0.2),
    "w_trend": (0.0, 0.4, 0.2),
    "hydro_lo_q": (0.3, 0.7, 0.5),
    "hydro_hi_q": (0.99, 0.9999, 0.999),
    "trend_ref_q": (0.95, 0.999, 0.99),
    "rain_ref_mm": (20.0, 60.0, 40.0),
}


def load(name: str):
    cfg = R.STATIONS[name]
    file, col = cfg["level"]
    level = R._naive(pd.read_parquet(CLEAN / f"{file}.parquet")[col].dropna())
    weather = R._naive(pd.read_parquet(CLEAN / f"{cfg['weather']}.parquet"))
    basin = R._naive(pd.read_parquet(CLEAN / f"{cfg['basin']}.parquet")) if cfg["basin"] else None
    events = pd.read_csv(R.EVENTS / f"events_{name}.csv")
    for c in ("start", "end", "t_cross_S1", "t_cross_S2", "t_cross_S3"):
        events[c] = pd.to_datetime(events[c], utc=True).dt.tz_convert(None)
    inputs = R.build_inputs(level, weather, basin)
    c0, c1 = inputs.index.min(), pd.Timestamp(cfg["calib_end"])
    t0, t1 = pd.Timestamp(cfg["test_start"]), inputs.index.max()
    sig, factors, _ = R.build_signals(inputs, c1)
    return inputs, factors, sig, events, (c0, c1, t0, t1)


def grid_for(model: str, s: pd.Series, c0, c1):
    if model.startswith("V"):
        return np.arange(10, 97.5, 2.5)
    cal = s[(s.index >= c0) & (s.index <= c1)].dropna()
    return np.unique(np.quantile(cal, np.linspace(0.90, 0.9999, 80)))


def sign_test(earlier: int, later: int) -> float:
    n = earlier + later
    if n == 0:
        return float("nan")
    k = min(earlier, later)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def operate(sig, events, level, periods, model, budget):
    c0, c1, t0, t1 = periods
    R.TARGET_FA_PER_YEAR = budget
    s = sig[model]
    a = R.threshold_for_budget(s, events, level, c0, c1, grid_for(model, s, c0, c1))
    r = R.evaluate(s >= a, events, level, t0, t1)
    leads = [v for v in r["leads"].values() if v is not None]
    return a, r, {"threshold": round(a, 2), "hits": len(leads), "events": len(r["leads"]),
                  "fa_per_year": round(len(r["false_starts"]) / r["years"], 2),
                  "lead_median_h": float(np.median(leads)) if leads else np.nan}


def paired(r_ref, r_mod) -> dict:
    p = R.paired_vs(r_ref["leads"], r_mod["leads"])
    p["sign_test_p"] = round(sign_test(p["earlier_than_B1"], p["later_than_B1"]), 4)
    return p


def part_a(data) -> pd.DataFrame:
    rows = []
    for name, (inputs, factors, sig, events, periods) in data.items():
        models = [m for m in ("V0", "V2ab", "V2c") if m in sig]
        for budget in BUDGETS:
            for lvl in ("S1", "S2"):
                _, r_b1, m_b1 = operate(sig, events, lvl, periods, "B1", budget)
                rows.append({"station": name, "budget": budget, "level": lvl, "model": "B1", **m_b1})
                for model in models:
                    _, r, m = operate(sig, events, lvl, periods, model, budget)
                    rows.append({"station": name, "budget": budget, "level": lvl, "model": model,
                                 **m, **paired(r_b1, r)})
    R.TARGET_FA_PER_YEAR = 1.0
    return pd.DataFrame(rows)


def part_b(inputs, sig, events, periods) -> pd.DataFrame:
    rows = []
    base_w, base_m = R.WINDOW, R.MERGE_GAP
    for w in WINDOWS_H:
        for mg in MERGES_H:
            R.WINDOW, R.MERGE_GAP = pd.Timedelta(hours=w), pd.Timedelta(hours=mg)
            _, r_b1, m_b1 = operate(sig, events, "S1", periods, "B1", 1.0)
            _, r_c, m_c = operate(sig, events, "S1", periods, "V2c", 1.0)
            rows.append({"window_h": w, "merge_h": mg,
                         "B1_hits": f"{m_b1['hits']}/{m_b1['events']}", "B1_fa": m_b1["fa_per_year"],
                         "B1_lead": m_b1["lead_median_h"],
                         "V2c_hits": f"{m_c['hits']}/{m_c['events']}", "V2c_fa": m_c["fa_per_year"],
                         "V2c_lead": m_c["lead_median_h"], **paired(r_b1, r_c)})
    R.WINDOW, R.MERGE_GAP = base_w, base_m
    return pd.DataFrame(rows)


def v2c_signal(x: dict, inputs, factors, calib_end) -> pd.Series:
    calib = inputs.index <= calib_end
    fresh = inputs["level_age"] <= R.MAX_STALENESS
    lvl_cal = inputs.loc[calib, "level_now"]
    lo, hi = float(lvl_cal.quantile(x["hydro_lo_q"])), float(lvl_cal.quantile(x["hydro_hi_q"]))
    rise = (inputs["level_now"] - inputs["trend_first"]) / R.TREND_WINDOW_HOURS
    ref = float(rise[calib & (rise > 0).to_numpy()].quantile(x["trend_ref_q"]))
    f = pd.DataFrame(index=inputs.index)
    f["rainfall"] = (inputs["rain24_basin"].clip(lower=0) / x["rain_ref_mm"]).clip(0, 1)
    f["hydrology"] = ((inputs["level_latest"] - lo) / (hi - lo)).clip(0, 1).where(fresh)
    f["environmental"] = factors["environmental"]
    f["trend"] = (rise / ref).clip(0, 1)
    w = {k: x[f"w_{k}"] for k in R.FACTORS}
    total = sum(w.values())
    return R.combine(f, {k: v / total for k, v in w.items()})


def part_c(inputs, factors, sig, events, periods) -> tuple[pd.DataFrame, pd.DataFrame]:
    c0, c1, t0, t1 = periods
    _, r_b1, _ = operate(sig, events, "S1", periods, "B1", 1.0)
    names = list(PARAMS)
    rng = np.random.default_rng(SEED)

    def to_x(u):
        return {n: PARAMS[n][0] + u[i] * (PARAMS[n][1] - PARAMS[n][0]) for i, n in enumerate(names)}

    def outputs(u):
        s = v2c_signal(to_x(u), inputs, factors, c1)
        a = R.threshold_for_budget(s, events, "S1", c0, c1, np.arange(10, 97.5, 2.5))
        r = R.evaluate(s >= a, events, "S1", t0, t1)
        leads = [v for v in r["leads"].values() if v is not None]
        p = R.paired_vs(r_b1["leads"], r["leads"])
        return {"POD": len(leads) / len(r["leads"]),
                "lead_median_h": float(np.median(leads)) if leads else 0.0,
                "fa_per_year": len(r["false_starts"]) / r["years"],
                "earlier_than_B1": p["earlier_than_B1"], "threshold": a}

    base_u = np.array([(PARAMS[n][2] - PARAMS[n][0]) / (PARAMS[n][1] - PARAMS[n][0]) for n in names])
    base = outputs(base_u)
    log(f"    V2c at base parameters: {base}")
    runs, effects = [], {n: [] for n in names}
    levels = np.array([0, 1 / 3, 2 / 3, 1])
    for t in range(MORRIS_R):
        u = rng.choice(levels[:2], size=len(names))
        y0 = outputs(u)
        runs.append({"trajectory": t, "step": -1, **to_x(u), **y0})
        for i in rng.permutation(len(names)):
            u2 = u.copy()
            u2[i] = u[i] + MORRIS_DELTA
            y1 = outputs(u2)
            runs.append({"trajectory": t, "step": int(i), **to_x(u2), **y1})
            effects[names[i]].append({k: (y1[k] - y0[k]) / MORRIS_DELTA for k in y0 if k != "threshold"})
            u, y0 = u2, y1
        log(f"    Morris trajectory {t + 1}/{MORRIS_R} done")
    rows = []
    for n, ee in effects.items():
        df = pd.DataFrame(ee)
        row = {"parameter": n}
        for k in df.columns:
            row[f"{k}_mu_star"] = round(float(df[k].abs().mean()), 3)
            row[f"{k}_sigma"] = round(float(df[k].std(ddof=1)), 3)
        rows.append(row)
    return pd.DataFrame(rows).sort_values("POD_mu_star", ascending=False), pd.DataFrame(runs)


def run() -> None:
    log("Loading Toulouse and Oslo Alna")
    data = {n: load(n) for n in ("toulouse_pontneuf", "oslo_alna")}
    pd.set_option("display.width", 220)
    pd.set_option("display.max_columns", 30)

    log("A. False-alarm budget")
    a = part_a(data)
    a.to_csv(R.RESULTS / "robust_budget.csv", index=False)
    print(a[["station", "budget", "level", "model", "hits", "events", "fa_per_year", "lead_median_h",
             "dlead_median_h", "earlier_than_B1", "later_than_B1", "sign_test_p"]].to_string(index=False))

    inputs, factors, sig, events, periods = data["toulouse_pontneuf"]
    log("B. Evaluation rules (Toulouse, S1)")
    b = part_b(inputs, sig, events, periods)
    b.to_csv(R.RESULTS / "robust_rules.csv", index=False)
    print(b[["window_h", "merge_h", "B1_hits", "B1_fa", "B1_lead", "V2c_hits", "V2c_fa", "V2c_lead",
             "earlier_than_B1", "later_than_B1", "sign_test_p"]].to_string(index=False))

    log("C. Morris elementary effects on V2c (Toulouse, S1)")
    c, runs = part_c(inputs, factors, sig, events, periods)
    c.to_csv(R.RESULTS / "morris_v2c.csv", index=False)
    runs.to_csv(R.RESULTS / "morris_runs.csv", index=False)
    print(c.to_string(index=False))
    log("Robustness finished")


if __name__ == "__main__":
    run()

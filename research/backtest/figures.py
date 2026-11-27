"""Manuscript figures (PDF for the paper, PNG for review) and summary tables.

Fig. 0  Architecture: live platform and backtest share the risk-factor code.
Fig. 1  January 2022 flood at Toulouse: water level and S1-S3, V0 and V2c
        scores with their thresholds and alert periods (budget 1/yr).
Fig. 2  Per-event lead time on the Toulouse test floods (S1): B1 vs V2c.
Fig. 3  Detection rate and median lead vs false-alarm budget (Toulouse, S1).
Fig. 4  Morris elementary effects on V2c (mu*): detection rate and lead time.
Fig. 5  Lead time across the three river regimes at a budget of 1/yr.

Tables: results/table_main.csv (budget 1/yr, all stations, S1 and S2).
Run after replay and robustness: python -m figures
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import replay as R  # noqa: E402
from robustness import load, operate  # noqa: E402

FIG = R.ROOT / "figures"
FIG.mkdir(parents=True, exist_ok=True)

COLORS = {"B1": "#1f5fa8", "V2c": "#2e8b3e", "V0": "#8cc63f", "V2ab": "#5aa9e6"}
LABELS = {"B1": "B1 water level only", "V0": "V0 engine as shipped",
          "V2ab": "V2ab corrected engine", "V2c": "V2c corrected + upstream rain"}
INK, MUTED, GRID = "#191919", "#666666", "#e6e6e6"
BUDGET_SWEEP = (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0)

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9, "axes.titlesize": 10,
    "axes.edgecolor": MUTED, "axes.labelcolor": INK, "xtick.color": MUTED, "ytick.color": MUTED,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False,
    "lines.linewidth": 2, "savefig.dpi": 300, "savefig.bbox": "tight",
})


def save(fig, name: str) -> None:
    for ext in ("pdf", "png"):
        fig.savefig(FIG / f"{name}.{ext}")
    plt.close(fig)
    R.log(f"    wrote figures/{name}.pdf/.png")


def fig0_architecture() -> None:
    from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

    fig, ax = plt.subplots(figsize=(7.6, 4.2))
    ax.set_xlim(0, 10)
    ax.set_ylim(0.7, 7.1)
    ax.axis("off")
    w, h = 3.25, 0.82

    def box(x, y, text, width=w, height=h, face="white", edge=MUTED, style="-", bold=False):
        ax.add_patch(FancyBboxPatch((x, y - height / 2), width, height, boxstyle="round,pad=0.02,rounding_size=0.08",
                                    facecolor=face, edgecolor=edge, linewidth=1.1, linestyle=style))
        ax.text(x + width / 2, y, text, ha="center", va="center", fontsize=6.6, color=INK,
                fontweight="bold" if bold else "normal", linespacing=1.35)

    def arrow(p, q, text=None):
        ax.add_patch(FancyArrowPatch(p, q, arrowstyle="-|>", mutation_scale=9, color=MUTED, linewidth=1.0,
                                     shrinkA=2, shrinkB=2))
        if text:
            ax.text((p[0] + q[0]) / 2, (p[1] + q[1]) / 2 + 0.14, text, ha="center", va="bottom",
                    fontsize=6.3, color=MUTED, style="italic")

    lx = 0.15
    rx = 10 - lx - w
    rows = (6.0, 4.8, 3.6, 2.4, 1.2)
    ax.text(lx + w / 2, 6.85, "Live platform", ha="center", fontsize=8.5, fontweight="bold", color=INK)
    ax.text(rx + w / 2, 6.85, "Historical backtest", ha="center", fontsize=8.5,
            fontweight="bold", color=INK)
    left = ("Open data APIs\nHub'Eau · NVE HydAPI · Open-Meteo",
            "Scheduled ingestion\nPostgreSQL / PostGIS, provenance",
            "risk_engine.py\ndatabase windows → score 0–100",
            "Early warnings · dashboard\nscenario simulator",
            "Language-model explanation\nreads the score, never computes it")
    right = ("Historical archives\ndata.gouv.fr · NVE HydAPI · ERA5",
             "Loaders\nhourly series, completeness report",
             "replay.py\nstrictly causal hour-by-hour replay",
             "events.py · scoring\nflood catalogue, scoring at\nmatched false-alarm budget",
             "robustness.py · figures.py\nsign test, bootstrap, Morris screening")
    for i, (yl, a, b) in enumerate(zip(rows, left, right)):
        box(lx, yl, a, style="--" if i == 4 else "-")
        box(rx, yl, b)
        if i < 4:
            arrow((lx + w / 2, yl - h / 2), (lx + w / 2, rows[i + 1] + h / 2))
            arrow((rx + w / 2, yl - h / 2), (rx + w / 2, rows[i + 1] + h / 2))
    cw, ch, cy = 2.1, 1.4, 3.6
    cx = 5 - cw / 2
    box(cx, cy, "risk_factors.py\nshared pure functions\nrainfall · hydrology\nsoil moisture · trend",
        width=cw, height=ch, face="#e3f1e5", edge=COLORS["V2c"], bold=False)
    arrow((lx + w, rows[2]), (cx, cy), "imports")
    arrow((rx, rows[2]), (cx + cw, cy), "imports")
    save(fig, "fig0_architecture")


def fig1_event(inputs, sig, events, periods) -> None:
    th = {}
    for m in ("V0", "V2c"):
        a, _, _ = operate(sig, events, "S1", periods, m, 1.0)
        th[m] = a
    t0, t1 = pd.Timestamp("2022-01-07"), pd.Timestamp("2022-01-14")
    lvl = inputs.loc[t0:t1, "level_now"] / 1000.0
    s = sig.loc[t0:t1]
    meta = pd.read_json(R.EVENTS / "thresholds_toulouse_pontneuf.json", typ="series")["thresholds_mm"]
    ev = events[(events["t_cross_S1"] >= t0) & (events["t_cross_S1"] <= t1)].iloc[0]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 5.0), sharex=True, height_ratios=[1, 1])
    ax1.plot(lvl.index, lvl.values, color=INK, linewidth=1.6)
    for k, ls in zip(("S1", "S2", "S3"), (":", "--", "-.")):
        ax1.axhline(meta[k] / 1000.0, color=MUTED, linewidth=1, linestyle=ls)
        ax1.text(lvl.index[0], meta[k] / 1000.0, f" {k}", va="bottom", color=MUTED, fontsize=8)
    ax1.set_ylabel("Water level at Pont-Neuf (m)")
    ax1.set_title("Garonne at Toulouse, January 2022 flood", loc="left")

    for m in ("V0", "V2c"):
        ax2.plot(s.index, s[m], color=COLORS[m], label=f"{LABELS[m]} (threshold {th[m]:.1f})")
        ax2.axhline(th[m], color=COLORS[m], linewidth=1, linestyle="--")
    b1_on = s["B1"] >= operate(sig, events, "S1", periods, "B1", 1.0)[0]
    first_b1 = b1_on[b1_on].index.min()
    first_v2c = s.index[s["V2c"] >= th["V2c"]].min()
    for ax in (ax1, ax2):
        ax.axvline(ev["t_cross_S1"], color=INK, linewidth=1)
    ax2.annotate("S1 crossed", (ev["t_cross_S1"], 98), ha="right", va="top", fontsize=8, color=INK,
                 xytext=(-4, 0), textcoords="offset points")
    for t, m in ((first_b1, "B1"), (first_v2c, "V2c")):
        if pd.notna(t):
            ax2.plot([t], [3], marker="v", markersize=9, color=COLORS[m],
                     markeredgecolor="white", markeredgewidth=1.5, clip_on=False)
    ax2.plot([], [], marker="v", linestyle="none", color=COLORS["V2c"], label="first V2c alert")
    ax2.plot([], [], marker="v", linestyle="none", color=COLORS["B1"], label="first B1 alert (level only)")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("Risk score (0-100)")
    ax2.legend(loc="upper center", bbox_to_anchor=(0.5, -0.38), ncol=2, fontsize=7.5)
    fig.autofmt_xdate()
    save(fig, "fig1_event_2022")


def fig2_paired(sig, events, periods) -> None:
    _, r_b1, _ = operate(sig, events, "S1", periods, "B1", 1.0)
    _, r_c, _ = operate(sig, events, "S1", periods, "V2c", 1.0)
    ts = sorted(r_b1["leads"])
    fig, ax = plt.subplots(figsize=(6.0, 4.2))
    for i, t in enumerate(ts):
        a, b = r_b1["leads"][t], r_c["leads"][t]
        if a is not None and b is not None:
            ax.plot([a, b], [i, i], color=GRID, linewidth=2, zorder=1)
        for v, m in ((a, "B1"), (b, "V2c")):
            if v is not None:
                ax.scatter([v], [i], s=55, color=COLORS[m], edgecolor="white", linewidth=1.5, zorder=2)
    ax.set_yticks(range(len(ts)))
    ax.set_yticklabels([t.strftime("%Y-%m-%d") for t in ts])
    ax.invert_yaxis()
    ax.set_xlabel("Lead time before the S1 crossing (h)")
    ax.set_title("Toulouse test floods (S1), budget 1 false alarm/yr", loc="left")
    for m in ("B1", "V2c"):
        ax.scatter([], [], s=55, color=COLORS[m], label=LABELS[m])
    ax.legend(loc="lower right", fontsize=8)
    ax.grid(axis="y", visible=False)
    save(fig, "fig2_paired_leads")


def fig3_budget(sig, events, periods) -> None:
    rows = []
    for b in BUDGET_SWEEP:
        for m in ("B1", "V0", "V2c"):
            _, r, met = operate(sig, events, "S1", periods, m, b)
            rows.append({"budget": b, "model": m, "POD": met["hits"] / met["events"],
                         "lead": met["lead_median_h"], "fa": met["fa_per_year"]})
    R.TARGET_FA_PER_YEAR = 1.0
    df = pd.DataFrame(rows)
    df.to_csv(R.RESULTS / "budget_sweep.csv", index=False)
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(7.2, 3.2))
    for m, ms in (("V2c", 8), ("V0", 6), ("B1", 4.5)):
        d = df[df["model"] == m]
        a1.plot(d["budget"], d["POD"], marker="o", markersize=ms, color=COLORS[m], label=LABELS[m])
        a2.plot(d["budget"], d["lead"], marker="o", markersize=ms, color=COLORS[m])
    a1.set_ylim(0, 1.05)
    a1.set_ylabel("Detection rate (test)")
    a2.set_ylabel("Median lead time (h)")
    for ax in (a1, a2):
        ax.set_xlabel("False-alarm budget on calibration (per year)")
    a1.legend(loc="lower right", fontsize=7.5)
    fig.suptitle("Toulouse, S1 floods: operating points chosen on calibration, scored on test",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, "fig3_budget_curves")


def fig4_morris() -> None:
    m = pd.read_csv(R.RESULTS / "morris_v2c.csv")
    names = {"w_rainfall": "rainfall weight", "w_hydrology": "hydrology weight",
             "w_environmental": "soil moisture weight", "w_trend": "trend weight",
             "hydro_lo_q": "hydrology lower bound", "hydro_hi_q": "hydrology upper bound",
             "trend_ref_q": "trend reference", "rain_ref_mm": "rainfall reference"}
    m["label"] = m["parameter"].map(names)
    fig, axes = plt.subplots(1, 2, figsize=(7.4, 3.8))
    panels = (("POD", "detection rate", False), ("lead_median_h", "median lead time (h)", True))
    for ax, (key, title, log) in zip(axes, panels):
        mu = m[f"{key}_mu_star"].clip(lower=1e-3)
        sd = m[f"{key}_sigma"].clip(lower=1e-3)
        lo = min(mu.min(), sd.min()) / 1.6 if log else 0.0
        hi = max(mu.max(), sd.max()) * (1.6 if log else 1.12)
        ax.scatter(mu, sd, s=36, color=COLORS["V2c"], edgecolor="white", linewidth=1.5, zorder=3)
        ax.plot([lo, hi], [lo, hi], color=INK, linewidth=0.8, linestyle="--", alpha=0.5, zorder=1)
        if log:
            ax.set_xscale("log")
            ax.set_yscale("log")
            for axis in (ax.xaxis, ax.yaxis):
                axis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:g}"))

        def pos(x, y):
            if log:
                return ((np.log10(x) - np.log10(lo)) / (np.log10(hi) - np.log10(lo)),
                        (np.log10(y) - np.log10(lo)) / (np.log10(hi) - np.log10(lo)))
            return (x - lo) / (hi - lo), (y - lo) / (hi - lo)

        groups = []
        for label, x, y in sorted(zip(m["label"], mu, sd), key=lambda r: -r[2]):
            px, py = pos(x, y)
            for g in groups:
                if abs(g["px"] - px) < 0.015 and abs(g["py"] - py) < 0.015:
                    g["labels"].append(label)
                    break
            else:
                groups.append({"x": x, "y": y, "px": px, "py": py, "labels": [label]})
        nudge = {("POD", "trend reference"): (5, 2, "bottom"), ("POD", "trend weight"): (5, -2, "top"),
                 ("lead_median_h", "rainfall weight"): (5, 2, "bottom"),
                 ("lead_median_h", "trend weight"): (5, -2, "top"),
                 ("lead_median_h", "hydrology upper bound"): (5, 2, "bottom"),
                 ("lead_median_h", "hydrology lower bound"): (5, -2, "top")}
        for g in groups:
            dx, dy, va = nudge.get((key, g["labels"][0]), (5, 0, "center"))
            ax.annotate(" / ".join(g["labels"]), (g["x"], g["y"]), xytext=(dx, dy),
                        textcoords="offset points", fontsize=7, color=INK, va=va)
        ax.set_xlim(lo, hi)
        ax.set_ylim(lo, hi)
        ax.set_xlabel(f"mu* on {title}" + (" (log)" if log else ""))
        ax.set_ylabel("sigma" + (" (log)" if log else ""))
    fig.suptitle("Morris elementary effects on V2c (Toulouse, S1, budget 1/yr); dashed line: sigma = mu*",
                 x=0.01, ha="left", fontsize=10)
    fig.tight_layout()
    save(fig, "fig4_morris")


def fig5_regimes(table: pd.DataFrame) -> None:
    st = [("toulouse_pontneuf", "Garonne, Toulouse\n(fast, upstream-fed)", "V2c"),
          ("oslo_alna", "Alna, Oslo\n(flashy urban stream)", "V2ab"),
          ("oslo_akerselva", "Akerselva, Oslo\n(lake-regulated)", "V2ab")]
    fig, ax = plt.subplots(figsize=(6.4, 3.4))
    x = np.arange(len(st))
    for k, (m_off, col) in enumerate(((-0.17, "B1"), (0.17, "composite"))):
        vals, labels = [], []
        for name, _, comp in st:
            model = "B1" if col == "B1" else comp
            r = table[(table["station"] == name) & (table["level"] == "S1") & (table["model"] == model)].iloc[0]
            vals.append(0 if pd.isna(r["lead_median_h"]) else r["lead_median_h"])
            labels.append(f"{int(r['hits'])}/{int(r['events'])}")
        color = COLORS["B1"] if col == "B1" else COLORS["V2c"]
        bars = ax.bar(x + m_off, vals, width=0.32, color=color,
                      label="B1 water level only" if col == "B1" else "corrected composite (V2c / V2ab)")
        for b, lab in zip(bars, labels):
            ax.text(b.get_x() + b.get_width() / 2, b.get_height() + 0.3, lab, ha="center", va="bottom",
                    fontsize=8, color=INK)
    ax.set_xticks(x)
    ax.set_xticklabels([s[1] for s in st])
    ax.set_ylabel("Median lead time, S1 floods (h)")
    ax.set_title("Same budget (1 false alarm/yr): floods detected shown above bars", loc="left")
    ax.set_ylim(0, max(ax.get_ylim()[1], 24) * 1.12)
    ax.legend(loc="upper left", fontsize=8)
    ax.grid(axis="x", visible=False)
    save(fig, "fig5_regimes")


def main_table() -> pd.DataFrame:
    keep = ("V0 fixed A=25", "V0", "V2a", "V2ab", "V2c", "B1", "B2", "B3", "B3c")
    frames = []
    for name in R.STATIONS:
        m = pd.read_csv(R.RESULTS / f"metrics_{name}.csv")
        p = pd.read_csv(R.RESULTS / f"paired_{name}.csv")
        m = m[m["model"].isin(keep)].merge(p, on=["level", "model"], how="left")
        m.insert(0, "station", name)
        frames.append(m)
    t = pd.concat(frames, ignore_index=True)
    cols = ["station", "level", "model", "threshold", "hits", "events", "fa_per_year", "POD_ci",
            "lead_median_h", "lead_q1_h", "lead_q3_h", "time_in_alert_pct", "dlead_median_h",
            "earlier_than_B1", "later_than_B1"]
    t[cols].to_csv(R.RESULTS / "table_main.csv", index=False)
    R.log("    wrote results/table_main.csv")
    return t


def run() -> None:
    fig0_architecture()
    R.log("Figures")
    table = main_table()
    inputs, factors, sig, events, periods = load("toulouse_pontneuf")
    fig1_event(inputs, sig, events, periods)
    fig2_paired(sig, events, periods)
    fig3_budget(sig, events, periods)
    fig4_morris()
    fig5_regimes(table)
    R.log("Figures finished")


if __name__ == "__main__":
    run()

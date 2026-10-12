"""
paper_figures.py — regenerate the data figures of the article from the models

Writes to Images/reproduced/:
    Figure_3.png   mixed-population failure probability P_fail(t, PCR)
    Figure_4.png   Weibull survival (A) and hazard (B)
    Figure_5.png   Monte Carlo check of the ASI-PLC interlock (n = 200, seed 2025)
    Figure_S1.png  Paris–Erdogan crack growth (Supplementary Note S1)
    Figure_S2.png  workforce DTMC (Supplementary Note S2)

The figures are recomputed from atc_models.py and atc_sim.py, so every plotted
value equals the value in the article. Fonts and layout may differ slightly
from the typeset versions in Images/. Figures 1 and 2 (architecture and state
machine) are diagrams, not model outputs, and are provided only as images.

Run:  python paper_figures.py
"""

from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

import atc_models as m
from atc_sim import SEED, FaultType, HEARTBEAT_THRESHOLD_MS, run_simulation, summarize

OUT = os.path.join("Images", "reproduced")
BLUE, ORANGE, GOLD, GREEN, RED, BROWN = "#2b78d6", "#e8673a", "#eaa000", "#18a37a", "#8b1a14", "#8a5a00"

plt.rcParams.update({
    "font.family": "serif",
    "font.serif": ["Liberation Serif", "Times New Roman", "DejaVu Serif"],
    "mathtext.fontset": "dejavuserif",
    "font.size": 12, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": "#e3e3e3", "axes.axisbelow": True,
    "savefig.dpi": 300, "savefig.bbox": "tight",
})


def figure_3():
    t = np.linspace(0, 30, 601)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    styles = [(0.60, ORANGE, "--"), (0.70, GOLD, "-."), (0.75, GREEN, ":"), (0.97, BLUE, "-")]
    for pcr, c, ls in styles:
        y = 100 * m.p_fail(t, pcr)
        ax.plot(t, y, color=c, ls=ls, lw=2.4)
        ax.text(30.4, y[-1], f"PCR = {pcr:.2f}", va="center", fontsize=11)
    ax.axvline(10, color="grey", ls=":", lw=1)
    for pcr, dy in [(0.60, 2.5), (0.97, -3.5)]:
        v = 100 * m.p_fail(10, pcr)
        ax.plot(10, v, "o", color="#222", ms=7, zorder=5)
        ax.text(10.5, v + dy, f"{v:.1f}%", fontsize=11)
    ax.set_xlim(0, 30); ax.set_ylim(0, 60)
    ax.set_xlabel("Service time t (years)"); ax.set_ylabel(r"$P_{fail}(t$, PCR) (%)")
    fig.savefig(os.path.join(OUT, "Figure_3.png")); plt.close(fig)


def figure_4():
    t = np.linspace(0.01, 30, 600)
    fig, (a, b) = plt.subplots(1, 2, figsize=(9.6, 3.9))
    a.plot(t, m.weibull_survival(t, m.BETA, m.ETA_C), color=BLUE, lw=2.4,
           label=rf"Compliant ($\eta_c$ = {m.ETA_C:.0f} yr)")
    a.plot(t, m.weibull_survival(t, m.BETA, m.ETA_N), color=ORANGE, lw=2.4, ls="--",
           label=rf"Non-compliant ($\eta_n$ = {m.ETA_N:.0f} yr)")
    a.set_xlim(0, 30); a.set_ylim(0, 1.02); a.legend(frameon=False, loc="lower left")
    a.set_xlabel("Service time t (years)"); a.set_ylabel("Survival R(t)")
    a.text(0.02, 1.02, "(A)", transform=a.transAxes, fontweight="bold")
    b.semilogy(t, m.weibull_hazard(t, m.BETA, m.ETA_C), color=BLUE, lw=2.4)
    b.semilogy(t, m.weibull_hazard(t, m.BETA, m.ETA_N), color=ORANGE, lw=2.4, ls="--")
    b.set_xlim(0, 30); b.set_ylim(1e-4, 10)
    b.set_xlabel("Service time t (years)"); b.set_ylabel("Hazard rate h(t) (1/yr, log scale)")
    b.text(0.02, 1.02, "(B)", transform=b.transAxes, fontweight="bold")
    fig.tight_layout(); fig.savefig(os.path.join(OUT, "Figure_4.png")); plt.close(fig)


def figure_5():
    res = run_simulation(seed=SEED)
    s = summarize(res)
    order = [(FaultType.NONE, "Valid"), (FaultType.NON_COMPLY, "Preheat"), (FaultType.MITM, "MitM"),
             (FaultType.REPLAY, "Replay"), (FaultType.TIMEOUT, "Timeout")]
    cols = [BLUE, ORANGE, GREEN, GOLD, BROWN]
    with plt.rc_context({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"]}):
        fig, ax = plt.subplots(1, 3, figsize=(12, 4.2))
        rng = np.random.default_rng(0)  # jitter only; does not touch the simulation
        for i, ((f, _), c) in enumerate(zip(order, cols)):
            lat = [r.latency_ms for r in res if r.fault_type == f]
            ax[0].scatter(i + rng.uniform(-0.25, 0.25, len(lat)), lat, s=14, color=c, alpha=0.85)
        ax[0].axhline(HEARTBEAT_THRESHOLD_MS, color=RED, ls="--", lw=1.6, label="500 ms threshold")
        ax[0].set_xticks(range(5)); ax[0].set_xticklabels([n for _, n in order], rotation=35, ha="right")
        ax[0].set_ylabel("Latency (ms)"); ax[0].set_title("(A) Latency by scenario"); ax[0].legend(frameon=False)

        states = ["COMPLIANT", "NON_COMPLIANT", "HARD_LOCK", "SOFT_LOCK"]
        vals = [s["state_counts"].get(k, 0) for k in states]
        bars = ax[1].bar(states, vals, color=[BLUE, ORANGE, RED, BROWN])
        for bar, v in zip(bars, vals):
            ax[1].text(bar.get_x() + bar.get_width() / 2, v + 2, str(v), ha="center")
        ax[1].set_ylim(0, max(vals) * 1.15); ax[1].set_ylabel("Runs")
        ax[1].set_title(f"(B) Outcomes (n = {s['n']})")
        ax[1].tick_params(axis="x", rotation=35)
        for lab in ax[1].get_xticklabels():
            lab.set_ha("right")

        x = np.arange(5)
        means = [np.mean([r.latency_ms for r in res if r.fault_type == f]) for f, _ in order]
        p95 = [np.percentile([r.latency_ms for r in res if r.fault_type == f], 95) for f, _ in order]
        ax[2].bar(x - 0.18, means, 0.36, color=BLUE, label="Mean")
        ax[2].bar(x + 0.18, p95, 0.36, color="#86b6f0", label="95th percentile")
        ax[2].axhline(HEARTBEAT_THRESHOLD_MS, color=RED, ls="--", lw=1.6)
        ax[2].set_xticks(x); ax[2].set_xticklabels([n for _, n in order], rotation=35, ha="right")
        ax[2].set_ylabel("Latency (ms)"); ax[2].set_title("(C) Mean and P95 latency")
        ax[2].legend(frameon=False, ncol=2, loc="upper left")
        ax[2].set_ylim(0, 680)
        fig.tight_layout(); fig.savefig(os.path.join(OUT, "Figure_5.png")); plt.close(fig)


def figure_s1():
    life_air, life_h = m.fatigue_life_years(m.C_AIR), m.fatigue_life_years(m.C_H)
    fig, ax = plt.subplots(figsize=(7.2, 4.6))
    t1 = np.linspace(0, life_air, 800); t2 = np.linspace(0, life_h, 800)
    ax.plot(t1, m.crack_depth(t1, m.C_AIR) * 1e3, color=BLUE, lw=3,
            label=rf"$C_{{air}}$: fracture at {life_air:.1f} yr")
    ax.plot(t2, m.crack_depth(t2, m.C_H) * 1e3, color=ORANGE, lw=3, ls="--",
            label=rf"$C_H = 4\,C_{{air}}$ (assumed): fracture at {life_h:.1f} yr")
    ax.axhline(m.AC * 1e3, color=RED, ls="--", lw=1.8)
    ax.text(1, m.AC * 1e3 + 0.3, r"Critical crack depth $a_c$ = 10 mm")
    ax.axvline(m.DESIGN_LIFE, color="grey", ls=":", lw=1.8)
    ax.text(m.DESIGN_LIFE + 0.8, 8.6, "30-yr design life", color="#444")
    a30 = m.crack_depth(30, m.C_AIR) * 1e3
    ax.plot(30, a30, "o", color=BLUE, ms=8); ax.text(31.5, a30 - 1.0, f"a(30 yr) ≈ {a30:.1f} mm")
    ax.plot([life_h, life_air], [10, 10], "o", color="#222", ms=9)
    ax.set_xlim(0, 60); ax.set_ylim(0, 11.2)
    ax.set_xlabel("Service time t (years)"); ax.set_ylabel("Crack depth a (mm)")
    ax.legend(loc="center", frameon=True)
    fig.savefig(os.path.join(OUT, "Figure_S1.png")); plt.close(fig)


def figure_s2():
    with plt.rc_context({"font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "axes.grid": False}):
        fig, axes = plt.subplots(1, 2, figsize=(10, 4), sharey=True)
        years = np.arange(31)
        for ax, P, title in [(axes[0], m.P_WITHOUT, "(A) Without intervention"),
                             (axes[1], m.P_WITH, "(B) With intervention")]:
            tr = 100 * m.dtmc_trajectory(P)
            st = 100 * m.dtmc_stationary(P)
            ax.stackplot(years, tr[:, 0], tr[:, 1], tr[:, 2], colors=["#e57373", "#ffb74d", "#64b5f6"],
                         labels=["Not H$_2$-ready (S$_0$)", "Partially ready (S$_1$)", "H$_2$-ready (S$_2$)"],
                         edgecolor="white", linewidth=0.6)
            ax.plot(10, 100 - tr[10, 2], "o", color="#1f3550", ms=7)
            ax.annotate(f"{tr[10, 2]:.1f}% at year 10", (10, 100 - tr[10, 2]), xytext=(12, 8),
                        textcoords="offset points", color="#1f3550",
                        bbox=dict(fc="white", ec="none", alpha=0.75))
            ax.axhline(100 - st[2], color="#1f3550", ls=":", lw=1.8)
            ax.text(29.5, 100 - st[2] + 3, f"stationary H$_2$-ready = {st[2]:.1f}%", ha="right",
                    color="#1f3550", bbox=dict(fc="white", ec="none", alpha=0.75))
            ax.set_xlim(0, 30); ax.set_ylim(0, 100); ax.set_title(title); ax.set_xlabel("Year")
        axes[0].set_ylabel("Share of workforce (%)")
        h, l = axes[0].get_legend_handles_labels()
        fig.legend(h, l, loc="lower center", ncol=3, frameon=False, bbox_to_anchor=(0.5, -0.06))
        fig.tight_layout(rect=(0, 0.06, 1, 1))
        fig.savefig(os.path.join(OUT, "Figure_S2.png")); plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for f in (figure_3, figure_4, figure_5, figure_s1, figure_s2):
        f()
        print(f"  {f.__name__} written")
    print(f"Done. Figures saved to {OUT}/")

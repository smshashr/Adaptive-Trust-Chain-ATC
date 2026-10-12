"""
reproduce_results.py — recompute every quantitative result reported in the
manuscript and the Supplementary Material and compare it with the reported value.

Run:   python reproduce_results.py
Exit code 0 if every value matches at the reported precision, 1 otherwise.

Reported values are taken from: Section 4.2 and Table 6 (mixed-population
Weibull model), Section 4.3 and Figure 4 (survival and hazard), Section 5.4,
Section 4.4 and Supplementary Table S2 (Monte Carlo), Supplementary Note S1
(fatigue) and Supplementary Note S2 (workforce DTMC).
"""

from __future__ import annotations

import sys

import numpy as np

import atc_models as m
from atc_sim import SEED, run_simulation, summarize

rows = []


def check(label, computed, reported, decimals=1):
    ok = round(float(computed), decimals) == round(float(reported), decimals)
    rows.append((label, f"{computed:.{decimals}f}", f"{reported:.{decimals}f}", ok))


pct = lambda x: 100.0 * float(x)

# ── Table 6 and Section 4.2 ──────────────────────────────────────────────────
TABLE6 = {  # (beta, eta_c, eta_n): (P(10) at 0.60 %, P(10) at 0.97 %, relative reduction %)
    (2.5, 50, 8): (34.1, 4.2, 87.7), (2.5, 40, 8): (34.9, 5.5, 84.3),
    (2.5, 60, 8): (33.7, 3.6, 89.4), (2.5, 50, 5): (40.9, 4.7, 88.5),
    (2.5, 50, 12): (19.8, 3.1, 84.2), (2.5, 40, 12): (20.6, 4.4, 78.7),
    (2.5, 60, 5): (40.5, 4.1, 89.9), (2.0, 50, 8): (34.0, 6.2, 81.8),
    (3.0, 50, 8): (34.8, 3.3, 90.4),
}
for (b, ec, en), (p60, p97, rr) in TABLE6.items():
    kw = dict(beta=b, eta_c=ec, eta_n=en)
    tag = f"Table 6 β={b}, ηc={ec}, ηn={en}"
    check(f"{tag}: P_fail(10), PCR 0.60 (%)", pct(m.p_fail(10, 0.60, **kw)), p60)
    check(f"{tag}: P_fail(10), PCR 0.97 (%)", pct(m.p_fail(10, 0.97, **kw)), p97)
    check(f"{tag}: relative reduction (%)", pct(m.relative_reduction(10, **kw)), rr)

check("Sec 4.2: 30-yr P_fail, PCR 0.60 (%)", pct(m.p_fail(30, 0.60)), 54.6)
check("Sec 4.2: 30-yr P_fail, PCR 0.97 (%)", pct(m.p_fail(30, 0.97)), 26.6)
check("Sec 4.2: 30-yr relative reduction (%)", pct(m.relative_reduction(30)), 51.3)
check("Sec 4.2: 10-yr reduction vs PCR 0.70 (%)", pct(m.relative_reduction(10, pcr_low=0.70)), 83.9)
check("Sec 4.2: 10-yr reduction vs PCR 0.75 (%)", pct(m.relative_reduction(10, pcr_low=0.75)), 80.9)
red10 = [pct(m.relative_reduction(10, beta=b, eta_c=ec, eta_n=en)) for b, ec, en in m.SENSITIVITY_CASES]
check("Sec 4.2: min 10-yr reduction across Table 6 (%)", min(red10), 78.7)
check("Sec 4.2: max 10-yr reduction across Table 6 (%)", max(red10), 90.4)
check("Sec 4.2: 30-yr reduction, ηc = 40 yr (%)", pct(m.relative_reduction(30, eta_c=40)), 36.0)
check("Sec 4.2: 30-yr reduction, ηc = 60 yr (%)", pct(m.relative_reduction(30, eta_c=60)), 62.4)

# ── Survival and hazard (Section 4.3, Figure 4) and Section 5.4 ────────────
check("Sec 4.3, Fig 4A: R_c(10)", m.weibull_survival(10, m.BETA, m.ETA_C), 0.98, 2)
check("Sec 4.3, Fig 4A: R_c(30)", m.weibull_survival(30, m.BETA, m.ETA_C), 0.76, 2)
check("Sec 4.3, Fig 4A: R_n(10)", m.weibull_survival(10, m.BETA, m.ETA_N), 0.17, 2)
check("Sec 4.3, Fig 4A: R_n(20) ('effectively zero')", m.weibull_survival(20, m.BETA, m.ETA_N), 0.00, 2)
check("Sec 4.3, Fig 4B: hazard ratio (ηc/ηn)^β", (m.ETA_C / m.ETA_N) ** m.BETA, 98, 0)
check("Sec 5.4: compliant P_c(30) (%)", pct(m.weibull_cdf(30, m.BETA, m.ETA_C)), 24, 0)

# ── Monte Carlo (Section 4.4, Supplementary Table S2) ────────────────────────
s = summarize(run_simulation(seed=SEED))
bf, sc = s["by_fault"], s["state_counts"]
check("MC: valid runs COMPLIANT", bf["none"]["COMPLIANT"], 120, 0)
check("MC: non-compliant preheat -> NON_COMPLIANT", bf["non_comply"]["NON_COMPLIANT"], 50, 0)
check("MC: MitM -> HARD_LOCK", bf["mitm"]["HARD_LOCK"], 10, 0)
check("MC: replay -> HARD_LOCK", bf["replay"]["HARD_LOCK"], 10, 0)
check("MC: timeout -> SOFT_LOCK", bf["timeout"]["SOFT_LOCK"], 9, 0)
check("MC: timeout -> COMPLIANT (within window)", bf["timeout"]["COMPLIANT"], 1, 0)
check("MC: total COMPLIANT", sc.get("COMPLIANT", 0), 121, 0)
check("MC: total NON_COMPLIANT", sc.get("NON_COMPLIANT", 0), 50, 0)
check("MC: total HARD_LOCK", sc.get("HARD_LOCK", 0), 20, 0)
check("MC: total SOFT_LOCK", sc.get("SOFT_LOCK", 0), 9, 0)
check("MC: false permits", s["false_permits"], 0, 0)
check("MC: false negatives", s["false_negatives"], 0, 0)
check("MC: valid latency mean (ms)", s["valid_mean_ms"], 274.6)
check("MC: valid latency 95th percentile (ms)", s["valid_p95_ms"], 320.6)
check("MC: valid latency maximum (ms)", s["valid_max_ms"], 348.6)
in_window = [lat for lat, state in s["timeout_runs"] if state == "COMPLIANT"]
check("MC: in-window timeout sample (ms)", in_window[0] if in_window else float("nan"), 486.2)

# ── Fatigue (Supplementary Note S1) ──────────────────────────────────────────
life_air, life_h = m.fatigue_life_years(m.C_AIR), m.fatigue_life_years(m.C_H)
check("Note S1: fracture life, C_air (years)", life_air, 53.6)
check("Note S1: fracture life, C_H = 4 C_air (years)", life_h, 13.4)
check("Note S1: a(30 yr), C_air (mm)", m.crack_depth(30, m.C_AIR) * 1e3, 1.6)
check("Note S1: fatigue-life reduction (%)", pct(1 - life_h / life_air), 75, 0)

# ── Workforce DTMC (Supplementary Note S2) ───────────────────────────────────
wo, wi = m.dtmc_trajectory(m.P_WITHOUT), m.dtmc_trajectory(m.P_WITH)
check("Note S2: H2-ready share at year 10, without (%)", pct(wo[10, 2]), 12.3)
check("Note S2: stationary H2-ready share, without (%)", pct(m.dtmc_stationary(m.P_WITHOUT)[2]), 22.6)
check("Note S2: H2-ready share at year 10, with (%)", pct(wi[10, 2]), 58.0)
check("Note S2: stationary H2-ready share, with (%)", pct(m.dtmc_stationary(m.P_WITH)[2]), 90.0)
check("Note S2: difference at year 10 (pp)", pct(wi[10, 2] - wo[10, 2]), 45.7)

# ── Report ───────────────────────────────────────────────────────────────────
w = max(len(r[0]) for r in rows)
print(f"{'Quantity'.ljust(w)}  {'Computed':>10}  {'Reported':>10}  Result")
print("-" * (w + 34))
for label, comp, rep, ok in rows:
    print(f"{label.ljust(w)}  {comp:>10}  {rep:>10}  {'PASS' if ok else 'FAIL'}")
n_fail = sum(not r[3] for r in rows)
print("-" * (w + 34))
print(f"{len(rows) - n_fail}/{len(rows)} values reproduced at the reported precision.")
sys.exit(1 if n_fail else 0)

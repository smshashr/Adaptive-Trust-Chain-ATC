"""
atc_models.py — analytical scenario models of the manuscript

* Mixed-population Weibull model (Section 3.4.1-3.4.2, Equations 1-2, Table 6)
* Paris–Erdogan fatigue crack growth (Supplementary Note S1, Equations S1-S2)
* Discrete-time Markov chain of workforce qualification (Supplementary Note S2)

All parameter values are scenario assumptions listed in Supplementary Table S1.
The outputs illustrate those assumptions; they are not estimates of observed
failure rates, crack growth in a specific weld, or workforce statistics.
"""

from __future__ import annotations

import numpy as np

# ── Mixed-population Weibull model ───────────────────────────────────────────
BETA = 2.5          # shape parameter (assumed)
ETA_C = 50.0        # characteristic life, compliant population (years, assumed)
ETA_N = 8.0         # characteristic life, non-compliant population (years, assumed)
PCR_LOW = 0.60      # lower-compliance scenario (assumed; not a measured rate)
PCR_HIGH = 0.97     # high-compliance scenario (assumed; not a demonstrated ATC performance)
PCR_SENSITIVITY = (0.70, 0.75)
DESIGN_LIFE = 30.0  # years

# Table 6: (beta, eta_c, eta_n)
SENSITIVITY_CASES = [
    (2.5, 50, 8), (2.5, 40, 8), (2.5, 60, 8), (2.5, 50, 5), (2.5, 50, 12),
    (2.5, 40, 12), (2.5, 60, 5), (2.0, 50, 8), (3.0, 50, 8),
]


def weibull_cdf(t, beta, eta):
    """P_i(t) = 1 - exp[-(t/eta)^beta]   (Equation 2)."""
    return 1.0 - np.exp(-np.power(np.asarray(t, dtype=float) / eta, beta))


def weibull_survival(t, beta, eta):
    """R_i(t) = 1 - P_i(t)."""
    return 1.0 - weibull_cdf(t, beta, eta)


def weibull_hazard(t, beta, eta):
    """h_i(t) = (beta/eta) (t/eta)^(beta-1)."""
    t = np.asarray(t, dtype=float)
    return (beta / eta) * np.power(t / eta, beta - 1.0)


def p_fail(t, pcr, beta=BETA, eta_c=ETA_C, eta_n=ETA_N):
    """P_fail(t, PCR) = PCR·P_c(t) + (1 − PCR)·P_n(t)   (Equation 1)."""
    return pcr * weibull_cdf(t, beta, eta_c) + (1.0 - pcr) * weibull_cdf(t, beta, eta_n)


def relative_reduction(t, pcr_low=PCR_LOW, pcr_high=PCR_HIGH, **kw):
    """1 − P_fail(t, PCR_high) / P_fail(t, PCR_low)."""
    return 1.0 - p_fail(t, pcr_high, **kw) / p_fail(t, pcr_low, **kw)


# ── Paris–Erdogan fatigue crack growth (Note S1) ─────────────────────────────
Y = 1.12                 # geometry factor (Newman and Raju, 1981, shallow long-crack limit)
A0 = 0.5e-3              # initial crack depth (m, assumed)
AC = 10e-3               # critical crack depth (m, assumed)
C_AIR = 6.9e-12          # m/cycle·(MPa√m)^-3 (Barsom and Rolfe, 1999)
M = 3.0
H_MULTIPLIER = 4.0       # C_H / C_air (assumed)
C_H = H_MULTIPLIER * C_AIR
DELTA_SIGMA = 200.0      # effective stress range (MPa, assumed)
CYCLES_PER_YEAR = 3000.0 # (assumed)


def _k(C):
    return C * (Y * DELTA_SIGMA) ** 3 * np.pi ** 1.5


def fatigue_life_years(C, a0=A0, ac=AC):
    """t_f = N_f / f with N_f = 2(a0^-1/2 − ac^-1/2) / [C (YΔσ)^3 π^3/2]   (Equation S2, m = 3)."""
    n_f = 2.0 * (a0 ** -0.5 - ac ** -0.5) / _k(C)
    return n_f / CYCLES_PER_YEAR


def crack_depth(t_years, C, a0=A0, ac=AC):
    """Closed-form a(t) from Equation S1 (m = 3), capped at the critical depth (m)."""
    t = np.asarray(t_years, dtype=float)
    inv_sqrt = a0 ** -0.5 - 0.5 * _k(C) * CYCLES_PER_YEAR * t
    a = np.where(inv_sqrt > 0, 1.0 / np.square(np.maximum(inv_sqrt, 1e-30)), np.inf)
    return np.minimum(a, ac)


# ── Workforce DTMC (Note S2) ─────────────────────────────────────────────────
PI0 = np.array([0.70, 0.22, 0.08])   # [S0 unqualified, S1 basic awareness, S2 H2-ready] (assumed)

# Annual transition matrices (rows: from-state; columns: to-state). All values
# are assumed scenario values (Supplementary Table S1). P_WITHOUT: voluntary
# upskilling S0->S1 of about 7%/yr and qualification losses S1->S0 and S2->S1.
P_WITHOUT = np.array([
    [0.927, 0.073, 0.000],
    [0.113, 0.858, 0.029],
    [0.000, 0.039, 0.961],
])
# P_WITH: structured intervention (targeted H2 training, refresher training,
# supervisory support). Optimistic in light of Blume et al. (2010).
P_WITH = np.array([
    [0.795, 0.205, 0.000],
    [0.080, 0.745, 0.175],
    [0.000, 0.014, 0.986],
])


def dtmc_trajectory(P, pi0=PI0, years=30):
    """π_{k+1} = π_k P; returns an array of shape (years + 1, 3)."""
    out = [np.asarray(pi0, dtype=float)]
    for _ in range(years):
        out.append(out[-1] @ P)
    return np.array(out)


def dtmc_stationary(P):
    """Stationary distribution π = π P with Σπ = 1."""
    n = P.shape[0]
    A = P.T - np.eye(n)
    A[-1] = 1.0
    b = np.zeros(n)
    b[-1] = 1.0
    return np.linalg.solve(A, b)

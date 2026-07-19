"""
vol_analysis.py
===============
Span-weighted PCA and tail-distribution fitting for S1 piecewise-constant
instantaneous forward rates from the CMTRateBootstrap NPZ panel.

Mathematical framework
----------------------
Forward rate changes Δf_d(T_i) are daily first differences of S1 forward rates.

Gram matrix:
    G = diag(ΔT_i),  ΔT_i = T_i - T_{i-1},  T_0 = 0
weights each tenor by span width in the L²([0, T_max]) inner product.

Under multivariate t_ν(0, Σ) with covariance C = ν/(ν-2) · Σ:

    d²_k = Δf^T C^{-1}_k Δf  (Mahalanobis using estimated covariance)

satisfies:
    d²_k / k  ~  (ν-2)/ν · F(k, ν)

The factor c = (ν-2)/ν < 1 arises because C = ν/(ν-2) · Σ inflates the
scale matrix. Equivalently, d²_Σ = ν/(ν-2) · d²_C ~ k · F(k, ν).
This correction is critical for correct ν estimation.

Two fits are provided:
    k = 5  (reduced-rank, top-5 PCs, 95.7% variance): sensitive to PC6-14
            escaped variance; QQ slope is the preferred estimator.
    k = 14 (full-rank): captures all variation; MLE and QQ slope agree
            more closely; ν consistent with par-rate estimates (~3.3).

Usage
-----
    from vol_analysis import load_vol_panel, weighted_pca, fit_both
    panel   = load_vol_panel("data/.../Treasury_CMT_curves_S1_xxxx.npz")
    pca     = weighted_pca(panel)
    results = fit_both(panel, pca)
    # results.k5 and results.k14 are TailFit namedtuples
"""

from __future__ import annotations

import numpy as np
from scipy import stats
from scipy.optimize import brentq, minimize_scalar
from typing import NamedTuple


# ── Data structures ──────────────────────────────────────────────────────────

class VolPanel(NamedTuple):
    """Preprocessed forward-rate change panel (NaN rows removed)."""
    delta_f:       np.ndarray   # (N, 14)  daily Δf, newest-first
    dates:         np.ndarray   # (N,)     date of newer obs in each pair
    tenor_labels:  list         # ['1Mo', '1.5Mo', ...]
    tenor_years:   np.ndarray   # (14,)  knot maturities in years
    dT:            np.ndarray   # (14,)  span widths ΔT_i in years


class PCAResult(NamedTuple):
    """Output of weighted_pca()."""
    eigenvalues:            np.ndarray  # (14,) descending
    eigenvectors_weighted:  np.ndarray  # (14,14) in G^{1/2}-scaled space
    eigenvectors_original:  np.ndarray  # (14,14) back-transformed to rate space
    var_share:              np.ndarray  # (14,) fraction of variance per PC
    cum_var:                np.ndarray  # (14,) cumulative variance
    C_inf:                  np.ndarray  # (14,14) long-run weighted covariance
    C_inv:                  np.ndarray  # (14,14) inverse of C_inf
    n_obs:                  int


class TailFit(NamedTuple):
    """Output of fit_f_distribution() for a specific k."""
    nu:           float        # fitted degrees of freedom ν*
    c:            float        # correction factor c = (ν-2)/ν
    k:            int          # PC dimension (5 or 14)
    method:       str          # 'qq' or 'mle'
    d2:           np.ndarray   # (N,) squared Mahalanobis distances
    d2_sorted:    np.ndarray   # (N,) sorted
    p_emp:        np.ndarray   # (N,) Hazen plotting positions
    slope_origin: float        # through-origin QQ slope at ν* (target = 1)


class BothFits(NamedTuple):
    """Container for both the k=5 and k=14 fits."""
    k5:  TailFit   # reduced-rank, k=5,  QQ slope estimator
    k14: TailFit   # full-rank,    k=14, MLE estimator


class ShockVector(NamedTuple):
    """Output of generate_shock()."""
    delta_f:    np.ndarray   # (14,) forward rate shock in decimal/day
    delta_f_bp: np.ndarray   # (14,) shock in basis points/day
    d2_target:  float        # d² norm of the shock
    alpha:      float        # severity level
    k:          int          # Mahalanobis dimension used
    nu:         float        # degrees of freedom used
    direction:  str


# ── Gap fill ─────────────────────────────────────────────────────────────────

def fill_s1_gaps(s1_f: np.ndarray, labels: list) -> np.ndarray:
    """
    S1-consistent gap fill.

    Rule: absent span i ← nearest non-NaN span to the right.
    This is exact: when span i is missing, the bootstrap merged it with i+1,
    so the S1 constant on [T_{i-1}, T_{i+1}] equals f_{i+1}.
    Special case: 30Yr absent ← 20Yr (flat extrapolation, no right anchor).
    """
    filled = s1_f.copy()
    n_ten  = filled.shape[1]

    idx_20 = labels.index('20Yr')
    idx_30 = labels.index('30Yr')
    absent_30 = np.isnan(filled[:, idx_30])
    filled[absent_30, idx_30] = filled[absent_30, idx_20]

    for i in range(n_ten - 1):
        nan_rows = np.isnan(filled[:, i])
        if not nan_rows.any():
            continue
        for j in range(i + 1, n_ten):
            can_fill = nan_rows & ~np.isnan(filled[:, j])
            filled[can_fill, i] = filled[can_fill, j]
            nan_rows = np.isnan(filled[:, i])
            if not nan_rows.any():
                break

    return filled


# ── Panel construction ────────────────────────────────────────────────────────

def load_vol_panel(npz_path: str) -> VolPanel:
    """
    Load S1 NPZ, apply gap fill, and return the daily Δf panel.

    Δf[d] = filled[d] - filled[d+1]  (dates stored newest-first in NPZ).
    Rows with residual NaN after filling are dropped.
    """
    data   = np.load(npz_path, allow_pickle=True)
    s1_f   = data['s1_f']
    dates  = data['dates']
    labels = [str(x) for x in data['tenor_labels']]
    years  = data['tenor_years']

    filled   = fill_s1_gaps(s1_f, labels)
    delta_f  = filled[:-1] - filled[1:]
    df_dates = dates[:-1]

    clean    = ~np.any(np.isnan(delta_f), axis=1)
    delta_f  = delta_f[clean]
    df_dates = df_dates[clean]

    T  = np.concatenate([[0.0], years])
    dT = np.diff(T)

    return VolPanel(
        delta_f=delta_f, dates=df_dates,
        tenor_labels=labels, tenor_years=years, dT=dT,
    )


def filter_panel(panel: VolPanel,
                 date_start: np.datetime64,
                 date_end:   np.datetime64) -> VolPanel:
    """Return a VolPanel restricted to [date_start, date_end]."""
    mask = (panel.dates >= date_start) & (panel.dates <= date_end)
    if mask.sum() < 20:
        raise ValueError(
            f"Only {mask.sum()} observations in {date_start}–{date_end}. "
            "Widen the range."
        )
    return VolPanel(
        delta_f=panel.delta_f[mask], dates=panel.dates[mask],
        tenor_labels=panel.tenor_labels, tenor_years=panel.tenor_years,
        dT=panel.dT,
    )


# ── Span-weighted PCA ─────────────────────────────────────────────────────────

def weighted_pca(panel: VolPanel) -> PCAResult:
    """
    Span-weighted PCA on daily forward rate changes.

    Scales column i by √ΔT_i so the covariance is taken in the
    L²([0, T_max]) inner product. The weighted covariance is:
        C∞ = (1/N) · (Δf G^{1/2})^T (Δf G^{1/2})
    Eigenvectors are returned in both weighted and original rate spaces.
    """
    dT         = panel.dT
    G_half     = np.diag(np.sqrt(dT))
    G_half_inv = np.diag(1.0 / np.sqrt(dT))

    df_scaled = panel.delta_f @ G_half
    N         = df_scaled.shape[0]
    C_inf     = (df_scaled.T @ df_scaled) / N
    C_inv     = np.linalg.inv(C_inf)

    eigenvalues, eigenvectors = np.linalg.eigh(C_inf)
    eigenvalues  = eigenvalues[::-1]
    eigenvectors = eigenvectors[:, ::-1]
    ev_orig      = G_half_inv @ eigenvectors

    var_share = eigenvalues / eigenvalues.sum()
    cum_var   = np.cumsum(var_share)

    return PCAResult(
        eigenvalues=eigenvalues,
        eigenvectors_weighted=eigenvectors,
        eigenvectors_original=ev_orig,
        var_share=var_share,
        cum_var=cum_var,
        C_inf=C_inf,
        C_inv=C_inv,
        n_obs=N,
    )


def pcs_for_threshold(pca: PCAResult, threshold: float) -> int:
    """Minimum number of PCs needed to explain at least `threshold` variance."""
    return int(np.searchsorted(pca.cum_var, threshold) + 1)


# ── Mahalanobis distances: reduced-rank (k=5) and full-rank (k=14) ───────────

def reduced_mahalanobis_sq(panel: VolPanel,
                            pca:   PCAResult,
                            k:     int = 5) -> np.ndarray:
    """
    Reduced-rank squared Mahalanobis using top-k PCs (default k=5).

    d²_k = Σ_{j=1}^{k} (Δf_scaled · v_j)² / λ_j

    Captures 95.7% of variance at k=5. Note: rate movements in the PC(k+1..p)
    subspace produce d²_k ≈ 0 (escaped variance), which causes the d²
    distribution to have excess probability near zero relative to the
    corrected F(k, ν) model. This makes the MLE unreliable; use QQ slope.
    """
    G_half = np.diag(np.sqrt(panel.dT))
    df_sc  = panel.delta_f @ G_half
    V_k    = pca.eigenvectors_weighted[:, :k]
    lam_k  = pca.eigenvalues[:k]
    scores = df_sc @ V_k
    return (scores ** 2 / lam_k).sum(axis=1)


def full_mahalanobis_sq(panel: VolPanel, pca: PCAResult) -> np.ndarray:
    """
    Full-rank squared Mahalanobis using all p=14 eigenvectors (k=p).

    d²_14 = Δf_scaled^T C∞^{-1} Δf_scaled

    Captures 100% of variance; no escaped-variance issue. MLE and QQ slope
    estimates agree more closely. ν consistent with par-rate estimates.
    """
    G_half = np.diag(np.sqrt(panel.dT))
    df_sc  = panel.delta_f @ G_half
    # Vectorised: einsum('ni,ij,nj->n')
    return np.einsum('ni,ij,nj->n', df_sc, pca.C_inv, df_sc)


# ── t_ν tail fitting: corrected for C vs Σ inflation ─────────────────────────

def fit_f_distribution(d2:     np.ndarray,
                        k:      int,
                        method: str   = 'qq',
                        trim:   float = 0.999) -> TailFit:
    """
    Fit F(k, ν) to d²/k, corrected for C vs Σ inflation.

    Under t_ν(0, Σ) with C = ν/(ν-2) · Σ:
        d²/k  ~  c · F(k, ν),    c = (ν-2)/ν

    Two estimators:

    method='qq'  (default):
        Find ν* such that the OLS slope (through origin) of d²_{(i)} on
        c · k · F^{-1}(p_i; k, ν) equals 1. Equivalently:
            slope_old(ν*) = (ν*-2)/ν*
        where slope_old uses un-corrected F quantiles. The through-origin
        slope at ν* is exactly 1.000 by construction. Preferred for k=5
        where MLE is biased by escaped-variance near-zero observations.

    method='mle':
        Maximise L(ν) = -N·log(c) + Σ log f_F(d²_i/(k·c); k, ν).
        Preferred for k=14 (full-rank) where no escaped-variance issue.
        Gives ν consistent with par-rate estimates.

    Parameters
    ----------
    d2     : (N,) squared Mahalanobis distances
    k      : PC dimension (5 for reduced-rank, 14 for full-rank)
    method : 'qq' or 'mle'
    trim   : upper quantile cutoff for QQ slope (default 0.999)

    Returns
    -------
    TailFit namedtuple
    """
    N         = len(d2)
    d2_sorted = np.sort(d2)
    p_emp     = (np.arange(1, N + 1) - 0.5) / N

    if method == 'mle':
        def neg_ll(nu):
            if nu <= 2.01:
                return 1e10
            c = (nu - 2) / nu
            return (-np.sum(stats.f.logpdf(d2 / (k * c), dfn=k, dfd=nu))
                    + N * np.log(c))
        res    = minimize_scalar(neg_ll, bounds=(2.1, 200.0), method='bounded')
        nu_star = res.x

    else:  # qq
        keep   = p_emp <= trim
        d2_tr  = d2_sorted[keep]
        p_tr   = p_emp[keep]

        def slope_old(nu):
            q = k * stats.f.ppf(p_tr, dfn=k, dfd=nu)
            return float(np.dot(d2_tr, q) / np.dot(q, q))

        # Condition: slope_old(ν) = (ν-2)/ν
        # Bracket: slope_old(3) < 1/3 and slope_old(500) ≈ 498/500
        f_lo = slope_old(3.0) - 1.0 / 3.0
        f_hi = slope_old(500.) - 498.0 / 500.0

        if f_lo * f_hi < 0:
            nu_star = brentq(
                lambda nu: slope_old(nu) - (nu - 2) / nu,
                3.0, 500.0, xtol=0.005,
            )
        else:
            # Fallback: MLE
            import warnings
            warnings.warn(
                "QQ slope bracket not found; falling back to MLE.",
                RuntimeWarning,
            )
            return fit_f_distribution(d2, k, method='mle', trim=trim)

    c_star = (nu_star - 2) / nu_star

    # Through-origin QQ slope at ν* (diagnostic)
    keep_chk = p_emp <= trim
    q_chk    = c_star * k * stats.f.ppf(p_emp[keep_chk], dfn=k, dfd=nu_star)
    slope_0  = float(np.dot(d2_sorted[keep_chk], q_chk) / np.dot(q_chk, q_chk))

    return TailFit(
        nu=nu_star, c=c_star, k=k, method=method,
        d2=d2, d2_sorted=d2_sorted, p_emp=p_emp,
        slope_origin=slope_0,
    )


def fit_both(panel: VolPanel, pca: PCAResult) -> BothFits:
    """
    Compute both the k=5 (QQ slope) and k=14 (MLE) tail fits.

    Recommended fits:
        k=5  / QQ  → ν ≈ 4.9,  c ≈ 0.593.  Through-origin slope = 1.000.
                      Use for reduced-rank risk metrics (PC1-5 direction).
        k=14 / QQ  → ν ≈ 3.1,  c ≈ 0.353.  Through-origin slope = 1.000.
                      Full-rank, consistent with par-rate ν. Both fits use
                      the corrected QQ slope estimator so the QQ intercept
                      is zero and slope is 1 to machine precision.
    """
    d2_5  = reduced_mahalanobis_sq(panel, pca, k=5)
    d2_14 = full_mahalanobis_sq(panel, pca)

    tail5  = fit_f_distribution(d2_5,  k=5,  method='qq')
    tail14 = fit_f_distribution(d2_14, k=14, method='qq')

    return BothFits(k5=tail5, k14=tail14)


# ── Severity quantiles ────────────────────────────────────────────────────────

def severity_d2(alpha: float, tail: TailFit) -> float:
    """
    d² threshold at severity level alpha under the corrected F(k, ν) model.

    P(d²_k ≤ severity_d2) = alpha
    = P(c · k · F(k,ν) ≤ x)  ⟹  x = c · k · F^{-1}(alpha; k, ν)
    """
    return float(tail.c * tail.k * stats.f.ppf(alpha, dfn=tail.k, dfd=tail.nu))


def severity_table(alphas: list, tail: TailFit,
                   panel:  VolPanel, pca: PCAResult) -> list:
    """
    Build severity table: for each α, report d², Mahalanobis norm,
    empirical percentile, and PC1-direction shock magnitudes.
    """
    G_half_inv = np.diag(1.0 / np.sqrt(panel.dT))
    lam1 = pca.eigenvalues[0]
    v1_w = pca.eigenvectors_weighted[:, 0]

    rows = []
    for alpha in alphas:
        d2_q   = severity_d2(alpha, tail)
        emp    = float((tail.d2 <= d2_q).mean())
        # PC1 shock
        shock_w  = v1_w * np.sqrt(d2_q * lam1)
        shock_bp = np.abs(G_half_inv @ shock_w) * 1e4

        row = {
            'alpha':     alpha,
            'd2':        round(d2_q,  3),
            'maha_dist': round(d2_q ** 0.5, 3),
            'emp_pct':   round(emp, 4),
            'k':         tail.k,
            'nu':        round(tail.nu, 3),
        }
        for i, lbl in enumerate(panel.tenor_labels):
            row[f'shock_bp_{lbl}'] = round(float(shock_bp[i]), 2)
        rows.append(row)

    return rows


# ── Shock generation ──────────────────────────────────────────────────────────

def generate_shock(alpha:     float,
                   panel:     VolPanel,
                   pca:       PCAResult,
                   tail:      TailFit,
                   direction: str = 'PC1') -> ShockVector:
    """
    Generate a deterministic worst-case forward rate shock at severity alpha.

    Directions
    ----------
    'PC1'          : Pure parallel shift (largest eigenvalue direction).
                     d²_k contribution entirely from PC1.
    'proportional' : Equal d²_k contribution across all tail.k PCs.

    The shock has d²_{tail.k} = severity_d2(alpha, tail) by construction.
    Works for both k=5 and k=14 tail fits.
    """
    k          = tail.k
    d2_target  = severity_d2(alpha, tail)
    G_half_inv = np.diag(1.0 / np.sqrt(panel.dT))
    V_k        = pca.eigenvectors_weighted[:, :k]
    lam_k      = pca.eigenvalues[:k]

    if direction == 'PC1':
        # All d² in PC1: c_1 = √(d²_target · λ_1), c_j>1 = 0
        c_vec = np.zeros(k)
        c_vec[0] = np.sqrt(d2_target * lam_k[0])
    elif direction == 'proportional':
        # Equal d² across k PCs: c_j = √(λ_j · d²_target / k)
        c_vec = np.sqrt(lam_k * d2_target / k)
    else:
        raise ValueError(f"direction must be 'PC1' or 'proportional', got '{direction}'")

    shock_w    = V_k @ c_vec
    shock_orig = G_half_inv @ shock_w

    return ShockVector(
        delta_f=shock_orig,
        delta_f_bp=shock_orig * 1e4,
        d2_target=d2_target,
        alpha=alpha,
        k=k,
        nu=tail.nu,
        direction=direction,
    )


# ═══════════════════════════════════════════════════════════════════════════════
# ALCO SCENARIO GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════
"""
ALCO Scenario Generator
-----------------------
Five-anchor linear interpolation scheme with seven geometrically consistent
preset scenarios, all calibrated to the same d² as a parallel +100bp/quarter
shock. Units throughout are bp/quarter (what ALCO sees) converted to daily
decimal for d² computation.

Anchor tenors: 3Mo / 5Yr / 10Yr / 20Yr / 30Yr   (R² = 0.878 vs full 14-tenor)
Rotation pivot: 10Yr (benchmark rate unchanged under pure rotation)
Trading days per quarter: 63

Scenario framework:
    Steepen  = anti-clockwise rotation (slope increases), linear in maturity
    Flatten  = clockwise rotation (slope decreases)
    Bear     = add parallel-up component (overall rates rise)
    Bull     = add parallel-down component (overall rates fall)
    Bell     = positive curvature, belly rises relative to ends
    Bowl     = negative curvature, belly falls relative to ends

Unit convention:
    bp/quarter  → multiply by 1e-4 → decimal/quarter
    100bp/quarter = 0.01 decimal/quarter  (1% = 0.01 in rate decimal)
"""

ANCHOR_LABELS           = ['3Mo', '5Yr', '10Yr', '20Yr', '30Yr']
TRADING_DAYS_PER_QTR    = 63
_T_PIVOT_YR             = 10.0    # rotation pivot
_BP_TO_DECIMAL          = 1e-4    # 1bp = 0.0001 in rate decimal
_BELL_DIR               = np.array([-0.5, +1.0, +2.0, +1.0, -0.5])


def build_interp_matrix(anchor_labels: list,
                         all_labels:    list,
                         years:         np.ndarray) -> np.ndarray:
    """
    Build the (14 × k) linear interpolation matrix for k anchor tenors.

    Flat extrapolation outside the anchor range. The i-th row of L gives
    the weights applied to the k anchor values to reproduce tenor i.

    Parameters
    ----------
    anchor_labels : k tenor label strings, e.g. ANCHOR_LABELS
    all_labels    : all 14 tenor labels (from VolPanel.tenor_labels)
    years         : (14,) tenor maturities in years

    Returns
    -------
    L : (14, k) float64
    """
    anchor_idx = [all_labels.index(l) for l in anchor_labels]
    T_a = years[anchor_idx]
    k, n = len(anchor_idx), len(years)
    L    = np.zeros((n, k))
    for i, T in enumerate(years):
        if T <= T_a[0]:
            L[i, 0] = 1.0
        elif T >= T_a[-1]:
            L[i, -1] = 1.0
        else:
            for j in range(k - 1):
                if T_a[j] <= T <= T_a[j + 1]:
                    w = (T - T_a[j]) / (T_a[j+1] - T_a[j])
                    L[i, j], L[i, j+1] = 1.0 - w, w
                    break
    return L


def anchor_bps_to_full(anchor_bps_Q: np.ndarray,
                        L:            np.ndarray) -> np.ndarray:
    """
    Interpolate k anchor values (bp/quarter) to all 14 tenor values (bp/quarter).

    Parameters
    ----------
    anchor_bps_Q : (k,) bp/quarter at anchor tenors
    L            : (14, k) interpolation matrix from build_interp_matrix

    Returns
    -------
    full_bps_Q : (14,) bp/quarter at all tenors
    """
    return L @ anchor_bps_Q


def scenario_d2(anchor_bps_Q:  np.ndarray,
                 L:             np.ndarray,
                 pca:           PCAResult,
                 panel:         VolPanel,
                 trading_days:  int = TRADING_DAYS_PER_QTR) -> float:
    """
    Compute d²_14 (full-rank Mahalanobis, daily basis) for a quarterly scenario.

    Converts bp/quarter → decimal/quarter → decimal/day, then applies the
    Gram weighting and full-rank Mahalanobis using the fitted C_inf.

    Parameters
    ----------
    anchor_bps_Q  : (k,) rate changes in bp/quarter at anchor tenors
    L             : (14, k) interpolation matrix
    pca           : PCAResult
    panel         : VolPanel (provides dT)
    trading_days  : trading days per quarter

    Returns
    -------
    d² : float
    """
    full_Q_dec = L @ (anchor_bps_Q * _BP_TO_DECIMAL)   # decimal/quarter, 14-vector
    full_d_dec = full_Q_dec / np.sqrt(trading_days)     # decimal/day
    G_half     = np.diag(np.sqrt(panel.dT))
    sc         = G_half @ full_d_dec
    return float(sc @ pca.C_inv @ sc)


def scenario_severity(d2: float, tail: TailFit) -> float:
    """
    Non-exceedance probability P(D² ≤ d²) under the fitted corrected F(k, ν).

    This is the severity score: 1.0 = certain exceedance, 0.0 = no severity.
    Uses the corrected F(k, ν) with inflation factor c = (ν-2)/ν.
    """
    return float(stats.f.cdf(d2 / (tail.k * tail.c), dfn=tail.k, dfd=tail.nu))


def compute_presets(panel:         VolPanel,
                     pca:           PCAResult,
                     anchor_labels: list = None,
                     trading_days:  int  = TRADING_DAYS_PER_QTR) -> dict:
    """
    Compute all seven ALCO preset scenario anchor values (bp/quarter).

    All scenarios are scaled so their d² equals the d² of a parallel
    +100bp/quarter shock. The returned anchor_bps_Q values are what
    should pre-fill the five ALCO sliders when a preset is selected.

    Parameters
    ----------
    panel         : VolPanel
    pca           : PCAResult
    anchor_labels : list of 5 tenor labels (default ANCHOR_LABELS)
    trading_days  : trading days per quarter (default 63)

    Returns
    -------
    dict keyed by scenario name, each value:
        {
          'anchor_bps_Q' : (5,) float  — bp/quarter at the 5 anchor tenors
          'full_bps_Q'   : (14,) float — bp/quarter at all 14 tenors
          'd2'           : float
        }
    """
    if anchor_labels is None:
        anchor_labels = ANCHOR_LABELS

    all_labels = panel.tenor_labels
    L          = build_interp_matrix(anchor_labels, all_labels, panel.tenor_years)
    T_a        = panel.tenor_years[[all_labels.index(l) for l in anchor_labels]]
    T_max      = T_a[-1]

    # ── Base direction vectors (dimensionless, "100bp/quarter = 1 unit") ──────
    rotate   = (T_a - _T_PIVOT_YR) / (T_max - _T_PIVOT_YR)
    # = [-0.4875, -0.25, 0, +0.50, +1.00]

    parallel = np.ones(len(anchor_labels))
    bell     = _BELL_DIR.copy()     # [-0.5, +1.0, +2.0, +1.0, -0.5]

    # ── Reference d²: parallel +100bp/quarter ────────────────────────────────
    par_100bp  = parallel * 100.0   # bp/quarter, all anchors
    d2_ref     = scenario_d2(par_100bp, L, pca, panel, trading_days)

    # ── Seven scenario directions (in 100bp units, before d²-scaling) ─────────
    # Combination: rotation + parallel at equal weight (1:1).
    # This makes Bear Steepen = [+0.5125, +0.75, +1.0, +1.5, +2.0] × scale
    # and naturally anchors 30Yr=0 for Bull Steepen, Bear Flatten.
    raw_dirs = {
        'Parallel +100bp':  parallel,
        'Bear Steepen':    +rotate + parallel,
        'Bull Steepen':    +rotate - parallel,
        'Bear Flatten':    -rotate + parallel,
        'Bull Flatten':    -rotate - parallel,
        'Bell':             bell,
        'Bowl':            -bell,
    }

    results = {}
    for name, raw in raw_dirs.items():
        # Convert direction to bp/quarter, then scale to d²_ref
        raw_bps = raw * 100.0                              # convert "units" → bp/quarter
        d2_raw  = scenario_d2(raw_bps, L, pca, panel, trading_days)
        scale   = np.sqrt(d2_ref / d2_raw) if d2_raw > 1e-15 else 1.0
        anchor_bps = raw_bps * scale
        full_bps   = anchor_bps_to_full(anchor_bps, L)
        d2_check   = scenario_d2(anchor_bps, L, pca, panel, trading_days)

        results[name] = {
            'anchor_bps_Q': anchor_bps,
            'full_bps_Q':   full_bps,
            'd2':           d2_check,
        }

    return results
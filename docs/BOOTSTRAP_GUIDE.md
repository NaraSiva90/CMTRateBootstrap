# Bootstrap Pipeline — User Guide
## Treasury Yield Curve Construction from CMT Par Rates

This guide documents the actual implementation in [`src/cmt_bootstrap.py`](../src/cmt_bootstrap.py).
Every function signature, dataclass, and CLI flag below matches that file directly —
if you edit `cmt_bootstrap.py`, please update this guide alongside it.

---

## Contents

1. [Overview](#1-overview)
2. [Mathematical Background](#2-mathematical-background)
3. [The Bootstrap Schemes](#3-the-bootstrap-schemes)
   - 3.1 Scheme 1 — Piecewise Constant Forwards
   - 3.2 Scheme 2 — Piecewise Linear Forwards
   - 3.3 Scheme 3 — Monotone Cubic Forwards
4. [How the Historical Panel Is Built](#4-how-the-historical-panel-is-built)
5. [Quick Start](#5-quick-start)
6. [Bootstrap Workflows — From Data to Analysis](#6-bootstrap-workflows--from-data-to-analysis)
7. [Choosing a Method](#7-choosing-a-method)
8. [API Reference](#8-api-reference)
9. [Design Notes & Implementation Lessons](#9-design-notes--implementation-lessons)
10. [Downstream Applications](#10-downstream-applications)
11. [References](#11-references)

---

## 1. Overview

`src/cmt_bootstrap.py` constructs zero-coupon yield curves from US Treasury Constant
Maturity (CMT) par rates using one of three bootstrapping schemes of increasing
forward-curve smoothness. It reads an entire historical workbook in a single run and
writes one NPZ panel (optionally also an Excel workbook) covering every date at once.

**Input:** a `CMT Rates` sheet with up to 14 CMT par rates per date, at standard
Treasury maturities 1Mo–30Yr (including the 1.5Mo / 45-day tenor).

**Output:** an NPZ panel with, for every date: discount factors P(0,T), continuously-
compounded spot rates R(T), instantaneous forward rates at each tenor endpoint,
implied par rates (round-trip check), and the scheme-specific curve parameters
needed to reconstruct the continuous forward function between tenors
(see [`scripts/curve_reconstruction.py`](../scripts/curve_reconstruction.py)).

### The Three Schemes

| Scheme | Function | Tenors | Forward Smoothness | Primary Use |
|--------|----------|--------|---------------------|-------------|
| 1 | `bootstrap_scheme1` | up to 14 CMT | C⁻¹ (jumps at knots) | Swap pricing, DV01, hedging |
| 2 | `bootstrap_scheme2` | up to 14 CMT | C⁰ (continuous) | Smoother visualization, SOFR-anchored |
| 3 | `bootstrap_scheme3` | up to 14 CMT | C¹ (smooth) | Monte Carlo, exotics, PCA input |

### Conventions

- **Day count:** 30/360 throughout. `T = months/12` exactly, via `parse_tenor_to_years()`
  (no rounding error).
- **Payment frequency:** `nu = 24` by default (every 15 days = 1/24 year), settable
  with `--nu`.
- **CMT tenors:** up to 14 — `1Mo 1.5Mo 2Mo 3Mo 4Mo 6Mo 1Yr 2Yr 3Yr 5Yr 7Yr 10Yr 20Yr 30Yr`.
  Missing tenors on a given date are skipped entirely (no interpolation) —
  see `used_mask` / `tenor_used_mask`.
- **Compounding:** Continuous. `R(T) = -ln P(0,T) / T`.
- **Par bond condition:** `S(T_i) = (1 - P(0,T_i)) / Ann(0,T_i)`, where the annuity
  sums discount factors at every payment date up to `T_i` at frequency `nu`
  (see `annuity_sum()`).
- **Round-trip precision:** implied par rates are recomputed from the fitted
  discount curve and compared to the input; errors are stored in basis points
  (`par_rate_err_bp`, `par_rate_err_maxabs_bp`, `par_rate_err_rms_bp`).

---

## 2. Mathematical Background

### The Bootstrapping Problem

Given par rates `{S(T_1), ..., S(T_N)}`, find discount factors `{P(0,T_i)}` such
that a par bond at each tenor prices at 100:

    S(T_i) = (1 - P(0,T_i)) / Ann(0,T_i)

where the annuity factor accumulates coupon present values at payment frequency `nu`:

    Ann(0,T_i) = (1/nu) * Σ_{k=1}^{m_i} P(0, k/nu),   m_i = pay_count(T_i, nu)

This is exactly `annuity_sum()` in the code, and `par_rate()` evaluates the par-bond
condition given any callable `discount_fn(t)`.

### Why Not Direct Inversion?

The par bond equation is a nonlinear function of the forward-rate parameters for
each interval — there's no closed form. Each scheme solves interval-by-interval,
using the already-determined discount factors from shorter maturities, with
`scipy.optimize.brentq` doing the 1D root-find per interval (`shat(fi) - Si == 0`,
or the cubic-reduced equivalent for Scheme 3).

The key implementation detail is `pay_count()`:

```python
def pay_count(t_years: float, nu: int) -> int:
    return int(round(nu * float(t_years) + 1e-9))
```

Floating-point safety requires `round()` before `int()` — see
[§9.1](#91-the-payment-count-fix--and-why-nu--24) for why, and why the small
`+1e-9` epsilon is there.

### CMT Tenors and Spacing

The tenor grid is parsed by `parse_tenor_to_years()` from labels like `"1.5 Mo"`,
`"10 Yr"`, etc. (see `read_cmt_rates_from_workbook()`). The full set spans 1 month
to 30 years:

    1Mo  1.5Mo  2Mo  3Mo  4Mo  6Mo  1Yr  2Yr  3Yr  5Yr  7Yr  10Yr  20Yr  30Yr

Missing tenors on any given date are simply skipped — the bootstrap advances
`T_prev` to the next *present* tenor rather than interpolating a value, so `dT`
(the interval width fed to the solver) can be wider than the nominal spacing
when a tenor is absent that day.

---

## 3. The Bootstrap Schemes

### 3.1 Scheme 1 — Piecewise Constant Forwards

`bootstrap_scheme1(S, T, nu, f_max=1.0, tol=1e-14) -> Scheme1Result`

**Forward curve:** `f(τ) = f_i` (constant) for `τ` in the interval ending at `T_i`.

**Discount factor:**

    P(0,T_i) = P(0,T_{i-1}) · exp(-f_i · dT_i),   dT_i = T_i - T_prev

**Continuity:** C⁻¹ — forwards are **discontinuous** at each tenor knot.

**Solver:** `brentq` per interval on `shat(f_i) - S_i`, with the code trying
progressively wider brackets (`±f_max`, then `±f_max·{2,5,10,20}`) if the initial
bracket doesn't contain a sign change. If no bracket is found, that date/tenor is
left `NaN` and a message is appended to `warns`.

**Returned fields (`Scheme1Result`):** `f`, `P`, `z` (spot, cc), `f_end` (== `f`,
kept for symmetry with Schemes 2/3), `used_mask`, `warns`, and `discount_fn` — a
closure that evaluates `P(t)` for arbitrary `t`, used for the round-trip par-rate
check.

**When to use:** Swap pricing, DV01, hedge ratios — anything needing exact pricing
at the quoted CMT tenors, where the discontinuous forward doesn't matter because
only the integrated discount factor is used.

---

### 3.2 Scheme 2 — Piecewise Linear Forwards

`bootstrap_scheme2(S, T, r0, nu, a_max=50.0, tol=1e-14) -> Scheme2Result`

**Forward curve:** `f(τ) = a_i·τ + b_i` for local `τ` in `[0, dT_i)` within
interval `i` (τ measured from the start of that interval, i.e. `T_prev`).

**C⁰ continuity:** `b_i` is set to the previous interval's forward value at its own
endpoint: `bi = f_prev_end`, where `f_prev_end` is updated each iteration as
`a_i·dT_i + b_i`. The very first interval uses `b_1 = r0` (the short-rate anchor).

**Discount factor:**

    P(0,T_i) = P(0,T_{i-1}) · exp(-(½·a_i·dT_i² + b_i·dT_i))

via `int_lin(a, b, t) = 0.5*a*t*t + b*t`.

**Solver:** `brentq` on the slope `a_i` only (the intercept `b_i` is fixed by
continuity before the solve). Bracket search tries `±a_max` first, then a list of
scaled brackets — the code specifically tries *narrower* brackets before wider
ones (`scales_to_try = [0.001, 0.01, 0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 20.0, 50.0, 100.0]`),
because wide CMT intervals (e.g. 10Yr→20Yr, or a gap left by a missing tenor) need
small slopes and a too-wide initial bracket can fail to bisect cleanly.

**Returned fields (`Scheme2Result`):** `a`, `b`, `P`, `z`, `f_end` (forward value at
the interval's own endpoint — the value the *next* interval's `b` will inherit),
`used_mask`, `warns`, `discount_fn`.

**When to use:** Continuous forwards without the cost of Scheme 3 — smoother
visualization, or anywhere anchoring the short end to the SOFR-based `r0` matters.
Also used internally by Scheme 3 to obtain the linear slopes needed for the
Fritsch-Carlson monotonicity condition (see below).

---

### 3.3 Scheme 3 — Monotone Cubic Forwards

`bootstrap_scheme3(S, T, r0, nu, a_max=200.0, tol=1e-13) -> Scheme3Result`

**Forward curve:** `f(τ) = a_i·τ³ + b_i·τ² + c_i·τ + d_i` for local `τ` in
`[0, dT_i)`.

**Two-pass algorithm, matching the code exactly:**

1. **Pass 1:** Run `bootstrap_scheme2(S, T, r0, nu)` to get linear slopes `s2.a`
   for every used tenor — these feed the monotonicity condition below.
2. **Pass 2a — Fritsch-Carlson targets:** For consecutive used-tenor slopes
   `l_j, l_{j+1}` (falling back to 0 for any `NaN` slope from a Scheme 2 failure):

       c_target[j+1] = (l_j·tau_j + l_{j+1}·tau_{j+1}) / (tau_j + tau_{j+1})   if l_j·l_{j+1} > 0
       c_target[j+1] = 0                                                      otherwise

   with `c_target[0] = 0` and `c_target[m] = 0` as the natural boundary conditions
   (flat forward at t=0 and at the last tenor).
3. **Pass 2b — solve for `(a_i, b_i)` per interval:** `c_i` and `d_i` are already
   fixed by continuity from the previous interval (`d_1 = r0`, `c_1 = 0`). The slope
   target `c_next` is known from Pass 2a, so `b_i` can be written in closed form as
   a function of `a_i`:

       b(a) = (c_next - c_i - 3·a·dT²) / (2·dT)

   which makes the par-bond residual **linear in `a`** after substitution — reducing
   what would be a fragile 2D nonlinear solve to a single well-conditioned 1D
   `brentq` call. See [§9.3](#93-scheme-3--dimension-reduction) for why this matters.

**Numerical fallbacks in the real code** (not present in Schemes 1/2):
- If the Brent bracket doesn't contain a root, the code tries progressively
  scaled brackets (same `scales_to_try` list as Scheme 2), then asymmetric
  bracket adjustment if only one side overflows.
- If cubic solving still fails for that tenor, it **falls back to a constant
  forward** for that interval only (binary-searched via a separate `brentq` on a
  constant `d_i`), logging a warning — this keeps the curve continuous even when
  the cubic is numerically unsound (typically only in pathological/very wide
  intervals from missing tenors).

**Continuity:** C¹ forwards (value and slope continuous at every knot), C² spots.

**Returned fields (`Scheme3Result`):** `a3`, `b3`, `c3`, `d3`, `c_target_next`,
`P`, `z`, `f_end`, `used_mask`, `warns`, `discount_fn`.

**Why no C²:** A fifth constraint on a four-parameter cubic would over-determine
the system. The only resolution is to drop monotonicity, which produces
Runge-phenomenon oscillation — especially across the 10Y→20Y gap. Monotonicity is
the deliberate substitute for C² (see [§9.4](#94-c-is-impossible-without-sacrificing-monotonicity)).

**When to use:** Monte Carlo path generation, path-dependent/barrier products,
research requiring the smoothest forward curve, or as PCA input (see
[§10](#10-downstream-applications)).

---

## 4. How the Historical Panel Is Built

There is no separate "batch" or "panel" API — `cmt_bootstrap.py`'s `main()` *is*
the panel builder. A single CLI invocation:

1. Reads every date row from the workbook's `CMT Rates` sheet
   (`read_cmt_rates_from_workbook`).
2. Builds the short-rate anchor `r0` for every date (`build_r0_series`), preferring
   `data/short_rates/short_rate_combined.csv` and falling back to separate
   Fed Funds / SOFR histories if that file is missing.
3. Loops over all `N` dates, running the chosen scheme's bootstrap function for
   each one, and stacking the per-date results into `(N, 14)` arrays.
4. Computes the round-trip par-rate check for every date/tenor pair that had
   input data.
5. Writes one NPZ (`save_panel_npz`) — and optionally one Excel workbook
   (`write_excel`) — covering the entire history in a single file.

So "building a historical panel for PCA" isn't a distinct workflow requiring a
manual per-date loop — it's simply what running the CLI once over the full
workbook already produces. The NPZ's `discount_factors_T`, `spot_rates_cc_T`, and
`forward_endpoint_T` arrays are already shaped `(N_dates, 14_tenors)`.

---

## 5. Quick Start

### CLI (recommended — this is what `scripts/run_bootstrap.py` wraps)

```bash
# Scheme 2 (piecewise linear forward — recommended default)
python src/cmt_bootstrap.py --workbook Treasury_CMT_Data_Tool.xlsx --scheme 2

# Scheme 3 (monotone cubic — smoother) with Excel output too
python src/cmt_bootstrap.py --workbook Treasury_CMT_Data_Tool.xlsx --scheme 3 --write-excel

# Or via the convenience wrapper (defaults --workbook to Treasury_CMT_Data_Tool.xlsx)
python scripts/run_bootstrap.py --scheme 2
python scripts/run_bootstrap.py --scheme 3 --write-excel
python scripts/run_bootstrap.py --scheme 2 --nu 12
```

This writes `Treasury_CMT_Data_Tool_curves_S<scheme>_<minyear>-<maxyear>.npz`
(and `.xlsx` if `--write-excel` is passed) next to the workbook.

### Direct Python API — single date

```python
import numpy as np
from cmt_bootstrap import bootstrap_scheme1, bootstrap_scheme3, parse_tenor_to_years

tenor_labels = ['1Mo','1.5Mo','2Mo','3Mo','4Mo','6Mo','1Yr','2Yr',
                '3Yr','5Yr','7Yr','10Yr','20Yr','30Yr']
T = np.array([parse_tenor_to_years(t) for t in tenor_labels])

# Par rates in decimal (e.g. 4.25% -> 0.0425); use np.nan for a missing tenor
S = np.array([0.0547, 0.0545, 0.0544, 0.0540, 0.0537, 0.0527,
              0.0502, 0.0471, 0.0454, 0.0433, 0.0428, 0.0436, 0.0471, 0.0451])
r0 = 0.0533  # short-rate anchor (SOFR), needed by Schemes 2 and 3

b1 = bootstrap_scheme1(S, T, nu=24)
b3 = bootstrap_scheme3(S, T, r0=r0, nu=24)

print(b1.z * 100)        # Scheme 1 spot rates (cc, percent) at each tenor
print(b3.f_end * 100)    # Scheme 3 forward rate at each tenor's own endpoint
print(b1.discount_fn(8.5))  # P(0, 8.5y) under the Scheme 1 step-function forward
```

### Reading an existing NPZ panel

```python
import numpy as np

data = np.load('Treasury_CMT_Data_Tool_curves_S2_1990-2026.npz', allow_pickle=True)
print(list(data.keys()))          # full schema — see §8 API Reference

dates  = data['dates']             # (N,) datetime64[D]
labels = [str(x) for x in data['tenor_labels']]
spot   = data['spot_rates_cc_T']   # (N, 14) continuously-compounded spot rates

i10y = labels.index('10Yr')
print(spot[-1, i10y] * 100)        # most recent 10Yr spot rate, in percent
```

---

## 6. Bootstrap Workflows — From Data to Analysis

### Workflow 1: Ad-Hoc Analysis (one date, interactively)

**Use case:** Inspect the curve for a specific date (e.g. quarter-end).
**Time:** ~1 minute, if the panel NPZ already exists.

If you already have an NPZ panel covering that date, just index into it — no
re-bootstrapping needed:

```python
import numpy as np

data   = np.load('Treasury_CMT_Data_Tool_curves_S3_1990-2026.npz', allow_pickle=True)
dates  = data['dates']
labels = [str(x) for x in data['tenor_labels']]

idx = np.where(dates == np.datetime64('2024-12-31'))[0][0]
for t in ['3Mo', '2Yr', '5Yr', '10Yr', '30Yr']:
    j = labels.index(t)
    print(f"{t:>5}: {data['spot_rates_cc_T'][idx, j]*100:.4f}%  "
          f"(roundtrip err {data['par_rate_err_bp'][idx, j]:.2e} bp)")
```

If the date isn't in an existing panel yet, either re-run
`scripts/run_bootstrap.py` after updating the workbook, or call
`bootstrap_scheme1/2/3` directly on that single date's par rates (see §5).

**When to use:** One-off analysis, presentations, due diligence.

---

### Workflow 2: Production (Automated Daily)

**Use case:** Nightly job that keeps the panel current.
**Architecture:** a scheduled task refreshes both source inputs — Treasury CMT
par rates *and* the SOFR/Fed-Funds short-rate history — then re-runs the
existing bootstrap CLI. There's no separate "daily" code path to maintain
beyond that chain.

```bash
# All-in-one (recommended — this is what scripts/update_all_data.py wraps)
python scripts/update_all_data.py --scheme 2
```

which is equivalent to running the three steps explicitly:

```bash
# 1. Pull the latest CMT par rates into the workbook
python scripts/update_treasury_cmt.py --start-year 2026 --end-year 2026

# 2. Refresh the SOFR/Fed-Funds short-rate history (feeds r0 for Schemes 2/3)
python scripts/update_short_rates.py

# 3. Re-run the bootstrap over the whole (now-extended) history
python scripts/run_bootstrap.py --scheme 2
```

Step 2 is easy to miss because it doesn't touch the workbook at all — it only
matters for Schemes 2/3, which anchor the short end of the curve to `r0`
([§3.2](#32-scheme-2--piecewise-linear-forwards), [§3.3](#33-scheme-3--monotone-cubic-forwards)).
An earlier, two-step version of this workflow ran only step 1 before
bootstrapping, which let `r0` go stale silently: `build_r0_series()` just keeps
reusing the latest available SOFR observation for every new curve date rather
than erroring. `cmt_bootstrap.py` now prints an explicit `WARNING` when the
newest curve date has outrun the SOFR history by more than
`--short-rate-staleness-days` (default 5) — see [§8](#8-api-reference) — but
running all three steps (or the wrapper) avoids hitting that warning in the
first place. Fed Funds (1954–2018) itself never needs re-fetching; it's a
closed historical range baked into `data/short_rates/fed_funds_1954_2018.csv`.

Because `main()` reprocesses every date in the workbook each time, the output
NPZ is always a complete, consistent panel — there's no incremental/append mode
to reason about.

**Scheduling (cron, Linux/Mac):**
```bash
0 17 * * 1-5 cd /path/to/CMTRateBootstrap && python scripts/update_all_data.py --scheme 2 >> production.log 2>&1
```

**Scheduling (Windows Task Scheduler):** Basic Task → Daily trigger → Action:
`python.exe` with arguments `scripts/update_all_data.py --scheme 2` (working
directory set to the repo root).

**When to use:** Keeping a live panel for risk systems or daily reporting.

---

### Workflow 3: Research (Historical Panel for PCA)

**Use case:** PCA, tail-risk fitting, or backtesting over the full history.

As noted in [§4](#4-how-the-historical-panel-is-built), this doesn't require a
manual per-date loop — the NPZ produced by a single Scheme 1 run over the full
workbook (1990–present) already **is** the panel:

```bash
python scripts/run_bootstrap.py --scheme 1   # PCA/tail-risk in this repo is built on Scheme 1
```

`data/samples/Treasury_CMT_Data_Tool_curves_S1_1990-2026.npz` is exactly this —
a pre-built Scheme 1 panel spanning 1990–2026, ready to feed straight into
`src/vol_analysis.py` (see [§10](#10-downstream-applications)).

**When to use:** Research, model development, backtesting.

---

### Workflow Comparison

| Aspect | Ad-Hoc | Production | Research |
|--------|--------|------------|----------|
| **Frequency** | Once or rarely | Daily | One-time / occasional refresh |
| **Mechanism** | Index into existing NPZ | Re-run CLI on updated workbook | Run CLI once over full history |
| **Output** | In-memory values | Refreshed NPZ (+ optional xlsx) | Full NPZ panel |
| **Tools** | Python/Jupyter | Cron/Task Scheduler + CLI | CLI + `vol_analysis.py` |

---

## 7. Choosing a Method

```
What do you need?
│
├── Pricing / hedging at CMT tenors (DV01, swap PV)
│   └── Scheme 1  (fastest, discontinuous forward doesn't matter)
│
├── Continuous forward curve for visualization or short-rate-model calibration?
│   ├── Need C² spot rates, Monte Carlo, or PCA input?
│   │   └── Scheme 3
│   └── Otherwise
│       └── Scheme 2 (cheaper than Scheme 3, still C⁰)
│
└── PCA / tail-risk / functional analysis on forward rate changes?
    └── Scheme 1 — src/vol_analysis.py is built specifically against Scheme 1's
        piecewise-constant forwards (see §10). Scheme 2/3 files will load into
        vol_analysis_app.py but produce incorrect results — the math there
        assumes step-function forwards.
```

### Method Comparison Summary

| Property | Scheme 1 | Scheme 2 | Scheme 3 |
|----------|----------|----------|----------|
| Forward continuity | ✗ | ✓ (C⁰) | ✓ (C¹) |
| Forward smoothness | ✗ | ✗ | ✓ |
| Arbitrage-free at knots | ✓ | ✓ | ✓ |
| Closed-form solve | ✗ (1D Brent) | ✗ (1D Brent) | ✗ (1D Brent, after dimension reduction) |
| Anchored to `r0` | ✗ | ✓ | ✓ |
| Used by `vol_analysis.py` | ✓ | ✗ | ✗ |

---

## 8. API Reference

All of the below are module-level members of `src/cmt_bootstrap.py`.

### Constants

- `EXP_CAP = 700.0` — clamp bound used by `safe_exp()` to avoid `OverflowError`.
- `SOFR_START = pd.Timestamp("2018-04-03")` — dates before this always fall back to EFFR.

### Helper functions

- **`safe_exp(x: float) -> float`** — `exp(x)`, clamped to `[0, inf]` outside `±EXP_CAP`.
- **`pay_count(t_years: float, nu: int) -> int`** — number of coupon payments in `t_years` at frequency `nu`, using `round()` before `int()` for float safety.
- **`parse_tenor_to_years(label: str) -> float`** — parses labels like `"1.5 Mo"`, `"10 Yr"`, `"6mo"`, `"30y"` into years.
- **`find_header_row(ws, required_first="Date", max_scan_rows=250) -> int`** — locates the header row in an openpyxl worksheet.
- **`read_cmt_rates_from_workbook(path, sheet_name="CMT Rates") -> (tenors, T, df, miny, maxy)`** — parses the `CMT Rates` sheet; auto-detects percent vs. decimal input per cell.
- **`load_combined_short_rates(path) -> DataFrame[Date, Rate_dec, Source]`**
- **`load_fed_funds_history(path) -> DataFrame[Date, Rate_dec, Source]`** — Source is always `"EFFR"`.
- **`load_sofr_history_optional(path) -> DataFrame[Date, Rate_dec, Source]`** — empty DataFrame if the file doesn't exist; filters to dates ≥ `SOFR_START`.
- **`build_r0_series(curve_dates, short_df) -> (r0: np.ndarray, source: np.ndarray)`** — for each date, uses the latest SOFR observation on/before that date if available and `date >= SOFR_START`, else falls back to the latest EFFR observation.
- **`check_short_rate_staleness(curve_dates, short_df, max_gap_days=5) -> str | None`** — returns a warning message (or `None`) if the newest curve date has outrun the latest SOFR observation by more than `max_gap_days`; `main()` prints this as `WARNING: ...` for Schemes 2/3 before bootstrapping. Guards against `build_r0_series()`'s silent-reuse behavior above.
- **`annuity_sum(discount_fn, Ti, nu) -> float`** — `(1/nu) * Σ discount_fn(k/nu)` for `k = 1..pay_count(Ti, nu)`.
- **`par_rate(discount_fn, Ti, nu) -> float`** — `(1 - discount_fn(Ti)) / annuity_sum(...)`.
- **`int_lin(a, b, t) -> float`** — `0.5*a*t² + b*t` (integral of a linear forward).
- **`int_cubic(a, b, c, d, t) -> float`** — `a*t⁴/4 + b*t³/3 + c*t²/2 + d*t` (integral of a cubic forward).

### Bootstrap functions and result dataclasses

```python
@dataclass
class Scheme1Result:
    f: np.ndarray            # (K,) constant forward per tenor interval
    P: np.ndarray             # (K,) discount factor at each tenor
    z: np.ndarray             # (K,) spot rate, continuous compounding
    f_end: np.ndarray         # (K,) == f (kept for symmetry with Scheme 2/3)
    used_mask: np.ndarray     # (K,) bool — which tenors had input data
    warns: list[str]
    discount_fn: Callable[[float], float]

def bootstrap_scheme1(S, T, nu, f_max=1.0, tol=1e-14) -> Scheme1Result: ...
```

```python
@dataclass
class Scheme2Result:
    a: np.ndarray             # (K,) forward slope per interval
    b: np.ndarray             # (K,) forward intercept per interval
    P: np.ndarray
    z: np.ndarray
    f_end: np.ndarray         # forward value at each interval's own endpoint
    used_mask: np.ndarray
    warns: list[str]
    discount_fn: Callable[[float], float]

def bootstrap_scheme2(S, T, r0, nu, a_max=50.0, tol=1e-14) -> Scheme2Result: ...
```

```python
@dataclass
class Scheme3Result:
    a3: np.ndarray            # (K,) cubic coefficients
    b3: np.ndarray
    c3: np.ndarray
    d3: np.ndarray
    c_target_next: np.ndarray # (K,) Fritsch-Carlson slope target used at each knot
    P: np.ndarray
    z: np.ndarray
    f_end: np.ndarray
    used_mask: np.ndarray
    warns: list[str]
    discount_fn: Callable[[float], float]

def bootstrap_scheme3(S, T, r0, nu, a_max=200.0, tol=1e-13) -> Scheme3Result: ...
```

All three take `S` (par rates, decimal, `NaN` for missing) and `T` (tenor years)
as parallel 1D arrays of the same length; Schemes 2 and 3 additionally require
`r0` (the short-rate anchor for that date).

### I/O

- **`save_panel_npz(out_path, payload: dict) -> None`** — wraps `np.savez_compressed`, boxing plain strings/string-lists as `dtype=object` arrays so `np.load(..., allow_pickle=True)` round-trips them.
- **`write_excel(out_xlsx, tenors, dates, par_in, P_T, z_T, f_end, par_impl, err_bp, maxabs, rms, method, nu, r0, r0_src, params) -> None`** — writes one sheet per array (Par Rates, Discount Factors, Spot Rates, Forward @ TenorEnd, Par Rates Implied, RoundTrip Error, one sheet per scheme parameter, Short Rate Anchor, and a README sheet).

### NPZ Panel Schema

Every array below (except the scalar/metadata ones) is shaped `(N_dates, 14_tenors)`
unless noted otherwise:

| Key | Meaning |
|-----|---------|
| `schema_version`, `generator`, `created_utc`, `method`, `nu`, `compounding` | metadata |
| `dates` | `(N,)` `datetime64[D]` |
| `tenor_labels` | `(14,)` strings, e.g. `'1Mo'` |
| `tenor_years` | `(14,)` float |
| `par_rates_input` | input par rates (decimal), `NaN` where missing |
| `r0`, `r0_source` | short-rate anchor and its source (`'SOFR'`/`'EFFR'`/`'MISSING'`) per date |
| `discount_factors_T`, `spot_rates_cc_T`, `forward_endpoint_T` | bootstrap outputs |
| `par_rates_implied`, `par_rate_err_bp`, `par_rate_err_maxabs_bp`, `par_rate_err_rms_bp` | round-trip validation |
| `status_code`, `log_messages` | `0`=clean, `1`=warnings (see `log_messages`), `2`=failed for that date |
| `tenor_used_mask` | which tenors had input data, per date |
| `s1_f` *(Scheme 1 only)* | constant forward per tenor |
| `s2_a`, `s2_b` *(Scheme 2 only)* | linear forward coefficients |
| `s3_a`, `s3_b`, `s3_c`, `s3_d`, `s3_c_target_next` *(Scheme 3 only)* | cubic forward coefficients |

### CLI (`main()`)

```
python src/cmt_bootstrap.py
    --workbook PATH               (required)
    --scheme {1,2,3}               (required)
    --nu INT                       (default: 24)
    --short-rate-combined PATH     (default: data/short_rates/short_rate_combined.csv)
    --fed-funds-csv PATH           (default: data/short_rates/fed_funds_1954_2018.csv)
    --sofr-csv PATH                (default: data/short_rates/sofr_2018_present.csv)
    --short-rate-staleness-days N  (default: 5; Schemes 2/3 only — see check_short_rate_staleness above)
    --out-npz PATH                 (default: <workbook>_curves_S<scheme>_<miny>-<maxy>.npz)
    --write-excel                  (flag)
    --out-xlsx PATH                (default: <workbook>_curves_S<scheme>_<miny>-<maxy>.xlsx)
```

`scripts/run_bootstrap.py` wraps this with a smaller flag set
(`--scheme`, `--write-excel`, `--nu`, `--workbook`, the last defaulting to
`Treasury_CMT_Data_Tool.xlsx`) and shells out to the command above.

---

## 9. Design Notes & Implementation Lessons

Non-obvious implementation decisions — the gap between textbook theory and working code.

### 9.1 The Payment Count Fix — and Why ν = 24

```python
# WRONG — causes systematic errors at 1.5Mo and other fractional tenors
n = int(nu * tau)          # int(24 * 0.5/12) = int(0.9999...) = 0

# CORRECT (what pay_count() actually does)
n = int(round(nu * tau + 1e-9))   # round(0.9999...) = 1
```

`nu = 24` (payments every 15 days) is deliberate. With `nu = 12` (monthly), the
1.5Mo interval gives `nu*tau = 12 * (0.5/12) = 0.5` — exactly on the rounding
boundary, which is implementation-defined (banker's rounding) and therefore
fragile. `nu = 24` maps every CMT interval to a clean, unambiguous integer.

### 9.2 30/360 and Exact Arithmetic

`parse_tenor_to_years()` computes `T = months/12` as exact float division rather
than day-counting actual/365, so every interval width is an exact multiple of
`1/12` — eliminating floating-point ambiguity in the tenor grid itself.

### 9.3 Scheme 3 — Dimension Reduction

The naive formulation of Scheme 3 is a 2D nonlinear root-find (`a_i` and `b_i`
both unknown), which is fragile — the 10Y→20Y interval in particular can produce
extreme parameter values. Because the slope constraint

    3·a·dT² + 2·b·dT + c_i - c_next = 0

is linear in `(a, b)`, `b_of_a(a)` eliminates `b` analytically, and the residual
becomes a well-conditioned 1D function of `a` alone — solved by `brentq` with a
scaled-bracket search (see §3.3). This is the actual `b_of_a` closure in
`bootstrap_scheme3`.

### 9.4 C² Is Impossible Without Sacrificing Monotonicity

Adding second-derivative continuity to Scheme 3 would need a fifth constraint on
a four-parameter cubic — over-determined. The code's actual fallback path (see
§3.3, "Numerical fallbacks") reflects this in practice: rather than force a C²
solve that would need to drop monotonicity, difficult intervals fall back to a
plain constant forward for that one interval, preserving continuity and
arbitrage-freeness at the cost of local smoothness.

### 9.5 Robustness of Scheme 3's Bracket Search

The real code goes further than a single bracket-widening loop: it scales the
initial bracket by interval width (`interval_scale = max(1.0, dT/0.15)`, since
wide intervals — often from a missing tenor — need larger cubic coefficients),
attempts asymmetric bracket repair if only one side of `residual()` overflows,
and only falls back to the constant-forward solve described above if all of that
fails. This is meaningfully more defensive than the simpler bracket-doubling used
in Schemes 1 and 2, reflecting that the cubic residual is the most numerically
fragile of the three.

---

## 10. Downstream Applications

### PCA / Tail-Risk Analysis (`src/vol_analysis.py`)

This is real, shipped code — not a design sketch. `vol_analysis.py` consumes a
**Scheme 1** NPZ panel directly:

```python
from vol_analysis import load_vol_panel, weighted_pca, fit_both

panel   = load_vol_panel('data/samples/Treasury_CMT_Data_Tool_curves_S1_1990-2026.npz')
pca     = weighted_pca(panel)     # span-weighted PCA on daily Δf
fits    = fit_both(panel, pca)    # k=5 and k=14 F(k,ν) tail fits

print(pca.var_share[:5])          # variance explained by PC1..PC5
print(fits.k5.nu, fits.k14.nu)    # fitted degrees of freedom
```

Why Scheme 1 specifically: `weighted_pca` builds a span-weighted covariance
(`Δf` scaled by `√ΔT_i` per tenor) directly from `s1_f`'s daily first differences,
after `fill_s1_gaps()` repairs missing-tenor gaps using the piecewise-constant
structure's own exactness property (an absent span's constant forward equals its
right-hand neighbor's, since the bootstrap merged them). That gap-fill logic is
specific to Scheme 1's step-function forwards; it isn't valid for Scheme 2/3
files, which is why `scripts/vol_analysis_app.py` requires a Scheme 1 panel (see
the app's own README section for the corresponding user-facing warning).

### Continuous Curve Reconstruction (`scripts/curve_reconstruction.py`)

Rather than an object with a `.forward_at(t)` method, reconstruction here is a
set of functions operating directly on one date-row of an NPZ panel:

```python
from curve_reconstruction import reconstruct_curves

# `data` is whatever np.load(npz_path, allow_pickle=True) returns, keyed the
# same as the schema in §8; date_idx indexes into its (N, 14) arrays.
curves = reconstruct_curves(data, date_idx=0, num_points=1000)
t_dense, f_dense, P_dense, z_dense = (
    curves['t_dense'], curves['forward_dense'],
    curves['discount_dense'], curves['spot_dense'],
)
```

Internally this dispatches on `data['method']` to
`reconstruct_scheme1_forward` / `reconstruct_scheme2_forward` /
`reconstruct_scheme3_forward`, then `integrate_forward_to_discount` and
`compute_spot_from_discount` — this is exactly what
`scripts/yield_curve_app.py` calls to draw the continuous curves in the
Streamlit app (see [`docs/CURVE_RECONSTRUCTION.md`](CURVE_RECONSTRUCTION.md)
for the underlying math).

### Swap Pricing / DV01

Scheme 1 is sufficient for exact pricing at CMT tenors, since only the integrated
discount factor matters:

```python
b1 = bootstrap_scheme1(S, T, nu=24)
i5y = tenor_labels.index('5Yr')
P_5y, z_5y = b1.P[i5y], b1.z[i5y]
```

For DV01, bump one entry of `S` by 1bp, re-run `bootstrap_scheme1`, and compare
the resulting discount factor or par rate.

---

## 11. References

**Bootstrapping methodology:**

Hagan, P. S. & West, G. (2006). "Interpolation Methods for Curve Construction."
*Applied Mathematical Finance*, 13(2), 89–129.

Hagan, P. S. & West, G. (2008). "Methods for Constructing a Yield Curve."
*Wilmott Magazine*, May 2008, 70–81.

**Monotone interpolation:**

Fritsch, F. N. & Carlson, R. E. (1980). "Monotone Piecewise Cubic Interpolation."
*SIAM Journal on Numerical Analysis*, 17(2), 238–246.

**US Treasury methodology:**

The US Treasury estimates its par yield curve using a monotone convex spline
method (equivalent to Scheme 3 in spirit). Published daily at:
https://home.treasury.gov/resource-center/data-chart-center/interest-rates/

---

## Code Reference

- [`src/cmt_bootstrap.py`](../src/cmt_bootstrap.py) — everything in this guide
- [`src/vol_analysis.py`](../src/vol_analysis.py) — PCA / tail-risk on Scheme 1 output
- [`scripts/curve_reconstruction.py`](../scripts/curve_reconstruction.py) — continuous curve evaluation
- [`scripts/run_bootstrap.py`](../scripts/run_bootstrap.py) — CLI convenience wrapper
- [`scripts/update_treasury_cmt.py`](../scripts/update_treasury_cmt.py) — fetches Treasury CMT par rates into the workbook
- [`scripts/update_short_rates.py`](../scripts/update_short_rates.py) — fetches/combines the SOFR + Fed Funds history that feeds `r0`
- [`scripts/update_all_data.py`](../scripts/update_all_data.py) — single entrypoint chaining the two fetchers above and the bootstrap (see Workflow 2)

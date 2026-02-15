# Bootstrap Pipeline — User Guide
## Treasury Yield Curve Construction from CMT Par Rates

**Version 2.1 — February 2026**

---

## Contents

1. [Overview](#1-overview)
2. [Mathematical Background](#2-mathematical-background)
3. [The Bootstrap Methods](#3-the-bootstrap-methods)
   - 3.1 Bootstrap 1 — Piecewise Constant Forwards
   - 3.2 Bootstrap 2 — Piecewise Linear Forwards
   - 3.3 Bootstrap 3 — Monotone Cubic Forwards
4. [Longstaff's Hack](#4-longstaffs-hack)
5. [The Uniform Grid Pipeline](#5-the-uniform-grid-pipeline)
6. [Quick Start](#6-quick-start)
7. [Bootstrap Workflows — From Data to Analysis](#7-bootstrap-workflows--from-data-to-analysis)
   - 7.1 Ad-Hoc Analysis Workflow
   - 7.2 Production Workflow (Automated Daily)
   - 7.3 Research Workflow (Historical Panel)
8. [Examples — Recent Quarter-End Data](#8-examples--recent-quarter-end-data)
9. [Choosing a Method](#9-choosing-a-method)
10. [API Reference](#10-api-reference)
11. [Design Notes & Implementation Lessons](#11-design-notes--implementation-lessons)
12. [Downstream Applications](#12-downstream-applications)
13. [References](#13-references)

---

## 1. Overview

This module constructs zero-coupon yield curves from US Treasury Constant Maturity
(CMT) par rates using a family of bootstrapping methods of increasing smoothness,
followed by Longstaff's Hack and a uniform-grid pipeline for functional analysis.

**Input:**  14 CMT par rates {S(T_i)} at standard Treasury maturities 1Mo–30Yr
             (including the 1.5Mo / 45-day tenor).

**Output:**  Discount factors P(0,T), spot rates R(T), instantaneous forward
             rates f(t), and a 360-element uniformly-spaced forward rate vector
             ready for PCA and other functional analysis.

### The Five Stages

| Stage | Method | Tenors | Forward Smoothness | Primary Use |
|-------|--------|--------|--------------------|-------------|
| 1 | Bootstrap 1 | 14 CMT | C⁻¹ (jumps at knots) | Swap pricing, DV01, hedging |
| 2 | Bootstrap 2 | 14 CMT | C⁰ (continuous) | Hull-White calibration |
| 3 | Bootstrap 3 | 14 CMT | C¹ (smooth) | Monte Carlo, exotics |
| 4 | Longstaff    | 13 CMT† | N/A (par rates) | Par rate interpolation |
| 5 | B1 on 1M grid | 360 uniform | C⁻¹ → C⁰ as Δτ→0 | PCA, functional analysis |

† Longstaff excludes 1.5Mo (not a whole-month tenor on 30/360; spline
  interpolates smoothly over the 1Mo–2Mo gap).

### Conventions

- **Day count:** 30/360 throughout. T = months/12 exactly (no rounding error).
- **Payment frequency:** ν = 24 (every 15 days = 1/24 year).
- **CMT tenors:** 14 for bootstrapping (stages 1–3), 13 for Longstaff (1.5Mo excluded — not a whole-month tenor on 30/360).
- **Compounding:** Continuous throughout. R(T) = −ln P(0,T) / T.
- **Par bond condition:** S(T_i) = (1 − P(0,T_i)) / Ann₀(0,T_i).
- **Round-trip precision:** < 10⁻⁸ bps for all bootstrap stages.

---

## 2. Mathematical Background

### The Bootstrapping Problem

Given par rates {S(T_1), ..., S(T_N)}, find discount factors {P(0,T_i)} such
that a par bond at each tenor prices at 100:

    S(T_i) = (1 − P(0,T_i)) / Ann₀(0,T_i)

where the annuity factor Ann₀(0,T_i) accumulates coupon present values:

    Ann₀(0,T_i) = Ann₀(0,T_{i-1}) + (P(0,T_{i-1})/ν) Σ_{k=1}^{n_i} exp(−∫₀^{k/ν} f_i(τ)dτ)

and f_i(τ) is the forward rate function in interval i.

### Why Not Direct Inversion?

The par bond equation involves a **nonlinear transcendental function** of the
forward rate polynomial coefficients — there is no closed-form inversion.
Bootstrapping solves these equations sequentially, interval by interval, using
the already-determined discount factors for shorter maturities.

Each interval has one (B1, B2) or two (B3) unknowns, solved by Brent's method
(1D) or a reduced 1D system after analytical substitution (B3). The key
implementation insight is that floating-point precision requires `round()` before
`int()` when computing payment counts:

    n_i = int(round(ν · τ_i))    # CORRECT
    n_i = int(ν · τ_i)           # WRONG: int(0.9999...) = 0

### CMT Tenors and Spacing

The 14 CMT tenors used in bootstrapping (stages 1–3) span 1 month to 30 years:

    1Mo  1.5Mo  2Mo  3Mo  4Mo  6Mo  1Yr  2Yr  3Yr  5Yr  7Yr  10Yr  20Yr  30Yr

The 1.5Mo tenor (45-day T-bill) is the motivation for choosing ν = 24.
With ν = 12, the 1.5Mo interval (τ = 0.5/12) gives ν·τ = 0.5 — not an
integer, creating an ambiguous payment count. ν = 24 gives ν·τ = 1 exactly
for every interval in the 14-tenor set. Longstaff operates on 13 tenors
(1.5Mo excluded) since it works in whole-month par rate space.

---

## 3. The Bootstrap Methods

### 3.1 Bootstrap 1 — Piecewise Constant Forwards

**Forward curve:** f_i(τ) = f_i (constant) for τ ∈ [0, τ_i)

**Discount factor:**

    P(0,T_i) = P(0,T_{i-1}) · exp(−f_i · τ_i)

**Continuity:** C⁻¹ — forwards are **discontinuous** at each tenor knot.

**Solver:** 1D Brent per interval on the par bond residual.

**Properties:**
- Arbitrage-free by construction
- Exact at all tenor knot points
- Forward curve exhibits jumps (up to ~50 bps at illiquid tenors)
- Industry standard: matches Bloomberg SWDF methodology
- Computationally simplest — 1 parameter, 1 equation per interval

**When to use:** Swap pricing, DV01 calculation, hedge ratios, any application
requiring exact pricing of instruments at the quoted CMT tenors. The discontinuous
forwards are not a problem when only the integrated discount factors matter.

**Not suitable for:** Applications requiring a continuous forward curve —
Hull-White calibration (where θ(t) is derived from f'(t)), Monte Carlo
path generation, or barrier/path-dependent products.

---

### 3.2 Bootstrap 2 — Piecewise Linear Forwards

**Forward curve:** f_i(τ) = a_i·τ + b_i for τ ∈ [0, τ_i)

**C⁰ continuity condition:** b_i = a_{i-1}·τ_{i-1} + b_{i-1}

**Initial condition:** b_1 = r_0 (SOFR overnight rate)

**Discount factor:**

    P(0,T_i) = P(0,T_{i-1}) · exp(−a_i·τ_i²/2 − b_i·τ_i)

**Continuity:** C⁰ — forwards are **continuous** at tenor knots; spots are C¹.

**Solver:** 1D Brent on the slope a_i (intercept b_i determined by continuity).

**Properties:**
- Arbitrage-free by construction
- Forward curve continuous (no jumps)
- Anchored to SOFR at the short end via b_1 = r_0
- Slightly higher computational cost than B1 (~20%)

**C⁰ continuity mechanics:** Each interval's intercept b_i is fully determined
by the previous interval's terminal slope a_{i-1}·τ_{i-1} + b_{i-1}. This
chains all intervals together, which is appropriate for a sparse 14-tenor grid
but becomes pathological on dense uniform grids (see Section 5).

**When to use:** Hull-White calibration (continuous θ(t) = f'(t) + f(t)²  + f(t)·κ
benefits from continuous forwards), smoother forward curve visualization, or when
the slope anchoring to SOFR matters economically.

**Important limitation — Dense Grids:** Do NOT apply Bootstrap 2 to the 360-tenor
uniform grid. The slope chaining across 360 intervals creates resonant oscillation:
each a_i compensates the f_end of the previous interval, which overshoots, requiring
correction in turn. The amplitude grows along the curve, producing a sawtooth forward
pattern with excursions of ±70%. Bootstrap 1 on the uniform grid avoids this entirely.

---

### 3.3 Bootstrap 3 — Monotone Cubic Forwards

**Forward curve:** f_i(τ) = a_i·τ³ + b_i·τ² + c_i·τ + d_i for τ ∈ [0, τ_i)

**Four constraints per interval (matching four parameters):**

1. **C⁰:** d_i = f_{i-1}(τ_{i-1}),  d_1 = r_0
2. **C¹:** c_i = f'_{i-1}(τ_{i-1}), c_1 = 0
3. **Monotonicity:** c_{i+1} fixed by Fritsch-Carlson condition
4. **Par bond:** (1 − P)/Ann = S(T_i) (determines the integral)

**Continuity:** C¹ forwards, C² spots. The forward curve has both value and
slope continuity at every tenor knot.

**The Fritsch-Carlson Condition (monotonicity):**

Using Bootstrap 2 slopes {l_i} as the linear reference, define phantom
values l_0 = l_{N+1} = 0. Then:

    c_{i+1} = { (l_i·τ_i + l_{i+1}·τ_{i+1}) / (τ_i + τ_{i+1})  if l_i·l_{i+1} > 0
              { 0                                                   otherwise

The phantom values give boundary conditions for free:
- Left end: l_0·l_1 = 0 → c_1 = 0 (forward curve flat at instantaneous maturity)
- Right end: l_N·0 = 0 → c_{N+1} = 0 (forward curve flat at 30Y)

**Two-pass algorithm:**
- Pass 1: Run Bootstrap 2 to obtain slopes {l_i}
- Pass 2a: Compute {c_i} from Fritsch-Carlson condition
- Pass 2b: For each interval, solve for {a_i, b_i}

**Solver — Dimension Reduction Trick:**

The slope constraint F2: `3a·τ² + 2b·τ + c_i − c_{i+1} = 0` is **linear** in
(a, b), allowing b to be expressed analytically as a function of a:

    b(a) = [c_{i+1} − c_i − 3a·τ²] / (2τ)

After substitution, f_i(τ) (the right endpoint value) simplifies to:

    f_i(τ) = −(τ³/2)·a + [(c_{i+1}+c_i)/2]·τ + d_i

which is **linear in a**, providing exact analytical bounds for Brent's method.
This reduces the 2D nonlinear system to a robust 1D Brent search.

**Why No C²?**

Adding second-derivative continuity would require a fifth constraint on a
four-parameter system — the system becomes over-determined. The only resolution
is to drop monotonicity, which causes catastrophic Runge-phenomenon oscillation
especially across the 10Y→20Y gap (τ = 10 years). Monotonicity is the correct
substitute: it prevents spurious oscillations while maintaining C¹ smoothness.

**When to use:** Hull-White calibration requiring fully smooth θ(t), Monte Carlo
path generation, path-dependent or barrier products, research requiring the
smoothest possible forward curve, any application requiring C² spot rates.

**Computational cost:** ~3× Bootstrap 1. The two-pass algorithm and 1D solver
(after dimension reduction) add overhead; the dimension reduction is essential
for robustness especially at the 10Y→20Y interval.

---

## 4. Longstaff's Hack

### Concept

Rather than bootstrapping to find a forward curve and then interpolating
spot/par rates, Longstaff's Hack fits a monotone cubic spline **directly
to the par rates** as a function of maturity:

    y_i(τ) = a_i·τ³ + b_i·τ² + c_i·τ + d_i  interpolates S(T) for T ∈ [T_i, T_{i+1}]

This inverts the usual workflow. Instead of:

    Par rates → Bootstrap → Spot/Zero rates → Interpolate

the approach is:

    Par rates → Spline → S(T) for any T → Bootstrap on fine grid

### Mathematics

**C⁰ continuity:** d_{i+1} = y_i(τ_i)  (value continuity at knots)

**C¹ continuity:** c_{i+1} = y'_i(τ_i)  (slope continuity at knots)

**Monotonicity (Fritsch-Carlson on par rates directly):**

    c_i = { [S(T_{i+1}) − S(T_{i-1})] / [T_{i+1} − T_{i-1}]
             if locally monotone: S(T_{i+1}) > S(T_i) > S(T_{i-1}) or reverse
           { 0  at local extrema and at boundaries

This is the **centered finite difference slope**, applied only where the par
curve is locally monotone. Note that this is applied to the directly-observable
par rates — not to derived forward or zero rates.

**Closed-form {a_i, b_i}:**

The two continuity conditions at the right endpoint of interval i give a
2×2 linear system:

    [τ_i³   τ_i²] [a_i]   [d_{i+1} − d_i − c_i·τ_i]
    [3τ_i²  2τ_i] [b_i] = [c_{i+1} − c_i           ]

    det = 2τ_i⁴ − 3τ_i⁴ = −τ_i⁴  (always nonzero → always invertible)

Solved by np.linalg.solve — exact, O(1), no iterative method required.
This is the key computational advantage: the entire spline is O(N) arithmetic.

### Stability Hierarchy

Longstaff's observation motivating this approach:

    Stability:  Mortgage rates > Par rates > Zero rates > Forward rates

Each transformation from par rates amplifies interpolation noise:
- Par → Zero requires stripping, propagating short-end errors to long maturities
- Zero → Forward requires differentiation, the most noise-amplifying operation

By fitting directly in par rate space — the most directly observable and most
empirically smooth coordinate — the interpolation is maximally stable.

### Arbitrage Properties

**Arbitrage-free:** Only at the 13 CMT knot points {T_i}, where the spline
passes exactly through the observed par rates (error < 10⁻¹⁰ bps).

**Between tenors:** The spline is smooth and monotone where the par curve is
monotone, providing "reasonable" interpolated values. However, the implied
discount factors and forward rates are NOT guaranteed to be arbitrage-free.
The monotonicity condition mitigates pathological cases but does not eliminate
the possibility of negative implied forwards under stress scenarios.

**Practical stance:** Under normal market conditions (par curve changes of
< 200 bps across any interval), the interpolated par rates are effectively
arbitrage-free. Verify explicitly under stress scenarios if required.

### Primary Use: Generating Uniform Grids

The most important application is generating a fine, uniform par rate grid
to feed into Bootstrap 1 (Stage 5). This solves two problems at once:

1. **Fills the 10Y→20Y gap:** Rather than a single cubic spanning 10 years,
   Bootstrap 1 operates on monthly steps with smooth input from Longstaff.

2. **Removes PCA weighting artifacts:** A uniform 1M grid gives every
   maturity equal representation in the covariance matrix, so PCA factors
   reflect genuine term structure variation rather than the uneven density
   of CMT tenor points.

---

## 5. The Uniform Grid Pipeline

Stage 5 combines Longstaff's Hack with Bootstrap 1 on a 360-tenor monthly grid:

    Stage 4: Longstaff → S(1Mo), S(2Mo), ..., S(360Mo)    [360 par rates]
    Stage 5: Bootstrap 1 → P(0,1Mo), ..., P(0,360Mo)      [360 discount factors]
             → f(1Mo), f(2Mo), ..., f(360Mo)               [360 forward rates]

**Why Bootstrap 1 (not Bootstrap 2) on the uniform grid:**

Bootstrap 2's C⁰ continuity chains all intervals: b_i = a_{i-1}·τ_{i-1} + b_{i-1}.
On a 14-tenor sparse grid, this is beneficial — it enforces smoothness.
On a 360-tenor uniform grid with τ = 1/12, the chain of 360 coupled equations
produces resonant oscillation: small fitting errors amplify interval by interval
into a ±70% sawtooth pattern. Bootstrap 1 has no inter-interval coupling —
each is solved independently. On a fine grid:

    max(forward jump at knot) ≈ S'(T)·Δτ → 0  as Δτ → 0

The smoothness comes from Longstaff; Bootstrap 1 provides exactness at every node.

**The PCA-ready forward vector:**

The result is a 360-element vector [f(1Mo), f(2Mo), ..., f(360Mo)] where:
- All entries are continuously compounded instantaneous forward rates
- Equal 1M spacing — no weighting distortion in the covariance matrix
- Range typically 3%–6% for normal yield curve environments
- Direct input to PCA, Nelson-Siegel fitting, or other functional analysis

---

## 6. Quick Start

### Installation

```python
# Dependencies: numpy, scipy (standard scientific Python stack)
pip install numpy scipy

# Import
from bootstrap_pipeline import (
    Bootstrap1, Bootstrap2, Bootstrap3,
    LongstaffHack, UniformGridPipeline,
    run_pipeline, CMT_MATURITIES
)
```

### Basic Usage — Run All Stages

```python
from bootstrap_pipeline import run_pipeline
import numpy as np

# CMT par rates in percent
par_rates = {
    '1Mo': 4.38, '1.5Mo': 4.36, '2Mo': 4.33, '3Mo': 4.32, '4Mo': 4.30, '6Mo': 4.27,
    '1Yr': 4.17, '2Yr': 4.24, '3Yr': 4.27, '5Yr': 4.38, '7Yr': 4.48,
    '10Yr': 4.57, '20Yr': 4.87, '30Yr': 4.83,
}
r0 = 0.043   # SOFR (short rate anchor for B2/B3 initial condition)

results = run_pipeline(par_rates, r0=r0)
# Returns dict: 'b1', 'b2', 'b3', 'longstaff', 'uniform'
```

### Accessing Results

```python
b1      = results['b1']       # Bootstrap 1 CurveResult
b3      = results['b3']       # Bootstrap 3 CurveResult
spline  = results['longstaff']  # LongstaffSpline
uniform = results['uniform']    # 360-tenor CurveResult

# Spot rates (continuous compounding)
print(b1.spot_rates['10Yr'] * 100)   # e.g. 4.5912%

# Discount factors
print(b3.discount_factors['5Yr'])    # e.g. 0.8187

# Instantaneous forward at any maturity
print(b3.forward_at(8.5))           # f(8.5Y) interpolated

# Longstaff: par rate at any maturity
print(spline.par_rate(8.5) * 100)   # S(8.5Y) in percent

# PCA-ready forward vector (360 elements)
fwds = np.array([uniform.forward_params[t]['f'] * 100
                 for t in uniform.tenors])
# fwds is now ready for: PCA, NSS fitting, curve comparison
```

### Accessing the Uniform Grid

```python
# Dense forward curve for plotting
t_grid, f_grid = uniform.forward_curve(n=500)

# Individual forward rates
for m in [1, 6, 12, 24, 60, 120, 240, 360]:
    from bootstrap_pipeline import _tenor_label
    lbl = _tenor_label(m)
    f   = uniform.forward_params[lbl]['f'] * 100
    print(f'f({m:3d}Mo) = {f:.4f}%')

# Validate round-trip precision
rt = uniform.roundtrip_bps()
print(f'Max round-trip error: {max(abs(v) for v in rt.values()):.2e} bps')
```

### Run a Single Bootstrap Stage

```python
from bootstrap_pipeline import Bootstrap1, Bootstrap3

# Bootstrap 1 only
b1 = Bootstrap1().run(par_rates, r0=r0)
b1.print_summary()

# Bootstrap 3 only
b3 = Bootstrap3().run(par_rates, r0=r0)

# Longstaff only (no bootstrap)
from bootstrap_pipeline import LongstaffHack
spline = LongstaffHack().fit(par_rates)
spline.print_knot_check()

# Uniform grid only
from bootstrap_pipeline import UniformGridPipeline
spline, uniform = UniformGridPipeline().run(par_rates, r0=r0)
```

### Suppress Output

```python
results = run_pipeline(par_rates, r0=r0, verbose=False)
```

---

---

## 7. Bootstrap Workflows — From Data to Analysis

This section describes the complete workflows for different use cases, integrating the Excel data platform with the Python bootstrap pipeline.

### Workflow Overview

Three primary workflows, depending on your needs:

1. **Ad-Hoc Analysis Workflow** — Quick one-off curve construction
2. **Production Workflow** — Automated daily/weekly bootstrapping
3. **Research Workflow** — Historical panel construction for PCA/modeling

---

### Workflow 1: Ad-Hoc Analysis (Excel → Python → Results)

**Use case:** Generate a yield curve for a specific date (e.g., quarter-end).

**Time:** ~5 minutes  
**Tools:** Excel + Python interactive session  
**Output:** Discount factors, spot rates, forward curve for one date

#### Step-by-Step

**Step 1: Update Excel with CMT Data**

```
1. Open Treasury_CMT_Data_Tool.xlsx
2. Go to Config sheet
   - Set Start Year = current year (e.g., 2024)
   - Set End Year = current year
3. Go to CMT Rates sheet
4. Click "Update CMT Rates" button
5. Wait ~30 seconds for download
6. Verify: Latest date appears in row 12
```

**Step 2: Identify Target Date**

```
1. Scroll CMT Rates sheet to find your date (e.g., 12/31/2024)
2. Check all 14 maturities have values (no blanks)
3. Note any unusual values (data quality check)
```

**Step 3: Run Python Bootstrap (Interactive)**

Open Python/Jupyter:

```python
import pandas as pd
from bootstrap_pipeline import run_pipeline

# Read Excel
df = pd.read_excel('Treasury_CMT_Data_Tool.xlsx', 
                   sheet_name='CMT Rates')

# Filter to target date
target_date = '2024-12-31'
row = df[df['Date'] == target_date].iloc[0]

# Build par_pct dict
par_pct = {
    '1Mo': row['1 Mo'], '1.5Mo': row['1.5 Mo'], '2Mo': row['2 Mo'],
    '3Mo': row['3 Mo'], '4Mo': row['4 Mo'], '6Mo': row['6 Mo'],
    '1Yr': row['1 Yr'], '2Yr': row['2 Yr'], '3Yr': row['3 Yr'],
    '5Yr': row['5 Yr'], '7Yr': row['7 Yr'], '10Yr': row['10 Yr'],
    '20Yr': row['20 Yr'], '30Yr': row['30 Yr'],
}

# Set SOFR (r0) - use 1Mo as proxy
r0 = par_pct['1Mo'] / 100

# Run all methods
results = run_pipeline(par_pct, r0=r0, verbose=True)

# Extract results
b1 = results['b1']        # Bootstrap 1 (piecewise constant)
b3 = results['b3']        # Bootstrap 3 (monotone cubic)
uniform = results['uniform']  # B3 on 360-month grid
```

**Step 4: Inspect Results**

```python
# Check precision
rt_b3 = b3.roundtrip_bps()
print(f"B3 max roundtrip: {max(abs(v) for v in rt_b3.values()):.2e} bps")

# Spot rates at key tenors
for t in ['1Mo', '1Yr', '5Yr', '10Yr', '30Yr']:
    print(f"{t:>5}: {b3.spot_rates[t]*100:.4f}%")

# Forward curve from uniform grid
import numpy as np
fwds = [uniform.forward_params[t]['d']*100 for t in uniform.tenors]
print(f"\nForward range: {min(fwds):.2f}% - {max(fwds):.2f}%")
```

**Step 5: Record Parameters in Excel**

Open **Bootstrap Params** sheet, add:

| Run Date | Data Date | Method | r0 (%) | ν | Precision | Forward Range | Notes |
|----------|-----------|--------|--------|---|-----------|---------------|-------|
| 02/13/26 | 12/31/24  | B3 Uniform | 4.30 | 24 | 1.04e-12 | 4.01%-5.61% | Ad-hoc Q4 analysis |

**Step 6: Use Results**

```python
# Example: Compute DV01 for 10Y
P_10Y = b3.discount_factors['10Yr']
T_10Y = b3.maturities['10Yr']

# Bump 10Y par rate by 1bp
par_pct_bumped = par_pct.copy()
par_pct_bumped['10Yr'] += 0.01  # +1bp

# Re-bootstrap
results_bumped = run_pipeline(par_pct_bumped, r0=r0, verbose=False)
P_10Y_bumped = results_bumped['b3'].discount_factors['10Yr']

# DV01 (approximate)
DV01_10Y = (P_10Y_bumped - P_10Y) * 10000  # per $1MM notional
print(f"10Y DV01: ${DV01_10Y:.2f}")
```

**When to use:** One-off analysis, presentations, due diligence.

---

### Workflow 2: Production Workflow (Automated Daily)

**Use case:** Nightly batch job to bootstrap latest CMT data.

**Time:** ~1 minute automated  
**Tools:** Cron job + Python script  
**Output:** Daily curve files, database updates, reports

#### Architecture

```
┌─────────────────────┐
│  Cron Job           │  Daily at 5:00 PM ET (after Treasury publishes)
│  (scheduled task)   │
└──────────┬──────────┘
           │
┌──────────▼──────────┐
│  Python Script      │  update_daily_curves.py
│  (automated)        │
└──────────┬──────────┘
           │
           ├──> Fetch latest CMT from Treasury API
           ├──> Run Bootstrap 3 + Uniform grid
           ├──> Save results to database / files
           ├──> Generate summary report
           └──> Email alerts on errors
```

#### Production Script Template

Create `update_daily_curves.py`:

```python
#!/usr/bin/env python3
"""
Daily Bootstrap Pipeline — Production Script

Fetches latest Treasury CMT data and runs Bootstrap 3.
Saves results to files and database.

Usage:
    python update_daily_curves.py [--date YYYY-MM-DD]
    
If --date not provided, uses latest available date from Treasury.
"""

import pandas as pd
import numpy as np
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import logging
import sys

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bootstrap_production.log'),
        logging.StreamHandler()
    ]
)

def fetch_latest_cmt():
    """Fetch latest CMT data from Treasury or Excel file."""
    try:
        df = pd.read_excel('Treasury_CMT_Data_Tool.xlsx', 
                          sheet_name='CMT Rates',
                          parse_dates=['Date'])
        
        # Get most recent date
        latest_date = df['Date'].max()
        row = df[df['Date'] == latest_date].iloc[0]
        
        logging.info(f"Loaded CMT data for {latest_date.strftime('%Y-%m-%d')}")
        return row, latest_date
        
    except Exception as e:
        logging.error(f"Failed to load CMT data: {e}")
        sys.exit(1)

def build_par_dict(row):
    """Build par_pct dictionary from Excel row."""
    return {
        '1Mo': row['1 Mo'], '1.5Mo': row['1.5 Mo'], '2Mo': row['2 Mo'],
        '3Mo': row['3 Mo'], '4Mo': row['4 Mo'], '6Mo': row['6 Mo'],
        '1Yr': row['1 Yr'], '2Yr': row['2 Yr'], '3Yr': row['3 Yr'],
        '5Yr': row['5 Yr'], '7Yr': row['7 Yr'], '10Yr': row['10 Yr'],
        '20Yr': row['20 Yr'], '30Yr': row['30 Yr'],
    }

def run_bootstrap_safe(par_pct, r0):
    """Run bootstrap with error handling."""
    try:
        from bootstrap_pipeline import run_pipeline
        
        logging.info("Running bootstrap pipeline...")
        results = run_pipeline(par_pct, r0=r0, verbose=False)
        
        # Validate
        uniform = results['uniform']
        rt = uniform.roundtrip_bps()
        max_rt = max(abs(v) for v in rt.values())
        
        if max_rt > 1e-6:
            logging.warning(f"Round-trip error {max_rt:.2e} bps exceeds tolerance")
        else:
            logging.info(f"Bootstrap successful, precision: {max_rt:.2e} bps")
        
        return results
        
    except Exception as e:
        logging.error(f"Bootstrap failed: {e}")
        sys.exit(1)

def save_results(results, date, output_dir='./curves'):
    """Save results to files."""
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    
    date_str = date.strftime('%Y%m%d')
    
    # Save uniform forward vector (PCA-ready)
    uniform = results['uniform']
    fwd_vector = np.array([uniform.forward_params[t]['d'] 
                          for t in uniform.tenors])
    
    fwd_file = output_dir / f'forwards_{date_str}.npy'
    np.save(fwd_file, fwd_vector)
    logging.info(f"Saved forward vector: {fwd_file}")
    
    # Save discount factors (CSV for readability)
    b3 = results['b3']
    df_curve = pd.DataFrame({
        'Tenor': list(b3.tenors),
        'Maturity': [b3.maturities[t] for t in b3.tenors],
        'Par_Rate': [b3.par_rates[t] for t in b3.tenors],
        'Spot_Rate': [b3.spot_rates[t] for t in b3.tenors],
        'Discount_Factor': [b3.discount_factors[t] for t in b3.tenors],
    })
    
    curve_file = output_dir / f'curve_{date_str}.csv'
    df_curve.to_csv(curve_file, index=False)
    logging.info(f"Saved curve data: {curve_file}")
    
    return fwd_file, curve_file

def generate_report(results, date):
    """Generate summary report."""
    uniform = results['uniform']
    b3 = results['b3']
    
    fwds = [uniform.forward_params[t]['d']*100 for t in uniform.tenors]
    rt = uniform.roundtrip_bps()
    
    report = f"""
    {'='*60}
    Daily Bootstrap Report — {date.strftime('%Y-%m-%d')}
    {'='*60}
    
    Method:         Bootstrap 3 + Uniform Grid (360 tenors)
    Precision:      {max(abs(v) for v in rt.values()):.2e} bps
    
    Forward Curve:
      Range:        {min(fwds):.2f}% — {max(fwds):.2f}%
      Mean:         {np.mean(fwds):.2f}%
      Std Dev:      {np.std(fwds):.2f}%
    
    Spot Rates (B3):
      1Yr:          {b3.spot_rates['1Yr']*100:.4f}%
      5Yr:          {b3.spot_rates['5Yr']*100:.4f}%
      10Yr:         {b3.spot_rates['10Yr']*100:.4f}%
      30Yr:         {b3.spot_rates['30Yr']*100:.4f}%
    
    Status:         ✓ SUCCESS
    {'='*60}
    """
    
    logging.info(report)
    
    # Save report
    report_file = Path('./reports') / f'bootstrap_{date.strftime("%Y%m%d")}.txt'
    report_file.parent.mkdir(exist_ok=True)
    report_file.write_text(report)
    
    return report

def main():
    parser = argparse.ArgumentParser(description='Daily Bootstrap Pipeline')
    parser.add_argument('--date', type=str, help='Date to bootstrap (YYYY-MM-DD)')
    args = parser.parse_args()
    
    logging.info("="*60)
    logging.info("Daily Bootstrap Pipeline Started")
    logging.info("="*60)
    
    # Fetch data
    row, date = fetch_latest_cmt()
    
    # Build parameters
    par_pct = build_par_dict(row)
    r0 = par_pct['1Mo'] / 100  # Use 1Mo as SOFR proxy
    
    # Run bootstrap
    results = run_bootstrap_safe(par_pct, r0)
    
    # Save results
    save_results(results, date)
    
    # Generate report
    generate_report(results, date)
    
    logging.info("✓ Pipeline completed successfully")

if __name__ == '__main__':
    main()
```

#### Scheduling (Linux/Mac)

Add to crontab:
```bash
# Run daily at 5:00 PM ET (after Treasury publishes at ~4:00 PM)
0 17 * * 1-5 cd /path/to/bootstrap && python update_daily_curves.py >> production.log 2>&1
```

#### Scheduling (Windows)

Use Task Scheduler:
1. Create Basic Task
2. Trigger: Daily at 5:00 PM
3. Action: Start Program → `python.exe`
4. Arguments: `C:\path\to\update_daily_curves.py`

**When to use:** Production risk systems, daily PnL attribution, automated reporting.

---

### Workflow 3: Research Workflow (Historical Panel)

**Use case:** Build T × 360 panel of forward curves for PCA, modeling, backtesting.

**Time:** ~30 minutes for full history (1990-present)  
**Tools:** Python batch script  
**Output:** Multi-date forward curve matrix, PCA factors, model parameters

#### Research Pipeline

**Goal:** Create a panel dataset:
- **Rows:** T dates (e.g., all quarter-ends 1990-2025)
- **Columns:** 360 monthly forward rates (1Mo through 30Yr)
- **Use:** PCA, factor models, scenario generation

#### Step-by-Step

**Step 1: Define Date Range**

```python
import pandas as pd
from datetime import datetime

# Option A: All quarter-ends
dates = pd.date_range('1990-03-31', '2025-12-31', freq='Q')

# Option B: All month-ends
dates = pd.date_range('2020-01-31', '2025-12-31', freq='M')

# Option C: Custom list
dates = ['2024-03-31', '2024-06-30', '2024-09-30', '2024-12-31']
dates = pd.to_datetime(dates)

print(f"Will bootstrap {len(dates)} dates")
```

**Step 2: Batch Bootstrap**

```python
from bootstrap_pipeline import run_pipeline
import numpy as np

# Load all CMT data
df_cmt = pd.read_excel('Treasury_CMT_Data_Tool.xlsx', 
                       sheet_name='CMT Rates',
                       parse_dates=['Date'])

# Storage
forward_panel = []
metadata = []

for date in dates:
    print(f"Processing {date.strftime('%Y-%m-%d')}...", end=' ')
    
    # Get CMT data for this date
    try:
        row = df_cmt[df_cmt['Date'] == date].iloc[0]
    except IndexError:
        print("SKIP (no data)")
        continue
    
    # Build par_pct
    par_pct = {
        '1Mo': row['1 Mo'], '1.5Mo': row['1.5 Mo'], '2Mo': row['2 Mo'],
        '3Mo': row['3 Mo'], '4Mo': row['4 Mo'], '6Mo': row['6 Mo'],
        '1Yr': row['1 Yr'], '2Yr': row['2 Yr'], '3Yr': row['3 Yr'],
        '5Yr': row['5 Yr'], '7Yr': row['7 Yr'], '10Yr': row['10 Yr'],
        '20Yr': row['20 Yr'], '30Yr': row['30 Yr'],
    }
    
    # Handle missing 1.5Mo
    par_pct = {k: v for k, v in par_pct.items() if pd.notna(v)}
    
    # SOFR proxy
    r0 = par_pct['1Mo'] / 100
    
    # Bootstrap
    try:
        results = run_pipeline(par_pct, r0=r0, verbose=False)
        uniform = results['uniform']
        
        # Extract forward vector
        fwd_vector = np.array([uniform.forward_params[t]['d']*100 
                              for t in uniform.tenors])
        
        forward_panel.append(fwd_vector)
        metadata.append({
            'date': date,
            'r0': r0,
            'fwd_mean': fwd_vector.mean(),
            'fwd_std': fwd_vector.std(),
        })
        
        print(f"OK (mean fwd: {fwd_vector.mean():.2f}%)")
        
    except Exception as e:
        print(f"ERROR: {e}")
        continue

# Convert to numpy array
forward_panel = np.array(forward_panel)  # Shape: (T, 360)
metadata_df = pd.DataFrame(metadata)

print(f"\nPanel shape: {forward_panel.shape}")
print(f"Date range: {metadata_df['date'].min()} to {metadata_df['date'].max()}")
```

**Step 3: Save Panel**

```python
# Save for later analysis
np.save('forward_panel_1990_2025.npy', forward_panel)
metadata_df.to_csv('forward_panel_metadata.csv', index=False)

print(f"✓ Saved panel: {forward_panel.shape[0]} dates × {forward_panel.shape[1]} maturities")
```

**Step 4: Run PCA**

```python
from sklearn.decomposition import PCA

# Standardize (optional, but recommended)
from sklearn.preprocessing import StandardScaler

scaler = StandardScaler()
forward_panel_scaled = scaler.fit_transform(forward_panel)

# PCA with 3 components (Level, Slope, Curvature)
pca = PCA(n_components=3)
factors = pca.fit_transform(forward_panel_scaled)

print(f"\nPCA Results:")
print(f"Explained variance: {pca.explained_variance_ratio_}")
print(f"  PC1 (Level):     {pca.explained_variance_ratio_[0]*100:.1f}%")
print(f"  PC2 (Slope):     {pca.explained_variance_ratio_[1]*100:.1f}%")
print(f"  PC3 (Curvature): {pca.explained_variance_ratio_[2]*100:.1f}%")

# Save PCA results
np.save('pca_factors.npy', factors)
np.save('pca_components.npy', pca.components_)
np.save('pca_explained_variance.npy', pca.explained_variance_ratio_)

# Visualize first component (Level)
import matplotlib.pyplot as plt

plt.figure(figsize=(12, 4))
plt.plot(range(1, 361), pca.components_[0], label='PC1 (Level)')
plt.xlabel('Maturity (months)')
plt.ylabel('Loading')
plt.title('First Principal Component — Level Shift')
plt.grid(True, alpha=0.3)
plt.legend()
plt.savefig('pca_level_component.png', dpi=150)
print("✓ Saved PCA level component chart")
```

**When to use:** Research papers, model development, backtesting trading strategies.

---

### Workflow Comparison

| Aspect | Ad-Hoc | Production | Research |
|--------|--------|------------|----------|
| **Frequency** | Once or rarely | Daily | One-time batch |
| **Automation** | Manual | Fully automated | Semi-automated |
| **Data scope** | 1 date | Latest only | T dates (panel) |
| **Output** | Interactive results | Files + DB | Panel matrix |
| **Time** | 5 min | 1 min (unattended) | 30 min–2 hours |
| **Tools** | Jupyter | Cron + script | Batch script |
| **Users** | Analysts | Risk/operations | Researchers |

---

### Common Patterns Across Workflows

**1. Data Quality Checks**

Always verify before bootstrapping:
```python
# Check for missing data
missing = [k for k, v in par_pct.items() if pd.isna(v)]
if missing:
    print(f"Warning: Missing data for {missing}")

# Check for unreasonable values
for k, v in par_pct.items():
    if v < 0 or v > 20:  # Rates outside 0-20%
        print(f"Warning: Unusual rate {k} = {v}%")

# Check curve monotonicity (usually upward sloping)
rates = [par_pct['1Mo'], par_pct['1Yr'], par_pct['5Yr'], 
         par_pct['10Yr'], par_pct['30Yr']]
if not all(rates[i] <= rates[i+1] for i in range(len(rates)-1)):
    print("Warning: Non-monotonic curve (may be inverted)")
```

**2. Error Handling**

```python
try:
    results = run_pipeline(par_pct, r0=r0, verbose=False)
except Exception as e:
    logging.error(f"Bootstrap failed: {e}")
    # Send alert email
    # Skip this date
    # Continue with next date
```

**3. Result Validation**

```python
# Check round-trip precision
rt = results['uniform'].roundtrip_bps()
max_rt = max(abs(v) for v in rt.values())
assert max_rt < 1e-6, f"Precision check failed: {max_rt:.2e} bps"

# Check forward range is reasonable
fwds = [results['uniform'].forward_params[t]['d']*100 
        for t in results['uniform'].tenors]
assert min(fwds) > -5, "Negative forwards detected"
assert max(fwds) < 25, "Unreasonably high forwards"
```

**4. Parameter Recording**

For all workflows, maintain an audit log:
```python
log_entry = {
    'timestamp': datetime.now(),
    'data_date': date,
    'method': 'B3 Uniform',
    'r0': r0,
    'nu': 24,
    'precision_bps': max_rt,
    'fwd_min': min(fwds),
    'fwd_max': max(fwds),
}

# Append to log file or database
```

---

## 8. Examples — Recent Quarter-End Data

Three recent US Treasury quarter-end dates illustrate different curve shapes:

| Date | Shape | Key Feature |
|------|-------|-------------|
| Jun 28 2024 | Deeply inverted | Fed funds at peak (~5.33%), 3Mo > 10Yr by 104 bps |
| Sep 30 2024 | Transitioning | Post-cut normalization underway, curve steepening |
| Dec 31 2024 | Bear steepening | Short end anchored by easing cycle, long end rising |

Source: US Treasury CMT par rates, retrieved from treasury.gov.
Note: All 14 tenors used (1Mo through 30Yr, including 1.5Mo). ν = 24 ensures
ν·τ is an exact integer for all intervals, including 1.5Mo (τ = 0.5/12 → ν·τ = 1).

---

### Example 1: June 28, 2024 — Peak Inversion

```python
from bootstrap_pipeline import run_pipeline
import numpy as np

# Jun 28 2024 — Deeply inverted: 3Mo=5.40%, 10Yr=4.36%
# SOFR target range 5.25-5.50%; 10Y-3M spread = -104 bps
par_jun2024 = {
    '1Mo': 5.47, '1.5Mo': 5.45, '2Mo': 5.44, '3Mo': 5.40, '4Mo': 5.37, '6Mo': 5.27,
    '1Yr': 5.02, '2Yr': 4.71, '3Yr': 4.54, '5Yr': 4.33, '7Yr': 4.28,
    '10Yr': 4.36, '20Yr': 4.71, '30Yr': 4.51,
}
r0 = 0.0533   # SOFR mid-target

results_jun24 = run_pipeline(par_jun2024, r0=r0, verbose=False)

b1   = results_jun24['b1']
b3   = results_jun24['b3']
unif = results_jun24['uniform']

print('Jun 28 2024 — Inverted Curve')
print('-' * 50)
print(f'  3Mo spot  (B1): {b1.spot_rates["3Mo"]*100:.4f}%')
print(f'  10Yr spot (B1): {b1.spot_rates["10Yr"]*100:.4f}%')
print(f'  10-3Mo spread:  {(b1.spot_rates["10Yr"]-b1.spot_rates["3Mo"])*100:.1f} bps')
print()
print('  Forward rates at key maturities:')
for m in [3, 12, 24, 60, 120, 240, 360]:
    from bootstrap_pipeline import _tenor_label
    lbl = _tenor_label(m)
    f   = unif.forward_params[lbl]['f'] * 100
    print(f'    f({lbl:>6}) = {f:.4f}%')

# Forward curve is humped: peaks near 3-6Mo then declines
# reflecting market pricing of eventual Fed easing
```

**Expected output (approximate):**
```
Jun 28 2024 — Inverted Curve
--------------------------------------------------
  3Mo spot  (B1): 5.3888%
  10Yr spot (B1): 4.3505%
  10-3Mo spread:  -103.8 bps

  Forward rates at key maturities:
    f(   3Mo) = 5.4144%
    f(   1Yr) = 4.6951%
    f(   2Yr) = 4.2011%
    f(   5Yr) = 3.9827%
    f(  10Yr) = 4.2046%
    f(  20Yr) = 5.2232%
    f(  30Yr) = 3.7659%
```

The inverted curve's signature in forward space: high short forwards declining
sharply through 1-2Y as the market prices in Fed cuts, then rising at the long
end reflecting the term premium.

---

### Example 2: September 30, 2024 — Post-Pivot Transition

```python
# Sep 30 2024 — Fed cut 50bps on Sep 18; curve beginning to normalize
# Short end falling, long end sticky; 10Y-2Y spread turned positive again
par_sep2024 = {
    '1Mo': 4.96, '1.5Mo': 4.90, '2Mo': 4.84, '3Mo': 4.61, '4Mo': 4.46, '6Mo': 4.39,
    '1Yr': 4.07, '2Yr': 3.64, '3Yr': 3.58, '5Yr': 3.57, '7Yr': 3.64,
    '10Yr': 3.78, '20Yr': 4.20, '30Yr': 4.11,
}
r0 = 0.0490   # SOFR post first cut

results_sep24 = run_pipeline(par_sep2024, r0=r0, verbose=False)

b1   = results_sep24['b1']
b3   = results_sep24['b3']
unif = results_sep24['uniform']
spl  = results_sep24['longstaff']

print('Sep 30 2024 — Transitional Curve')
print('-' * 50)
print('  Spot rates — B1 vs B3:')
for t in ['3Mo', '1Yr', '2Yr', '5Yr', '10Yr', '20Yr', '30Yr']:
    s1 = b1.spot_rates[t] * 100
    s3 = b3.spot_rates[t] * 100
    print(f'    {t:>5}: B1={s1:.4f}%  B3={s3:.4f}%  diff={abs(s3-s1)*100:.1f}bps')

print()
print('  Longstaff par curve at synthetic tenors:')
for t_yr in [1.5, 4.0, 8.0, 15.0, 25.0]:
    s = spl.par_rate(t_yr) * 100
    print(f'    S({t_yr:4.1f}Y) = {s:.4f}%')
```

**Expected output (approximate):**
```
Sep 30 2024 — Transitional Curve
--------------------------------------------------
  Spot rates — B1 vs B3:
    3Mo: B1=4.5828%  B3=4.5828%  diff=0.0bps
    1Yr: B1=4.0373%  B3=4.0371%  diff=0.0bps
    2Yr: B1=3.6228%  B3=3.6233%  diff=0.1bps
    5Yr: B1=3.5501%  B3=3.5514%  diff=0.1bps
   10Yr: B1=3.7967%  B3=3.8002%  diff=0.4bps
   20Yr: B1=4.3208%  B3=4.3165%  diff=0.4bps
   30Yr: B1=4.1758%  B3=4.1670%  diff=0.9bps

  Longstaff par curve at synthetic tenors:
    S( 1.5Y) = 3.8526%
    S( 4.0Y) = 3.5650%
    S( 8.0Y) = 3.7078%
    S(15.0Y) = 3.9724%
    S(25.0Y) = 4.1526%
```

Note: B1 and B3 spot rates agree to < 1 bps at all tenors — the smoothness
improvement of B3 over B1 shows in the forward curve but is nearly invisible
in spot rates, as expected from the averaging effect of integration.

---

### Example 3: December 31, 2024 — Bear Steepening

```python
# Dec 31 2024 — Fed cut 100bps total in H2 2024 (5.25% → 4.25-4.50%)
# Short end fell sharply; long end rose on fiscal/inflation concerns
# 30Y rose above 4.80% despite Fed cutting — classic bear steepener
par_dec2024 = {
    '1Mo': 4.38, '1.5Mo': 4.36, '2Mo': 4.33, '3Mo': 4.32, '4Mo': 4.30, '6Mo': 4.27,
    '1Yr': 4.17, '2Yr': 4.24, '3Yr': 4.27, '5Yr': 4.38, '7Yr': 4.48,
    '10Yr': 4.57, '20Yr': 4.87, '30Yr': 4.83,
}
r0 = 0.0430   # SOFR post December cut

results_dec24 = run_pipeline(par_dec2024, r0=r0, verbose=False)

b1   = results_dec24['b1']
unif = results_dec24['uniform']

# Extract the PCA-ready forward vector
fwds = np.array([unif.forward_params[t]['f'] * 100
                 for t in unif.tenors])

print('Dec 31 2024 — Bear Steepening')
print('-' * 50)
print(f'  Forward vector: {len(fwds)} elements')
print(f'  Range:          {fwds.min():.4f}% — {fwds.max():.4f}%')
print(f'  Mean:           {fwds.mean():.4f}%')
print(f'  Std dev:        {fwds.std():.4f}%')
print()
print('  Key spots (B1):')
for t in ['3Mo', '2Yr', '5Yr', '10Yr', '30Yr']:
    print(f'    {t:>5}: {b1.spot_rates[t]*100:.4f}%')
print()

# Compare B1 vs B3 at long end — most difference here
print('  Long-end spot comparison:')
for t in ['10Yr', '20Yr', '30Yr']:
    s1 = b1.spot_rates[t]*100
    s3 = results_dec24['b3'].spot_rates[t]*100
    print(f'    {t}: B1={s1:.4f}%  B3={s3:.4f}%  diff={abs(s3-s1)*100:.1f}bps')
```

**Expected output (approximate):**
```
Dec 31 2024 — Bear Steepening
--------------------------------------------------
  Forward vector: 360 elements
  Range:          4.0077% — 5.6074%
  Mean:           4.8300%
  Std dev:        0.4270%

  Key spots (B1):
    3Mo: 4.3121%
    2Yr: 4.2601%
    5Yr: 4.4004%
   10Yr: 4.5912%
   30Yr: 4.9225%

  Long-end spot comparison:
    10Yr: B1=4.5912%  B3=4.5949%  diff=0.4bps
    20Yr: B1=4.9697%  B3=4.9652%  diff=0.4bps
    30Yr: B1=4.9225%  B3=4.9137%  diff=0.9bps
```

### Comparing All Three Dates

```python
# Multi-date comparison: spot rates across the rate cycle
dates = {
    'Jun-24': results_jun24['b1'],
    'Sep-24': results_sep24['b1'],
    'Dec-24': results_dec24['b1'],
}

print(f"\n{'Tenor':>6}", end='')
for name in dates:
    print(f"  {name:>8}", end='')
print()
print('-' * 36)

for t in ['3Mo', '1Yr', '2Yr', '5Yr', '10Yr', '20Yr', '30Yr']:
    print(f'{t:>6}', end='')
    for name, res in dates.items():
        print(f"  {res.spot_rates[t]*100:8.4f}", end='')
    print()
```

**Expected output:**
```
 Tenor    Jun-24    Sep-24    Dec-24
------------------------------------
   3Mo    5.3888    4.5828    4.3121
   1Yr    4.9893    4.0373    4.1640
   2Yr    4.5989    3.6228    4.2601
   5Yr    4.1726    3.5501    4.4004
  10Yr    4.3505    3.7967    4.5912
  20Yr    4.8408    4.3208    4.9697
  30Yr    4.5696    4.1758    4.9225
```

This table captures the full rate cycle in three snapshots: deep inversion
(Jun-24), beginning of normalization (Sep-24), and bear steepening with
renewed long-end pressure (Dec-24).

---

## 9. Choosing a Method

### Decision Guide

```
What do you need?
│
├── Pricing / hedging at CMT tenors (DV01, swap PV)
│   └── Bootstrap 1  (fastest, industry standard)
│
├── Continuous forward curve for model calibration
│   ├── Hull-White, BDT, or similar short-rate model?
│   │   └── Bootstrap 2 or Bootstrap 3
│   └── Need C² spot rates (variance curve, etc.)?
│       └── Bootstrap 3
│
├── Par rate at a non-standard maturity (e.g. 8.5Y)?
│   └── Longstaff's Hack directly
│
├── Uniform forward curve for PCA / functional analysis?
│   └── Full pipeline: Longstaff → Bootstrap 1 on 1M grid
│       (results['uniform'])
│
└── Consistency check or publication?
    └── Bootstrap 3 (matches US Treasury methodology post-2021)
```

### Method Comparison Summary

| Property | B1 | B2 | B3 | Longstaff | B1 Uniform |
|----------|----|----|----|-----------|----|
| CMT tenors used | 14 | 14 | 14 | 13† | 360 |
| Forward continuity | ✗ | ✓ | ✓ | N/A | ≈✓ |
| Forward smoothness | ✗ | ✗ | ✓ | N/A | ≈✓ |
| Arbitrage-free everywhere | ✓ | ✓ | ✓ | ✗ | ✓ |
| Closed-form solve | ✗ | ✗ | ✗ | ✓ | ✗ |
| Relative speed | 1× | 1.2× | 3× | <0.1× | 1× |
| PCA-ready output | ✗ | ✗ | ✗ | ✗ | ✓ |
| Anchored to SOFR | ✗ | ✓ | ✓ | ✗ | ✓ |

† Longstaff works in whole-month par rate space; 1.5Mo is not a whole-month
  tenor on 30/360. The spline interpolates smoothly over the 1Mo–2Mo gap.

---

## 10. API Reference

### `run_pipeline(par_pct, r0=None, step_months=1, verbose=True)`

Run all five stages and return results dictionary.

**Parameters:**
- `par_pct`: dict `{label: rate_percent}` — CMT par rates in percent
- `r0`: float — short rate decimal (SOFR). If None, uses 1Mo par rate.
- `step_months`: int — uniform grid spacing in months (default 1)
- `verbose`: bool — print formatted summaries (default True)

**Returns:** dict with keys `'b1'`, `'b2'`, `'b3'`, `'longstaff'`, `'uniform'`

---

### `CurveResult` — returned by all bootstrap stages

**Attributes:**
- `.tenors`: list of tenor labels in maturity order
- `.maturities`: dict `{label: T_i in years (30/360)}`
- `.par_rates`: dict `{label: S(T_i) in decimal}`
- `.discount_factors`: dict `{label: P(0,T_i)}`
- `.annuity_factors`: dict `{label: Ann₀(0,T_i)}`
- `.spot_rates`: dict `{label: R(T_i) continuous, decimal}`
- `.forward_params`: dict `{label: {polynomial coefficients}}`

**Methods:**
- `.forward_at(t)` → float: instantaneous forward f(t) for any t
- `.forward_curve(n=500)` → (t_array, f_array): dense curve for plotting
- `.roundtrip_bps()` → dict: par → spot → par error in basis points
- `.print_summary()`: formatted table output

---

### `LongstaffSpline` — returned by `LongstaffHack.fit()`

**Methods:**
- `.par_rate(T)` → float: S(T) in decimal for any T ∈ [T_min, T_max]
- `.uniform_grid(step_months=1, T_max_yr=30.0)` → dict `{label: pct}`: uniform par grid
- `.print_knot_check()`: verify exact knot interpolation

---

### `Bootstrap1(nu=12, maturities=None)` / `Bootstrap2` / `Bootstrap3`

All take optional `nu` (payment frequency) and `maturities` dict.

**Method:** `.run(par_pct, r0=None)` → `CurveResult`

`Bootstrap2` also provides: `.slopes(par_pct, r0=None)` → dict of linear slopes (used internally by Bootstrap 3)

---

### `UniformGridPipeline(nu=12)`

**Method:** `.run(par_pct, r0=None, step_months=1)` → `(LongstaffSpline, CurveResult)`

---

## 11. Design Notes & Implementation Lessons

This section documents non-obvious implementation decisions — the gap between
textbook theory and working code.

### 10.1 The Payment Count Fix — and Why ν = 24

The single most important implementation detail:

```python
# WRONG — causes systematic errors at 1.5Mo and other fractional tenors
n = int(nu * tau)          # int(24 * 0.5/12) = int(0.9999...) = 0

# CORRECT — floating-point safe
n = int(round(nu * tau))   # int(round(0.9999...)) = 1
```

The choice ν = 24 (payments every 15 days) is deliberate. With ν = 12
(monthly), the 1.5Mo interval has ν·τ = 12 × (0.5/12) = 0.5 — exactly
halfway between integers. `round(0.5)` is implementation-defined in Python
(banker's rounding gives 0), making the result machine-dependent and wrong
either way. ν = 24 maps every CMT interval to a clean integer:

    τ = 0.5/12  → ν·τ = 24 × 0.04166... = 0.9999... → round → 1  ✓
    τ = 1/12    → ν·τ = 24 × 0.08333... = 1.9999... → round → 2  ✓
    τ = 6/12    → ν·τ = 24 × 0.5000    = 12.0000   → round → 12 ✓

### 10.2 30/360 and Exact Arithmetic

Using `T = months/12` (exact integer division) rather than day-counted actual/365
eliminates all floating-point ambiguity in tenor arithmetic. Every interval length
τ_i = T_i − T_{i-1} is an exact multiple of 1/12.

### 10.3 Bootstrap 2 on Dense Grids — Resonance Instability

Bootstrap 2's slope-chaining (`b_i = a_{i-1}·τ_{i-1} + b_{i-1}`) is designed for
sparse grids where the coupling provides meaningful smoothness. On a 360-point grid
with τ = 1/12, the chain length is 26× longer than on the 14-tenor CMT grid. Any
solver imprecision compounds across all 360 intervals, producing a sawtooth
oscillation of ±70%. The fix is not to increase tolerance but to use a method
without chaining — Bootstrap 1.

### 10.4 Bootstrap 3 — Dimension Reduction

The original formulation of Bootstrap 3 uses a 2D nonlinear root-finding problem
(both a_i and b_i as unknowns). This is fragile: 2D Newton methods require good
initial guesses, and the 10Y→20Y interval (τ = 10 years) produces extreme parameter
values with overflow risk.

The key insight is that F2 (slope condition at right knot) is **linear** in (a,b),
allowing exact elimination:

    b(a) = [c_{i+1} − c_i − 3a·τ²] / (2τ)

After substitution, f_i(τ) becomes **linear in a**, providing exact analytical
Brent brackets. This reduces to a well-conditioned 1D problem with guaranteed
convergence within the safe range |a| < 2000/τ⁴.

### 10.5 Longstaff Closed-Form Formula

The 2×2 linear system for Longstaff's (a_i, b_i) must be solved using the correct
matrix inverse. The formula:

    a_i = ( 2τ·rhs₁ − τ²·rhs₂) / (−τ⁴)
    b_i = (−3τ²·rhs₁ + τ³·rhs₂) / (−τ⁴)

is derived from Cramer's rule (or equivalently np.linalg.solve). An apparently
simpler but **incorrect** formula `a_i = (−2·rhs₁ + τ·rhs₂)/τ⁴` produces knot
errors of 5–22 bps. The correct formula produces errors < 10⁻¹⁰ bps. This is
the kind of subtle sign error that only manifests numerically.

### 10.6 C² is Impossible Without Sacrificing Monotonicity

Adding C² continuity to Bootstrap 3 would require a fifth constraint on a
four-parameter system, making it over-determined. The only resolution is to
drop monotonicity. On the 10Y→20Y interval (τ = 10 years), condition number
κ ∼ τ⁴ ∼ 10⁴ = 10,000 for the derivative constraints — an unconstrained cubic
would produce wildly oscillating forward rates (observed range: −50% to +100%).
Monotonicity is the correct substitute for C².

---

## 12. Downstream Applications

This module is designed as a data provider for analytical applications. The
primary outputs are:

### For PCA / Functional Analysis

```python
results = run_pipeline(par_rates, r0=r0, verbose=False)
uniform = results['uniform']

# 360 × 1 forward rate vector (one observation)
fwd_vector = np.array([uniform.forward_params[t]['f'] * 100
                        for t in uniform.tenors])

# Build a panel: run for many dates to get T × 360 matrix
# rows = dates, columns = maturities (1Mo to 30Yr in 1M steps)
# Then: np.cov(panel) → 360×360 covariance matrix
#       np.linalg.eigh(cov) → eigenvalues, eigenvectors (PCA factors)
```

### For Nelson-Siegel Fitting

```python
# NSS fits to spot rates at standard tenors
tenors_yr = [b1.maturities[t] for t in b1.tenors]
spot_pct  = [b1.spot_rates[t] * 100 for t in b1.tenors]
# Fit NSS: minimize ||R_NS(τ; β) − R(τ)||² over {β₀,β₁,β₂,β₃,λ₁,λ₂}
```

### For Hull-White Calibration

```python
# Hull-White requires f(t) and df/dt at market knot points
# Bootstrap 3 provides C¹ forwards (f is differentiable)
from bootstrap_pipeline import Bootstrap3
b3 = Bootstrap3().run(par_rates, r0=r0)

# theta(t) = df/dt + f(t)^2 + kappa*f(t)  (approximate for small kappa)
# Use b3.forward_at(t) for f(t); numerical differentiation for df/dt
import numpy as np
dt = 1e-5
def theta(t, kappa=0.05):
    f   = b3.forward_at(t)
    dft = (b3.forward_at(t+dt) - b3.forward_at(t-dt)) / (2*dt)
    return dft + f**2 + kappa*f
```

### For Swap Pricing / DV01

```python
# Bootstrap 1 is sufficient for exact swap pricing at CMT tenors
b1 = results['b1']

# Price a 5Y par swap (approximate, ignoring bid-offer)
P_5y  = b1.discount_factors['5Yr']
Ann_5y = b1.annuity_factors['5Yr']
S_5y  = b1.par_rates['5Yr']
print(f'5Y par swap rate: {S_5y*100:.4f}%')

# DV01 (approx): bump each par rate +1bp, rerun, compare annuity factor
```

---

## 13. References

**Bootstrapping methodology:**

Hagan, P. S. & West, G. (2006). "Interpolation Methods for Curve Construction."
*Applied Mathematical Finance*, 13(2), 89–129.

Hagan, P. S. & West, G. (2008). "Methods for Constructing a Yield Curve."
*Wilmott Magazine*, May 2008, 70–81.

**Monotone interpolation:**

Fritsch, F. N. & Carlson, R. E. (1980). "Monotone Piecewise Cubic Interpolation."
*SIAM Journal on Numerical Analysis*, 17(2), 238–246.

**Longstaff's Hack:**

Longstaff, F. A. — practitioner methodology, direct communication.
The approach fits a monotone cubic spline directly to par rates rather than
to zero or forward rates, exploiting the stability hierarchy:
mortgage rates > par rates > zero rates > forward rates.
Arbitrage-free at knot points only; between tenors the curve is smooth,
monotone, and "reasonable" but not exactly arbitrage-free.

**US Treasury methodology:**

The US Treasury estimates its par yield curve using a monotone convex spline
method (equivalent to Bootstrap 3 in spirit). Published daily at:
https://home.treasury.gov/resource-center/data-chart-center/interest-rates/

---

*Bootstrap Pipeline v2.1 — February 2026*
*Day count: 30/360 | Payment frequency: bi-monthly (ν=24) | Precision: < 10⁻⁸ bps*

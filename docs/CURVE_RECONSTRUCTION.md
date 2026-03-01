# Mathematical Curve Reconstruction

This document explains the mathematical principles behind reconstructing continuous yield curves from bootstrap parameters.

## The Problem

Bootstrap algorithms output parameters at **discrete tenor points** (1Mo, 3Mo, 1Yr, etc.). However, the true yield curve is a **continuous function** of maturity.

**Common mistake:** Connect tenor points with straight lines (linear interpolation)

**Correct approach:** Reconstruct the continuous function using the bootstrap parameters

## Why Linear Interpolation is Wrong

### Example: Discount Factors

The discount factor P(T) represents the present value of $1 received at time T.

**Truth:** P(T) = exp(-∫₀ᵀ f(s) ds) where f(s) is the instantaneous forward rate

This is an **exponential decay**, not a straight line!

**Linear interpolation error:**
- Between 1Yr (P=0.96) and 2Yr (P=0.93)
- Linear: P(1.5Yr) = 0.945
- True: P(1.5Yr) = exp(...) ≈ 0.944

The error compounds at longer maturities and for derivatives pricing.

### Example: Forward Rates

**Scheme 1 (Piecewise Constant):**
- Truth: f(t) is constant within each interval, then jumps
- Linear interpolation: Incorrectly smooths the jumps

**Scheme 3 (Monotone Cubic):**
- Truth: f(t) = a×t³ + b×t² + c×t + d (smooth cubic)
- Linear interpolation: Replaces smooth curve with kinked segments

## Bootstrap Schemes

Each scheme defines a different forward rate structure.

### Scheme 1: Piecewise Constant

**Forward rate function:**
```
f(t) = f_i    for T_{i-1} ≤ t < T_i
```

**Discount factor:**
```
P(T_i) = P(T_{i-1}) × exp(-f_i × ΔT_i)

where ΔT_i = T_i - T_{i-1}
```

**Continuous reconstruction:**

For any t in [T_{i-1}, T_i]:

```python
integral = Σ(f_j × ΔT_j) + f_i × (t - T_{i-1})
P(t) = exp(-integral)
z(t) = -log(P(t)) / t
```

**Properties:**
- Simplest scheme
- Forward rate has discontinuities (jumps) at tenor boundaries
- Discount curve is piecewise exponential (continuous, but kinked)
- Spot curve is smooth despite kinked discounts

**Use case:** Quick calculations, when smoothness isn't critical

### Scheme 2: Piecewise Linear

**Forward rate function:**
```
f(t) = a_i × (t - T_{i-1}) + b_i    for T_{i-1} ≤ t < T_i
```

where a_i is the slope and b_i is chosen to maintain continuity:
```
b_i = f_{i-1}(T_{i-1})  (forward at previous endpoint)
```

**Discount factor:**

Integral of piecewise linear function:
```
∫(a×t + b)dt = ½a×t² + b×t + C
```

For interval [T_{i-1}, T_i]:
```
P(T_i) = P(T_{i-1}) × exp(-½a_i×ΔT_i² - b_i×ΔT_i)
```

**Continuous reconstruction:**

For any t in [T_{i-1}, T_i]:

```python
dt = t - T_{i-1}
integral_prev = Σ(previous intervals)
integral_current = ½a_i×dt² + b_i×dt
P(t) = exp(-(integral_prev + integral_current))
z(t) = -log(P(t)) / t
```

**Properties:**
- Forward rate is continuous with linear segments
- Discount curve is smooth (no kinks)
- Good balance of accuracy and efficiency
- **Recommended for most use cases**

**Use case:** Production systems, derivatives pricing, risk management

### Scheme 3: Monotone Cubic

**Forward rate function:**
```
f(t) = a_i×t³ + b_i×t² + c_i×t + d_i    for T_{i-1} ≤ t < T_i

where t is measured from T_{i-1}
```

Parameters chosen to ensure:
1. Continuity: f(T_i⁻) = f(T_i⁺)
2. Monotonicity: f'(t) has consistent sign (no oscillation)
3. Match par rates: Discount factors produce correct par rates

**Discount factor:**

Integral of cubic polynomial:
```
∫(a×t³ + b×t² + c×t + d)dt = ¼a×t⁴ + ⅓b×t³ + ½c×t² + d×t + C
```

**Continuous reconstruction:**

For any t in [T_{i-1}, T_i]:

```python
dt = t - T_{i-1}
f_t = a_i×dt³ + b_i×dt² + c_i×dt + d_i
integral = ¼a_i×dt⁴ + ⅓b_i×dt³ + ½c_i×dt² + d_i×dt
P(t) = P(T_{i-1}) × exp(-integral)
z(t) = -log(P(t)) / t
```

**Properties:**
- Smoothest possible curves (C¹ continuous)
- No artificial kinks or oscillations
- Most realistic for market-implied forward path
- Computationally intensive

**Use case:** Derivatives pricing, scenario analysis, regulatory reporting

## Numerical Integration

To compute P(t) from f(t), we need: ∫₀ᵀ f(s) ds

We use the **trapezoidal rule** for numerical stability:

```python
# Create dense grid
t = [0, 0.01, 0.02, ..., T_max]

# Evaluate forward at each point
f = [f(t_i) for t_i in t]

# Trapezoidal integration
dt = diff(t)
f_avg = (f[:-1] + f[1:]) / 2
integral = cumsum(f_avg × dt)

# Discount factors
P = exp(-integral)
```

**Accuracy:** Error ~ O(Δt²)

With 1000 points over 30 years:
- Δt ≈ 0.03 years
- Error ~ 10⁻¹⁰ (negligible)

## Spot Rate Calculation

From discount factors, compute spot (zero) rates:

```
z(T) = -log(P(T)) / T    for T > 0
```

**Special case at T = 0:**

Direct computation gives 0/0 (indeterminate).

Use L'Hôpital's rule:
```
lim(T→0) z(T) = lim(T→0) -log(P(T)) / T
              = lim(T→0) -P'(T)/(P(T)×1)
              = lim(T→0) f(T)
              = f(0) = r₀
```

**Implementation:**
```python
z[0] = f[0]  # short rate
z[t > 0] = -log(P[t]) / t
```

This ensures smooth curves starting from the short rate anchor.

## Implementation Algorithm

### Step 1: Extract Bootstrap Parameters

```python
if scheme == 'S1':
    params = npz['s1_f'][date_idx]  # Constant forwards
elif scheme == 'S2':
    a = npz['s2_a'][date_idx]  # Linear slopes
    b = npz['s2_b'][date_idx]  # Intercepts
elif scheme == 'S3':
    a = npz['s3_a'][date_idx]  # Cubic coefficients
    b = npz['s3_b'][date_idx]
    c = npz['s3_c'][date_idx]
    d = npz['s3_d'][date_idx]
```

### Step 2: Create Dense Evaluation Grid

```python
T_max = max_tenor × 1.02  # Extend slightly
t_dense = linspace(0, T_max, 1000)
```

### Step 3: Reconstruct Forward Curve

```python
f_dense = zeros(1000)

for i, interval in enumerate(tenor_intervals):
    T_start, T_end = interval
    mask = (t_dense >= T_start) & (t_dense < T_end)
    dt = t_dense[mask] - T_start
    
    if scheme == 'S1':
        f_dense[mask] = params[i]
    elif scheme == 'S2':
        f_dense[mask] = a[i]×dt + b[i]
    elif scheme == 'S3':
        f_dense[mask] = a[i]×dt³ + b[i]×dt² + c[i]×dt + d[i]
```

### Step 4: Integrate to Discount Factors

```python
# Trapezoidal rule
dt = diff(t_dense)
f_avg = (f_dense[:-1] + f_dense[1:]) / 2
integral = zeros(len(t_dense))
integral[1:] = cumsum(f_avg × dt)

# Discount factors
P_dense = exp(-integral)
```

### Step 5: Compute Spot Rates

```python
z_dense = zeros(len(t_dense))
z_dense[0] = f_dense[0]  # r₀
mask = t_dense > 1e-6
z_dense[mask] = -log(P_dense[mask]) / t_dense[mask]
```

### Step 6: Plot Smooth Curves

```python
plot(t_dense, f_dense, label='Forward (smooth)')
plot(t_dense, P_dense, label='Discount (smooth)')
plot(t_dense, z_dense, label='Spot (smooth)')

# Overlay tenor points
scatter(T_nodes, f_nodes, marker='o')
```

## Validation

To verify reconstruction accuracy:

### Test 1: Par Rate Recovery

Bootstrap ensures P(T_i) produces correct par rates.

Check that using reconstructed P(t) also produces correct par rates:

```python
for i, T_i in enumerate(tenors):
    # Compute par rate from reconstructed P(t)
    P_i = P_dense[t_dense ≈ T_i]
    A_i = annuity_sum(P_dense, T_i)
    par_implied = (1 - P_i) / A_i
    
    assert |par_implied - par_input[i]| < 1e-10
```

### Test 2: Continuity

Check that curves are smooth:

```python
# Forward continuity (S2 and S3 only)
assert max(|diff(f_dense)|) < threshold

# Discount smoothness
assert max(|diff(diff(log(P_dense)))|) < threshold
```

### Test 3: Monotonicity

For normal yield curves:

```python
# Forward should be mostly increasing
assert sum(diff(f_dense) < 0) / len(f_dense) < 0.1

# Discount should be strictly decreasing
assert all(diff(P_dense) < 0)
```

## Comparison to Other Methods

### Nelson-Siegel

Parametric model: z(T) = β₀ + β₁×((1-e^(-λT))/(λT)) + β₂×((1-e^(-λT))/(λT) - e^(-λT))

**Pros:** Smooth, few parameters  
**Cons:** Not arbitrage-free, doesn't match all par rates exactly

### Spline Methods (Cubic B-splines)

Fit smooth functions directly to spot or forward rates.

**Pros:** Very smooth  
**Cons:** Complex, may not match par rates exactly, requires careful knot selection

### Our Bootstrap Approach

Directly inverts par rates to discount factors, then reconstructs.

**Pros:** Exact (matches all par rates), arbitrage-free, choice of smoothness (S1/S2/S3)  
**Cons:** Requires numerical integration

## Further Reading

- Hagan & West (2006): "Methods for Constructing a Yield Curve"
- Cairns (2004): "Interest Rate Models: An Introduction"
- Hull (2017): "Options, Futures, and Other Derivatives" (Chapter 4)

## Code Reference

- `curve_reconstruction.py`: Implementation
- `cmt_bootstrap.py`: Bootstrap algorithms that generate parameters
- `yield_curve_app_v2.py`: Visualization using reconstruction

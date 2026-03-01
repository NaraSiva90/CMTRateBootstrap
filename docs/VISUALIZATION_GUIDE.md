# Visualization Guide

Interactive exploration of Treasury yield curves using Plotly and Streamlit.

## Quick Start

```bash
# Install dependencies
pip install plotly streamlit

# Run the app
python -m streamlit run scripts/yield_curve_app_v2.py
```

The app will open in your browser at `http://localhost:8501`

## Features

### 1. Mathematical Curve Reconstruction

Unlike typical financial charting tools that use linear interpolation, this visualizer reconstructs the **true mathematical curves** from bootstrap parameters.

#### How It Works

**Scheme 1 (Piecewise Constant):**
- Forward: f(t) = constant within each interval
- Discount: P(t) = exp(-f_i × Δt)
- Result: Step-function forwards, kinked discounts

**Scheme 2 (Piecewise Linear):**
- Forward: f(t) = a_i × t + b_i
- Discount: P(t) = exp(-∫(a×t + b)dt) = exp(-½a×t² - b×t)
- Result: Linear segment forwards, smooth exponential discounts

**Scheme 3 (Monotone Cubic):**
- Forward: f(t) = a×t³ + b×t² + c×t + d
- Discount: P(t) = exp(-∫cubic dt)
- Result: Perfectly smooth curves everywhere

The spot rate is then derived: z(t) = -log(P(t))/t

**Why This Matters:**

Plotting only tenor endpoint values and connecting with straight lines (typical approach) misrepresents the actual curve shape. Our reconstruction shows the true continuous function.

### 2. Interactive Controls

**Date Selection:**
- **Calendar picker**: Jump to specific dates
- **Slider**: Browse chronologically
- Auto-finds closest available date

**Curve Toggles:**
- Show/hide par rates
- Show/hide spot rates
- Show/hide forward rates
- Mix and match for comparison

**View Options:**
- Main yield curves
- Discount factor curves
- Spot-par spread (basis points)
- Time series for any tenor

### 3. Data Export

**CSV Download:**
- Complete data table
- All rates and discount factors
- Formatted for Excel

**Chart Export:**
- PNG/SVG via Plotly toolbar
- Copy to clipboard
- Save as HTML (interactive)

## Usage Examples

### Example 1: Compare Bootstrap Schemes

1. Load `Treasury_CMT_Data_Tool_curves_S1_*.npz`
2. Note the step-function forward curve
3. Load `Treasury_CMT_Data_Tool_curves_S3_*.npz`
4. See the smooth cubic forward curve

**Observation:** S3 provides superior smoothness for derivatives pricing.

### Example 2: Track Yield Curve Inversion

1. Select **10Yr** tenor
2. Choose **spot** rate
3. Observe time series through 2022-2023
4. Note inversion periods (short > long rates)

### Example 3: Analyze Term Premium

1. Select a date
2. View **Spot-Par Spread** chart
3. Positive spread = term premium (longer maturities)
4. Negative spread = inversion (unusual)

### Example 4: Examine Forward Rate Path

1. Select **Scheme 2** or **Scheme 3** data
2. Toggle on **Forward Rates** only
3. Observe the forward rate path
4. Compare to market expectations (Fed policy)

## Technical Details

### Curve Reconstruction Algorithm

The `curve_reconstruction.py` module:

1. **Loads bootstrap parameters** from NPZ file
   - S1: f_i (constant forward per interval)
   - S2: a_i, b_i (linear coefficients)
   - S3: a, b, c, d (cubic coefficients)

2. **Creates dense time grid** (default: 1000 points)
   - Spans from 0 to max tenor
   - Smooth evaluation everywhere

3. **Evaluates forward function** f(t) at each point
   - S1: Lookup constant for interval
   - S2: Compute a×t + b
   - S3: Compute a×t³ + b×t² + c×t + d

4. **Integrates to discount** using trapezoidal rule
   - ∫₀ᵀ f(s) ds ≈ Σ f_avg × Δt
   - P(t) = exp(-integral)

5. **Derives spot rate**
   - z(t) = -log(P(t))/t for t > 0
   - z(0) = f(0) (L'Hôpital's rule)

### Performance

- **Curve reconstruction:** ~10ms per date
- **Caching:** Streamlit caches NPZ data
- **Rendering:** Plotly handles 1000+ points smoothly

### Limitations

- **NPZ file size:** Large files (>100MB) may be slow to load
- **Browser memory:** 10,000+ points may lag in browser
- **Numerical integration:** Trapezoidal rule (accurate to ~1e-10)

## Troubleshooting

### App won't start

**Problem:** `streamlit: command not found`

**Solution:**
```bash
python -m streamlit run scripts/yield_curve_app_v2.py
```

### Curves look wrong

**Problem:** Curves show as straight lines

**Solution:** Ensure you're using `yield_curve_app_v2.py` (not the old version)

### Missing dates

**Problem:** Date picker shows dates but no data

**Solution:** The NPZ file may not have that date. Use the slider to find available dates.

### Slow performance

**Problem:** App is laggy

**Solutions:**
- Reduce `num_points` in curve reconstruction (default: 1000)
- Use smaller NPZ files (filter date range when running bootstrap)
- Close other browser tabs

## Advanced: Customization

### Change Number of Evaluation Points

Edit `curve_reconstruction.py`:

```python
# Default
curves = reconstruct_curves(data, date_idx, num_points=1000)

# Higher resolution (slower)
curves = reconstruct_curves(data, date_idx, num_points=5000)

# Faster (less smooth)
curves = reconstruct_curves(data, date_idx, num_points=500)
```

### Customize Colors

Edit `yield_curve_app_v2.py`:

```python
# Change spot rate color from purple to blue
line=dict(color='#2E86AB', ...)  # Instead of '#A23B72'
```

### Add Custom Charts

The framework makes it easy to add new visualizations:

```python
def plot_my_custom_view(data, date_idx):
    curves = reconstruct_curves(data, date_idx)
    
    fig = go.Figure()
    # Your custom Plotly code here
    
    return fig
```

Then add to the main app.

## FAQ

**Q: Why does S1 show kinked discount curves?**

A: S1 uses piecewise constant forwards, which create discontinuities at tenor boundaries. This is mathematically correct for that scheme.

**Q: Can I export to Excel?**

A: Yes, use the CSV download button. The data table includes all rates and can be opened in Excel.

**Q: How do I compare two dates?**

A: Currently not supported in the UI. You can screenshot two dates and compare manually, or modify the code to add multi-date overlays.

**Q: What's the difference between par and spot rates?**

A: Par rates (blue) are the input CMT rates from Treasury. Spot rates (purple) are zero-coupon rates derived from bootstrap. The spread between them represents the term structure.

**Q: Why start from zero on the x-axis?**

A: The curves are defined from t=0 (today) to max maturity. The first tenor (1Mo) is at ~0.083 years.

## Further Reading

- `CURVE_RECONSTRUCTION.md` - Mathematical derivation
- `BOOTSTRAP_GUIDE.md` - Bootstrap methodology
- Plotly documentation: https://plotly.com/python/
- Streamlit documentation: https://docs.streamlit.io/

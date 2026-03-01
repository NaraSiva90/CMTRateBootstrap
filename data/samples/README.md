# Sample Data Files

Pre-bootstrapped Treasury CMT yield curves (January 2022 - February 2026)

## Files

- **Treasury_CMT_curves_S1_2022_2026.npz** - Piecewise constant forwards (see step functions)
- **Treasury_CMT_curves_S2_2022_2026.npz** - Piecewise linear forwards (recommended)
- **Treasury_CMT_curves_S3_2022_2026.npz** - Monotone cubic forwards (smoothest curves)

## Usage

These files work directly with the visualization app:
```bash
python -m streamlit run scripts/yield_curve_app.py
```

The app will auto-detect these files. Select from the dropdown in the sidebar.

## What's Inside

Each file contains ~1,028 trading days with:
- Par rates (Treasury CMT input)
- Spot rates (zero-coupon)
- Discount factors
- Forward rates
- Bootstrap parameters
- Short rate (EFFR/SOFR)

## Key Dates to Explore

- **2022-03-17:** Fed begins hiking (0.25% → 0.50%)
- **2023-03-22:** Banking crisis (SVB collapse)
- **2024-09-18:** Fed begins cutting (-50bp)
- **2026-02-27:** Recent data

## Generate Your Own

To bootstrap your own data:
```bash
# Download CMT data from Treasury
python scripts/build_initial_treasury_file.py --start-date 2020-01-01

# Run bootstrap
python src/cmt_bootstrap.py --scheme 2 --write-npz
```

See main [README](../../README.md) for complete instructions.
# Sample Data Files

Pre-bootstrapped Treasury CMT yield curves.

## Files

- **Treasury_CMT_Data_Tool_curves_S1_2022-2026.npz** - Piecewise constant forwards, Jan 2022 - Feb 2026 (see step functions)
- **Treasury_CMT_Data_Tool_curves_S2_2022-2026.npz** - Piecewise linear forwards, Jan 2022 - Feb 2026 (recommended)
- **Treasury_CMT_Data_Tool_curves_S3_2022-2026.npz** - Monotone cubic forwards, Jan 2022 - Feb 2026 (smoothest curves)
- **Treasury_CMT_Data_Tool_curves_S1_1990-2026.npz** - Piecewise constant forwards, full history Jan 1990 - Jul 2026 (use for [vol_analysis_app.py](../../scripts/vol_analysis_app.py) — the long history gives the PCA and tail fits far more observations than the 2022-2026 sample)

## Usage

The 2022-2026 files work directly with the yield curve visualization app:
```bash
python -m streamlit run scripts/yield_curve_app.py
```

The app will auto-detect these files. Select from the dropdown in the sidebar.

The 1990-2026 S1 file is for the volatility analysis app instead:
```bash
python -m streamlit run scripts/vol_analysis_app.py
```

This app does **not** auto-detect files — click 📂 in the sidebar or paste the path directly, e.g. `data/samples/Treasury_CMT_Data_Tool_curves_S1_1990-2026.npz`.

## What's Inside

The 2022-2026 files each contain ~1,028 trading days; the 1990-2026 file contains ~9,139. Each contains:
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

# Run bootstrap (--scheme 1 for the vol analysis app, --scheme 2/3 for yield curves)
python scripts/run_bootstrap.py --scheme 1
```

See main [README](../../README.md) for complete instructions.
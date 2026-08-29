# User Guide

## Inputs

### CMT workbook
Workbook must include a sheet named **`CMT Rates`** with:
- Column A: `Date`
- Remaining columns: tenor labels (`1 Mo`, `1.5 Mo`, ..., `30 Yr`)
Rates may be percent (4.25) or decimals (0.0425).

### Short-rate history (preferred)
Preferred input file used by the bootstrap:
- `data/short_rates/short_rate_combined.csv` (Date, Rate, Source)

This is created by:
- `scripts/update_short_rates.py`

If `short_rate_combined.csv` is missing, the bootstrap falls back to:
- `data/short_rates/fed_funds_1954_2018.csv`
- `data/short_rates/sofr_2018_present.csv` (optional)

**Keeping it current:** Schemes 2/3 anchor to `r0` from this file (§3.2/§3.3 of
[BOOTSTRAP_GUIDE.md](BOOTSTRAP_GUIDE.md)); Scheme 1 doesn't use `r0` at all. Fed Funds
(1954–2018) never needs re-fetching — it's a closed historical range — but SOFR
(2018–present) does, so `scripts/update_short_rates.py` needs to run alongside
`scripts/update_treasury_cmt.py`, not instead of it. `scripts/update_all_data.py` runs
both plus the bootstrap in one command. If the combined file goes stale anyway,
`cmt_bootstrap.py` prints a `WARNING` rather than failing silently (see
`--short-rate-staleness-days` in [BOOTSTRAP_GUIDE.md §8](BOOTSTRAP_GUIDE.md#8-api-reference)).

## Run bootstrap

```bash
python src/cmt_bootstrap.py --workbook Treasury_CMT_Data_Tool.xlsx --scheme 1
python src/cmt_bootstrap.py --workbook Treasury_CMT_Data_Tool.xlsx --scheme 2
python src/cmt_bootstrap.py --workbook Treasury_CMT_Data_Tool.xlsx --scheme 3
```

Optional Excel output:
```bash
python src/cmt_bootstrap.py --workbook Treasury_CMT_Data_Tool.xlsx --scheme 3 --write-excel
```

## Outputs

### NPZ panel (Option A)
Single NPZ covering all dates:

- axes: dates, tenor_labels, tenor_years
- inputs: par_rates_input, r0, r0_source
- tenor-node outputs: discount_factors_T, spot_rates_cc_T, forward_endpoint_T
- parameters:
  - S1: s1_f
  - S2: s2_a, s2_b
  - S3: s3_a, s3_b, s3_c, s3_d, s3_c_target_next
- validation:
  - par_rates_implied
  - par_rate_err_bp, maxabs/rms per date
- diagnostics: status_code, log_messages, tenor_used_mask

# Data Directory

## Required Files (Download)

### Treasury Historical Data
Download from: https://home.treasury.gov/resource-center/data-chart-center/interest-rates/TextView?type=daily_treasury_yield_curve

Save as: `par-yield-curve-rates-1990-2023.csv`

## Included Files

- `short_rates/fed_funds_1954_2018.csv` - FRED DFF series
- `short_rates/sofr_manual.csv` - SOFR baseline

## Generated Files (Not in Git)

These are created by scripts:
- `Treasury_CMT_Data_Tool.xlsx` - Main data file
- `short_rates/short_rate_combined.csv` - Combined short rate history
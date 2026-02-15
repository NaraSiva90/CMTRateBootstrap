"""
Short Rate Updater
==================

Manages combined Fed Funds (1954-2018) + SOFR (2018-present) history.

One-time setup:
    1. Download Fed Funds from FRED: https://fred.stlouisfed.org/series/DFF
    2. Save as data/short_rates/fed_funds_1954_2018.csv
    3. Run: python update_short_rates.py --init

Regular updates:
    python update_short_rates.py
"""

import pandas as pd
import requests
from pathlib import Path
from datetime import datetime, timedelta
import argparse

# Paths
SHORT_RATE_DIR = Path('data/short_rates')
SHORT_RATE_DIR.mkdir(parents=True, exist_ok=True)

FED_FUNDS_FILE = SHORT_RATE_DIR / 'fed_funds_1954_2018.csv'
SOFR_FILE = SHORT_RATE_DIR / 'sofr_2018_present.csv'
COMBINED_FILE = SHORT_RATE_DIR / 'short_rate_combined.csv'

# Date boundaries
SOFR_START_DATE = '2018-04-03'  # First SOFR publication
FED_FUNDS_END_DATE = '2018-04-02'  # Last day before SOFR


def fetch_sofr_from_nyfed(start_date='2018-04-03'):
    """Fetch SOFR history from NY Fed API."""
    
    # NY Fed API has a limit on 'last' endpoint, use search with date range instead
    end_date = datetime.now().strftime('%Y-%m-%d')
    
    # Try the search endpoint first
    url = "https://markets.newyorkfed.org/api/rates/secured/sofr/search.json"
    params = {
        'startDate': start_date,
        'endDate': end_date
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        
        if 'refRates' not in data or len(data['refRates']) == 0:
            print("  No SOFR data returned from API")
            return None
        
        sofr_df = pd.DataFrame(data['refRates'])
        sofr_df['Date'] = pd.to_datetime(sofr_df['effectiveDate'])
        sofr_df['Rate'] = sofr_df['percentRate'].astype(float)
        sofr_df['Source'] = 'SOFR'
        sofr_df = sofr_df[['Date', 'Rate', 'Source']].sort_values('Date')
        
        return sofr_df
        
    except requests.exceptions.HTTPError as e:
        print(f"Error fetching SOFR from NY Fed API: {e}")
        
        # Fallback: try 'last' endpoint with smaller number
        try:
            print("  Trying fallback with last 1000 observations...")
            url_fallback = "https://markets.newyorkfed.org/api/rates/secured/sofr/last/1000.json"
            response = requests.get(url_fallback, timeout=30)
            response.raise_for_status()
            data = response.json()
            
            sofr_df = pd.DataFrame(data['refRates'])
            sofr_df['Date'] = pd.to_datetime(sofr_df['effectiveDate'])
            sofr_df['Rate'] = sofr_df['percentRate'].astype(float)
            sofr_df['Source'] = 'SOFR'
            sofr_df = sofr_df[['Date', 'Rate', 'Source']].sort_values('Date')
            
            return sofr_df
            
        except Exception as e2:
            print(f"  Fallback also failed: {e2}")
            return None
            
    except Exception as e:
        print(f"Error fetching SOFR from NY Fed: {e}")
        return None


def load_fed_funds_manual():
    """Load manually downloaded Fed Funds history."""
    
    if not FED_FUNDS_FILE.exists():
        print(f"ERROR: {FED_FUNDS_FILE} not found!")
        print("\nPlease download Fed Funds history:")
        print("1. Go to: https://fred.stlouisfed.org/series/DFF")
        print("2. Click 'Download'")
        print("3. Date range: 1954-07-01 to 2018-04-02")
        print("4. Format: CSV")
        print(f"5. Save to: {FED_FUNDS_FILE}")
        return None
    
    try:
        df = pd.read_csv(FED_FUNDS_FILE)
        
        # Handle different possible column names from FRED (case-insensitive)
        # Normalize column names to lowercase for comparison
        df.columns = df.columns.str.strip()
        col_lower = {col.lower(): col for col in df.columns}
        
        # Find date column
        if 'date' in col_lower:
            date_col = col_lower['date']
        elif 'observation_date' in col_lower:
            date_col = col_lower['observation_date']
        else:
            print(f"ERROR: Cannot find date column in {FED_FUNDS_FILE}")
            print(f"Available columns: {list(df.columns)}")
            return None
        
        # Find rate column (DFF is the series ID, but file might have different name)
        if 'dff' in col_lower:
            rate_col = col_lower['dff']
        elif 'value' in col_lower:
            rate_col = col_lower['value']
        elif 'rate' in col_lower:
            rate_col = col_lower['rate']
        else:
            # If only 2 columns, assume second is the rate
            if len(df.columns) == 2:
                rate_col = df.columns[1]
                print(f"  Assuming column '{rate_col}' contains rates")
            else:
                print(f"ERROR: Cannot find rate column in {FED_FUNDS_FILE}")
                print(f"Available columns: {list(df.columns)}")
                return None
        
        df['Date'] = pd.to_datetime(df[date_col])
        df['Rate'] = pd.to_numeric(df[rate_col], errors='coerce')
        df['Source'] = 'EFFR'
        df = df[['Date', 'Rate', 'Source']].dropna()
        
        # Filter to pre-SOFR period
        df = df[df['Date'] <= FED_FUNDS_END_DATE]
        
        return df
        
    except Exception as e:
        print(f"Error loading Fed Funds file: {e}")
        import traceback
        traceback.print_exc()
        return None


def combine_short_rates(fed_funds_df, sofr_df):
    """Merge Fed Funds and SOFR into single time series."""
    
    # Concatenate
    combined = pd.concat([fed_funds_df, sofr_df], ignore_index=True)
    
    # Sort by date
    combined = combined.sort_values('Date').reset_index(drop=True)
    
    # Remove duplicates (keep SOFR if overlap)
    combined = combined.drop_duplicates(subset='Date', keep='last')
    
    return combined


def update_short_rates(init_mode=False):
    """Main update logic."""
    
    print("\n" + "="*70)
    print("Short Rate History Updater")
    print("="*70 + "\n")
    
    # 1. Load Fed Funds (manual download)
    print("Loading Fed Funds history (1954-2018)...")
    fed_funds_df = load_fed_funds_manual()
    
    if fed_funds_df is None:
        return False
    
    print(f"  Loaded {len(fed_funds_df)} Fed Funds observations")
    print(f"  Range: {fed_funds_df['Date'].min().date()} to {fed_funds_df['Date'].max().date()}")
    
    # 2. Fetch SOFR
    print("\nFetching SOFR history (2018-present)...")
    sofr_df = fetch_sofr_from_nyfed()
    
    if sofr_df is None:
        print("  Could not fetch SOFR from NY Fed API")
        
        # Try to use cached SOFR
        if SOFR_FILE.exists():
            print(f"  Using cached SOFR from {SOFR_FILE}")
            sofr_df = pd.read_csv(SOFR_FILE, parse_dates=['Date'])
        else:
            print("\n  SOFR API failed and no cached data available.")
            print("\n  Manual download option:")
            print("  1. Go to: https://markets.newyorkfed.org/read?productCode=50&eventCodes=500&limit=2500&startPosition=0&sort=postDt:-1&format=csv")
            print("  2. Save as: data/short_rates/sofr_manual.csv")
            print("  3. Re-run this script")
            print("\n  Or wait and the script will retry with API later.")
            
            # Check for manual SOFR file
            manual_sofr = SHORT_RATE_DIR / 'sofr_manual.csv'
            if manual_sofr.exists():
                print(f"\n  Found manual SOFR file: {manual_sofr}")
                try:
                    df_manual = pd.read_csv(manual_sofr)
                    # Handle NY Fed CSV format
                    df_manual.columns = df_manual.columns.str.strip()
                    col_lower = {col.lower(): col for col in df_manual.columns}
                    
                    # Date column
                    if 'effective date' in col_lower:
                        date_col = col_lower['effective date']
                    elif 'date' in col_lower:
                        date_col = col_lower['date']
                    else:
                        date_col = df_manual.columns[0]
                    
                    # Rate Type column (to filter for SOFR only)
                    if 'rate type' in col_lower:
                        type_col = col_lower['rate type']
                    else:
                        type_col = None
                    
                    # Rate column
                    if 'rate (%)' in col_lower:
                        rate_col = col_lower['rate (%)']
                    elif 'rate' in col_lower:
                        rate_col = col_lower['rate']
                    elif 'sofr' in col_lower:
                        rate_col = col_lower['sofr']
                    else:
                        # Assume third column has the rate
                        rate_col = df_manual.columns[2] if len(df_manual.columns) > 2 else df_manual.columns[1]
                    
                    # Filter for SOFR only (file contains EFFR, OBFR, SOFR)
                    if type_col:
                        df_manual = df_manual[df_manual[type_col].str.upper() == 'SOFR']
                        print(f"  Filtered to SOFR rate type only ({len(df_manual)} rows)")
                    
                    sofr_df = pd.DataFrame()
                    sofr_df['Date'] = pd.to_datetime(df_manual[date_col])
                    sofr_df['Rate'] = pd.to_numeric(df_manual[rate_col], errors='coerce')
                    sofr_df['Source'] = 'SOFR'
                    sofr_df = sofr_df.dropna()
                    
                    # Filter to SOFR era (2018-04-03 onwards)
                    sofr_df = sofr_df[sofr_df['Date'] >= SOFR_START_DATE]
                    
                    if len(sofr_df) == 0:
                        print("  ERROR: No SOFR data found after filtering")
                        print("  Make sure the file contains SOFR rate type")
                        return False
                    
                    print(f"  Loaded {len(sofr_df)} SOFR observations from manual file")
                    print(f"  Range: {sofr_df['Date'].min().date()} to {sofr_df['Date'].max().date()}")
                    
                except Exception as e:
                    print(f"  Error loading manual SOFR: {e}")
                    import traceback
                    traceback.print_exc()
                    return False
            else:
                print("  ERROR: No SOFR data available")
                return False
    else:
        print(f"  Fetched {len(sofr_df)} SOFR observations")
        print(f"  Range: {sofr_df['Date'].min().date()} to {sofr_df['Date'].max().date()}")
        
        # Save SOFR for caching
        sofr_df.to_csv(SOFR_FILE, index=False)
        print(f"  Cached SOFR to {SOFR_FILE}")
    
    # 3. Combine
    print("\nCombining Fed Funds + SOFR...")
    combined_df = combine_short_rates(fed_funds_df, sofr_df)
    
    print(f"  Total observations: {len(combined_df)}")
    print(f"  Date range: {combined_df['Date'].min().date()} to {combined_df['Date'].max().date()}")
    
    # Check for gaps
    combined_df['Date_diff'] = combined_df['Date'].diff()
    gaps = combined_df[combined_df['Date_diff'] > timedelta(days=3)]
    
    if len(gaps) > 0:
        print(f"\n  Warning: Found {len(gaps)} gaps > 3 days:")
        for _, row in gaps.head(5).iterrows():
            print(f"    Gap before {row['Date'].date()}")
    
    # 4. Save combined file
    combined_df = combined_df[['Date', 'Rate', 'Source']]
    combined_df.to_csv(COMBINED_FILE, index=False)
    
    print(f"\n  Saved combined short rate history to {COMBINED_FILE}")
    
    # 5. Summary statistics
    print("\nSummary by source:")
    summary = combined_df.groupby('Source').agg({
        'Date': ['min', 'max', 'count'],
        'Rate': ['mean', 'std', 'min', 'max']
    })
    print(summary.to_string())
    
    print("\n" + "="*70)
    print("[OK] Short rate history updated successfully")
    print("="*70 + "\n")
    
    return True


def main():
    parser = argparse.ArgumentParser(description='Update short rate history')
    parser.add_argument('--init', action='store_true',
                       help='Initial setup mode')
    args = parser.parse_args()
    
    success = update_short_rates(init_mode=args.init)
    
    if not success:
        print("\nUpdate failed. Please check error messages above.")
        return 1
    
    return 0


if __name__ == '__main__':
    exit(main())
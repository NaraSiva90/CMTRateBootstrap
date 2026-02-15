#!/usr/bin/env python3
"""
run_bootstrap.py

Convenience wrapper to run cmt_bootstrap.py on Treasury_CMT_Data_Tool.xlsx

Usage:
    python scripts/run_bootstrap.py --scheme 2
    python scripts/run_bootstrap.py --scheme 3 --write-excel
"""

import argparse
import subprocess
import sys
from pathlib import Path

def main():
    parser = argparse.ArgumentParser(
        description='Run bootstrap on Treasury CMT data',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_bootstrap.py --scheme 2
    → Bootstrap with piecewise linear forwards (recommended)
  
  python scripts/run_bootstrap.py --scheme 3 --write-excel
    → Bootstrap with monotone cubic forwards + Excel output
  
  python scripts/run_bootstrap.py --scheme 2 --nu 12
    → Use 12 payments per year (monthly)
        """
    )
    
    parser.add_argument('--scheme', type=int, choices=[1, 2, 3], required=True,
                        help='Bootstrap scheme: 1=constant, 2=linear (recommended), 3=cubic')
    parser.add_argument('--write-excel', action='store_true',
                        help='Generate Excel output (in addition to NPZ)')
    parser.add_argument('--nu', type=int, default=24,
                        help='Payment frequency per year (default: 24)')
    parser.add_argument('--workbook', default='Treasury_CMT_Data_Tool.xlsx',
                        help='Path to Treasury data Excel file')
    
    args = parser.parse_args()
    
    # Check if workbook exists
    workbook_path = Path(args.workbook)
    if not workbook_path.exists():
        print(f"Error: Workbook not found: {args.workbook}")
        print()
        print("Please run build_initial_treasury_file.py first:")
        print("  python scripts/build_initial_treasury_file.py")
        sys.exit(1)
    
    # Build command
    cmd = [
        sys.executable,
        'src/cmt_bootstrap.py',
        '--workbook', args.workbook,
        '--scheme', str(args.scheme),
        '--nu', str(args.nu)
    ]
    
    if args.write_excel:
        cmd.append('--write-excel')
    
    # Run bootstrap
    print("="*70)
    print(f"Running Bootstrap Scheme {args.scheme}")
    print("="*70)
    print(f"Workbook: {args.workbook}")
    print(f"Payment frequency: {args.nu}/year")
    print(f"Excel output: {'Yes' if args.write_excel else 'No'}")
    print()
    
    result = subprocess.run(cmd)
    
    if result.returncode == 0:
        print()
        print("="*70)
        print("✓ Bootstrap completed successfully!")
        print("="*70)
    else:
        print()
        print("="*70)
        print("✗ Bootstrap failed!")
        print("="*70)
        sys.exit(1)

if __name__ == '__main__':
    main()

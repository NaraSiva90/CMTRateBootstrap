#!/usr/bin/env python3
"""
update_all_data.py

Single entrypoint for the daily data refresh. Runs, in order:

    1. update_treasury_cmt.py  - latest Treasury CMT par rates -> workbook
    2. update_short_rates.py   - latest SOFR/Fed Funds history -> r0 anchor for S2/S3
    3. run_bootstrap.py        - re-bootstrap the full history

S2 and S3 anchor their short end to r0 (SOFR-preferred), so step 2 is not
optional if you want current-day S2/S3 curves - only step 1 was previously
documented as part of the daily job, which let the short-rate anchor go
stale silently. See docs/BOOTSTRAP_GUIDE.md, Workflow 2 (Production).

Each step is run and reported separately so one step's failure doesn't mask
another's - a NY Fed API outage (step 2) is distinguishable from a Treasury
API outage (step 1). By default the chain keeps going even if a step fails,
so later steps still run against whatever data is already on disk (e.g. the
bootstrap runs against yesterday's cached short-rate file); pass
--stop-on-error to abort immediately instead.

Usage:
    python scripts/update_all_data.py --scheme 2
    python scripts/update_all_data.py --scheme 3 --write-excel
    python scripts/update_all_data.py --scheme 2 --stop-on-error
"""

import argparse
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent


def run_step(label, cmd):
    print("=" * 70)
    print(label)
    print("=" * 70)
    print(" ".join(cmd))
    print()

    result = subprocess.run(cmd)
    ok = result.returncode == 0

    print()
    print(f"{label}: {'OK' if ok else f'FAILED (exit {result.returncode})'}")
    print()
    return ok


def main():
    parser = argparse.ArgumentParser(
        description='Refresh Treasury CMT rates + short-rate history, then re-run the bootstrap.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/update_all_data.py --scheme 2
    -> Daily refresh: Treasury CMT + SOFR, then Scheme 2 bootstrap

  python scripts/update_all_data.py --scheme 3 --write-excel
    -> Same, with Scheme 3 and an Excel workbook alongside the NPZ

Intended as the single daily cron / Task Scheduler entrypoint - see
docs/BOOTSTRAP_GUIDE.md, Workflow 2 (Production).
        """
    )
    parser.add_argument('--scheme', type=int, choices=[1, 2, 3], default=2,
                        help='Bootstrap scheme to run after the data refresh (default: 2)')
    parser.add_argument('--write-excel', action='store_true',
                        help='Also write an Excel workbook of the bootstrap output')
    parser.add_argument('--nu', type=int, default=24,
                        help='Payment frequency per year (default: 24)')
    parser.add_argument('--workbook', default='Treasury_CMT_Data_Tool.xlsx',
                        help='Path to Treasury data Excel file')
    parser.add_argument('--full', action='store_true',
                        help='Full historical Treasury refresh (1990-present) instead of '
                             'current year only')
    parser.add_argument('--stop-on-error', action='store_true',
                        help='Abort the chain on the first failed step instead of continuing '
                             'with whatever data is already on disk')
    args = parser.parse_args()

    # Always pass explicit --start-year/--end-year (rather than relying on
    # update_treasury_cmt.py's own default/interactive-menu behavior) so this
    # never blocks on stdin regardless of how it's invoked.
    current_year = datetime.now().year
    start_year = 1990 if args.full else current_year
    treasury_cmd = [sys.executable, str(SCRIPTS_DIR / 'update_treasury_cmt.py'),
                     '--workbook', args.workbook,
                     '--start-year', str(start_year), '--end-year', str(current_year)]

    short_rate_cmd = [sys.executable, str(SCRIPTS_DIR / 'update_short_rates.py')]

    bootstrap_cmd = [sys.executable, str(SCRIPTS_DIR / 'run_bootstrap.py'),
                      '--scheme', str(args.scheme), '--nu', str(args.nu),
                      '--workbook', args.workbook]
    if args.write_excel:
        bootstrap_cmd.append('--write-excel')

    results = []

    results.append(('Treasury CMT rates',
                     run_step('[1/3] Treasury CMT rates', treasury_cmd)))
    if args.stop_on_error and not results[-1][1]:
        print("Stopping: Treasury CMT fetch failed and --stop-on-error was set.")
        sys.exit(1)

    results.append(('Short rate history (SOFR/Fed Funds)',
                     run_step('[2/3] Short rate history (SOFR/Fed Funds)', short_rate_cmd)))
    if args.stop_on_error and not results[-1][1]:
        print("Stopping: short-rate update failed and --stop-on-error was set.")
        sys.exit(1)

    results.append((f'Bootstrap (Scheme {args.scheme})',
                     run_step(f'[3/3] Bootstrap (Scheme {args.scheme})', bootstrap_cmd)))

    print("=" * 70)
    print("Summary")
    print("=" * 70)
    for name, ok in results:
        print(f"  {'OK  ' if ok else 'FAIL'}  {name}")
    print()

    if not all(ok for _, ok in results):
        print("One or more steps failed - see the log above. If the bootstrap step ran, "
              "check for a WARNING about a stale short-rate anchor (r0).")
        sys.exit(1)

    print("All steps completed successfully.")


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""
Simple Backfill Download System for The Breaker of Babylon.

This is the dedicated, easy-to-use backfill system.

- Focuses on high-value sources for documents (court, press, CRS/GAO, FOIA) and especially politicians (for individual profile files).
- Uses deep historical windows when --backfill (default).
- High max_new by default for backfill runs (override with --max-new).
- Calls the core monitor logic but with backfill-optimized sources and settings.
- Idempotent (won't re-download existing keys in R2).
- Activate: run via GH workflow or locally with R2 env.
- Maintain: this script + the politician discovers (expanded years on backfill) + monitor cron occasionally calling with backfill.

Usage (in GH Actions or with R2_* env):
  python scripts/simple_backfill.py --max-new 500

Or via the backfill workflow.

This replaces flaky ad-hoc backfills. Run periodically or on demand for historical catch-up.
"""

import os
import sys
import argparse

# Reuse the core monitor
sys.path.insert(0, os.path.dirname(__file__))
from monitor_and_ingest import run_monitor

# Focused sources for backfill (politicians heavy for profiles + docs)
BACKFILL_SOURCES = "politicians_fec,politicians_congress,politicians_courts_recap,politicians_state_elections,politicians_opensecrets,court_documents,press_releases,crs_gao_reports,foia_documents"

def main():
    parser = argparse.ArgumentParser(description="Simple dedicated backfill system. Deep historical ingest for politicians/docs.")
    parser.add_argument("--max-new", type=int, default=500, help="Max new items this run (high for backfill)")
    parser.add_argument("--dry-run", action="store_true", help="Discover only")
    parser.add_argument("--sources", default=BACKFILL_SOURCES, help="Override sources (comma sep)")
    args = parser.parse_args()

    print("=== Simple Backfill System ===")
    print(f"Sources: {args.sources}")
    print(f"Max new: {args.max_new}")
    print("Backfill mode: deep historical windows enabled in discovers")
    print("This will pull missing older data (FEC years back, congress history, court bulk, etc.)")
    print("")

    ingested = run_monitor(
        sources=[s.strip() for s in args.sources.split(",") if s.strip()],
        max_new=args.max_new,
        dry_run=args.dry_run,
        backfill=True,  # Always deep for this system
        auto_process=True
    )

    print(f"\nSimple backfill complete. Ingested {len(ingested)} this run.")
    if ingested:
        print("New items will have triggered process/analyze where applicable.")
        print("Profiles can be rebuilt with the profiles workflow to incorporate new politician data.")

if __name__ == "__main__":
    main()

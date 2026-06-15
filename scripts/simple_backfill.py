#!/usr/bin/env python3
"""
Simple Backfill Download System — Grok Improved v1
- Structured JSON logging
- --force flag to bypass some idempotency
- Better error handling and summary
"""
import os
import sys
import argparse
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from monitor_and_ingest import run_monitor

def main():
    parser = argparse.ArgumentParser(description="Improved Backfill System")
    parser.add_argument("--max-new", type=int, default=800)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--backfill-level", choices=["light", "medium", "deep"], default="deep")
    parser.add_argument("--sources", default="politicians_fec,politicians_congress,politicians_courts_recap,politicians_state_elections,politicians_opensecrets,court_documents,press_releases,crs_gao_reports,foia_documents")
    args = parser.parse_args()

    log = {
        "timestamp": datetime.utcnow().isoformat(),
        "mode": "backfill",
        "level": args.backfill_level,
        "force": args.force,
        "sources": args.sources,
        "status": "started"
    }
    print("=== Grok Improved Backfill Started ===")
    print(json.dumps(log, indent=2))

    try:
        ingested = run_monitor(
            sources=[s.strip() for s in args.sources.split(",") if s.strip()],
            max_new=args.max_new,
            dry_run=args.dry_run,
            backfill=True,
            force=args.force,
            backfill_level=args.backfill_level,
            auto_process=True
        )
        log["status"] = "success"
        log["ingested_count"] = len(ingested or [])
        print(f"\n[OK] Backfill complete. Ingested {len(ingested or [])} items this run.")
    except Exception as e:
        log["status"] = "failed"
        log["error"] = str(e)
        print(f"[ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        with open("backfill_log.json", "w") as f:
            json.dump(log, f, indent=2)
        print("[LOG] Full JSON log saved to backfill_log.json")

if __name__ == "__main__":
    main()

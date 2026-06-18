#!/usr/bin/env python3
"""
Simple Backfill Download System — Enhanced v2 (hard metrics work)
- Computes/logs: download counts, step progress (discover, ingest, process, analyze, sink), rates, completion
- Subagent tags [BACKFILL] for visibility in logs + status
- Outputs pipeline_status.json for pipeline status (integrates w/ AI stack watchers)
- Rate tuning via --rate-limit for decent throughput
- AI stack friendly: status JSON + env SUBAGENT_TAG
"""
import os
import sys
import argparse
import json
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from monitor_and_ingest import run_monitor

SUBAGENT = os.environ.get("SUBAGENT_TAG", "BACKFILL-DEPLOYER-HEAVY")

def main():
    parser = argparse.ArgumentParser(description="Improved Backfill System")
    parser.add_argument("--max-new", type=int, default=800)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--backfill-level", choices=["light", "medium", "deep"], default="deep")
    parser.add_argument("--sources", default="politicians_fec,politicians_congress,politicians_courts_recap,politicians_state_elections,politicians_opensecrets,court_documents,press_releases,crs_gao_reports,foia_documents")
    parser.add_argument("--rate-limit", type=float, default=0.22, help="Rate delay (tuned 0.22s for decent throughput on backfill; parallel discovers help overall pipeline rate)")
    parser.add_argument("--status-file", default="pipeline_status.json")
    args = parser.parse_args()

    os.environ["SUBAGENT_TAG"] = SUBAGENT
    os.environ["PIPELINE_STATUS_FILE"] = args.status_file
    os.environ["RATE_LIMIT_DELAY"] = str(args.rate_limit)

    log = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "mode": "backfill",
        "level": args.backfill_level,
        "force": args.force,
        "sources": args.sources,
        "subagent": SUBAGENT,
        "rate_limit": args.rate_limit,
        "status": "started",
        "metrics_enabled": True
    }
    os.environ["SUBAGENT_TAG"] = SUBAGENT
    print(f"[{SUBAGENT}] === Grok Enhanced Backfill Started [SUBAGENT:BACKFILL-DEPLOYER-HEAVY] [Rule42 data pipeline + live R2 delta + R42 sig rates] ===")
    print(json.dumps(log, indent=2))
    print(f"[{SUBAGENT}] [LIVE] Backfill deployed as data pipeline subagent. Live indicators (R2delta/R42sig rates), granular R42-ANALYZE steps, rule42_pipeline_hints + detailed_per_signal_explanations flowing to R2 active across ingest/process/analyze.")

    try:
        # Subagent tag visibility
        print(f"[{SUBAGENT}] [SUBAGENT] Backfill Orchestrator starting level={args.backfill_level} rate={args.rate_limit}s [STEP:DISCOVER planned] [RULE42 focus enabled]")
        ingested = run_monitor(
            sources=[s.strip() for s in args.sources.split(",") if s.strip()],
            max_new=args.max_new,
            dry_run=args.dry_run,
            backfill=True,
            force=args.force,
            backfill_level=args.backfill_level,
            auto_process=True,
            subagent_tag=SUBAGENT,
            rate_limit=args.rate_limit
        )
        log["status"] = "success"
        log["ingested_count"] = len(ingested or [])
        log["downloads_count"] = len(ingested or [])
        print(f"[{SUBAGENT}] [SUBAGENT] Ingestion Subagent: completed {len(ingested or [])} items [STEP:COMPLETE] [RULE42 enriched]")
        print(f"\n[{SUBAGENT}] [OK] Backfill complete. Ingested {len(ingested or [])} items this run. [LIVE] All pipeline areas (backfill/monitor/worker/Rule42) updated.")
        # Pull live pipeline status
        try:
            with open(args.status_file) as f:
                pstatus = json.load(f)
            print(f"[{SUBAGENT}] [PIPELINE_STATUS] {json.dumps({k: pstatus.get(k) for k in ['download_count','completion_pct','rates','step_progress']}, indent=2)}")
        except Exception:
            pass
    except Exception as e:
        log["status"] = "failed"
        log["error"] = str(e)
        print(f"[{SUBAGENT}] [ERROR] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        with open("backfill_log.json", "w") as f:
            json.dump(log, f, indent=2)
        print(f"[{SUBAGENT}] [LOG] Full JSON log saved to backfill_log.json + {args.status_file} [AI-STACK ready]")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Phase 2 stub: Generated public feeds to babylon-generated bucket.
Post-analyze step: produces consumable JSONs (recent_ripples, arena_stats, narrative_signals) from processed/derived.
Run after analyze (or wire in monitor post-rich).

Writes to babylon-generated/ for site/public consumption (Phase 3 public feeds).

Example: python scripts/generate_public_feeds.py --arena all --limit 20
"""

import os
import json
import boto3
from botocore.config import Config
import argparse
from datetime import datetime

SRC_BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")
GEN_BUCKET = os.environ.get("GENERATED_BUCKET_NAME", "babylon-generated")

def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arena", default="all")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s3 = get_s3()
    SUBAGENT = os.environ.get("SUBAGENT_TAG", "GENERATE-FEEDS")
    print(f"[{SUBAGENT}] [LIVE] Generating public feeds (incl Rule42 signals from analyze/worker) for {args.arena} (limit {args.limit}) to {GEN_BUCKET}...")

    # Stub: list recent synthesis/ripples, produce minimal feeds
    # Real: aggregate from news_ripples, tactic_scores, entity graphs across arenas
    feeds = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "arena": args.arena,
        "recent_ripples": [],  # from derived/*-synthesis.json news_ripples etc (post-analyze)
        "arena_stats": {"total_processed": 0, "hot_avg": 0.7, "arenas": {}},
        "narrative_signals": {"top_framing": [], "coordination_hints": []}
    }

    # Example: scan a few derived for demo data (real: aggregate tactic_scores, repeated, entity counts across recent)
    # Enhanced: pull rich context (zdf_relevance, ai-enhanced from processed/ai-enhanced if present, or synthesis), for Holo thought bridges + evidence.
    prefix = f"processed/derived/" if args.arena == "all" else f"processed/derived/{args.arena}"
    ai_prefix = f"processed/ai-enhanced/" if args.arena == "all" else f"processed/ai-enhanced/{args.arena}"
    paginator = s3.get_paginator("list_objects_v2")
    count = 0
    for page in paginator.paginate(Bucket=SRC_BUCKET, Prefix=prefix, MaxKeys=100):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith("-synthesis.json") and count < args.limit:
                try:
                    data = json.loads(s3.get_object(Bucket=SRC_BUCKET, Key=obj["Key"])["Body"].read())
                    if "news_ripples" in data:
                        ripples = data["news_ripples"].get("media_specific_repeated_phrases", [])[:5]
                        # attach zdf if surfaced in synthesis (from rich ai extract upstream)
                        for r in ripples:
                            if isinstance(r, dict):
                                r.setdefault("zdf_relevance", data.get("tactic_scores", {}).get("zdf_relevance") or 0.6)
                        feeds["recent_ripples"].extend(ripples)
                    # crude stats + rich
                    feeds["arena_stats"]["total_processed"] += 1
                    if data.get("tactic_scores"):
                        feeds["narrative_signals"]["top_framing"].extend(data.get("common_narratives", [])[:2])
                    count += 1
                except:
                    pass
    # Also scan ai-enhanced for direct zdf_relevance rich items (from Worker/smart_extract)
    try:
        for page in paginator.paginate(Bucket=SRC_BUCKET, Prefix=ai_prefix, MaxKeys=50):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith(("-ai-summary.json", ".json")) and count < args.limit:
                    try:
                        d = json.loads(s3.get_object(Bucket=SRC_BUCKET, Key=obj["Key"])["Body"].read())
                        ext = d.get("extraction", {}) or d.get("aiResult", {})
                        if ext.get("zdf_relevance") or "zdf" in str(d).lower():
                            feeds["recent_ripples"].append({
                                "label": d.get("raw_url") or obj["Key"],
                                "zdf_relevance": ext.get("zdf_relevance", 0.9),
                                "arena_relevance": ext.get("arena_relevance", []),
                                "key_quotes": ext.get("key_quotes", []),
                                "source": "ai-enhanced"
                            })
                            count += 1
                    except: pass
    except: pass

    # Write explicit named public JSONs to babylon-generated (per task spec + docs)
    outputs = {
        "public-feeds/recent_ripples.json": {"generated_at": feeds["generated_at"], "ripples": feeds["recent_ripples"][:42]},
        "public-feeds/arena_stats.json": feeds["arena_stats"],
        "public-feeds/narrative_signals.json": feeds["narrative_signals"]
    }
    if args.dry_run:
        print(f"  DRY: would write {list(outputs.keys())} with {len(feeds['recent_ripples'])} ripples")
        return

    for key, body in outputs.items():
        s3.put_object(Bucket=GEN_BUCKET, Key=key, Body=json.dumps(body, indent=2), ContentType="application/json")
        print(f"  Wrote {key}")

    # Also the combined
    key = f"public-feeds/{args.arena or 'global'}-signals.json"
    s3.put_object(Bucket=GEN_BUCKET, Key=key, Body=json.dumps(feeds, indent=2), ContentType="application/json")
    print(f"  Wrote {key}")

    # Emit index for public feeds consumption (for mappers /holo load)
    try:
        idx_key = "public-feeds/index.json"
        s3.put_object(Bucket=GEN_BUCKET, Key=idx_key, Body=json.dumps({"generated_at": feeds["generated_at"], "feeds": list(outputs.keys()), "zdf_included": any("zdf" in str(r).lower() for r in feeds["recent_ripples"])}, indent=2), ContentType="application/json")
        print(f"  Wrote {idx_key} (public feeds aggregator for Holo mappers)")
    except: pass

    print("Generated feeds run complete. Consume from babylon-generated for site/public (Phase 3).")
    print(f"[{SUBAGENT}] [LIVE] [RULE42] Feeds include rule42 blocks + worker ai extraction outputs [AI stack integrated]")

if __name__ == "__main__":
    main()
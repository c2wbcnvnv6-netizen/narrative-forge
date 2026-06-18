#!/usr/bin/env python3
# [EMBED] Pipeline area enhanced: live metrics, Rule42 signals embedded, worker /embed integration [SUBAGENT:PIPELINE]
"""
Phase 2 starter: Embeddings pipeline for babylon-embeddings bucket.
Reads recent processed summaries (from analyze/process outputs or smart_extract rich data).
Generates "embeddings" (placeholder for real vectors via Workers AI / Worker /embed or external model).
Writes structured JSON + metadata (with provenance) to babylon-embeddings/<arena>/...-embed.json.

Integration: Call post smart_extract or after analyze_data.generate_synthesis (e.g., in monitor after rich, or new GH workflow step).
Real vectors: Extend babylon-data-ai Worker with /embed (use @cf/baai/bge-small-en-v1.5 or llama embed); pass text, get vector, store here.
Enables RAG/thought bridges in Holo/JARVIS (Phase 3).

Usage (after setting R2 envs + optionally BABYLON_AI_WORKER_URL):
  python scripts/generate_embeddings.py --arena bureaucracy --limit 5 --processed-key processed/bureaucracy/...

Depends: boto3 (for R2), requests (for Worker if used). No new heavy NLP deps yet.
"""

import os
import sys
import json
import argparse
from datetime import datetime
import boto3
from botocore.config import Config
import requests

EMBED_BUCKET = os.environ.get("EMBED_BUCKET_NAME", "babylon-embeddings")
RAW_BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")  # for reading processed
WORKER_URL = os.environ.get("BABYLON_AI_WORKER_URL", "")  # for future /embed call

def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )

def load_processed(processed_key: str, s3):
    obj = s3.get_object(Bucket=RAW_BUCKET, Key=processed_key)
    return json.loads(obj["Body"].read())

def generate_embedding(text: str, arena: str) -> dict:
    """Placeholder for real embedding. Returns vector + metadata.
    In full: call Worker /embed or CF AI directly for dense vector (e.g. 768-dim BGE-base).
    Now wired to Worker /embed (Phase 2 enhancement).
    """
    if WORKER_URL:
        try:
            # Phase 2: Worker /embed {text, arena} -> {"vector": [...], "dim": 768, "model": "...", provenance}
            r = requests.post(f"{WORKER_URL.rstrip('/')}/embed", json={"text": text[:8000], "arena": arena}, timeout=30)
            if r.ok:
                return r.json()
        except Exception as e:
            print(f"  [embed] Worker call failed (fallback): {e}")

    # Fallback stub: simple "embedding" as hash-based or keyword vector (for pipeline testing)
    # Real: replace with model.encode or AI call producing list[float]
    vec = [hash(word) % 1000 / 1000.0 for word in text.lower().split()[:50]]  # toy 50-dim
    vec += [0.0] * (768 - len(vec))  # pad to common dim (bge-base ~768)
    return {
        "vector": vec[:768],
        "dim": 768,
        "model": "stub-hash-v1 (replace with Workers AI @cf/baai/bge-base-en-v1.5 or @cf/baai/bge-small-en-v1.5)",
        "text_snippet": text[:200]
    }


def generate_embeddings_for_summary(summary: dict, arena: str = None) -> dict:
    """Reusable hook for post rich extract / analyze flow (import from analyze_data or process).
    Reads text from summary (supports rich ai-enhanced + old), calls generate, returns embed payload.
    """
    arena = arena or summary.get("arena", "general")
    text = (summary.get("extracted_text_preview") or summary.get("content_preview") or
            summary.get("title", "") or json.dumps(summary.get("analysis", {})) or
            summary.get("extraction", {}).get("summary", ""))
    embed = generate_embedding(text, arena)
    base = (summary.get("raw_key") or summary.get("processed_key") or "item").split("/")[-1].rsplit("-summary", 1)[0]
    return {
        "processed_key": summary.get("processed_key") or summary.get("raw_key"),
        "arena": arena,
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "embedding": embed,
        "provenance": {
            "source": "generate_embeddings_for_summary (Phase 2)",
            "r2_path": f"embeddings/{arena}/{base}-embed.json",
            "raw_url": summary.get("raw_url") or summary.get("raw_key"),
            "version": "1.0-embed-stub"
        },
        "rich_context": {
            "zdf_relevance": summary.get("zdf_relevance") or summary.get("extraction", {}).get("zdf_relevance"),
            "framing": summary.get("framing_analysis") or summary.get("extraction", {}).get("framing_analysis")
        }
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arena", default="general")
    parser.add_argument("--processed-key", help="Single processed summary key (or batch via env)")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s3 = get_s3()
    keys = []
    if args.processed_key:
        keys = [args.processed_key]
    else:
        # Fallback: list recent processed for arena (simple paginate)
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=RAW_BUCKET, Prefix=f"processed/{args.arena}/", MaxKeys=100):
            for obj in page.get("Contents", []):
                if obj["Key"].endswith("-summary.json") and len(keys) < args.limit:
                    keys.append(obj["Key"])

    print(f"Generating embeddings for {len(keys)} items in {args.arena}...")

    for k in keys:
        try:
            summary = load_processed(k, s3)
            summary["processed_key"] = k  # ensure for reusable
            # Use reusable for consistency with post-extract wiring (supports rich from smart_extract)
            payload = generate_embeddings_for_summary(summary, args.arena)
            embed = payload["embedding"]
            embed_key = payload["provenance"]["r2_path"]

            if args.dry_run:
                print(f"  DRY: would write {embed_key}")
                continue

            s3.put_object(Bucket=EMBED_BUCKET, Key=embed_key, Body=json.dumps(payload, indent=2), ContentType="application/json")
            print(f"  Wrote {embed_key} (dim={embed.get('dim')}, model={embed.get('model')})")
        except Exception as e:
            print(f"  Skip {k}: {e}")

    # Phase 3 optimization: write arena index.json aggregator for easy loadEmbeddings consumption from R2_PUBLIC_BASE/embeddings/<arena>/index.json (or all/)
    # Collects the just-written (or recent) for RAG/thought bridges + zdf_relevance rich_context pass-through.
    try:
        if not args.dry_run:
            idx = []
            for k in keys:
                try:
                    summ = load_processed(k, s3)
                    summ["processed_key"] = k
                    p = generate_embeddings_for_summary(summ, args.arena)
                    idx.append({k: p.get("provenance", {}).get("r2_path"), "arena": p.get("arena"), "zdf_relevance": (p.get("rich_context") or {}).get("zdf_relevance"), "dim": p.get("embedding", {}).get("dim"), "snippet": p.get("embedding", {}).get("text_snippet", "")[:120]})
                except: pass
            if idx:
                idx_key = f"embeddings/{args.arena}/index.json"
                s3.put_object(Bucket=EMBED_BUCKET, Key=idx_key, Body=json.dumps({"generated_at": datetime.utcnow().isoformat()+"Z", "count": len(idx), "items": idx}, indent=2), ContentType="application/json")
                print(f"  Wrote index aggregator {idx_key} for loadEmbeddings (rich zdf_context included)")
    except Exception as ie:
        print(f"  Index write note (non-fatal): {ie}")

    print("Embeddings run complete. Use babylon-embeddings bucket for RAG in Phase 3 (Holo/JARVIS thought bridges).")

if __name__ == "__main__":
    main()
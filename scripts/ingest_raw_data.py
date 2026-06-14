#!/usr/bin/env python3
"""
Ingest script for raw data to babylon-raw-data (or BUCKET_NAME) bucket in Cloudflare R2.

Supports:
- Manual / one-off via workflow_dispatch (ARENA, SOURCE_URL, TARGET_KEY)
- Algorithmic / monitor-driven mode (called from monitor_and_ingest.py)
- Idempotent: skips if target_key already exists in bucket (unless FORCE=1)
- Streaming for huge files (low RAM)

Reusable: call ingest() directly from other scripts.

In GitHub Actions:
  - Manual: "Ingest Raw Data (for first download parameters)" 
  - Auto: monitor-ingest.yml calls this script in batch mode.

First: Test connection with "Test R2 Raw-Data Bucket Connection" workflow.

Streaming design:
  Uses requests.get(..., stream=True) + boto3 upload_fileobj on the raw stream.
  This supports huge initial dumps (hundreds of MB – many GB) with low RAM usage.
  No full file is held in memory.

Local run (advanced testing only): export the R2_* vars + SOURCE_URL etc then python scripts/ingest_raw_data.py
"""
import os
import sys
import time
from datetime import datetime
import requests
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

def get_s3_client():
    endpoint = os.environ["R2_ENDPOINT"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        config=Config(signature_version="s3v4"),
    )

def key_exists(bucket: str, key: str, s3=None) -> bool:
    """Check if object already exists in R2 (for idempotency / monitoring)."""
    if s3 is None:
        s3 = get_s3_client()
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            return False
        raise

def ingest(source_url: str, target_key: str, arena: str = "media", 
           bucket: str = "babylon-raw-data", force: bool = False, s3=None):
    """
    Core streaming ingest. Returns True if downloaded, False if skipped (already exists).
    """
    if s3 is None:
        s3 = get_s3_client()

    start_time = time.time()
    print(f"[{datetime.utcnow().isoformat()}] Starting ingest arena={arena} -> {target_key}")

    if not force and key_exists(bucket, target_key, s3):
        print(f"  SKIP: {target_key} already exists in {bucket} (use FORCE=1 to override)")
        return False

    print(f"  Source: {source_url}")
    print(f"  Target: s3://{bucket}/{target_key}")
    print("Downloading (stream mode)...")

    with requests.get(source_url, stream=True, timeout=(10, 600), allow_redirects=True) as response:
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        ctype = response.headers.get('content-type', 'unknown')
        size_str = f"{total_size / (1024*1024):.1f} MB" if total_size else "unknown"

        print(f"  HTTP {response.status_code} | Size: {size_str} | Content-Type: {ctype}")

        print("Uploading to R2 (streaming)...")
        s3.upload_fileobj(response.raw, bucket, target_key)

        elapsed = time.time() - start_time
        print(f"  Upload complete. Transferred {size_str} in {elapsed:.1f}s.")

    print(f"[{datetime.utcnow().isoformat()}] Ingest finished for {target_key}")
    return True

def main():
    # Legacy / direct env mode (used by manual workflow)
    arena = os.environ.get("ARENA", "media")
    source_url = os.environ.get("SOURCE_URL")
    target_key = os.environ.get("TARGET_KEY", f"raw/{arena}/data.bin")
    bucket = os.environ.get("BUCKET_NAME", "babylon-raw-data")
    force = os.environ.get("FORCE", "0") == "1"

    if not source_url:
        print("ERROR: SOURCE_URL env var is required (or call ingest() directly)")
        sys.exit(1)

    success = ingest(source_url, target_key, arena, bucket, force)
    if not success:
        # Non-fatal for monitoring
        print("Ingest skipped (already present).")
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

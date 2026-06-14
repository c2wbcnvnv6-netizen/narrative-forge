#!/usr/bin/env python3
"""
Ingest script for raw data to babylon-raw-data (or BUCKET_NAME) bucket in Cloudflare R2.

READY FOR FIRST DOWNLOAD DATA PARAMETERS.

In GitHub Actions:
  Use the "Ingest Raw Data (for first download parameters)" workflow.
  Required inputs:
    - arena: e.g. congress | elections | finance | media | bureaucracy | scotus | migration | etc. (maps to the 11 arenas)
    - source_url: A direct public HTTP/S URL that serves the raw file bytes (no login wall). Examples: bulk CSVs or JSON from usaspending.gov, congress.gov, fec.gov, census.gov, etc.
    - target_key: Destination object key inside the bucket, e.g. raw/congress/2024/awards-full.csv or raw/elections/2024/fec-donors.json

Strongly recommended FIRST STEP (before any ingest):
  Dispatch the "Test R2 Raw-Data Bucket Connection" workflow (zero inputs). It proves the 4 R2 secrets (from GitHub) are correct and you can reach babylon-raw-data.

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

def main():
    start_time = time.time()
    print(f"[{datetime.utcnow().isoformat()}] Starting raw data ingest (first download parameters mode)")

    # Required from env (set in workflow or .env)
    endpoint = os.environ["R2_ENDPOINT"]
    access_key = os.environ["R2_ACCESS_KEY_ID"]
    secret_key = os.environ["R2_SECRET_ACCESS_KEY"]

    # Parameters for the download (passed via workflow_dispatch inputs or env)
    arena = os.environ.get("ARENA", "congress")
    source_url = os.environ.get("SOURCE_URL")
    target_key = os.environ.get("TARGET_KEY", f"raw/{arena}/data.bin")

    bucket = os.environ.get("BUCKET_NAME", "babylon-raw-data")

    if not source_url:
        print("ERROR: SOURCE_URL env var is required")
        sys.exit(1)

    print(f"Starting ingest for arena='{arena}'")
    print(f"  Source: {source_url}")
    print(f"  Target: s3://{bucket}/{target_key}")
    print(f"  Bucket (set BUCKET_NAME to override): {bucket}")

    # Stream download to handle huge files without loading all in memory
    print("Downloading (stream mode for huge initial dumps)...")
    with requests.get(source_url, stream=True, timeout=(10, 300)) as response:
        response.raise_for_status()
        total_size = int(response.headers.get('content-length', 0))
        ctype = response.headers.get('content-type', 'unknown')
        size_str = f"{total_size / (1024*1024):.1f} MB" if total_size else "unknown (no content-length header)"
        print(f"  HTTP {response.status_code} | Size: {size_str}")
        print(f"  Content-Type: {ctype}")

        # S3 client for R2 (S3-compatible, zero-egress friendly for repeated AI reads later)
        s3 = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4"),
        )

        print("Uploading to R2 (streaming upload_fileobj)...")
        s3.upload_fileobj(response.raw, bucket, target_key)

        elapsed = time.time() - start_time
        print(f"Upload complete. Transferred {size_str} in {elapsed:.1f}s.")

    print(f"[{datetime.utcnow().isoformat()}] Ingest finished successfully.")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {str(e)}")
        sys.exit(1)

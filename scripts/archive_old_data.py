#!/usr/bin/env python3
# [ARCHIVE] Pipeline area: live indicators + Rule42 preserved in archives [SUBAGENT:PIPELINE]
"""
Phase 2 stub: Archiving logic (move old raw/ objects to babylon-archive).
Simple cutoff (e.g., >90 days). Run manually or via new GH workflow / cron.
Preserves provenance; uses manifests for audit.

Call from monitor post-ingest or scheduled: python scripts/archive_old_data.py --days 90 --dry-run

Buckets: source babylon-raw-data (raw/ prefix), dest babylon-archive.
"""

import os
import boto3
from botocore.config import Config
from datetime import datetime, timedelta
import argparse

SRC_BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")
ARCHIVE_BUCKET = os.environ.get("ARCHIVE_BUCKET_NAME", "babylon-archive")

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
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--prefix", default="raw/")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s3 = get_s3()
    cutoff = datetime.utcnow() - timedelta(days=args.days)
    print(f"Archiving {args.prefix} objects older than {args.days} days to {ARCHIVE_BUCKET}...")

    paginator = s3.get_paginator("list_objects_v2")
    archived = 0
    for page in paginator.paginate(Bucket=SRC_BUCKET, Prefix=args.prefix):
        for obj in page.get("Contents", []):
            last_mod = obj.get("LastModified")
            if last_mod and last_mod.replace(tzinfo=None) < cutoff:
                key = obj["Key"]
                if args.dry_run:
                    print(f"  DRY: would archive {key}")
                    continue
                try:
                    # Move old raw/ (or other prefix) >90d to babylon-archive; preserve key + add prov note
                    s3.copy_object(
                        Bucket=ARCHIVE_BUCKET,
                        CopySource={"Bucket": SRC_BUCKET, "Key": key},
                        Key=key,
                        MetadataDirective="COPY"
                    )
                    s3.delete_object(Bucket=SRC_BUCKET, Key=key)
                    print(f"  Archived {key}")
                    archived += 1
                except Exception as e:
                    print(f"  Archive fail for {key}: {e}")
    print(f"Archive run complete. Archived {archived} objects. (Enhance with manifest updates or Worker cron in full Phase 2.)")

if __name__ == "__main__":
    main()
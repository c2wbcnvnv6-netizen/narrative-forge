#!/usr/bin/env python3
"""
Phase 3/4: Cross-Arena Entity Directory + Intelligence Builder.

Scans processed/ (and derived from analysis) to build:
- Unified entity directory (politicians, agencies, bills, cases) with source links, counts, arenas.
- Cross-arena links (e.g. a justice in SCOTUS opinion + press + CRS report).
- Ready for website directory, oppo research, thought bridges.

Outputs: processed/directory/entities.json + summary.

Run after analysis. Substantial for "complete DC/politics directory" and "one living system".

Extensible to full resolution (fuzzy name match etc.).
"""

import os
import json
import boto3
from collections import defaultdict
from datetime import datetime

BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")

def get_s3():
    return boto3.client("s3", endpoint_url=os.environ["R2_ENDPOINT"], aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"], aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"])

def list_processed(prefix="processed/"):
    s3 = get_s3()
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            if obj["Key"].endswith("-summary.json") or obj["Key"].endswith("-synthesis.json"):
                keys.append(obj["Key"])
    return keys

def main():
    s3 = get_s3()
    keys = list_processed()
    entities = defaultdict(lambda: {"count": 0, "sources": [], "arenas": set(), "types": set()})

    for k in keys:
        try:
            data = json.loads(s3.get_object(Bucket=BUCKET, Key=k)["Body"].read())
            arena = data.get("arena", "unknown")
            raw = data.get("raw_key", k)
            # From basic analysis
            analysis = data.get("analysis", {})
            for etype, elist in analysis.get("entities", {}).items():
                for e in elist:
                    key = (etype, e.lower())
                    entities[key]["count"] += 1
                    entities[key]["sources"].append(raw)
                    entities[key]["arenas"].add(arena)
                    entities[key]["types"].add(etype)
            # From deep synthesis if present
            if "entities" in data:  # direct in some
                for etype, elist in data.get("entities", {}).items():
                    for e in elist:
                        key = (etype, e.lower())
                        entities[key]["count"] += 1
                        entities[key]["sources"].append(raw)
                        entities[key]["arenas"].add(arena)
        except:
            pass

    # Format
    directory = []
    for (etype, name), info in sorted(entities.items(), key=lambda x: -x[1]["count"]):
        directory.append({
            "type": etype,
            "name": name,
            "count": info["count"],
            "arenas": list(info["arenas"]),
            "sample_sources": info["sources"][:3]
        })

    out_key = "processed/directory/entities.json"
    s3.put_object(Bucket=BUCKET, Key=out_key, Body=json.dumps({"generated": datetime.utcnow().isoformat(), "entities": directory}, indent=2), ContentType="application/json")
    print(f"Directory built with {len(directory)} entities -> {out_key}")
    print(f"NOTIFY: directory updated with cross-arena entities")

if __name__ == "__main__":
    main()

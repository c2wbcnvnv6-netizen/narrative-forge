#!/usr/bin/env python3
"""
Algorithmically driven monitor for new public bulk datasets.

- Discovers fresh dumps from high-value sources (GDELT, Common Crawl, HF mirrors, IA Twitter streams, etc.).
- Compares against what's already in babylon-raw-data (via R2 listing + optional manifest).
- Automatically ingests only new items using the streaming ingest logic.
- Designed to run on schedule (cron) in GitHub Actions for continual archiving.
- Supports --dry-run, --max-new, --sources, --arena filter.

Usage (local, with R2_* env):
  python scripts/monitor_and_ingest.py --sources gdelt,commoncrawl,media --max-new 5 --dry-run

In GitHub Actions (monitor-ingest.yml):
  - Scheduled daily/weekly.
  - Calls this, which then calls ingest() for new items (or can dispatch sub-workflows).

Add new sources by implementing a discover_xxx_new() function that yields (arena, source_url, target_key).
"""

import os
import sys
import argparse
import json
import subprocess
from datetime import datetime, timedelta
from typing import List, Tuple, Generator
import requests
import boto3
from botocore.config import Config

# Re-use the improved ingest (works when run as `python scripts/monitor_and_ingest.py`)
sys.path.insert(0, os.path.dirname(__file__))
from ingest_raw_data import ingest, get_s3_client, key_exists

BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")
MANIFEST_KEY = "manifests/ingested.json"  # Simple persistent tracker in R2 (optional but recommended)

def get_s3():
    return get_s3_client()

def load_manifest(s3) -> dict:
    """Load or initialize the ingested manifest."""
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=MANIFEST_KEY)
        return json.loads(obj["Body"].read())
    except Exception:
        return {"ingested": {}, "last_checked": {}}

def save_manifest(s3, manifest: dict):
    s3.put_object(
        Bucket=BUCKET,
        Key=MANIFEST_KEY,
        Body=json.dumps(manifest, indent=2),
        ContentType="application/json"
    )

def list_existing_prefix(s3, prefix: str) -> set:
    """Return set of keys under a raw/ prefix (for quick existence check)."""
    keys = set()
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix, MaxKeys=1000):
        for obj in page.get("Contents", []):
            keys.add(obj["Key"])
    return keys

# ============== SOURCE DISCOVERY FUNCTIONS (add more here) ==============

def discover_gdelt_new(s3, existing_keys: set, days_back: int = 14) -> Generator[Tuple[str, str, str], None, None]:
    """GDELT v2 daily GKG + Mentions (media / narrative / global signals)."""
    base = "http://data.gdeltproject.org/v2"
    today = datetime.utcnow()
    for i in range(days_back):
        d = today - timedelta(days=i)
        date_str = d.strftime("%Y%m%d")
        for table in ["gkg", "mentions"]:
            if table == "gkg":
                url = f"{base}/gkg/{date_str}.gkg.csv.zip"
                key = f"raw/media/gdelt-gkg-{date_str}.csv.zip"
            else:
                url = f"{base}/mentions/{date_str}.mentions.CSV.zip"
                key = f"raw/media/gdelt-mentions-{date_str}.csv.zip"
            if key not in existing_keys and not key_exists(BUCKET, key, s3):
                yield "media", url, key

def discover_commoncrawl_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Common Crawl new crawls (media / social domain filtering). 
    Checks the official crawl-data index for the latest CC-MAIN- entries.
    """
    try:
        # Simple heuristic: fetch the main page or known recent, but for reliability we check a few recent patterns
        # In production: scrape https://commoncrawl.org/ or use their blog feed. Here we probe the last ~3 months.
        base = "https://data.commoncrawl.org/crawl-data"
        today = datetime.utcnow()
        for months_back in range(0, 4):
            for week in range(1, 53):
                d = today - timedelta(days=months_back*30)
                crawl_id = f"CC-MAIN-{d.year}-{week:02d}"
                for ptype in ["wat.paths.gz", "wet.paths.gz", "segment.paths.gz"]:
                    url = f"{base}/{crawl_id}/{ptype}"
                    key = f"raw/media/{crawl_id.lower()}-{ptype}"
                    # HEAD to see if the crawl exists (cheap)
                    try:
                        r = requests.head(url, timeout=10, allow_redirects=True)
                        if r.status_code == 200 and key not in existing_keys and not key_exists(BUCKET, key, s3):
                            yield "media", url, key
                            break  # only yield the first good type per crawl to keep volume reasonable
                    except Exception:
                        pass
    except Exception as e:
        print(f"  CC discovery error (non-fatal): {e}")

def discover_hf_pushshift_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """HF mirrors of Pushshift Reddit (media / social). 
    Uses public HF API to list recent files in a dataset.
    """
    datasets = [
        ("open-index/arctic", "comments"),   # or submissions
        # Add more HF public social datasets here
    ]
    for repo, split in datasets:
        try:
            api_url = f"https://huggingface.co/api/datasets/{repo}/tree/main/data/{split}"
            resp = requests.get(api_url, timeout=15)
            if resp.status_code != 200:
                continue
            for item in resp.json():
                if item.get("type") == "file" and item["path"].endswith(".parquet"):
                    fname = item["path"].split("/")[-1]
                    url = f"https://huggingface.co/datasets/{repo}/resolve/main/data/{split}/{fname}"
                    key = f"raw/media/hf-reddit-{split}-{fname}"
                    if key not in existing_keys and not key_exists(BUCKET, key, s3):
                        yield "media", url, key
        except Exception as e:
            print(f"  HF discovery error for {repo}: {e}")

def discover_ia_twitter_new(s3, existing_keys: set, months_back: int = 3) -> Generator[Tuple[str, str, str], None, None]:
    """Internet Archive ArchiveTeam Twitter streams (recent months)."""
    # Known pattern from IA: archiveteam-twitter-stream-YYYY-MM/
    base = "https://archive.org/download"
    today = datetime.utcnow()
    for i in range(months_back + 1):
        d = today - timedelta(days=i*30)
        coll = f"archiveteam-twitter-stream-{d.year}-{d.month:02d}"
        # Probe a couple of daily tars
        for day in range(1, 29, 7):  # sample a few days per month to keep it light
            tar_name = f"twitter-stream-{d.year}{d.month:02d}{day:02d}.tar"
            url = f"{base}/{coll}/{tar_name}"
            key = f"raw/media/ia-twitter-{coll}-{tar_name}"
            try:
                r = requests.head(url, timeout=8, allow_redirects=True)
                if r.status_code == 200 and key not in existing_keys and not key_exists(BUCKET, key, s3):
                    yield "media", url, key
            except Exception:
                pass

# ============== ADDITIONAL DISCOVER FUNCTIONS (for expansive list: lobbying, patents, health, education, legal, global, general) ==============

def discover_lobbying_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Lobbying & Influence (OpenSecrets, FollowTheMoney). Portals may require signup; yields main packs if missing."""
    candidates = [
        ("lobbying", "https://www.opensecrets.org/bulk-downloads", "raw/lobbying/opensecrets-lobbying.zip"),
        ("lobbying", "https://www.followthemoney.org", "raw/lobbying/followthemoney-states.zip"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            yield arena, url, key

def discover_patents_new(s3, existing_keys: set, years_back: int = 2) -> Generator[Tuple[str, str, str], None, None]:
    """Patents & IP (USPTO bulk, PatentsView). Probes for recent dated zips where possible."""
    # USPTO example dated structure (adjust as needed; ingest will skip bad ones)
    today = datetime.utcnow()
    base = "https://bulkdata.uspto.gov/data/patent/grant/redbook"
    for y in range(today.year - years_back, today.year + 1):
        for m in [1, 4, 7, 10]:  # quarterly sample
            url = f"{base}/{y}/{y}{m:02d}.zip"
            key = f"raw/patents/uspto-grants-{y}{m:02d}.zip"
            try:
                r = requests.head(url, timeout=8, allow_redirects=True)
                if r.status_code == 200 and key not in existing_keys and not key_exists(BUCKET, key, s3):
                    yield "patents", url, key
            except Exception:
                pass
    # PatentsView main
    url = "https://patentsview.org/download"
    key = "raw/patents/patentsview-full.zip"
    if key not in existing_keys and not key_exists(BUCKET, key, s3):
        yield "patents", url, key

def discover_health_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Health & Medical (CMS, CDC/NHANES, MEPS)."""
    candidates = [
        ("health", "https://healthdata.gov", "raw/health/cms-provider-data.zip"),
        ("health", "https://www.cdc.gov/nchs", "raw/health/cdc-nhanes.zip"),
        ("health", "https://meps.ahrq.gov", "raw/health/meps-full.zip"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            yield arena, url, key

def discover_education_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Education (IPEDS, CCD)."""
    candidates = [
        ("education", "https://nces.ed.gov/ipeds/use-the-data/download-access-database", "raw/education/ipeds-2024-25.zip"),
        ("education", "https://nces.ed.gov/ccd", "raw/education/ccd-full.zip"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            yield arena, url, key

def discover_legal_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Courts & Legal (govinfo courts, CourtListener/RECAP)."""
    candidates = [
        ("legal", "https://www.govinfo.gov/bulkdata", "raw/legal/govinfo-courts.zip"),
        ("legal", "https://www.courtlistener.com/api/bulk-info/", "raw/legal/courtlistener-recap.zip"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            yield arena, url, key

def discover_global_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """International & Global (WorldBank direct preferred, UN Comtrade, Our World in Data)."""
    candidates = [
        ("global", "https://databankfiles.worldbank.org/public/ddpext_download/WDI_CSV.zip", "raw/global/wdi-csv.zip"),
        ("global", "https://comtradeplus.un.org", "raw/global/un-comtrade.zip"),
        ("global", "https://ourworldindata.org", "raw/global/ourworldindata-full.zip"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            yield arena, url, key

def discover_general_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Bonus Mega Portals (data.gov etc.)."""
    candidates = [
        ("general", "https://catalog.data.gov/dataset", "raw/general/datagov-selected-bulk.zip"),
        ("general", "https://www.data.gov", "raw/general/us-open-data-archive.zip"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            yield arena, url, key

# ============== MAIN MONITOR LOGIC ==============

SOURCE_MAP = {
    "gdelt": discover_gdelt_new,
    "commoncrawl": discover_commoncrawl_new,
    "hf-reddit": discover_hf_pushshift_new,
    "ia-twitter": discover_ia_twitter_new,
    "lobbying": discover_lobbying_new,
    "patents": discover_patents_new,
    "health": discover_health_new,
    "education": discover_education_new,
    "legal": discover_legal_new,
    "global": discover_global_new,
    "general": discover_general_new,
}

def run_monitor(sources: List[str] = None, max_new: int = 10, dry_run: bool = False, arena_filter: str = None,
                backfill: bool = False, auto_process: bool = False):
    s3 = get_s3()
    manifest = load_manifest(s3)

    # Build existing set (fast path)
    existing = set()
    for prefix in ["raw/media/", "raw/global/", "raw/elections/", "raw/congress/"]:
        existing.update(list_existing_prefix(s3, prefix))

    # Also respect manifest
    for k in manifest.get("ingested", {}):
        existing.add(k)

    # Windows for backfill vs normal
    days_back = 365 if backfill else 14
    months_back = 12 if backfill else 3
    years_back = 5 if backfill else 2

    discovered = []
    sources = sources or list(SOURCE_MAP.keys())

    for src in sources:
        if src not in SOURCE_MAP:
            print(f"Unknown source: {src}")
            continue
        print(f"\n=== Discovering new from {src} ===")
        discover_func = SOURCE_MAP[src]
        # Pass window params where supported (functions use defaults or **kwargs style)
        try:
            if src in ["gdelt"]:
                gen = discover_func(s3, existing, days_back=days_back)
            elif src in ["commoncrawl", "ia-twitter"]:
                gen = discover_func(s3, existing, months_back=months_back) if "months_back" in discover_func.__code__.co_varnames else discover_func(s3, existing)
            elif src in ["patents"]:
                gen = discover_func(s3, existing, years_back=years_back)
            else:
                gen = discover_func(s3, existing)
        except TypeError:
            gen = discover_func(s3, existing)

        for arena, url, key in gen:
            if arena_filter and arena != arena_filter:
                continue
            if key in existing:
                continue
            discovered.append((arena, url, key, src))
            if len(discovered) >= max_new:
                break
        if len(discovered) >= max_new:
            break

    print(f"\nDiscovered {len(discovered)} new candidate(s).")

    ingested = []
    for arena, url, key, src in discovered[:max_new]:
        print(f"  -> {arena}: {key} (from {src})")
        if dry_run:
            continue
        try:
            ok = ingest(url, key, arena=arena, bucket=BUCKET, force=False, s3=s3)
            if ok:
                ingested.append(key)
                manifest.setdefault("ingested", {})[key] = {
                    "source": src,
                    "arena": arena,
                    "ingested_at": datetime.utcnow().isoformat() + "Z",
                    "url": url
                }
                if auto_process:
                    try:
                        repo = os.environ.get("GITHUB_REPOSITORY", "")
                        if repo:
                            cmd = [
                                "gh", "workflow", "run", "process-data.yml",
                                "-R", repo,
                                "-f", f"arena={arena}",
                                "-f", f"raw_key={key}"
                            ]
                            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
                            if result.returncode == 0:
                                print(f"    Auto-triggered process workflow for {key}")
                            else:
                                print(f"    Auto-process trigger: {result.stderr.strip()[:200]}")
                    except Exception as e:
                        print(f"    Auto-process trigger failed for {key}: {e}")
        except Exception as e:
            print(f"    ERROR ingesting {key}: {e}")

    if ingested:
        manifest["last_checked"] = manifest.get("last_checked", {})
        manifest["last_checked"]["last_run"] = datetime.utcnow().isoformat() + "Z"
        save_manifest(s3, manifest)
        print(f"\nUpdated manifest with {len(ingested)} new items.")

    print(f"\nMonitor complete. Ingested this run: {len(ingested)}")
    return ingested

def main():
    parser = argparse.ArgumentParser(description="Monitor public data sources and auto-ingest new bulk files to R2. 'Just do it' mode for continual archive.")
    parser.add_argument("--sources", default="gdelt,commoncrawl,hf-reddit,ia-twitter,lobbying,patents,health,education,legal,global,general",
                        help="Comma-separated sources to check (broad default for 'just do it')")
    parser.add_argument("--max-new", type=int, default=10, help="Maximum new items to ingest this run")
    parser.add_argument("--dry-run", action="store_true", help="Discover only, do not download")
    parser.add_argument("--arena", help="Only ingest for this arena")
    parser.add_argument("--backfill", action="store_true", help="Backfill mode: much larger historical windows (e.g. 1 year+), pull missing older data")
    parser.add_argument("--auto-process", action="store_true", help="After successful ingest, automatically trigger the Process Ingested Data workflow for the new raw_key")
    args = parser.parse_args()

    sources = [s.strip() for s in args.sources.split(",") if s.strip()]
    run_monitor(
        sources=sources,
        max_new=args.max_new,
        dry_run=args.dry_run,
        arena_filter=args.arena,
        backfill=args.backfill,
        auto_process=args.auto_process
    )

if __name__ == "__main__":
    main()

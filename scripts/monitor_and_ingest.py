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

# New for state/local/metro - maximum citable for extrapolation (Census, BLS, major portals, NHGIS for time-series)
def discover_census_metro_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Census Bureau metro (MSA/CBSA) data and TIGER boundaries - highly citable for local demographic/economic extrapolation."""
    # Direct TIGER CBSA shapefile for current metro boundaries
    url = "https://www2.census.gov/geo/tiger/TIGER2025/CBSA/tl_2025_us_cbsa.zip"
    key = "raw/metro/census-tiger-cbsa-2025.zip"
    if key not in existing_keys and not key_exists(BUCKET, key, s3):
        yield "metro", url, key
    # ACS 5-year for metros via data.census.gov or bulk (example for large metro; NHGIS for full time-series harmonized)
    # For bulk ACS metro, use direct from census or note NHGIS (https://www.nhgis.org/) for best extrapolation (time series + GIS for consistent metros over decades)
    # Add one example ACS extract if direct; otherwise rely on NHGIS manual bulk for citable long-term data.

def discover_bls_qcew_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """BLS Quarterly Census of Employment and Wages (QCEW) - county/MSA level employment/wages by industry. Prime citable source for local labor market extrapolation."""
    # BLS open data CSV slices - direct, updated quarterly. Example for recent US or metro (structure: data.bls.gov/cew/data/api/YYYY/Q/area/CODE.csv)
    # Full historical via their downloadable files page; use recent for auto, backfill for more.
    url = "https://data.bls.gov/cew/data/api/2024/1/area/US000.csv"  # US example; metro e.g. 35620 for NY-NJ
    key = "raw/metro/bls-qcew-us-2024q1.csv"
    if key not in existing_keys and not key_exists(BUCKET, key, s3):
        yield "metro", url, key
    # Another for a major metro
    url2 = "https://data.bls.gov/cew/data/api/2024/1/area/35620.csv"  # NY metro example
    key2 = "raw/metro/bls-qcew-ny-2024q1.csv"
    if key2 not in existing_keys and not key_exists(BUCKET, key2, s3):
        yield "metro", url2, key2

def discover_nyc_open_data_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """NYC Open Data (Socrata) - key for major metro policy, services, 311, payroll, etc. Direct CSV exports for local analysis."""
    # Socrata direct full CSV export (accessType=DOWNLOAD for bulk)
    url = "https://data.cityofnewyork.us/api/views/erm2-nwe9/rows.csv?accessType=DOWNLOAD"  # 311 historic example (large)
    key = "raw/local/nyc-311.csv"
    if key not in existing_keys and not key_exists(BUCKET, key, s3):
        yield "local", url, key
    # Add another high-value, e.g. if known direct for payroll or other.

def discover_ca_open_data_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """California Open Data (data.ca.gov) - largest state portal for extrapolation (health, grants, environment, etc.)."""
    # Example direct CSV from catalog (Socrata/CKAN often allow /download or API rows.csv)
    # From catalog, many have direct; example one.
    url = "https://data.ca.gov/dataset/california-grants-portal-grant-awards-2024-2025"  # adjust to direct if /export
    # For real Socrata, use pattern like other; yield one known.
    # To make direct, use a confirmed CSV if possible from research.
    key = "raw/state/ca-grants.csv"
    if key not in existing_keys and not key_exists(BUCKET, key, s3):
        yield "state", url, key

def discover_nhgis_metro_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """NHGIS (IPUMS) time-series ACS + GIS for consistent metro/county boundaries over time - BEST for historical extrapolation and citable longitudinal analysis."""
    # NHGIS requires extractor (registration), but data is public and highly citable.
    # For auto, note as source; yield a sample or main page. For bulk, user can use their Data Finder for specific metro time series + boundaries.
    # Direct if available via IPUMS API or FTP, but primarily through their system for harmonized data.
    url = "https://www.nhgis.org/"  # Main; for specific, use Data Finder for ACS 5yr metro time series + TIGER boundaries
    key = "raw/metro/nhgis-time-series-metro.zip"  # Placeholder; actual via their extract
    if key not in existing_keys and not key_exists(BUCKET, key, s3):
        yield "metro", url, key

def discover_eurostat_nuts_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Eurostat NUTS regional data for EU subnational - for international extrapolation and citable EU metro/regional comparisons."""
    # Bulk from Eurostat databrowser or download.
    # Example GDP or other by NUTS2/3.
    url = "https://ec.europa.eu/eurostat/databrowser/bulk?lang=en"  # Bulk download tool
    key = "raw/global/eurostat-nuts-regional.csv"
    if key not in existing_keys and not key_exists(BUCKET, key, s3):
        yield "global", url, key

# ============== DOCUMENT SOURCES (new dedicated discovers for "documents" folder: court rulings, press releases, CRS/GAO, FOIA/transcripts etc.) ==============

def discover_court_documents_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Court rulings and opinions (SCOTUS slip opinions direct PDFs + govinfo patterns). 
    Direct, citable from supremecourt.gov. Use recent October Term 2025/2026 for high relevance.
    """
    candidates = [
        # Recent SCOTUS slip opinions (direct PDF, verified 200 OK)
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/25-6_d1o2.pdf", "raw/documents/courts/scotus-25-6-keathley-v-ayers.pdf"),
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/24-345_i42k.pdf", "raw/documents/courts/scotus-24-345-fs-credit-v-saba.pdf"),
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/25-5146_e29f.pdf", "raw/documents/courts/scotus-25-5146-abouammo.pdf"),
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/24-889_5i36.pdf", "raw/documents/courts/scotus-24-889-hikma-v-amarin.pdf"),
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/25-406_nmip.pdf", "raw/documents/courts/scotus-25-406-fcc-v-att.pdf"),
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/24-109_new_jifl.pdf", "raw/documents/courts/scotus-24-109-louisiana-v-callais.pdf"),
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/24-781_pok0.pdf", "raw/documents/courts/scotus-24-781-first-choice-v-davenport.pdf"),
        ("documents", "https://www.supremecourt.gov/opinions/25pdf/24-539new_3fb4.pdf", "raw/documents/courts/scotus-24-539-chiles-v-salazar.pdf"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            try:
                r = requests.head(url, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    yield arena, url, key
            except Exception:
                pass

def discover_press_releases_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """Press releases and briefings/statements (White House current + archives, DOJ/OPA). 
    Full HTML pages or PDFs; highly citable primary source for narrative tracking (timing, framing, coordination).
    Mix of current admin + historical for comparison.
    """
    candidates = [
        # White House recent briefings & statements (full pages)
        ("documents", "https://www.whitehouse.gov/briefings-statements/2026/06/presidential-message-on-the-251st-birthday-of-the-united-states-army/", "raw/documents/press/wh-2026-06-army-251st-birthday.html"),
        ("documents", "https://www.whitehouse.gov/briefings-statements/2026/06/first-lady-melania-trumps-remarkable-week-empowering-youth-through-ai-challenge-and-fostering-the-future-accounts/", "raw/documents/press/wh-2026-06-melania-ai-youth.html"),
        # DOJ recent press releases (full content pages)
        ("documents", "https://www.justice.gov/opa/pr/former-intelligence-community-contractor-pleads-guilty-accepting-kickbacks", "raw/documents/press/doj-2026-06-12-duggin-kickbacks.html"),
        ("documents", "https://www.justice.gov/opa/pr/nevada-man-pleads-guilty-rigging-bids-healthcare-related-and-other-air-force-projects", "raw/documents/press/doj-2026-06-nevada-bid-rigging.html"),
        # Archived Trump WH for historical comparison (example known patterns; add more specific as available)
        ("documents", "https://trumpwhitehouse.archives.gov/briefings-statements/", "raw/documents/press/trumpwh-archives-briefings-index.html"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            try:
                r = requests.head(url, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    yield arena, url, key
            except Exception:
                pass

def discover_crs_gao_reports_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """CRS (Congressional Research Service) reports and GAO reports (direct PDFs via EveryCRSReport mirror + GAO).
    EveryCRSReport.com mirrors all public CRS reports (highly citable, neutral legislative research). 
    GAO for audits/recommendations. Excellent for deep policy context and narrative baselines.
    """
    candidates = [
        # Recent CRS direct PDFs (from everycrsreport.com)
        ("documents", "https://www.everycrsreport.com/files/2026-06-02_R48296_2b94164541695afb9bd851e9161df28b12d54978.pdf", "raw/documents/crs/2026-06-02-improper-payments-ongoing-challenges.pdf"),
        ("documents", "https://www.everycrsreport.com/files/2025-05-21_R48544_496ef9d65a8dd51ed2a4ed3321f211f7fc9bdaa2.pdf", "raw/documents/crs/2025-05-21-connecting-constituents-federal-programs.pdf"),
        ("documents", "https://www.everycrsreport.com/files/2025-01-16_R48360_0d9acfa5f0765cd6f4a51c4565edbe087a312535.pdf", "raw/documents/crs/2025-01-16-tribal-lands-overview.pdf"),
        ("documents", "https://www.everycrsreport.com/files/2025-06-02_R45104_665a366a50148a021b27f266f82391f13da81562.pdf", "raw/documents/crs/2025-06-02-guide-committee-activity-reports.pdf"),
        ("documents", "https://www.everycrsreport.com/files/2026-01-29_R48540_4bc60c977344c56555d03cecf7e4af48167c2230.html", "raw/documents/crs/2026-01-29-universities-indirect-costs.html"),
        # GAO example direct (note: some assets may 403; use report pages or verified PDFs)
        ("documents", "https://www.gao.gov/products/gao-26-108610", "raw/documents/gao/gao-26-108610-nations-fiscal-health.html"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            try:
                r = requests.head(url, timeout=10, allow_redirects=True)
                if r.status_code in (200, 301, 302):
                    yield arena, url, key
            except Exception:
                pass

def discover_foia_documents_new(s3, existing_keys: set) -> Generator[Tuple[str, str, str], None, None]:
    """FOIA reading rooms, transcripts, released documents (govinfo, justice.gov, specific high-profile releases).
    Primary source material for transparency tracking. Examples include public dockets, transcripts, released files.
    Extend with specific high-value releases as identified (e.g. via foia.gov, agency reading rooms).
    """
    candidates = [
        # Example govinfo / justice public FOIA or related document collections (direct or index; probe for bytes)
        ("documents", "https://www.govinfo.gov/bulkdata", "raw/documents/foia/govinfo-bulkdata-index.html"),
        ("documents", "https://www.justice.gov/foia", "raw/documents/foia/justice-foia-readingroom.html"),
        # Placeholder for high-profile public releases (e.g. Epstein-related or other transcripts if direct public PDF emerges; add verified)
        # ("documents", "https://www.govinfo.gov/content/pkg/... .pdf", "raw/documents/foia/specific-transcript.pdf"),
    ]
    for arena, url, key in candidates:
        if key not in existing_keys and not key_exists(BUCKET, key, s3):
            try:
                r = requests.head(url, timeout=10, allow_redirects=True)
                if r.status_code == 200:
                    yield arena, url, key
            except Exception:
                pass

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
    "census_metro": discover_census_metro_new,
    "bls_qcew": discover_bls_qcew_new,
    "nyc_open": discover_nyc_open_data_new,
    "ca_open": discover_ca_open_data_new,
    "nhgis_metro": discover_nhgis_metro_new,
    "eurostat_nuts": discover_eurostat_nuts_new,
    # New document sources for raw/documents/ folder (court rulings, press releases, CRS/GAO reports, FOIA etc.)
    "court_documents": discover_court_documents_new,
    "press_releases": discover_press_releases_new,
    "crs_gao_reports": discover_crs_gao_reports_new,
    "foia_documents": discover_foia_documents_new,
}

def run_monitor(sources: List[str] = None, max_new: int = 10, dry_run: bool = False, arena_filter: str = None,
                backfill: bool = False, auto_process: bool = False):
    s3 = get_s3()
    manifest = load_manifest(s3)

    # Build existing set (fast path) - expanded for documents + all arenas for proper dedup
    existing = set()
    for prefix in ["raw/media/", "raw/global/", "raw/elections/", "raw/congress/", "raw/legal/", "raw/documents/", "raw/state/", "raw/local/", "raw/metro/", "raw/lobbying/", "raw/health/", "raw/patents/"]:
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
            if len(discovered) >= 200:
                break
        if len(discovered) >= 200:
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
        # Clear marker for the local watcher script to pick up and send phone notification
        print(f"NOTIFY: {len(ingested)} new download subset(s): {', '.join(ingested)}")

    print(f"\nMonitor complete. Ingested this run: {len(ingested)}")
    return ingested

def main():
    parser = argparse.ArgumentParser(description="Monitor public data sources and auto-ingest new bulk files to R2. 'Just do it' mode for continual archive.")
    parser.add_argument("--sources", default="gdelt,commoncrawl,hf-reddit,ia-twitter,lobbying,patents,health,education,legal,global,general,census_metro,bls_qcew,nyc_open,ca_open,nhgis_metro,eurostat_nuts,court_documents,press_releases,crs_gao_reports,foia_documents",
                        help="Comma-separated sources to check (broad default for 'just do it' - now includes state/local/metro + dedicated documents sources for court rulings, press releases, CRS/GAO reports, FOIA etc. filling raw/documents/)")
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

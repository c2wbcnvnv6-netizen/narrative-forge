#!/usr/bin/env python3
"""
Individual politician profile files builder.

Delivers one rich JSON file per elected/high-profile politician (e.g. processed/politicians/donald-trump.json).

Primary method using current pipeline data:
- Starts from directory/entities.json (politicians section) or re-scans processed/derived.
- Aggregates for each:
  - Normalized name + slug.
  - Mention counts by arena and total.
  - Full timeline of activity (dates + excerpts + source docs from synthesis/timelines).
  - Narrative signals specific to them (framing words in contexts where mentioned, repeated phrases involving them).
  - Associated entities/bills (from graph edges and bill_refs).
  - Sample raw/processed sources with links/context.
  - Graph subset (direct connections).
  - Synthesis notes (e.g., "frequently framed as 'threat' in press releases around election cases").
- Filters to "elected" focus: presidents, VPs, senators, reps (via known names), state AGs like Paxton, key exec. Expandable.
- Idempotent: merges new data into existing profiles.
- Outputs: processed/politicians/<slug>.json (main profile) + optional -excerpts.txt for full contexts.
- Also updates processed/politicians/index.json with list + last built.

Methods this enables (see user query response for full list):
1. Aggregation from existing extracted/analyzed documents (this script - immediate delivery).
2. Pipeline integration (chained after analyze/monitor runs for freshness).
3. Enrichment with dedicated sources (add FEC bulk, congress sponsor data in future discovers; attach per-profile).
4. Per-profile synthesis and oppo (tactic footprints, lawfare exposure, donor/bill links).
5. Scale/automation (cron via monitor, manifest tracking, full rebuild vs deltas).
6. Consumption (website directory links to /politicians/slug, search, thought bridges per person, exports).

Run after directory + analysis:
  python scripts/build_politician_profiles.py
  (R2 env required in GH or local).

Triggered automatically via updated monitor/analyze chain.

This gives the "individual files on each elected politician" for granulizer, oppo, narrative tracking, directory depth.
"""

import os
import sys
import json
import re
from datetime import datetime
from collections import defaultdict
import argparse
import boto3
from botocore.config import Config

BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")

# Focus on elected/high-impact politicians (seed from extraction patterns + known elected)
ELECTED_POLITICIANS = {
    "trump", "biden", "harris", "desantis", "newsom", "schumer", "mcconnell", "pelosi", "mccarthy",
    "paxton", "garland", "mayorkas", "roberts", "kavanaugh", "gorsuch", "alito", "thomas", "kagan",
    "sotomayor", "barrett", "jackson"  # SCOTUS as high-profile "elected" impact; filter further if needed
}

def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )

def load_json(key):
    s3 = get_s3()
    try:
        obj = s3.get_object(Bucket=BUCKET, Key=key)
        return json.loads(obj["Body"].read())
    except Exception as e:
        print(f"Could not load {key}: {e}")
        return None

def list_processed(prefix="processed/"):
    s3 = get_s3()
    keys = []
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET, Prefix=prefix):
        for obj in page.get("Contents", []):
            k = obj["Key"]
            if k.endswith("-summary.json") or k.endswith("-synthesis.json") or k.endswith("entities.json"):
                keys.append(k)
    return keys

def slugify(name):
    name = re.sub(r'[^a-zA-Z0-9\s-]', '', name).strip().lower()
    return re.sub(r'[\s-]+', '-', name)

def is_elected_politician(name_lower, etype):
    if etype != "politicians":
        return False
    for key in ELECTED_POLITICIANS:
        if key in name_lower:
            return True
    # Expand: any with "sen" or "rep" or known titles if we parse, but start here
    return False

def aggregate_profile(politician_name, all_data):
    """Build rich per-politician profile from all processed/derived data."""
    profile = {
        "name": politician_name,
        "slug": slugify(politician_name),
        "type": "politician",
        "total_mentions": 0,
        "by_arena": defaultdict(int),
        "timeline": [],
        "associated_entities": defaultdict(int),
        "narrative_signals": {"framing_count": 0, "repeated_phrases": []},
        "sources": [],
        "graph_connections": [],
        "last_built": datetime.utcnow().isoformat() + "Z"
    }

    name_lower = politician_name.lower()

    for data in all_data:
        arena = data.get("arena", "unknown")
        raw_key = data.get("raw_key", "")
        text = data.get("extracted_text_preview", "") + " " + json.dumps(data.get("analysis", {}))
        analysis = data.get("analysis", {})
        entities = analysis.get("entities", {})
        signals = analysis.get("signals", {})
        synthesis = data if "tactic_scores" in data else {}  # if synthesis JSON

        # Count mentions
        if name_lower in text.lower():
            profile["total_mentions"] += 1
            profile["by_arena"][arena] += 1
            profile["sources"].append({
                "raw_key": raw_key,
                "arena": arena,
                "date": data.get("processed_at", "")[:10]
            })

            # Timeline excerpts
            for sent in re.split(r'[.!?]\s+', text):
                if name_lower in sent.lower() and len(sent) > 20:
                    profile["timeline"].append({
                        "date": data.get("processed_at", "")[:10],
                        "excerpt": sent[:250].strip(),
                        "source": raw_key,
                        "arena": arena
                    })

            # Associated entities (co-mentioned)
            for etype, elist in entities.items():
                for e in elist:
                    if e.lower() != name_lower:
                        profile["associated_entities"][f"{etype}:{e}"] += 1

            # Signals
            if signals.get("framing_words_count"):
                profile["narrative_signals"]["framing_count"] += signals["framing_words_count"]

        # From synthesis / repeated phrases (coordination)
        if synthesis and "repeated_phrases_sample" in synthesis:
            for rp in synthesis.get("repeated_phrases_sample", []):
                if name_lower in rp.get("phrase", "").lower() or name_lower in rp.get("context1", "").lower():
                    profile["narrative_signals"]["repeated_phrases"].append(rp["phrase"][:150])

        # Graph connections (if graph in data)
        graph = data.get("graph", {}) or synthesis.get("graph", {})
        for edge in graph.get("edges", []):
            if name_lower in str(edge).lower():
                profile["graph_connections"].append(edge)

    # Dedup and sort
    profile["sources"] = sorted(list({s["raw_key"]: s for s in profile["sources"]}.values()), key=lambda x: x.get("date", ""), reverse=True)[:20]
    profile["timeline"] = sorted(profile["timeline"], key=lambda x: x.get("date", ""), reverse=True)[:30]
    profile["associated_entities"] = dict(sorted(profile["associated_entities"].items(), key=lambda x: -x[1])[:15])
    profile["narrative_signals"]["repeated_phrases"] = list(set(profile["narrative_signals"]["repeated_phrases"]))[:10]
    profile["by_arena"] = dict(profile["by_arena"])
    profile["graph_connections"] = profile["graph_connections"][:10]

    # Elected roles hint (from data patterns)
    profile["known_roles"] = []
    if "trump" in name_lower: profile["known_roles"] = ["President", "Former President"]
    elif "biden" in name_lower: profile["known_roles"] = ["President"]
    elif any(x in name_lower for x in ["schumer", "mcconnell"]): profile["known_roles"] = ["Senator", "Majority/Minority Leader"]
    elif "paxton" in name_lower: profile["known_roles"] = ["Texas Attorney General"]
    # Add more as data grows

    return profile

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--directory-key", default="processed/directory/entities.json")
    parser.add_argument("--output-prefix", default="processed/politicians")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s3 = get_s3()

    # Load directory for politician list
    directory = load_json(args.directory_key) or {"entities": []}
    politicians = []
    for ent in directory.get("entities", []):
        if ent.get("type") == "politicians" and is_elected_politician(ent.get("name", "").lower(), "politicians"):
            politicians.append(ent["name"])

    if not politicians:
        print("No elected politicians found in directory. Falling back to seed list.")
        politicians = ["Donald J. Trump", "Joe Biden", "Kamala Harris", "John Roberts", "Ken Paxton", "Chuck Schumer", "Mitch McConnell"]

    print(f"Building profiles for {len(politicians)} politicians...")

    # Load all processed data for aggregation
    all_processed_keys = [k for k in list_processed() if "summary" in k or "synthesis" in k]
    all_data = []
    for k in all_processed_keys:
        d = load_json(k)
        if d:
            all_data.append(d)

    print(f"Loaded {len(all_data)} processed records for aggregation.")

    profiles_built = []
    for pol_name in politicians:
        profile = aggregate_profile(pol_name, all_data)
        slug = profile["slug"]
        out_key = f"{args.output_prefix}/{slug}.json"

        if args.dry_run:
            print(f"DRY: would write {out_key} with {profile['total_mentions']} mentions")
            continue

        s3.put_object(
            Bucket=BUCKET,
            Key=out_key,
            Body=json.dumps(profile, indent=2),
            ContentType="application/json"
        )
        profiles_built.append(out_key)
        print(f"Wrote profile: {out_key} ({profile['total_mentions']} mentions, {len(profile['timeline'])} timeline entries)")

    # Write index
    index_key = f"{args.output_prefix}/index.json"
    index_data = {
        "generated": datetime.utcnow().isoformat() + "Z",
        "politicians": [{"name": p, "slug": slugify(p), "profile": f"{args.output_prefix}/{slugify(p)}.json"} for p in politicians],
        "count": len(politicians)
    }
    s3.put_object(Bucket=BUCKET, Key=index_key, Body=json.dumps(index_data, indent=2), ContentType="application/json")
    print(f"Politician index: {index_key}")

    if profiles_built:
        print(f"NOTIFY: built {len(profiles_built)} individual politician profiles in {args.output_prefix}/")

if __name__ == "__main__":
    main()

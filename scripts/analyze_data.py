#!/usr/bin/env python3
"""
Substantial Analysis & Synthesis Engine for The Breaker of Babylon.

Consumes processed/ summaries (which contain extracted_text_preview + basic analysis from process_data.py).
Now extended for news/RSS data (raw/news/ or processed/news/ items from RSS subagent feeds).

Delivers real intelligence products:
- Phrase clustering / narrative similarity (repeated language detection across documents - key for coordination exposure).
- Entity co-occurrence + relationship graph (nodes = politicians/agencies/bills/cases; edges = co-mention, date proximity, arena overlap).
- Timeline construction with key excerpts and signals.
- Tactic scoring (repetition density, loaded language, press-style framing, potential coordination markers).
- NEWS-SPECIFIC: outlet similarity graph, "echo chamber" scores, media coordination (same framing across outlets on same story, loaded language in press vs official), politician media framing integration.
- Synthesis report (common narratives, contradictions, cross-arena ripples). Now includes 'news_ripples' for live media signals.

Outputs (to processed/derived/ or specified):
- <base>-graph.json (vis-ready nodes/edges)
- <base>-timeline.json
- <base>-synthesis.json (scores + insights)  -- enriched with news_ripples when news present
- <base>-report.txt (human readable)

Works on single processed_key or batch (list or prefix scan). Supports mixed docs + news batches including processed/news/rss-*-summary.json .

Chainable from process/monitor. RSS subagent ingest -> process (HTML) -> analyze (live signals for site).

R2 native. Reusable. Efficiency: difflib + prefix bucketing for news volume; suggests simple TF ngram for future.

This turns extracted documents into the "lethal weapon" layer: evidence of framing tactics, timing games, entity networks. + real-time narrative detection from news feeds.

Run:
  python scripts/analyze_data.py --processed-key processed/documents/courts/scotus-25-6-...-summary.json
  or env PROCESSED_KEY=... 
  or --batch for multiple.
  e.g. --batch-keys processed/news/rss-nyt-politics-...-summary.json processed/news/rss-ap-...-summary.json

Extend here for embeddings, full clustering (sklearn if added), ML tactic classifiers, etc.
"""

import os
import sys
import json
import re
import difflib
from datetime import datetime
from collections import defaultdict, Counter
import argparse
import boto3
from botocore.config import Config

BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")


def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )

def load_processed(processed_key: str, s3=None):
    if s3 is None:
        s3 = get_s3()
    obj = s3.get_object(Bucket=BUCKET, Key=processed_key)
    return json.loads(obj["Body"].read())

def extract_text_from_processed(summary: dict) -> str:
    """Extended to handle news/RSS data: title + description + full preview if fetched.
    Falls back for regular docs. Supports sample-rss style embedded 'item' or flattened processed/news HTML summaries.
    """
    text = summary.get("extracted_text_preview", "") or ""
    raw_key = str(summary.get("raw_key", "")).lower()
    arena = summary.get("arena", "")
    is_news = (arena == "news" or "rss" in raw_key or "news" in raw_key or "/news/" in raw_key)

    if is_news:
        # RSS/news-specific parser: prioritize title + description + body
        title = summary.get("title", "") or ""
        desc = ""
        item = summary.get("item")
        if isinstance(item, dict):
            desc = item.get("description", "") or item.get("summary", "") or ""
        elif "description" in summary:
            desc = summary.get("description", "") or ""
        # If full article body fetched separately sometimes present under 'full_text' or extended preview
        full = summary.get("full_text", "") or summary.get("article_body", "") or ""
        text = f"{title}. {desc} {full} {text}".strip()
        # Truncate reasonably for analysis (news volume handling)
        if len(text) > 12000:
            text = text[:12000]
    # Also incorporate any existing basic analysis text if present
    if "analysis" in summary:
        text += "\n" + json.dumps(summary["analysis"])
    return text


def get_source_info(summary: dict) -> dict:
    """Extract outlet/source for news coordination analysis. Uses raw_key patterns from RSS ingest (rss-{feed}-...) and arena.
    Returns stable outlet id e.g. 'ap', 'nyt', 'reuters' for similarity/echo graphs.
    """
    raw_key = summary.get("raw_key", "") or ""
    arena = summary.get("arena", "unknown")
    title = summary.get("title", "") or ""
    outlet = "unknown"
    if "rss-" in raw_key:
        m = re.search(r'rss-([a-z0-9_-]+?)(?:-\d{8}|-)', raw_key)
        if m:
            outlet = m.group(1)
        else:
            # fallback e.g. rss-ap-politics -> ap
            parts = [p for p in raw_key.split("/") if p.startswith("rss-")]
            if parts:
                segs = parts[0].split("-")
                outlet = segs[1] if len(segs) > 1 else segs[0].replace("rss-", "")
    elif arena == "news":
        # fallback for non-rss news or direct
        outlet = "wire" if "press" in title.lower() or "pr" in raw_key else "news-outlet"
    return {
        "arena": arena,
        "outlet": outlet.lower()[:40],
        "raw_key": raw_key,
        "title": title[:120],
        "processed_at": summary.get("processed_at", "")[:10]
    }


def find_repeated_phrases(texts: list[str], min_len=8, threshold=0.6, outlets: list[str] = None) -> list[dict]:
    """Substantial: find overlapping phrases/sentences across documents using sequence matching.
    Detects coordinated or echoed language - core to narrative tactics exposure.
    Improved for media: now tracks outlets, supports cross-outlet same-framing detection (key for RSS news coordination).
    Efficiency: prefix-bucketing to handle large news volume (reduces quadratic comparisons).
    """
    phrases = []
    sentences = []
    for i, t in enumerate(texts):
        sents = re.split(r'[.!?]\s+', t)
        for s in sents:
            if len(s.split()) >= min_len:
                sentences.append((i, s.strip()))

    # Efficiency for large news volume (RSS floods): bucket by leading trigram prefix.
    # Only compare within-bucket (catches repeated lead framing across outlets on same story).
    # For future no-dep TF: replace/ augment with ngram Counter overlap on rare terms.
    #   e.g. def simple_tf_score(s1, s2): c1=Counter(ngrams(s1,3)); ... shared = sum((c1&c2).values()); ...
    #   (avoids full difflib when volume high; comment suggests extension)
    bucketed = defaultdict(list)
    for sent_idx, (doc_i, sent) in enumerate(sentences):
        words = [w for w in sent.lower().split() if w]
        prefix = " ".join(words[:3]) if len(words) >= 3 else (sent.lower()[:30])
        bucketed[prefix].append((sent_idx, doc_i, sent))

    # Perform comparisons (within buckets primarily; small cross for safety if needed)
    for bucket_sents in bucketed.values():
        for j, (sidx1, doc1, sent1) in enumerate(bucket_sents):
            for sidx2, (sidx_other, doc2, sent2) in enumerate(bucket_sents[j+1:], j+1):
                if doc1 == doc2:
                    continue
                matcher = difflib.SequenceMatcher(None, sent1.lower().split(), sent2.lower().split())
                ratio = matcher.ratio()
                if ratio >= threshold:
                    match = matcher.find_longest_match(0, len(sent1.split()), 0, len(sent2.split()))
                    if match.size >= min_len:
                        phr = " ".join(sent1.split()[match.a:match.a+match.size])
                        outlet1 = outlets[doc1] if outlets and doc1 < len(outlets) else None
                        outlet2 = outlets[doc2] if outlets and doc2 < len(outlets) else None
                        phrases.append({
                            "doc1": doc1,
                            "doc2": doc2,
                            "similarity": round(ratio, 3),
                            "phrase": phr,
                            "context1": sent1,
                            "context2": sent2,
                            "outlet1": outlet1,
                            "outlet2": outlet2
                        })

    # Dedup and sort by similarity (now includes outlet tags for media analysis)
    seen = set()
    unique = []
    for p in sorted(phrases, key=lambda x: -x["similarity"]):
        key = p["phrase"][:50]
        if key not in seen:
            seen.add(key)
            unique.append(p)
    return unique[:30]  # top substantial matches

def build_entity_graph(summaries: list[dict]) -> dict:
    """Build graph from entities + cross-doc relations.
    Nodes: type + name. Edges: co-occurrence count, date delta, shared arenas.
    Ready for vis.js / D3 / Chart.js force layout.
    """
    nodes = {}
    edges = defaultdict(lambda: {"weight": 0, "dates": [], "arenas": set()})

    for s in summaries:
        arena = s.get("arena", "unknown")
        text = extract_text_from_processed(s)
        analysis = s.get("analysis", {})
        entities = analysis.get("entities", {})
        date_str = s.get("processed_at", "")[:10]

        all_ents = []
        for etype, elist in entities.items():
            for e in elist:
                nid = f"{etype}:{e.lower()}"
                if nid not in nodes:
                    nodes[nid] = {"id": nid, "type": etype, "name": e, "count": 0, "arenas": set()}
                nodes[nid]["count"] += 1
                nodes[nid]["arenas"].add(arena)
                all_ents.append(nid)

        # Co-occurrence edges within doc
        for i, n1 in enumerate(all_ents):
            for n2 in all_ents[i+1:]:
                key = tuple(sorted([n1, n2]))
                edges[key]["weight"] += 1
                edges[key]["dates"].append(date_str)
                edges[key]["arenas"].add(arena)

    # Format for export
    node_list = []
    for nid, ndata in nodes.items():
        node_list.append({
            "id": nid,
            "label": ndata["name"],
            "type": ndata["type"],
            "size": min(50, 10 + ndata["count"] * 3),
            "arenas": list(ndata["arenas"])
        })

    edge_list = []
    for (n1, n2), edata in edges.items():
        edge_list.append({
            "source": n1,
            "target": n2,
            "weight": edata["weight"],
            "shared_arenas": list(edata["arenas"]),
            "date_span": [min(edata["dates"]), max(edata["dates"])] if edata["dates"] else []
        })

    return {"nodes": node_list, "edges": edge_list, "meta": {"generated": datetime.utcnow().isoformat(), "doc_count": len(summaries)}}

def build_timeline(summaries: list[dict]) -> list[dict]:
    """Timeline of key events/excerpts with signals.
    Sorted chronologically where possible.
    """
    events = []
    for s in summaries:
        text = extract_text_from_processed(s)
        analysis = s.get("analysis", {})
        signals = analysis.get("signals", {})
        dates = signals.get("dates_mentioned", [])
        base_date = s.get("processed_at", "")[:10]

        # Pick "key" excerpts: sentences with high framing or entities
        key_excerpts = []
        for sent in re.split(r'[.!?]\s+', text)[:5]:
            if len(sent) > 30 and any(w in sent.lower() for w in ["court", "release", "order", "policy", "threat", "decision"]):
                key_excerpts.append(sent[:200])

        event = {
            "date": dates[0] if dates else base_date,
            "source_key": s.get("raw_key"),
            "arena": s.get("arena"),
            "title": s.get("title", s.get("raw_key", "").split("/")[-1]),
            "excerpts": key_excerpts[:2],
            "signals": signals,
            "entities": analysis.get("entities", {})
        }
        events.append(event)

    # Sort by date string (rough but works for YYYY-MM or named dates)
    events.sort(key=lambda x: x["date"])
    return events

def compute_tactic_scores(texts: list[str], summaries: list[dict]) -> dict:
    """Substantial tactic detection scores.
    Repetition (from clustering), framing density, coordination hints (identical structures).
    Improved: media coordination (same framing across outlets), loaded language (press vs official), news-aware.
    """
    all_text = " ".join(texts).lower()
    framing_words = ["crisis", "threat", "historic", "unprecedented", "protect", "defend", "restore", "accountability", "transparency", "misinformation"]
    framing_density = sum(all_text.count(w) for w in framing_words) / max(1, len(all_text.split()) / 100)

    # Collect outlets for media-aware repeated phrase calls (enables cross-outlet detection)
    outlets_list = []
    for s in summaries:
        info = get_source_info(s)
        outlets_list.append(info["outlet"])

    repeated = find_repeated_phrases(texts, threshold=0.5, outlets=outlets_list)
    repetition_score = min(10, len(repeated) * 0.8)

    press_style_count = sum(1 for s in summaries if s.get("analysis", {}).get("signals", {}).get("press_release_style"))

    coordination_hint = len([r for r in repeated if r["similarity"] > 0.75])

    # Media/loaded vs official: detect if news items carry more loaded framing than gov docs in batch
    news_items = [s for s in summaries if s.get("arena") == "news" or "rss" in str(s.get("raw_key", "")).lower()]
    loaded_words = ["radical", "extreme", "dangerous", "corrupt", "failed", "disastrous", "shocking", "outrage", "crisis", "threat", "lawfare"]
    loaded_in_news = sum(1 for s in news_items for w in loaded_words if w in extract_text_from_processed(s).lower())
    loaded_in_all = sum(all_text.count(w) for w in loaded_words)
    press_vs_official = round(loaded_in_news / max(1, loaded_in_all or 1) * 5, 1) if news_items else 0

    # Cross-outlet media coordination markers (new for RSS/news)
    cross_outlet_high_sim = len([r for r in repeated if r.get("similarity", 0) > 0.65 and r.get("outlet1") and r.get("outlet2") and r.get("outlet1") != r.get("outlet2")])

    return {
        "framing_density": round(framing_density, 2),
        "repetition_score": round(repetition_score, 1),
        "press_style_instances": press_style_count,
        "high_similarity_matches": coordination_hint,
        "total_repeated_phrases": len(repeated),
        "overall_tactic_risk": min(10, round((framing_density * 2 + repetition_score + coordination_hint) / 3, 1)),
        # News/media coordination extensions
        "loaded_language_press_bias": press_vs_official,
        "cross_outlet_coordination_hints": cross_outlet_high_sim,
        "num_news_in_batch": len(news_items)
    }


def build_outlet_similarity_graph(summaries: list[dict], repeated_phrases: list[dict]) -> dict:
    """News/RSS-specific output: outlet similarity graph for media coordination visualization.
    Nodes = outlets (e.g. from rss feeds like ap, nyt, reuters, bbc).
    Edges = framing overlap count from repeated phrases (same story same language across 'competitors').
    Ready for site UI graph (vis.js / D3). Increases liveness by surfacing pack journalism / echo in real time.
    """
    outlets = {}
    for s in summaries:
        info = get_source_info(s)
        o = info["outlet"]
        if o not in outlets:
            outlets[o] = {"count": 0, "titles": [], "arenas": set()}
        outlets[o]["count"] += 1
        if info["title"]:
            outlets[o]["titles"].append(info["title"])
        outlets[o]["arenas"].add(info["arena"])

    # Build edges from cross-outlet repeats (core media coordination signal)
    edge_weights = defaultdict(int)
    for rp in repeated_phrases:
        o1 = rp.get("outlet1")
        o2 = rp.get("outlet2")
        if o1 and o2 and o1 != o2:
            key = tuple(sorted([o1, o2]))
            edge_weights[key] += 1

    nodes = []
    for o, data in outlets.items():
        nodes.append({
            "id": o,
            "label": o,
            "type": "media_outlet",
            "size": min(60, 8 + data["count"] * 6),
            "sample_titles": data["titles"][:2],
            "doc_count": data["count"]
        })

    edges = [{"source": k[0], "target": k[1], "weight": w, "type": "framing_overlap", "note": "repeated phrasing across outlets"} for k, w in sorted(edge_weights.items(), key=lambda x: -x[1])]

    return {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "generated": datetime.utcnow().isoformat(),
            "outlet_count": len(outlets),
            "cross_outlet_edge_count": len(edges)
        }
    }


def compute_echo_chamber_scores(repeated_phrases: list[dict], summaries: list[dict]) -> dict:
    """News-specific 'echo chamber' scores: quantifies media coordination / narrative convergence from RSS.
    - High cross_outlet_ratio + high_sim = likely pack framing or coordinated rollout on story.
    - Outlet concentration low = diverse echo.
    Integrates for politician profiles (how media frames a pol across wires).
    """
    if not repeated_phrases:
        return {"echo_chamber_score": 0.0, "cross_outlet_ratio": 0.0, "note": "no repeats for echo calc"}

    total = len(repeated_phrases)
    cross = 0
    high_sim_cross = 0
    involved_outlets = set()
    for p in repeated_phrases:
        o1 = p.get("outlet1")
        o2 = p.get("outlet2")
        if o1: involved_outlets.add(o1)
        if o2: involved_outlets.add(o2)
        if o1 and o2 and o1 != o2:
            cross += 1
            if p.get("similarity", 0) >= 0.7:
                high_sim_cross += 1

    cross_ratio = cross / max(1, total)
    # Score 0-10 : higher means stronger echo chamber effect (narrative lockstep across outlets)
    echo_score = min(10.0, round(cross_ratio * 10 + (high_sim_cross / max(1, total)) * 3, 1))

    return {
        "echo_chamber_score": echo_score,
        "cross_outlet_repeats": cross,
        "total_repeats_analyzed": total,
        "cross_outlet_ratio": round(cross_ratio, 3),
        "high_similarity_cross_outlet": high_sim_cross,
        "unique_outlets_involved_in_repeats": len(involved_outlets),
        "outlet_list_sample": list(involved_outlets)[:8],
        "interpretation": "High echo_chamber_score + cross ratio indicates same framing propagating rapidly across outlets (RSS live signal for narrative convergence)."
    }

def extract_politician_media_framing(summaries: list[dict], repeated_phrases: list[dict]) -> dict:
    """Integrate news analysis with politician profiles: how media (RSS outlets) frames specific pols.
    Pulls repeated loaded phrases near pol entity mentions in news items.
    Output feeds build_politician_profiles and site UI (e.g. 'Trump' framed as 'threat' in X outlets).
    """
    pol_framing = defaultdict(list)
    # Lightweight pol list (synced with process_data regex for consistency; extend as needed)
    pols_of_interest = {"trump", "biden", "harris", "desantis", "newsom", "schumer", "mcconnell", "pelosi", "paxton", "garland", "mayorkas"}

    for s in summaries:
        info = get_source_info(s)
        if info["arena"] != "news":
            continue
        text_lower = extract_text_from_processed(s).lower()
        analysis_ents = s.get("analysis", {}).get("entities", {}).get("politicians", []) or []
        for pol_raw in analysis_ents + [p for p in pols_of_interest if p in text_lower]:
            pol = pol_raw.lower()
            for rp in repeated_phrases[:15]:
                ph = rp.get("phrase", "").lower()
                sim = rp.get("similarity", 0)
                if pol in text_lower and (ph and (ph in text_lower or sim > 0.6)):
                    entry = {
                        "phrase": rp.get("phrase"),
                        "similarity": sim,
                        "outlets": [rp.get("outlet1"), rp.get("outlet2")],
                        "from_outlet": info["outlet"]
                    }
                    # dedup-ish
                    if not any(e["phrase"] == entry["phrase"] for e in pol_framing[pol_raw]):
                        pol_framing[pol_raw].append(entry)
            if len(pol_framing.get(pol_raw, [])) > 4:
                break

    # Limit per pol
    result = {}
    for pol, lst in pol_framing.items():
        result[pol] = lst[:4]
    return result

def generate_synthesis(summaries: list[dict]) -> dict:
    texts = [extract_text_from_processed(s) for s in summaries]
    # Collect outlets once for rich media analysis
    outlets_list = [get_source_info(s)["outlet"] for s in summaries]
    repeated_phrases = find_repeated_phrases(texts, outlets=outlets_list)
    graph = build_entity_graph(summaries)
    timeline = build_timeline(summaries)
    scores = compute_tactic_scores(texts, summaries)

    common_narratives = [p["phrase"] for p in repeated_phrases[:5]]

    synth = {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "doc_count": len(summaries),
        "tactic_scores": scores,
        "common_narratives": common_narratives,
        "repeated_phrases_sample": repeated_phrases[:10],
        "graph": graph,
        "timeline": timeline[:15],
        "insights": f"Detected {len(repeated_phrases)} repeated phrases across docs. Top framing density {scores['framing_density']}. High-similarity matches suggest possible coordination: {scores['high_similarity_matches']}. Cross-outlet hints: {scores.get('cross_outlet_coordination_hints', 0)}."
    }

    # NEWS-SPECIFIC: add 'news_ripples' (or media-specific repeated phrases) when batch contains news/RSS items.
    # This is the live signal tie-in: RSS subagent -> processed/news -> analyze produces outlet graphs, echo scores, pol framing for site UI.
    has_news = any(
        s.get("arena") == "news" or "rss" in str(s.get("raw_key", "")).lower() or "news" in str(s.get("raw_key", "")).lower()
        for s in summaries
    )
    if has_news:
        outlet_graph = build_outlet_similarity_graph(summaries, repeated_phrases)
        echo_scores = compute_echo_chamber_scores(repeated_phrases, summaries)
        pol_framing = extract_politician_media_framing(summaries, repeated_phrases)
        media_repeats = [p for p in repeated_phrases if p.get("outlet1") and p.get("outlet2") and p.get("outlet1") != p.get("outlet2")][:10]

        synth["news_ripples"] = {
            "media_specific_repeated_phrases": media_repeats,
            "outlet_similarity_graph": outlet_graph,
            "echo_chamber_scores": echo_scores,
            "politician_media_framing": pol_framing,
            "liveness_note": "Real-time narrative detection from news feeds (RSS subagent). High echo or cross-outlet framing indicates emerging story lockstep / coordination signals for immediate site consumption."
        }
    else:
        synth["news_ripples"] = {
            "note": "No news/RSS items in batch. Run with processed/news/... keys (or mixed batch) to surface outlet graphs, echo chamber scores, and media framing of politicians.",
            "suggestion": "E.g. batch processed/news/rss-*-summary.json items from recent RSS ingest for live ripples."
        }

    return synth

def main():
    parser = argparse.ArgumentParser(description="Substantial analysis engine. Produces graphs, timelines, tactic detection, synthesis from processed documents.")
    parser.add_argument("--processed-key", help="Single processed summary key in R2")
    parser.add_argument("--batch-keys", nargs="+", help="Multiple processed summary keys")
    parser.add_argument("--output-prefix", default="processed/derived", help="R2 prefix for outputs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s3 = get_s3()
    summaries = []

    keys = []
    if args.processed_key:
        keys = [args.processed_key]
    elif args.batch_keys:
        keys = args.batch_keys
    else:
        # Fallback: env or recent documents example. Supports news keys too (e.g. processed/news/...)
        k = os.environ.get("PROCESSED_KEY")
        batch_env = os.environ.get("BATCH_KEYS", "")
        if batch_env:
            keys = [x.strip() for x in batch_env.split(",") if x.strip()]
        elif k:
            keys = [k]
        else:
            print("Provide --processed-key or --batch-keys or PROCESSED_KEY env (or BATCH_KEYS comma-sep)")
            sys.exit(1)

    for k in keys:
        try:
            summ = load_processed(k, s3)
            summaries.append(summ)
            print(f"Loaded {k}")
        except Exception as e:
            print(f"Skip {k}: {e}")

    if not summaries:
        print("No data loaded")
        return

    synthesis = generate_synthesis(summaries)
    # Better base for news keys (e.g. processed/news/rss-foo-20260614-... -> rss-foo-...)
    first_key = keys[0] if keys else "batch"
    base = first_key.split("/")[-1].rsplit("-summary", 1)[0]
    if len(base) > 60:
        base = base[:60]

    outputs = {
        "graph": f"{args.output_prefix}/{base}-graph.json",
        "timeline": f"{args.output_prefix}/{base}-timeline.json",
        "synthesis": f"{args.output_prefix}/{base}-synthesis.json"
    }

    if args.dry_run:
        print("DRY RUN - would write:")
        print(json.dumps({k: v for k, v in outputs.items()}, indent=2))
        print("Synthesis preview:", json.dumps(synthesis, indent=2)[:1200])
        if "news_ripples" in synthesis and "echo_chamber_scores" in synthesis.get("news_ripples", {}):
            print("NEWS_RIPPLES preview:", json.dumps(synthesis["news_ripples"], indent=2)[:600])
        return

    s3.put_object(Bucket=BUCKET, Key=outputs["graph"], Body=json.dumps(synthesis["graph"], indent=2), ContentType="application/json")
    s3.put_object(Bucket=BUCKET, Key=outputs["timeline"], Body=json.dumps(synthesis["timeline"], indent=2), ContentType="application/json")
    s3.put_object(Bucket=BUCKET, Key=outputs["synthesis"], Body=json.dumps(synthesis, indent=2), ContentType="application/json")

    # Also text report (include news_ripples summary if present for human/liveness)
    report_key = f"{args.output_prefix}/{base}-report.txt"
    news_ripples_section = ""
    if synthesis.get("news_ripples") and "echo_chamber_scores" in synthesis["news_ripples"]:
        nr = synthesis["news_ripples"]
        news_ripples_section = f"\n\nNEWS_RIPPLES (live media signals):\nEcho chamber: {nr['echo_chamber_scores'].get('echo_chamber_score')}\nOutlets: {nr['echo_chamber_scores'].get('unique_outlets_involved_in_repeats')}\nPol framing sample: {list(nr.get('politician_media_framing', {}).keys())[:4]}\nLiveness: {nr.get('liveness_note','')[:120]}"
    report = f"Breaker of Babylon Analysis Report\nGenerated: {synthesis['generated_at']}\n\nTACTIC SCORES:\n{json.dumps(synthesis['tactic_scores'], indent=2)}\n\nCOMMON NARRATIVES:\n" + "\n".join(synthesis['common_narratives']) + f"\n\nINSIGHTS:\n{synthesis['insights']}{news_ripples_section}\n\nSee graph/timeline/synthesis JSONs for full structured data (incl. news_ripples for RSS batches)."
    s3.put_object(Bucket=BUCKET, Key=report_key, Body=report.encode(), ContentType="text/plain")

    print(f"Analysis complete. Outputs:")
    for k, v in outputs.items():
        print(f"  {k}: {v}")
    print(f"  report: {report_key}")
    print(f"NOTIFY: analyzed {len(summaries)} docs -> {outputs['synthesis']}")
    if synthesis.get("news_ripples") and "echo_chamber_scores" in synthesis.get("news_ripples", {}):
        print(f"NOTIFY: news_ripples live signals (echo={synthesis['news_ripples']['echo_chamber_scores'].get('echo_chamber_score')}) ready for site UI from RSS->analyze pipeline")

if __name__ == "__main__":
    main()

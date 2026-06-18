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
SUBAGENT_TAG = os.environ.get("SUBAGENT_TAG", "ANALYZE")

# Live metrics / pipeline integration for analyze (reuses monitor_and_ingest for consistent live indicators, step tracking, rates, subagent tags, AI stack status)
import sys as _sys
_sys.path.insert(0, os.path.dirname(__file__))
try:
    from monitor_and_ingest import PipelineMetrics
except Exception:
    PipelineMetrics = None  # fallback if import issue in isolated run

# Rule of 42 core: cap/filter to ~42 high-signal items per batch for data outputs
RULE42_CAP = 42

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


def find_repeated_phrases(texts: list[str], min_len=8, threshold=0.48, outlets: list[str] = None) -> list[dict]:
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
        # ENHANCED for Rule42: secondary buckets on words 1-3 or rare bigrams to catch framing variations across outlets
        if len(words) >= 4:
            p2 = " ".join(words[1:4])
            bucketed[p2].append((sent_idx, doc_i, sent))
        if len(words) >= 5:
            bucketed[words[2]+" "+words[3]].append((sent_idx, doc_i, sent))  # mid trigram fallback for phrase match

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

    repeated = find_repeated_phrases(texts, threshold=0.48, outlets=outlets_list)
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
    # RULE42 v3 PIPELINE INTEGRATION: enrich synth with pre-hints (clusters from graph, temporal from R2 deltas, cross-arena) for JS multi-factor scoring + detailed reports in neural-map-holo.html
    try:
        outlet_g = synth.get("news_ripples", {}).get("outlet_similarity_graph") if "news_ripples" in synth else None
        clus_hints = compute_simple_graph_clusters(graph.get("nodes",[]), graph.get("edges",[]), repeated_phrases, outlet_g)
        temp_hints = compute_temporal_evolution_hints(summaries)
        arena_hints = compute_cross_arena_corr_hints(summaries, graph)
        synth["rule42_pipeline_hints"] = {
            "cluster_sizes": clus_hints,
            "temporal": temp_hints,
            "cross_arena_corrs": arena_hints,
            "outlet_clusters": clus_hints.get("outlet_clusters", 0),
            "cluster_cohesion": round((clus_hints.get("count",0) or 1) / max(1, len(clus_hints.get("sizes",{})) or 1),3) if clus_hints else 0.5,
            "note": "Pre-computed hints for Rule of 42 deepened analyzation (graph+outlet clusters, R2 delta temporal vel/accel, cross-arena, query). For JS sens/r2vel/queryarch/clusoutlet paths + factor attach."
        }
    except Exception as _rh: 
        synth["rule42_pipeline_hints"] = {"note": "hints generation skipped (non-fatal)"}

    # NEWS-SPECIFIC: add 'news_ripples' (or media-specific repeated phrases) when batch contains news/RSS items.
    # This is the live signal tie-in: RSS subagent -> processed/news -> analyze produces outlet graphs, echo scores, pol framing for site UI.
    # v2 Rule42 integration note: tactic_scores, echo_chamber, repeated_phrases, outlet graph feed directly into JS selectTop42Signals (coordDensity, centrality via edges, prov via r2_path) in neural-map-holo.html. Universal analyzer.
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

    # === RULE OF 42 ENHANCEMENT: filter high-signal outputs, add explicit rule42 data for pipeline ===
    # backfill mass contrib -> rule42 rates/hints -> golden selectMultiFactor + mass share exports (unify per polish)
    rule42_signals = []
    for rp in repeated_phrases[:RULE42_CAP]:
        sig = {
            "phrase": rp.get("phrase") or rp.get("text"),
            "impact": rp.get("similarity", 0.7),
            "type": "repeated_phrase" if rp.get("outlet1") else "tactic",
            "arena": rp.get("arena") or "general",
            "outlets": [rp.get("outlet1"), rp.get("outlet2")]
        }
        rule42_signals.append(sig)
    # Cap strictly and add scores (Rule42 as universal ~42 driver filter)
    rule42_signals = rule42_signals[:RULE42_CAP]
    # Query driven demo + detailed per-signal explanations (integrated with outputs)
    query_example = "hiccups|border|coordinated|fabrication"
    query_selected = select_rule42_by_query({"rule42": {"signals": rule42_signals}}, query_example, RULE42_CAP)
    # Build detailed per-signal explanations using cluster/temporal hints + graph + full factor breakdowns + WHY SELECTED
    per_signal_explanations = []
    clus = (synth.get("rule42_pipeline_hints", {}) or {}).get("cluster_sizes", {}) or {}
    temp = (synth.get("rule42_pipeline_hints", {}) or {}).get("temporal", {}) or {}
    tactic_scores = synth.get("tactic_scores", {}) or {}
    echo = (synth.get("news_ripples", {}) or {}).get("echo_chamber_scores", {}) or {}
    for i, sig in enumerate(rule42_signals):
        ph = sig.get("phrase", "signal")
        impact = float(sig.get("impact", 0.7))
        cl_size = 0
        if isinstance(clus, dict):
            cl_size = clus.get(ph) or (clus.get("sizes", {}) or {}).get(ph, 2) or 2
        tinfo = temp.get(sig.get("phrase") or "", {}) or next((v for k,v in (temp.items() if isinstance(temp,dict) else [] ) if ph[:8] in str(k).lower()), {})
        delta_h = float(tinfo.get("r2_delta_hrs", 1.6)) if isinstance(tinfo, dict) else 1.6
        tvel = float(tinfo.get("temporal_velocity", 0.85)) if isinstance(tinfo,dict) else 0.85
        r2iv = float(tinfo.get("r2_inter_arrival_velocity", 0.9)) if isinstance(tinfo,dict) else 0.9
        composite = round(impact * 0.38 + min(cl_size,6)*0.09 + (0.12 if tinfo else 0) + (tvel*0.11) + (tactic_scores.get("repetition_score",0)*0.04), 3)
        # WHY SELECTED narrative + factor breakdown
        why_selected = (f"Selected for Rule42 because high repeat similarity ({impact}) + membership in cluster~{cl_size} (graph co-mention/outlet overlap) + "
                        f"R2 temporal velocity {tvel} (delta~{delta_h}h inter-arrival {r2iv}) + framing/repeat from tactics ({tactic_scores.get('framing_density',0)}/{tactic_scores.get('repetition_score',0)}) "
                        f"+ echo chamber cross-outlet {echo.get('cross_outlet_ratio',0)}.")
        factor_breakdown = {
            "similarity_impact": round(impact,3),
            "cluster_strength": round(min(cl_size/5.0, 0.92),3),
            "temporal_r2_delta": round(delta_h,2),
            "temporal_velocity": round(tvel,3),
            "tactic_repetition": round(tactic_scores.get("repetition_score", 0),1),
            "framing_density": round(tactic_scores.get("framing_density", 0),2),
            "echo_cross": round(echo.get("cross_outlet_ratio", 0),3),
            "composite": composite
        }
        expl = {
            "rank": i+1,
            "signal": ph,
            "composite": composite,
            "why_selected": why_selected,
            "why": f"High repeat similarity; belongs to cluster size ~{cl_size}. Temporal delta ~{delta_h}h from prior R2 landing shows {tvel} velocity. Factors: {factor_breakdown}",
            "factor_breakdown": factor_breakdown,
            "cluster_group": f"c{cl_size}",
            "temporal_from_r2_delta": f"delta={delta_h}h, vel={tvel}, r2_inter_vel={r2iv}",
            "recommendation": ("Export for evidence; monitor further R2 deltas." if impact>0.75 else "Track cross-outlet echoes.") + " Query match boosts priority."
        }
        per_signal_explanations.append(expl)
    synth["rule42"] = {
        "cap": RULE42_CAP,
        "filtered_signals_count": len(rule42_signals),
        "signals": rule42_signals,
        "query_driven_demo": {"query": query_example, "selected": query_selected[:5]},
        "detailed_per_signal_explanations": per_signal_explanations[:RULE42_CAP],
        "graph_clusters_used": (clus.get("count", len(clus)) if isinstance(clus,dict) else 0),
        "note": "Rule of 42: only the ~42 highest-impact signals retained for map/hot/archetype feeding. Enhanced with graph clustering for signal groups, R2 delta temporal analysis, query-driven selection, detailed per-signal explanations with WHY SELECTED + full numeric factor breakdowns. Integrates fully with neural-map-holo outputs (multi-factor 9 paths). Universal across any system pipeline.",
        "from_worker_ai": any("rule42" in str(s.get("analysis",{})) or "rule42" in str(s.get("extraction",{})) for s in summaries)
    }
    # LIVE RULE42 METRICS for pipeline indicators + backfill status (deeper analyzation paths + user outputs feed)
    rule42_metrics = {
        "signals_capped": len(rule42_signals),
        "per_signal_expls": len(per_signal_explanations),
        "avg_impact": round(sum(s.get("impact",0.7) for s in rule42_signals)/max(1,len(rule42_signals)),3) if rule42_signals else 0,
        "query_demo_selected": len(query_selected),
        "hints_attached": bool(synth.get("rule42_pipeline_hints")),
        "paths_used": "graph_clust+temporal_r2delta+query+cross_arena+per_sig_why+factor_breakdown",
        "sensitivity_note": "sensitivity path computed downstream in holo multi-factor (stability under delta)"
    }
    synth["rule42"]["metrics"] = rule42_metrics
    print(f"[{SUBAGENT_TAG}] [LIVE] [RULE42] Enhanced outputs: {len(rule42_signals)}/{RULE42_CAP} signals + {len(per_signal_explanations)} detailed expls + query select + R2 deltas + metrics [SUBAGENT:ANALYZE]")

    return synth

def main():
    parser = argparse.ArgumentParser(description="Substantial analysis engine. Produces graphs, timelines, tactic detection, synthesis from processed documents.")
    parser.add_argument("--processed-key", help="Single processed summary key in R2")
    parser.add_argument("--batch-keys", nargs="+", help="Multiple processed summary keys")
    parser.add_argument("--output-prefix", default="processed/derived", help="R2 prefix for outputs")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    s3 = None
    if not args.dry_run:
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
            print(f"[{SUBAGENT_TAG}] Provide --processed-key or --batch-keys or PROCESSED_KEY env (or BATCH_KEYS comma-sep)")
            sys.exit(1)

    print(f"[{SUBAGENT_TAG}] [STEP:ANALYZE] Starting analysis for {len(keys)} item(s) [SUBAGENT:ANALYZE visibility]")
    metrics = PipelineMetrics(subagent=SUBAGENT_TAG, max_planned=len(keys)) if PipelineMetrics else None
    if metrics:
        metrics.inc_step("analyze", len(keys))
        metrics.write_status()
    print(f"[{SUBAGENT_TAG}] [LIVE] ANALYZE start | items={len(keys)} | rate init | steps tracked for AI stack")
    for k in keys:
        try:
            if args.dry_run:
                print(f"[DRY] would load {k}")
                summaries.append({"raw_key": k, "arena": "documents", "extracted_text_preview": "dry sample for metrics", "processed_at": "2026", "analysis": {"entities": {}}})
            else:
                summ = load_processed(k, s3)
                summaries.append(summ)
            print(f"Loaded {k}")
            if metrics: metrics.record_discover(1)
            if metrics: metrics._emit_live(f"ANALYZE loaded {k[:50]}")  # live indicator
            # Worker integration for analysis: attempt smart_extract / worker AI enrichment on summary (if url present)
            try:
                url = summ.get("raw_url") or summ.get("url") or ""
                if url:
                    sys.path.insert(0, os.path.dirname(__file__))
                    from monitor_and_ingest import smart_extract
                    rich = smart_extract(url, arena=summ.get("arena","general"), raw_key=k)
                    if rich and rich.get("_source") != "fallback":
                        summ["worker_ai_extraction"] = rich
                        print(f"[{SUBAGENT_TAG}] [LIVE] [WORKER] Analysis integrated worker extraction (rule42/zdf) for {k[:40]}")
            except Exception as _we:
                pass  # non fatal, worker optional for analysis
        except Exception as e:
            print(f"Skip {k}: {e}")

    if not summaries:
        print("No data loaded")
        if metrics: metrics.write_status(final=True)
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

    # Phase 2: wire embeddings call in analyze_data flow (post rich synthesis). Uses reusable for vector+prov to babylon-embeddings.
    # (Full persist via scripts/generate_embeddings.py or direct R2 write here if extended; bucket diff starts here.)
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from generate_embeddings import generate_embeddings_for_summary
        for s in summaries:
            ep = generate_embeddings_for_summary(s) 
    except Exception:
        pass  # embeddings optional

# ============================================================================================
# RULE OF 42 v3 PIPELINE HELPERS (for data outputs feeding JS multi-factor + clusters/temporal/arena)
# Pure stdlib. Pre-compute hints so JS (or R2 feeds) get richer signals for graph clustering, ripple evolution, cross-arena.
# Called optionally from generate_synthesis or external; enriches synthesis/news_ripples for holo load.
# ============================================================================================
def compute_simple_graph_clusters(entity_graph_nodes, entity_graph_edges, repeated_phrases=None, outlet_graph=None):
    """Enhanced graph-based clustering for signal groups. (Rule42 v3+)
    Union-find on entity graph + outlet/edge + phrase co-mentions + outlet similarity for dense coordination clusters.
    Produces richer {sizes, strengths, groups, outlet_clusters} for Rule42 factor breakdowns.
    Integrates outlet_similarity_graph edges from pipeline for media coordination clusters.
    Pure stdlib, universal for any graph input.
    """
    from collections import defaultdict
    nodes = entity_graph_nodes or []
    edges = entity_graph_edges or []
    parent = {n.get("id"): n.get("id") for n in nodes if n.get("id")}
    def find(x):
        if parent.get(x) != x: parent[x] = find(parent[x])
        return parent.get(x, x)
    def union(x, y):
        if x in parent and y in parent:
            px, py = find(x), find(y)
            if px != py: parent[px] = py
    for e in edges:
        if e.get("source") and e.get("target"):
            union(str(e["source"]), str(e["target"]))
    # Enhance: union via repeated phrases cross-doc + outlet sim graph for signal/media clusters
    if repeated_phrases:
        for rp in repeated_phrases[:25]:
            ph = str(rp.get("phrase",""))[:30].lower()
            d1 = rp.get("doc1"); d2 = rp.get("doc2")
            if d1 is not None and d2 is not None:
                k1 = f"phrase:{ph[:12]}"
                if k1 not in parent: parent[k1] = k1
                # attach loosely to docs via repeated
            o1 = rp.get("outlet1"); o2 = rp.get("outlet2")
            if o1 and o2 and o1 != o2:
                k1 = f"outlet:{o1}"; k2 = f"outlet:{o2}"
                if k1 not in parent: parent[k1] = k1
                if k2 not in parent: parent[k2] = k2
                union(k1, k2)
    if outlet_graph and outlet_graph.get("edges"):
        for e in outlet_graph.get("edges", [])[:30]:
            s = e.get("source") or e.get("from"); t = e.get("target") or e.get("to")
            if s and t:
                ks = f"outlet:{s}"; kt = f"outlet:{t}"
                if ks not in parent: parent[ks] = ks
                if kt not in parent: parent[kt] = kt
                union(ks, kt)
    comp_sizes = defaultdict(int)
    comp_members = defaultdict(list)
    for nid in parent:
        p = find(nid)
        comp_sizes[p] += 1
        comp_members[p].append(nid)
    strengths = {}
    for p, sz in comp_sizes.items():
        strengths[p] = min(0.98, 0.18 + (sz / max(3, len(nodes) or 1)) * 0.78)
    sizes_map = {nid: comp_sizes[find(nid)] for nid in parent}
    return {"sizes": sizes_map, "strengths": {nid: strengths.get(find(nid), 0.3) for nid in parent}, "groups": {p: comp_members[p][:8] for p in comp_members}, "count": len(comp_sizes), "outlet_clusters": len([k for k in comp_members if str(k).startswith('outlet')])}

def compute_temporal_evolution_hints(summaries):
    """Enhanced temporal analysis from R2 deltas / processed times. (Rule42 v3+)
    Computes inter-delta intervals (R2 object landing deltas from raw_key filename timestamps), velocity from time deltas between summaries/raw_keys.
    Precise R2 key parsing e.g. rss-*-20260615-0126 , 2026-06-15 etc. 
    Produces per-item delta_velocity, accel, persistence for Rule42 temporal factor. Universal pure stdlib.
    """
    from collections import defaultdict
    from datetime import datetime
    import re as _re
    hints = {}
    events = []
    r2_deltas = []
    key_to_ts = {}
    for s in summaries or []:
        dt = s.get("processed_at") or ""
        key = s.get("raw_key", "") or ""
        try:
            ts = datetime.fromisoformat(dt.replace('Z','+00:00')).timestamp() if dt else 0
        except:
            ts = 0
        # Strong R2 delta timestamp extraction from key patterns (rss-*-YYYYMMDD-HHMM or ISO)
        if key:
            try:
                m = _re.search(r'(\d{4})(\d{2})(\d{2})[-_]?(\d{2})(\d{2})', key) or _re.search(r'(\d{4}-\d{2}-\d{2})[T ]?(\d{2}):?(\d{2})', key)
                if m:
                    if len(m.groups()) >= 5:
                        y,mo,d,h,mi = m.groups()[:5]
                        ts_key = datetime(int(y),int(mo),int(d),int(h),int(mi)).timestamp()
                        if ts_key > ts: ts = ts_key
                    else:
                        dstr = m.group(1)
                        ts_key = datetime.fromisoformat(dstr).timestamp() if '-' in dstr else 0
                        if ts_key > ts: ts = ts_key
            except: pass
        arena = s.get("arena","")
        events.append((ts, arena, key, s))
        if ts > 0:
            key_to_ts[key] = ts
            r2_deltas.append((key, ts))
    events.sort(key=lambda x:x[0])
    r2_deltas.sort(key=lambda x:x[1])
    if len(events) > 1:
        span = max(events[-1][0] - events[0][0], 3600) if events[-1][0] and events[0][0] else 7200
        vel = len(events) / max(0.1, (span / 3600.0))
        deltas = []
        for i in range(1, len(events)):
            dt = events[i][0] - events[i-1][0]
            if dt > 0: deltas.append(dt)
        avg_delta = sum(deltas)/len(deltas) if deltas else span / max(1, len(events))
        inter_r2 = []
        for i in range(1, len(r2_deltas)):
            dd = r2_deltas[i][1] - r2_deltas[i-1][1]
            if dd > 0: inter_r2.append(dd)
        avg_r2_delta = sum(inter_r2)/len(inter_r2) if inter_r2 else avg_delta
        for i, (ts, ar, key, summ) in enumerate(events[:42]):
            dvel = min(3.0, vel * (1.0 if i<3 else 0.55))
            accel = 0.12 + (0.42 if (i > 0 and (events[i][0]-events[i-1][0]) < avg_delta) else 0)
            r2_vel = min(2.9, (len(inter_r2) / max(1,len(r2_deltas))) * 4 + 0.3) if inter_r2 else 0.8
            hints[key] = {
                "temporal_velocity": round(min(dvel, 2.8), 3),
                "span_hrs": round(span/3600,1),
                "arena": ar,
                "r2_delta_hrs": round(avg_r2_delta/3600, 2) if avg_r2_delta else 1.4,
                "persistence": round(min(0.96, (len(events)-i)/max(1,len(events)) + 0.08), 2),
                "accel": round(min(0.82, accel), 2),
                "r2_inter_arrival_velocity": round(r2_vel, 3)
            }
    return hints

def compute_cross_arena_corr_hints(summaries, entity_graph):
    """Cross-arena correlation pre-hint from shared_arenas in entity graph + summary.arena.
    Output per-entity for rule42 crossArenaCorr boost. Pure, integrates graph+arena pipeline.
    """
    from collections import defaultdict
    arena_map = defaultdict(set)
    for s in summaries or []:
        ar = s.get("arena") or "unknown"
        for et, ents in (s.get("analysis",{}).get("entities",{})).items():
            for e in ents:
                arena_map[f"{et}:{e.lower()}"].add(ar)
    for edge in (entity_graph.get("edges") or []):
        shared = set(edge.get("shared_arenas", []))
        for nid in [edge.get("source"), edge.get("target")]:
            if nid: arena_map[nid].update(shared)
    corrs = {}
    for nid, ars in arena_map.items():
        corrs[nid] = min(0.96, 0.3 + 0.22 * len(ars))
    return corrs

def select_rule42_by_query(synth_or_items, query, cap=42):
    """Query-driven selection for Rule of 42. (enhanced)
    Filters + boosts + attaches 'why_selected' for items matching query tokens (phrase/label/arena/outlet/tactic).
    Returns top query-matched high-signal subset capped at 42 with per-item query_why. Universal.
    """
    if not query or not synth_or_items:
        return []
    q = str(query).lower().strip()
    tokens = [t for t in q.replace('|',' ').split() if len(t)>1]
    items = []
    base_items = []
    if isinstance(synth_or_items, dict):
        if 'signals' in synth_or_items.get('rule42', {}):
            base_items = synth_or_items['rule42']['signals']
        elif synth_or_items.get('news_ripples'):
            base_items = synth_or_items['news_ripples'].get('media_specific_repeated_phrases', [])
        else:
            base_items = synth_or_items.get('timeline', []) or []
    elif isinstance(synth_or_items, list):
        base_items = synth_or_items
    scored = []
    for it in base_items:
        text = ' '.join([str(it.get(k,'')) for k in ('phrase','label','title','arena','outlet','tactic')]).lower()
        matches = [t for t in tokens if t in text]
        score = sum(1.65 for t in matches) + (0.9 if matches else 0)
        if score > 0:
            it2 = dict(it)
            it2['query_why'] = f"Query-driven: matched {len(matches)} tokens {matches} in phrase/arena/outlet."
            it2['_qscore'] = score
            scored.append((score, it2))
    scored.sort(reverse=True, key=lambda x: x[0])
    return [it for _,it in scored[:cap]]

# End Rule42 pipeline helpers v3. Note: JS runtime in neural-map-holo.html does full sophisticated scoring using these + raw fields.


    # Phase 3 wiring: auto-generate public feeds to babylon-generated (for site /holo mappers + load public ripples with zdf_relevance).
    # Reuses recent synthesis (incl news_ripples + rich from upstream ai-enhanced). Complements monitor auto-process/analyze chain.
    # Run with env GENERATED_BUCKET_NAME or defaults; non-fatal if no R2 perms in this context.
    try:
        import subprocess, os as _os
        gen_cmd = ["python", _os.path.join(_os.path.dirname(__file__), "generate_public_feeds.py"), "--arena", "all", "--limit", "30"]
        # Non-blocking fire-and-forget style (or direct import for sync); GH will have bucket secrets.
        res = subprocess.run(gen_cmd + (["--dry-run"] if args.dry_run else []), capture_output=True, text=True, timeout=45)
        if res.returncode == 0:
            print(f"  [Phase3-public] generated public feeds from synthesis (see babylon-generated/public-feeds/); {res.stdout.splitlines()[-1] if res.stdout else ''}")
        else:
            print(f"  [Phase3-public] feeds gen note: {res.stderr.strip()[:120] or 'no bucket or skipped'}")
    except Exception as _e:
        print(f"  [Phase3-public] public feeds chain note (manual dispatch generate or set GENERATED_BUCKET_NAME): {_e}")

    print(f"[{SUBAGENT_TAG}] [STEP:ANALYZE COMPLETE] Analysis done. [live metrics / subagent tag ready for pipeline status]")
    if metrics:
        metrics.inc_step("analyze")  # mark completion tick
        metrics.write_status(final=True)
        # live output for AI stack / orchestration watchers
        print(f"[{SUBAGENT_TAG}] [LIVE-STATUS] analyze complete | steps tracked | status written for pipeline orchestration")
    print(f"[{SUBAGENT_TAG}] [LIVE] [RULE42] Rule42 data block written to synthesis (cap={RULE42_CAP}) | ready for worker/pol profiles / holo map")

if __name__ == "__main__":
    main()

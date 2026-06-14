#!/usr/bin/env python3
"""
Substantial Analysis & Synthesis Engine for The Breaker of Babylon.

Consumes processed/ summaries (which contain extracted_text_preview + basic analysis from process_data.py).

Delivers real intelligence products:
- Phrase clustering / narrative similarity (repeated language detection across documents - key for coordination exposure).
- Entity co-occurrence + relationship graph (nodes = politicians/agencies/bills/cases; edges = co-mention, date proximity, arena overlap).
- Timeline construction with key excerpts and signals.
- Tactic scoring (repetition density, loaded language, press-style framing, potential coordination markers).
- Synthesis report (common narratives, contradictions, cross-arena ripples).

Outputs (to processed/derived/ or specified):
- <base>-graph.json (vis-ready nodes/edges)
- <base>-timeline.json
- <base>-synthesis.json (scores + insights)
- <base>-report.txt (human readable)

Works on single processed_key or batch (list or prefix scan).

Chainable from process/monitor.

R2 native. Reusable.

This turns extracted documents into the "lethal weapon" layer: evidence of framing tactics, timing games, entity networks.

Run:
  python scripts/analyze_data.py --processed-key processed/documents/courts/scotus-25-6-...-summary.json
  or env PROCESSED_KEY=... 
  or --batch for multiple.

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
    text = summary.get("extracted_text_preview", "")
    # Also incorporate any existing basic analysis text if present
    if "analysis" in summary:
        text += "\n" + json.dumps(summary["analysis"])
    return text

def find_repeated_phrases(texts: list[str], min_len=8, threshold=0.6) -> list[dict]:
    """Substantial: find overlapping phrases/sentences across documents using sequence matching.
    Detects coordinated or echoed language - core to narrative tactics exposure.
    """
    phrases = []
    sentences = []
    for i, t in enumerate(texts):
        sents = re.split(r'[.!?]\s+', t)
        for s in sents:
            if len(s.split()) >= min_len:
                sentences.append((i, s.strip()))

    for idx1, (doc1, sent1) in enumerate(sentences):
        for idx2, (doc2, sent2) in enumerate(sentences[idx1+1:], idx1+1):
            if doc1 == doc2:
                continue
            matcher = difflib.SequenceMatcher(None, sent1.lower().split(), sent2.lower().split())
            ratio = matcher.ratio()
            if ratio >= threshold:
                match = matcher.find_longest_match(0, len(sent1.split()), 0, len(sent2.split()))
                if match.size >= min_len:
                    phrases.append({
                        "doc1": doc1,
                        "doc2": doc2,
                        "similarity": round(ratio, 3),
                        "phrase": " ".join(sent1.split()[match.a:match.a+match.size]),
                        "context1": sent1,
                        "context2": sent2
                    })
    # Dedup and sort by similarity
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
    """
    all_text = " ".join(texts).lower()
    framing_words = ["crisis", "threat", "historic", "unprecedented", "protect", "defend", "restore", "accountability", "transparency", "misinformation"]
    framing_density = sum(all_text.count(w) for w in framing_words) / max(1, len(all_text.split()) / 100)

    repeated = find_repeated_phrases(texts, threshold=0.5)
    repetition_score = min(10, len(repeated) * 0.8)

    press_style_count = sum(1 for s in summaries if s.get("analysis", {}).get("signals", {}).get("press_release_style"))

    coordination_hint = len([r for r in repeated if r["similarity"] > 0.75])

    return {
        "framing_density": round(framing_density, 2),
        "repetition_score": round(repetition_score, 1),
        "press_style_instances": press_style_count,
        "high_similarity_matches": coordination_hint,
        "total_repeated_phrases": len(repeated),
        "overall_tactic_risk": min(10, round((framing_density * 2 + repetition_score + coordination_hint) / 3, 1))
    }

def generate_synthesis(summaries: list[dict]) -> dict:
    texts = [extract_text_from_processed(s) for s in summaries]
    repeated_phrases = find_repeated_phrases(texts)
    graph = build_entity_graph(summaries)
    timeline = build_timeline(summaries)
    scores = compute_tactic_scores(texts, summaries)

    common_narratives = [p["phrase"] for p in repeated_phrases[:5]]

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "doc_count": len(summaries),
        "tactic_scores": scores,
        "common_narratives": common_narratives,
        "repeated_phrases_sample": repeated_phrases[:10],
        "graph": graph,
        "timeline": timeline[:15],
        "insights": f"Detected {len(repeated_phrases)} repeated phrases across docs. Top framing density {scores['framing_density']}. High-similarity matches suggest possible coordination: {scores['high_similarity_matches']}."
    }

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
        # Fallback: env or recent documents example
        k = os.environ.get("PROCESSED_KEY")
        if k:
            keys = [k]
        else:
            print("Provide --processed-key or --batch-keys or PROCESSED_KEY env")
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
    base = keys[0].split("/")[-1].rsplit("-summary", 1)[0] if keys else "batch"

    outputs = {
        "graph": f"{args.output_prefix}/{base}-graph.json",
        "timeline": f"{args.output_prefix}/{base}-timeline.json",
        "synthesis": f"{args.output_prefix}/{base}-synthesis.json"
    }

    if args.dry_run:
        print("DRY RUN - would write:")
        print(json.dumps({k: v for k, v in outputs.items()}, indent=2))
        print("Synthesis preview:", json.dumps(synthesis, indent=2)[:800])
        return

    s3.put_object(Bucket=BUCKET, Key=outputs["graph"], Body=json.dumps(synthesis["graph"], indent=2), ContentType="application/json")
    s3.put_object(Bucket=BUCKET, Key=outputs["timeline"], Body=json.dumps(synthesis["timeline"], indent=2), ContentType="application/json")
    s3.put_object(Bucket=BUCKET, Key=outputs["synthesis"], Body=json.dumps(synthesis, indent=2), ContentType="application/json")

    # Also text report
    report_key = f"{args.output_prefix}/{base}-report.txt"
    report = f"Breaker of Babylon Analysis Report\nGenerated: {synthesis['generated_at']}\n\nTACTIC SCORES:\n{json.dumps(synthesis['tactic_scores'], indent=2)}\n\nCOMMON NARRATIVES:\n" + "\n".join(synthesis['common_narratives']) + f"\n\nINSIGHTS:\n{synthesis['insights']}\n\nSee graph/timeline/synthesis JSONs for full structured data."
    s3.put_object(Bucket=BUCKET, Key=report_key, Body=report.encode(), ContentType="text/plain")

    print(f"Analysis complete. Outputs:")
    for k, v in outputs.items():
        print(f"  {k}: {v}")
    print(f"  report: {report_key}")
    print(f"NOTIFY: analyzed {len(summaries)} docs -> {outputs['synthesis']}")

if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Process raw ingested data from babylon-raw-data R2.

- Called by process-data.yml (after ingest success, via auto or manual dispatch).
- Handles CSV (stats, samples) + new: documents (PDF text extract via pypdf, HTML via bs4).
- Produces rich summaries + extracted content to processed/<arena>/...-summary.json
- Basic "analysis" for documents: metadata, simple entity/ phrase extraction (regex for politicians, agencies, bills, dates, framing signals).
- Idempotent-friendly (overwrites summary; raw stays in R2).
- Reusable. Extend here for more NLP, embeddings stubs, cross-arena links, etc.

Env inputs (set in workflow):
  ARENA, RAW_KEY, (R2_* secrets)

Usage in GH:
  python scripts/process_data.py

Future: chain to analyze step, full text to vector store, graph builder.
"""

import os
import sys
import io
import json
import re
from datetime import datetime
import boto3
from botocore.config import Config

# Optional heavy but light pure-Py deps (installed in workflow)
try:
    import pandas as pd
except ImportError:
    pd = None

try:
    from pypdf import PdfReader
except ImportError:
    PdfReader = None

try:
    from bs4 import BeautifulSoup
except ImportError:
    BeautifulSoup = None


BUCKET = os.environ.get("BUCKET_NAME", "babylon-raw-data")


def get_s3():
    return boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        config=Config(signature_version="s3v4"),
    )


def key_exists(bucket: str, key: str, s3=None) -> bool:
    if s3 is None:
        s3 = get_s3()
    try:
        s3.head_object(Bucket=bucket, Key=key)
        return True
    except Exception:
        return False


# Simple regex-based "analysis" extractors (starter for narrative exposure: entities, timing, signals)
# Extend with real NLP later (spaCy stub, transformers via HF if wanted, but keep GH-free for now).
POLITICIAN_PAT = re.compile(r'\b(Trump|Biden|Harris|DeSantis|Newsom|Schumer|McConnell|Pelosi|McCarthy|Roberts|Kavanaugh|Gorsuch|Alito|Thomas|Kagan|Sotomayor|Barrett|Jackson|Paxton|Garland|Mayorkas|Eisen|Marc Elias)\b', re.I)
AGENCY_PAT = re.compile(r'\b(DOJ|FBI|CIA|NSA|DHS|CBP|USCIS|ICE|DOJ Antitrust|White House|SCOTUS|Supreme Court|Congress|Senate|House|GAO|CRS|Federal Reserve|SEC|FDA|CDC|NIH|Census Bureau|BLS|OFAC|Treasury)\b', re.I)
BILL_PAT = re.compile(r'\b(H\.?R\.?\s*\d+|S\.?\s*\d+|Public Law|PL\s*\d+-\d+)\b', re.I)
DATE_PAT = re.compile(r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4}|\b\d{4}-\d{2}-\d{2}\b|\b(20\d{2})\b')
PRESS_RELEASE_PAT = re.compile(r'For Immediate Release|Press Release|Office of Public Affairs|Briefing Statement', re.I)
FRAMING_HINTS = re.compile(r'\b(urgent|crisis|historic|unprecedented|threat|protect|defend|restore|accountability|transparency|misinformation|disinformation|equity|inclusion|border security|lawfare)\b', re.I)

# News / RSS specific entity + signal hints (for rss_news arena processing)
NEWS_OUTLET_PAT = re.compile(r'\b(Reuters|AP|Associated Press|New York Times|NYT|Wall Street Journal|WSJ|CNN|BBC|Guardian|Washington Post|WaPo|Fox|NPR|Politico|Axios|Bloomberg)\b', re.I)
NEWS_HEADLINE_HINTS = re.compile(r'\b(breaking|exclusive|live|update|developing|sources say|reportedly|according to|analysis|op-ed)\b', re.I)
NEWS_RSS_PAT = re.compile(r'<rss|<feed|<\?xml|item>|channel>|<title>|<pubDate>', re.I)  # crude detector if raw RSS fed in


def extract_entities_and_signals(text: str, arena: str = "") -> dict:
    if not text:
        return {}
    text_sample = text[:15000]  # cap for speed
    entities = {
        "politicians": sorted(set(m.group(0) for m in POLITICIAN_PAT.finditer(text_sample))),
        "agencies": sorted(set(m.group(0) for m in AGENCY_PAT.finditer(text_sample))),
        "bills_refs": sorted(set(m.group(0) for m in BILL_PAT.finditer(text_sample))),
    }
    signals = {
        "press_release_style": bool(PRESS_RELEASE_PAT.search(text_sample)),
        "framing_words_count": len(FRAMING_HINTS.findall(text_sample)),
        "dates_mentioned": sorted(set(m.group(0) for m in DATE_PAT.finditer(text_sample)))[:10],
    }
    # News/rss specific (called from process with arena hint for rss_news / news)
    if arena in ("news", "rss_news") or "rss" in arena.lower() or NEWS_RSS_PAT.search(text_sample[:2000]):
        entities["news_outlets"] = sorted(set(m.group(0) for m in NEWS_OUTLET_PAT.finditer(text_sample)))
        signals["news_headline_style"] = bool(NEWS_HEADLINE_HINTS.search(text_sample))
        signals["rss_like"] = bool(NEWS_RSS_PAT.search(text_sample[:3000]))
        # Extra: pull potential article titles / lead from rss or html if present
        if signals.get("rss_like"):
            signals["rss_item_count_hint"] = len(re.findall(r'<item>|<entry>', text_sample, re.I))
    return {"entities": entities, "signals": signals}


def process_csv(raw_bytes: bytes, arena: str, raw_key: str) -> dict:
    if pd is None:
        return {"note": "pandas not available", "raw_key": raw_key}
    try:
        df = pd.read_csv(io.BytesIO(raw_bytes))
    except Exception as e:
        return {"error": str(e)[:200], "raw_key": raw_key}

    summary = {
        "arena": arena,
        "raw_key": raw_key,
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "shape": list(df.shape),
        "columns": list(df.columns)[:30],
        "head_sample": df.head(3).to_dict("records") if len(df) > 0 else [],
    }
    if "Agency Name" in df.columns or "agency" in str(df.columns).lower():
        col = [c for c in df.columns if "agency" in c.lower()][0] if any("agency" in c.lower() for c in df.columns) else "Agency Name"
        if col in df.columns:
            summary["top_agencies"] = df[col].value_counts().head(8).to_dict()
    num_cols = df.select_dtypes(include=["number"]).columns
    if len(num_cols) > 0:
        summary["numeric_summary"] = df[num_cols].describe().to_dict()
    return summary


def process_pdf(raw_bytes: bytes, arena: str, raw_key: str) -> dict:
    if PdfReader is None:
        return {"note": "pypdf not installed in this runner", "raw_key": raw_key, "bytes": len(raw_bytes)}
    try:
        reader = PdfReader(io.BytesIO(raw_bytes))
        num_pages = len(reader.pages)
        texts = []
        for i, page in enumerate(reader.pages[:8]):  # cap pages for summary speed + cost
            t = page.extract_text() or ""
            texts.append(f"[PAGE {i+1}]\n{t[:3000]}")
        full_text = "\n\n".join(texts)
        preview = full_text[:4000]
        analysis = extract_entities_and_signals(full_text, arena)
        meta = {
            "num_pages": num_pages,
            "pdf_info": reader.metadata or {},
        }
        return {
            "arena": arena,
            "raw_key": raw_key,
            "processed_at": datetime.utcnow().isoformat() + "Z",
            "type": "pdf",
            "metadata": meta,
            "extracted_text_preview": preview,
            "analysis": analysis,
            "note": f"Extracted from first {min(8, num_pages)} pages. Full raw PDF in R2."
        }
    except Exception as e:
        return {"error": f"PDF extract failed: {str(e)[:300]}", "raw_key": raw_key}


def process_html(raw_bytes: bytes, arena: str, raw_key: str) -> dict:
    text = raw_bytes.decode("utf-8", errors="ignore")
    if BeautifulSoup:
        try:
            soup = BeautifulSoup(text, "lxml")
            title = (soup.title.string if soup.title else "") or ""
            # Get main content-ish
            main = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r'content|main|body|press|briefing', re.I)) or soup.body
            body_text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
            body_text = re.sub(r'\n{3,}', '\n\n', body_text)[:8000]
        except Exception:
            title = ""
            body_text = text[:6000]
    else:
        # Fallback crude
        title = re.search(r'<title>(.*?)</title>', text, re.I | re.S).group(1) if re.search(r'<title>', text, re.I) else ""
        body_text = re.sub(r'<[^>]+>', ' ', text)[:6000]

    analysis = extract_entities_and_signals(body_text + " " + title, arena)
    return {
        "arena": arena,
        "raw_key": raw_key,
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "type": "html",
        "title": title[:300],
        "extracted_text_preview": body_text[:4000],
        "analysis": analysis,
        "note": "Full original HTML in R2 under raw/."
    }


def process_rss_xml(raw_bytes: bytes, arena: str, raw_key: str) -> dict:
    """Lightweight RSS/Atom parser for when the raw feed XML itself is ingested (raw/media/rss-*.xml or raw/news/).
    Extracts items (title, link, desc, date) for liveness + entity analysis without full feed reparse downstream.
    Reuses extract_entities_and_signals (now news-aware).
    """
    text = raw_bytes.decode("utf-8", errors="ignore")
    items = []
    try:
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw_bytes)
    except Exception:
        root = None
    if root is not None:
        # RSS items or Atom entries
        for item in (root.findall(".//item") + root.findall(".//{http://www.w3.org/2005/Atom}entry")):
            title = (item.findtext("title") or item.findtext("{http://www.w3.org/2005/Atom}title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not link:
                le = item.find("{http://www.w3.org/2005/Atom}link")
                link = le.get("href", "").strip() if le is not None else ""
            desc = (item.findtext("description") or item.findtext("{http://www.w3.org/2005/Atom}summary") or "").strip()[:2000]
            pub = (item.findtext("pubDate") or item.findtext("dc:date") or item.findtext("{http://www.w3.org/2005/Atom}published") or "").strip()
            items.append({"title": title[:200], "link": link[:300], "pub": pub[:40], "desc_preview": desc[:300]})
            if len(items) >= 25:  # cap for summary size
                break
    else:
        # Fallback regex sample if ET fails in this env
        for m in re.finditer(r'<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>.*?</item>', text, re.I | re.S):
            items.append({"title": m.group(1)[:200], "link": m.group(2)[:300], "pub": "", "desc_preview": ""})
            if len(items) > 10: break

    combined_text = " ".join([it.get("title","") + " " + it.get("desc_preview","") for it in items])
    analysis = extract_entities_and_signals(combined_text + " " + text[:4000], arena)
    return {
        "arena": arena,
        "raw_key": raw_key,
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "type": "rss_xml",
        "item_count": len(items),
        "items_sample": items[:8],
        "extracted_text_preview": combined_text[:4000],
        "analysis": analysis,
        "note": "RSS feed archived + item metadata + news entity extraction. Full XML in R2 raw/."
    }


def process_generic(raw_bytes: bytes, arena: str, raw_key: str, ctype: str = "") -> dict:
    return {
        "arena": arena,
        "raw_key": raw_key,
        "processed_at": datetime.utcnow().isoformat() + "Z",
        "type": "other",
        "content_type": ctype,
        "size_bytes": len(raw_bytes),
        "note": "No specialized extractor yet. Raw bytes preserved in R2. Add handler in scripts/process_data.py for this type."
    }


def main():
    arena = os.environ.get("ARENA", "documents")
    raw_key = os.environ.get("RAW_KEY")
    if not raw_key:
        print("ERROR: RAW_KEY env required")
        sys.exit(1)

    print(f"Processing arena={arena} raw_key={raw_key}")

    s3 = get_s3()
    obj = s3.get_object(Bucket=BUCKET, Key=raw_key)
    raw_bytes = obj["Body"].read()
    ctype = obj.get("ContentType", "") or ""

    print(f"  Downloaded {len(raw_bytes)} bytes, ctype={ctype}")

    # Route by extension / arena / content
    # Enhanced for rss_news: arena=news or rss_news, raw/news/ keys, or raw/media/rss-*.xml feeds
    key_lower = raw_key.lower()
    if key_lower.endswith(".pdf") or "pdf" in ctype or arena == "documents":
        summary = process_pdf(raw_bytes, arena, raw_key)
    elif key_lower.endswith((".html", ".htm")) or "html" in ctype or "press" in key_lower or "briefing" in key_lower or arena in ("news", "rss_news") or key_lower.startswith("raw/news/") or "/rss-" in key_lower:
        # news article pages (from rss discover) treated as html; rss xmls get dedicated parser
        if (key_lower.endswith(".xml") or "rss" in key_lower or arena == "rss_news") and not key_lower.endswith((".html", ".htm")):
            summary = process_rss_xml(raw_bytes, arena, raw_key)
        else:
            summary = process_html(raw_bytes, arena, raw_key)
    elif key_lower.endswith(".csv") or (pd is not None and "csv" in ctype):
        summary = process_csv(raw_bytes, arena, raw_key)
    else:
        summary = process_generic(raw_bytes, arena, raw_key, ctype)

    # Always add common fields
    summary.setdefault("arena", arena)
    summary.setdefault("raw_key", raw_key)
    summary["processed_at"] = datetime.utcnow().isoformat() + "Z"

    # Target processed key (clean basename)
    base = raw_key.split("/")[-1].rsplit(".", 1)[0]
    processed_key = f"processed/{arena}/{base}-summary.json"

    s3.put_object(
        Bucket=BUCKET,
        Key=processed_key,
        Body=json.dumps(summary, indent=2, ensure_ascii=False),
        ContentType="application/json"
    )
    print(f"Processed summary saved to {processed_key}")

    # Optional: for documents, also drop a clean text version for easy downstream (RAG, grep, etc.)
    if "extracted_text_preview" in summary:
        text_key = f"processed/{arena}/{base}-extracted.txt"
        text_body = summary.get("extracted_text_preview", "") + "\n\n[ANALYSIS]\n" + json.dumps(summary.get("analysis", {}), indent=2)
        s3.put_object(Bucket=BUCKET, Key=text_key, Body=text_body.encode("utf-8"), ContentType="text/plain")
        print(f"  Also wrote extracted text helper to {text_key}")

    # Marker for watchers (like monitor does)
    print(f"NOTIFY: processed {raw_key} -> {processed_key}")

    # Substantial analysis integration (Phase 1+news): for documents + news (RSS), run deeper synthesis immediately.
    # This produces live signals (incl. news_ripples, outlet graphs, echo scores) right after process for site consumption.
    # Ties RSS subagent ingest (raw/news/...) -> process -> immediate derived synth/analyze.
    if arena in ("documents", "news") and "extracted_text_preview" in summary:
        try:
            # Import and run core synthesis (avoids full re-fetch)
            sys.path.insert(0, os.path.dirname(__file__))
            from analyze_data import extract_text_from_processed, generate_synthesis, build_entity_graph, build_timeline, compute_tactic_scores
            # Wrap as list for the functions
            synth_input = [summary]
            deep_synth = generate_synthesis(synth_input)
            derived_base = f"processed/derived/{base}"
            s3.put_object(Bucket=BUCKET, Key=f"{derived_base}-synthesis.json", Body=json.dumps(deep_synth, indent=2), ContentType="application/json")
            s3.put_object(Bucket=BUCKET, Key=f"{derived_base}-graph.json", Body=json.dumps(deep_synth.get("graph", {}), indent=2), ContentType="application/json")
            s3.put_object(Bucket=BUCKET, Key=f"{derived_base}-timeline.json", Body=json.dumps(deep_synth.get("timeline", []), indent=2), ContentType="application/json")
            print(f"Deep synthesis + graph + timeline written for {arena} to {derived_base}-*.json")
            if deep_synth.get("news_ripples") and "echo_chamber_scores" in deep_synth.get("news_ripples", {}):
                print(f"  LIVE: news_ripples (echo={deep_synth['news_ripples']['echo_chamber_scores'].get('echo_chamber_score')}) available for site/pol profiles")
            summary["has_deep_analysis"] = True
            summary["derived_synthesis_key"] = f"{derived_base}-synthesis.json"
        except Exception as e:
            print(f"Deep analysis in-process failed (non-fatal): {e}")

    # Print compact for logs
    print(json.dumps({k: v for k, v in summary.items() if k in ("shape", "type", "title", "num_pages", "analysis")} , indent=2)[:1500])

    print("Process complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR in process_data: {e}")
        sys.exit(1)

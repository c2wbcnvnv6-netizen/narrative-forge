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


def extract_entities_and_signals(text: str) -> dict:
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
        analysis = extract_entities_and_signals(full_text)
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

    analysis = extract_entities_and_signals(body_text + " " + title)
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
    key_lower = raw_key.lower()
    if key_lower.endswith(".pdf") or "pdf" in ctype or arena == "documents":
        summary = process_pdf(raw_bytes, arena, raw_key)
    elif key_lower.endswith((".html", ".htm")) or "html" in ctype or "press" in key_lower or "briefing" in key_lower:
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

    # Print compact for logs
    print(json.dumps({k: v for k, v in summary.items() if k in ("shape", "type", "title", "num_pages", "analysis")} , indent=2)[:1500])

    print("Process complete.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR in process_data: {e}")
        sys.exit(1)

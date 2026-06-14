# DATA PROCESSING PIPELINE — The Breaker of Babylon

Post-ingest processing, extraction, analysis, and synthesis for all raw data (CSVs, PDFs, HTML press/rulings/CRS reports, etc.) landing in babylon-raw-data.

## Current Flow (as of 2026-06-14)
1. **Ingest** (raw/ prefix):
   - `scripts/ingest_raw_data.py` (streaming requests + boto3 to R2).
   - Triggered by `monitor_and_ingest.py` (algorithmic discovers + HEAD probes) or manual `ingest-raw-data.yml`.
   - Idempotent via key_exists + manifest.
   - Now includes dedicated documents discovers (SCOTUS direct PDFs, WH/DOJ press HTML, CRS PDFs from everycrsreport, etc.).

2. **Process** (processed/ prefix):
   - `process-data.yml` (workflow_dispatch with arena + raw_key).
   - Called automatically from monitor if --auto-process (or manual).
   - Now uses `scripts/process_data.py` (new dedicated processor).
   - Deps in GH: pandas, boto3, pypdf, beautifulsoup4, lxml.
   - Routes:
     - PDFs (court rulings, CRS reports): pypdf page text extraction (first ~8 pages for summary), metadata.
     - HTML (press releases, briefings, indexes): BS4 title + main body text.
     - CSVs (most other arenas): pandas shape/cols/head/numeric/Agency counts (existing behavior preserved + richer).
     - Fallback: size + note.
   - Always writes `processed/<arena>/<basename>-summary.json`.
   - For documents: also writes companion `-extracted.txt` with preview + analysis JSON.
   - Embeds starter "analysis":
     - Regex entities: politicians (Trump, justices, AGs, etc.), agencies (DOJ, SCOTUS, Census, etc.), bill refs (H.R. \d+, S. \d+).
     - Signals: press-release style, framing word counts, dates mentioned.
     - Why this matters: Turns opaque PDFs/HTML into structured, searchable, synthesizable knowledge for detecting narrative coordination, timing vs. events, doublespeak, lawfare patterns, etc.

3. **Notifications**:
   - Ingest and process both emit `NOTIFY: ...` lines.
   - Local `scripts/watch_for_new_downloads.py` (bg, every ~5min via nohup) polls `gh run` logs for NOTIFY/Ingested/processed and sends iMessage/SMS + Mail to naomiseibt@gmx.de (dual as requested).
   - GitHub step logs + R2 objects provide audit.

4. **"At all times"**:
   - Cron in monitor-ingest.yml (daily + mid-week) + manual aggressive dispatches (backfill, high max_new, broad sources including all document ones).
   - Direct ingest dispatches for immediate high-value documents.
   - Auto-process chained where possible.

## How to Use / Trigger
- Specific document: `gh workflow run process-data.yml -f arena=documents -f raw_key=raw/documents/courts/scotus-25-6-keathley-v-ayers.pdf`
- Monitor that will auto-process new: already includes `court_documents,press_releases,...` and --auto-process.
- Local test (with R2 env): `python scripts/process_data.py` (after setting ARENA/RAW_KEY + R2 vars).
- View results: R2 `processed/documents/...-summary.json` (and -extracted.txt). Use boto3 or GH process logs.

## Next / Everything We Need to Do With the Data (Roadmap)
**Immediate / rocking now (this session priorities):**
- Full text extraction for all landed documents (done in processor).
- Entity + signal extraction (regex starter; ready for upgrade).
- Rich processed JSON ready for consumption.
- Continue parallel ingestion + processing dispatches.

**Short-term expansions:**
- Deeper NLP: phrase clustering for identical language across releases (coordination detection), sentiment/loaded language scoring, quote attribution.
- Timelines & graphs: build event nodes (release date + arena + key entities) → JSON for Chart.js / vis (nodes = pols/agencies/media, edges = timing/funding/narrative overlap).
- Cross-arena synthesis: e.g. link SCOTUS opinion date to preceding WH/DOJ press, CRS report, migration stats, etc.
- Granulizer tie-in: parse bill refs from CRS/press/court docs → feed congressional arena.
- Full-text store: for RAG/thought bridges (step-by-step guided paths e.g. "Show me lawfare on election cases 2024-2026").
- More formats: zips (unzip + recurse), XML (govinfo), images in releases (OCR stub).

**Medium / website + synthesis:**
- Static/derived feeds under processed/ or a `public-feeds/` prefix: `recent_documents.json`, `arena_stats.json`, `narrative_signals.json` (for index.html canvases, thought steps, memes).
- Enhance index.html + future PHP/Next layer to consume the processed JSON (live cards per arena, interactive timelines, entity graphs).
- Memes + viz: auto-generate simple charts from summaries (or use Chart.js with the data); "narrative collision" visuals.
- Oppo/granulizer: bill status cross with spending (USAspending) + CRS + press.
- 11 arenas as living system: correlation matrices, "what this means for X arena" bridges.

**Ops / scale:**
- Update monitor auto-process to also trigger a light "analyze" workflow after process for documents.
- Manifest enhancements (track processed + analysis versions).
- Local helpers (download sample from R2 to raw-downloads/documents/ for offline review).
- Cost/egress: R2 zero-egress perfect for repeated re-processing + AI reads.
- Backfill historical documents (more SCOTUS terms, full CRS mirror, archived admins).

**Citatability & integrity:**
- Every processed summary includes original raw_key + processed_at + source URLs from discovers.
- All data remains public .gov mirrors (SCOTUS, everycrsreport, whitehouse.gov, justice.gov, gao.gov) — no proprietary.

## Current Status & Landed Items (example)
Recent direct document ingests (raw/):
- Several SCOTUS PDFs (e.g. 25-6, 25-406, etc.)
- CRS reports (R48296 etc.)
- WH/DOJ press HTML

Process these with the new workflow (they will now get real text + entities instead of placeholder).

Run `gh run list ...` or the bg watcher for live status + NOTIFYs (phone + email).

This turns the "huge" archive from passive storage into an active, queryable, synthesizable weapon for narrative exposure and "mile wide, inch deep" understanding.

Extend process_data.py liberally — that's where the magic for "everything with the data" lives.
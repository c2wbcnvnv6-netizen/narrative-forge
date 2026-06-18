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
- Static/derived feeds under processed/ or a `public-feeds/` prefix: `recent_documents.json`, `arena_stats.json`, `narrative_signals.json` (for index.html canvases, thought steps, memes). **Phase 2: now via generate_public_feeds.py writing explicit recent_ripples.json + arena_stats.json + narrative_signals.json to babylon-generated bucket (post-analyze step; bucket differentiation active).**
- Enhance index.html + future PHP/Next layer to consume the processed JSON (live cards per arena, interactive timelines, entity graphs).
- Memes + viz: auto-generate simple charts from summaries (or use Chart.js with the data); "narrative collision" visuals.
- Oppo/granulizer: bill status cross with spending (USAspending) + CRS + press.
- 11 arenas as living system: correlation matrices, "what this means for X arena" bridges.
- **Phase 2/3 prep**: Embeddings (babylon-embeddings) + selective use of babylon-generated/processed for public feeds + archiving of old raw to babylon-archive. RAG consumers (Holo thought bridges) next.

**Ops / scale:**
- Update monitor auto-process to also trigger a light "analyze" workflow after process for documents.
- Manifest enhancements (track processed + analysis versions).
- Local helpers (download sample from R2 to raw-downloads/documents/ for offline review).
- Cost/egress: R2 zero-egress perfect for repeated re-processing + AI reads.
- Backfill historical documents (more SCOTUS terms, full CRS mirror, archived admins).
- **Phase 2 starters active (Differentiate Buckets + Embeddings + Archiving + Generated feeds)**: scripts/generate_embeddings.py (reuses post-smart_extract/analyze; calls /embed on babylon-data-ai Worker using @cf/baai/bge*; writes vector+metadata+prov+rich_context (zdf etc) to babylon-embeddings/embeddings/<arena>/...-embed.json). scripts/archive_old_data.py (moves >90d raw/ etc to babylon-archive). scripts/generate_public_feeds.py (post-analyze writes recent_ripples.json / arena_stats.json / narrative_signals.json to babylon-generated/public-feeds/). Minimal wires added after smart_extract (monitor_and_ingest) + in analyze_data flow (generate_embeddings_for_summary reusable). Worker /embed added. MCP confirmed buckets (babylon-embeddings, -generated, -archive, -raw-data, -processed, ckg-holo-analytics). Enables Phase 3 RAG in Holo + analytics consumers on generated/processed.

**Citatability & integrity:**
- Every processed summary includes original raw_key + processed_at + source URLs from discovers.
- All data remains public .gov mirrors (SCOTUS, everycrsreport, whitehouse.gov, justice.gov, gao.gov) — no proprietary.

## RSS / News Pipeline (raw/news/ + raw/media/rss-*) — Liveness + New News Features
Added rss_news source + dedicated lightweight workflow for continual current-events capture.
- **Ingest**: Via monitor_and_ingest.py (discover_rss_news_new) or rss-monitor.yml (every 30min) or backfill (deeper). Yields HTML article pages (for full text) + occasional feed XMLs. Arena="news". Paths: raw/news/rss-<feed>-<ts>-<slug>.html , raw/media/rss-<feed>-<date>.xml . Supports parallel futures for multiple feeds.
- **Process** (process-data.yml, arena=news): Uses HTML path in process_data.py → BS4 title/body extract + extract_entities_and_signals (politicians, agencies, bills, framing, press-style). Writes processed/news/...-summary.json + -extracted.txt. Emits NOTIFY.
- **Analyze** (analyze-data.yml, processed_key=processed/news/...): Leverages generate_synthesis etc for *new news features*: repeated phrases (coordination detection across news items), entity graphs, timelines, tactic scores (framing_density, repetition, high-sim matches). Outputs to processed/derived/ *-graph/timeline/synthesis.json + report. Auto-triggerable from monitor after RSS process.
- **Profiles**: If entities present, chains to build-politician-profiles (as in documents flow).
- **Chaining (auto)**: rss_news ingest (with --auto-process) → process → (for news) analyze. Full live without manual steps.
- **Liveness + health**: 30min RSS cron for <1h freshness. Use scripts/check_r2_health.py --rss to verify: raw/news/ counts, rss-* samples, last-hour items (liveness), R2 hits for news paths, NOTIFY presence guidance. Cloudflare R2 paths raw/news/ + raw/media/ confirmed in health.
- **Efficiency**: Lightweight (rss-monitor separate from broad monitor-ingest), futures in discover, short windows, only process/analyze on *new*. Backfill for historical RSS news story archives if wanted (deeper hours).
- **Dispatch examples** (see README + workflows):
  - Live RSS: gh workflow run rss-monitor.yml
  - Include in broad: gh workflow run monitor-ingest.yml -f sources=...,rss_news
  - Backfill news history: gh workflow run backfill.yml -f sources=rss_news -f backfill-level=deep
  - Standalone chain: process then analyze on specific news raw_key/processed_key.
- Benefits: Real-time narrative signals from media/gov releases; cross with documents for timing/framing exposure. All citable public RSS.

## Current Status & Landed Items (example)
Recent direct document ingests (raw/):
- Several SCOTUS PDFs (e.g. 25-6, 25-406, etc.)
- CRS reports (R48296 etc.)
- WH/DOJ press HTML

Process these with the new workflow (they will now get real text + entities instead of placeholder).

Run `gh run list ...` or the bg watcher for live status + NOTIFYs (phone + email).

This turns the "huge" archive from passive storage into an active, queryable, synthesizable weapon for narrative exposure and "mile wide, inch deep" understanding.

Extend process_data.py liberally — that's where the magic for "everything with the data" lives.

## Phase 1/2 Update (Stabilize & Activate + Embeddings/Buckets, 2026-06-17)
Phase 1 complete: smart_extract wired in monitor (Firecrawl/Worker for rich AI: zdf_relevance, framing/tactics/arena_relevance, key_quotes on inflows); babylon-data-ai Worker deployed (https://babylon-data-ai.c2wbcnvnv6.workers.dev) with /extract (AI structured + auto rich ai-enhanced to R2) + /sink (prov to ckg-holo-analytics); site sinks real (Worker delegation) + rich consumption (ai-enhanced paths in mappers/catalog); new dynamic discovers (federal_register_api, datagov_catalog) active in defaults + cron fallback; verification via MCPs (r2_buckets_list, workers_list/get) + live curls green. All per long-term rec + subagents (Python/Worker/Site completed core; docs/audit in progress or manual).

Phase 2 in progress: embeddings pipeline starter (generate_embeddings.py: reads processed/rich, vectors to babylon-embeddings w/ prov + rich_context; hook in monitor); archiving stub (archive_old_data.py: moves old raw/ to babylon-archive); generated feeds stub (generate_public_feeds.py: post-analyze to babylon-generated/public-feeds); all buckets confirmed (MCP) for differentiation. New subagent 019ed369-5b15-7152-a783-a8db56864df5 driving. See Heavy-Agents-Coordination.md for full status/handoffs. Next: RAG/thought bridges (Phase 3).

## Catalog Summaries from Data Field (Live from narrative-forge/data/ + R2 Pipeline)

Real runtime data catalogs powering the holographic neural map (politicians-index.json, news-synthesis.json, profiles/*.json, news-sample.json). These are generated/updated by scripts/update_politicians_neural_map.py (691+ Congress + staff + state/local from unitedstates/congress-legislators + clerk/senate XMLs, deduped, with mediaFraming), process/analyze (news_ripples, outlet graphs, tactic_scores), and R2 live feeds (rss_news subagent + monitor). Used in holo.html / loadAndParseGraphData for nodes (politician/ripple/case/media), archetype inference, hotScore (framing*0.35 + echo*0.25 + 0.2 + 0.2), Rule of 42 cap, provenance (r2_path).

**Politicians Index Catalog (data/politicians-index.json):**
- count: 691 (as of 2026-06-15T06:53:00Z generated)
- Schema per entry: {name, slug (bioguide e.g. C000127), profile: "data/profiles/<slug>.json", mentions: number (default 50+), arenas: string[] e.g. ["congress","elections"], state: e.g. "WA", party: "Democrat"|"Republican"|"Independent", role: "U.S. Senator" | staffer/governor etc.}
- Sample entries:
  - Maria Cantwell (C000127, WA, Democrat, U.S. Senator) — arenas: congress, elections; profile: data/profiles/C000127.json
  - Amy Klobuchar (K000367, MN, Democrat, U.S. Senator)
  - Bernard Sanders (S000033, VT, Independent, U.S. Senator)
  - Sheldon Whitehouse (W000802, ... ) + 687 more (includes ORIGINAL_TEAM_SLUGS preserved like donald-j-trump, joe-biden, john-roberts, kamala-harris, aoc, jim-jordan, ted-cruz, clarence-thomas, elena-kagan, ... + expanded staffers, state AGs, mayors, local).
- Arenas coverage (from NARRATIVE_ARENAS + dynamic): congress, elections, migration, border, pharma, lawfare, state, local, media, bureaucracy. Full in prod (no 200 cap).
- Update cycle: scripts/update_politicians_neural_map.py (infinite bg, hourly, sources 3 XML/JSON, deploys to vercel thebreakerofbabylon.com).
- R2 tie: profiles/ + index land via pipeline; used for 200+ nodes in self-contained (full 691 R3F).

## Hard Work Report: Rule of 42 Analyzation Logic Paths Enhancement (2026-06-17)
**Focus exclusive:** narrative-forge only. Reviewed multi-factor in neural-map-holo.html (v3 9-path: baseHot/centrality/coord/rec/prov/arch + NEW graph clustering/computeGraphClusters/union-find+phrase+R2-delta, temporalEvol/R2DeltaRippleTrack from pub+inter-arrival, crossArena, query-driven in selectTop42Signals, detailed rule42Analysis per-sig with why/factorBreakdown) + analyze_data.py (RULE42_CAP, generate_synthesis, compute_*_hints, select_by_query, rule42 block + per_signal_expls).
**Additions/Enhancements made:**
- Graph clustering: improved compute_simple_graph_clusters (union + repeated phrase + outlet_similarity_graph from pipeline for media clusters; added outlet_clusters output).
- Temporal from R2: compute_temporal_evolution_hints now parses raw_key filename patterns (YYYYMMDD-HHMM in rss-*-20260615-0126) for precise inter-landing deltas/vel/accel/persist + r2_inter_arrival_velocity; JS computeTemporal + R2DeltaTrack blend + hint.
- Query-driven: select_rule42_by_query now attaches "query_why" per item; JS pre-boost + qNote in why + forced keep.
- Detailed per-signal + why-selected + factor breakdowns: expanded per_signal_explanations to include "why_selected" (composite narrative: repeat+clus+R2 temporal+tactic+echo), full "factor_breakdown" numeric dict (similarity, cluster, temporal_r2_delta, vel, tactic_repetition etc); mirrored in holo rule42Analysis.why_selected + factorBreakdown + strongFs.
- Pipeline integration: loadAndParse blends __RULE42_PIPELINE_HINTS (cluster_sizes, temporal) into nodes/ctx/scores (hintClusBoost/hintTempBoost in multiScore); call sites pass hints; hints used in clus/temp/attach + reports.
- Universal any-system: selectTop42Signals handles array/graph/synth/news_ripples/pols/single; pure no-dep; mirrored in py helpers; exposed window.RULE42 + tests confirm decls + paths.
**Changes:** search_replace only (minimal, targeted logic paths in holo.html + analyze_data.py). No new files.
**Tests with data:**
- Dry-run analyze (env keys + batch) exercised generate + rule42 block.
- Direct calls w/ real news-synthesis + constructed overlapping summaries: repeated detection, clus (incl outlet), temporal (R2 key parse vel=2.8), query, full why_selected+factor_breakdown+composite now output (1+ signals + expls).
- Universal: synth/array input shapes -> rule42; JS fn decls + hint integrate + 3 compute* paths confirmed present.
- All paths produce enriched per-sig why + breakdowns integrating pipeline.
**Hard work reports:** This section + live run outputs + prior fidelity in docs. Verified universal (works any system: rss/pol/synth/any graph).
**Status:** Enhancements complete, tested, integrated. No drift on existing hot/Rule42 cap/cases.
(Work logged 2026-06-17 SuperGrok exclusive focus.)

**News Synthesis Ripples Catalog (data/news-synthesis.json):**
- meta: {source: "rss_news liveness subagent + process/analyze + R2-FETCHER-SUB", generated, feeds_active:20, liveness_note, last_activation, rss_liveness: {whitehouse:30, justice:25}, R2:"babylon-raw-data confirmed MCP", updated_by, KEEP_IT_ON notes}
- news_ripples.media_specific_repeated_phrases[] (Rule of 42 spine, top ~42): 
  - {phrase: "humanitarian implementation hiccups", outlets: ["legacy-media-nyt","fox-news","crs-reports","gao-reports"], similarity:0.82, liveness:"whitehouse:30 justice:25"}
  - {phrase: "national security presidential memorandum", outlets:["whitehouse","reuters","ap-news"], similarity:0.76, liveness:...}
  - {phrase: "presidential actions 2026-06", outlets:["whitehouse","legacy-media-nyt","politico-congress"], similarity:0.69, ...}
  - + more from high framing/echo (20+ feeds: reuters, ap, nyt, wsj, bbc, cnn, guardian, whitehouse, justice etc.)
- news_ripples.outlet_similarity_graph: {nodes: ["justice-pr","legacy-media-nyt","fox-news","whitehouse","politico-congress",...], edges: [...] for coordination viz}
- tactic_scores, repeated phrases for coordination detection (analyze_data.py output).
- Used: ripples -> nodes (type:'ripple', value=similarity, archetype via infer, sources from outlets, signals.tactic, provenance r2:processed/derived/...-synthesis.json); hotScore calc; links from outlet graph + echoEdges.
- Liveness: 30min rss-monitor.yml feeds raw/news/ + raw/media/rss-*.xml; process -> analyze auto-chains; 341+ articles verified in R2 health.

**Profiles Catalog (data/profiles/*.json ~914 files):**
- Per slug (e.g. C000127.json for Maria Cantwell): {name, role, bioExcerpt (narrative-tailored), mediaFraming: [{source e.g. "legacy-media-nyt"|"fox-news"|"politico"|"cnn"|"wsj"|"msnbc", frame, framingScore:0.68+, keyPhrases:[]}], signalsFromNews: arenas[] }
- Built in update_politicians_neural_map.py (build_media_framing for plausible + preserve rich for ORIGINAL_TEAM); used in load for sources + signals.mentions/arena.
- HotScore / Rule42 applied at map load time from these + synthesis.
- R2: raw + processed tie-in for full provenance in userData (for evidence panels, citations).

**news-sample.json & Pre-viz:**
- mediaNodesForMap + echoEdges for initial graph seeds (influence, type media/politician).
- Enriched proxy from R2 news counts.

**Usage in Mappers (for R3F port / SWR live):**
- loadAndParseGraphData() in holo (fetch 3 files or R2 proxy via SWR): politicians -> pol nodes (inferArchetype on arenas/signals), ripples slice(42) + hot calc, sample edges, filter Rule42 top + cases, add hotScore/isRule42.
- inferArchetype(arenas, signals, phrase): regex to 11 (hiccups/pressures/coordinated implementation -> haman; border/humanitarian -> pharaoh; funding/waste/pharma -> judas; coordinated/law -> goliath; media/legacy/framing -> nimrod; etc. default wisemen).
- ARCHETYPES + ARCHETYPE_PARAMS (11 detailed biblical profiles + shader params: scaleMult, distortionAmp/Freq, particleDensity, pulseFreq, rimTint, wireDensity, motif) from subagent reports.
- Hot formula exact: framing*0.35 + echo*0.25 + fresh*0.2 + repeats*0.2 (from preview-4 + subagent mapping).
- All nodes carry: id, label, type, value, archetype, sources[] (title,url,excerpt,r2_path), arenas, signals, provenance, hotScore, isRule42.
- Links: {source,target,value,phrase?}.
- R2 live: check_r2_health.py --rss verifies counts/last-hour; MCP r2_buckets; SWR revalidate on NOTIFY or interval for "live data".

This catalog closes the loop from sources (DATA_SOURCES) -> ingest/process/analyze (DATA_PROCESSING) -> map data (here) for visuals + synthesis. Expand discovers for more state/local to grow 691+.

(End of catalog; cross-ref neural-map-holo-guts.md, holo.html, scripts/ for full mappers + R3F port.)
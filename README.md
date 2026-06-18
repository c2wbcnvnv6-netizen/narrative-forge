# narrative-forge
**The Breaker of Babylon** — A high-signal truth engine and holographic neural map that cuts through coordinated narrative noise to the ~42 signals that actually move power.

Pinnacle: The Elon/ZDF case — a documented fabrication lie ("Jagd auf Migranten") by German state media, exposed via primary X data, 4D timeline, signed provenance bundles, and Rule of 42 filtering. Built as a demonstration of value for clarity, accountability, and primary-source reasoning.

- **Golden Artifact**: `neural-map-holo.html` — self-contained, production-ready Three.js holographic map (full 691 politicians + ripples, 11 archetypes, Rule of 42 v3 multi-factor (9 paths: base+centrality+coord+rec+prov+arch+graph-clustering+temporal-evolution+cross-arena + pipeline hint blend), strict top-42 + forced, ZDF 4D scrub t=-6.8, WebAudio sonification, live R2 delta, provenance exports, PWA/offline). Detailed per-signal why_selected + factorBreakdowns. Pipeline (analyze_data.py rule42 hints + enhanced clus/temporal/query) integrated. Universal.
- **Data Fidelity**: Verified exact (691 pols, 11 arches coverage, hotScore = framing*0.35 + echo*0.25 + fresh*0.2 + repeats*0.2, Rule of 42 cap, full provenance roundtrips).
- **Pipeline**: Public RSS + gov sources → R2 (babylon-raw-data) → CF Worker AI extraction (zdf_relevance etc.) → processed/ripples → map.
- **For Attention**: One-click "ELON ZDF SUIT EVIDENCE BUNDLE" produces citable, signed package with 3D state, PNG capture, X quote proof (ID 2066565993040593115), 4D timeline, reclaim sequence.

This is the version to show. It demonstrates becoming valuable by making the invisible structure visible with rigorous, exportable evidence. No noise. Only signal.

**Core Invariants (never break)**: 691 politicians, 11 archetypes, Rule of 42 as the filter, exact hot formula, full provenance on everything, ZDF as the flagship demonstration case.

## Core / Public Separation (enforced)
- **Core** (internal/pipeline): data ingest/process/analyze (scripts/), loadAndParse + infer/hot/Rule42/filter (golden + fidelity tests), R2 health, provenance sign/verify, MASTER_CATALOG. Universal framing lives here (multi-factor cap applies to any domain).
- **Public** (mass-market/user-facing): exports (PNG/JSON bundles rich with analysis+overlays hints+deep links+embed notes+universal msg "Rule of 42 applies to any system: only ~42 high-signal nodes move power"), share logic, /holo UI, PWA, vision-market-ready.html, accessible dashboards, JARVIS framing for broad audiences.
- Docs: This README + IMPLEMENTATION_TASKS.md + vision-market-ready note separation + universal framing. Edits via stack-coord subagents verified no drift.
- Live sustain: pipeline_status + subagent tags (BACKFILL, MASS-MARKET, VERIFICATION) + schedulers enforce.

See `neural-map-holo.html` (launch it), `tests/data-fidelity.js`, `neural-map-holo-guts.md` for implementation. Data lives in `data/`. Live feeds via R2 + `scripts/`.

The map is the product. The ZDF case proves the thesis.

## RSS News (rss_news source) - Liveness & New News Features
- Added dedicated `rss_news` source in monitor/backfill + new lightweight `rss-monitor.yml` (cron `*/30 * * * *`).
- Discover pulls from public high-signal RSS (Reuters, AP, NYT, BBC, CNN, Guardian, WSJ, gov feeds) → ingests article HTMLs to `raw/news/rss-*-*.html` + feed XML snapshots to `raw/media/rss-*.xml` (and `raw/news/`).
- **Auto chaining for efficiency & liveness**: `ingest RSS` (monitor or rss-monitor) → `process-data.yml` (text extract + entity/signals for news items) → `analyze-data.yml` (new news features: repeated phrases/coordination detection, framing density, timelines, tactic scores, entity graphs from current events) → `build-politician-profiles.yml` if entities detected.
- **Liveness benefits**: 30min cadence catches breaking news/gov releases fast (last-hour items in health checks). Low-overhead (small max_new, parallel futures for feeds in discover_rss_news_new, short windows). Complements daily broad monitor + weekly backfill (rss_news supports --backfill for historical news story depth).
- **Health**: Use `python scripts/check_r2_health.py --rss --liveness-hours 1` (counts in raw/news/ + raw/media/rss-*, samples, last-hour live items, R2 path hits, NOTIFY guidance). Cloudflare R2 UI cross-check under `raw/news/` and `raw/media/`.
- **Dispatch examples**:
  - Lightweight live: `gh workflow run rss-monitor.yml` (or auto every 30min).
  - Full with RSS: `gh workflow run monitor-ingest.yml -f sources=rss_news,gdelt,... -f auto_process=true`.
  - Historical RSS: `gh workflow run backfill.yml -f sources=rss_news -f backfill-level=deep`.
  - Manual specific: after ingest, `gh workflow run process-data.yml -f arena=news -f raw_key=raw/news/rss-...` then analyze with the processed_key.
- Sources list (in discover): reuters, ap-*, nyt-*, wsj, bbc, cnn, guardian + gov (whitehouse, justice, gao). Extend in monitor_and_ingest.py.
- See DATA_PROCESSING.md, DATA_SOURCES_TESTED.md, workflows/*.yml, scripts/monitor_and_ingest.py (rss special casing + futures concurrency), scripts/check_r2_health.py.
- Keeps everything efficient and live: targeted RSS avoids full scan cost, futures parallelize, auto-chain only on new, health verifies paths/live state.

## Holographic Neural Map + R3F Migration (Docs/Delegation focus)
- Core: neural-map-holo.html (full self-contained vanilla Three prototype) + neural-map-holo-guts.md (extracted + now expanded). See Phase 1 platform updates (top of this file) for rich AI data from narrative-forge pipeline (smart_extract + Worker) feeding Holo/ZDF.
- Historical subagent work (perf, sonif, visuals, deployment, migration, archetypes, R2) referenced in agent-history/ reports + Heavy-Agents-Coordination.md. Repetitive MAX SUSTAIN credits/spam cleaned (targeted) here per AGENTS.md rules to keep docs focused/maintainable. Refer to Heavy-Agents-Coordination.md Phase 1 status and roadmap.
- **DATA_*.md** enhanced historically with catalog summaries; current focus Phase 1 rich data + ckg-holo-analytics sinks.

**Archetypes / ZDF notes (historical, cleaned per AGENTS.md):** Full 11 + ZDF/Elon deep (nimrod etc) prior work complete. See Heavy-Agents-Coordination.md + agent-history/ for details and Phase 1 updates (rich data from Worker now feeds ZDF evidence). No MAX SUSTAIN spam.

**Single-repo narrative-forge deployment by background subagent 019eccff-2b6e-7933-8f95-32a32c3d26f5.** Explicit credit + "Single-repo narrative-forge deployment" in this README, IMPLEMENTATION_TASKS.md, neural-map-holo-guts.md (and cross narrative-forge docs/TEST/IMPLEMENTATION/README). Verifier/enhancer confirmed full ZDF/Elon parity + cross-wiring (4D scrub/glitch sonif/export signed bundles with 4D/PNG/prov/X/reclaim/analytics sink/live deltas/WebGPU/fallback/PWA/deep links in both golden self-contained + deprecated R3F port). Golden review artifact; narrative-forge prod. Exact mappers. Fidelity roundtrip ZDF PASS. New spawn 019ecd52-8ec2-7840-a665-16e0-holo-verifier. Keep field hot; rec to continuous orchestrator (ZDF/Elon pinnacle sustain).
- Data: data/politicians-index.json, news-synthesis.json, profiles/, news-sample.json + scripts/update_politicians_neural_map.py + R2 workflows (monitor/rss).
- Deploy target: narrative-forge static golden holo — see its README + copy skeleton from guts. Deploy: static holo.html artifact on thebreakerofbabylon.com.
- Delegate: use expanded list in guts.md; open teams for parallel work. R2 live via existing crons + SWR.

Cross-ref R2_VERIFIER_CYCLE.md, preview-*.html, DATA_*, holo.html, scripts/, .github/workflows/.

# narrative-forge
Narrative Forge - The 11-domain interactive truth engine exposing legacy media, political, bureaucratic, legal, financial, cultural, and health systems tactics through thought bridges, graphs, flowcharts, memes, and public data synthesis. Built with PHP/Composer backend + modern JS frontend.

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

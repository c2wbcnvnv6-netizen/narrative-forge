# DATA INGEST FIRST RUN — One Step at a Time

This gets the raw data download pipeline live and ready for your first (and huge initial) data parameters.

Everything below is deliberately tiny steps. Do **one thing**, then pause. No pressure.

## Why this matters (short)
- Your 4 R2 secrets are already in the repo (from the GitHub page you showed).
- The workflows + script you asked for are now in the code.
- Once pushed (this doc helps), the "Actions" tab on GitHub will show two new workflows:
  1. "Test R2 Raw-Data Bucket Connection" — zero inputs, proves everything talks to your babylon-raw-data bucket.
  2. "Ingest Raw Data (for first download parameters)" — exactly the 3 inputs you need (arena + source_url + target_key).
- The Python script is built for huge files (streams, low memory).
- This is the foundation for all 11 arenas data + later analysis/NLP/graphs.

## Prerequisites (already done by you)
- 4 Repository secrets added: R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_ENDPOINT, R2_ACCOUNT_ID
- A bucket named `babylon-raw-data` (or change the default in the script later)
- You are on the GitHub page for c2wbcnvnv6-netizen/narrative-forge

## Tiny Step 1 — Push the files (this makes the workflows appear)

Since the local folder on your machine is not yet a git repo for this project, the easiest safe way is:

**Option A (recommended — let the system push for you if it offers)**
- If after this you see a confirmation that files were pushed via the connected tools, great.

**Option B (you do the push — exact commands, copy/paste one line at a time)**

1. Open your terminal (the same one you use for this).
2. Run exactly this (copy the whole line):

   ```
   cd /Users/daboss/narrative-forge
   ```

3. Check what is here (one command):

   ```
   ls -la .github/workflows scripts DATA_INGEST_FIRST_RUN.md
   ```

4. Initialize git + connect to your GitHub repo (only needed once):

   ```
   git init
   git branch -M main
   git remote add origin https://github.com/c2wbcnvnv6-netizen/narrative-forge.git
   ```

5. Add only the new pipeline pieces:

   ```
   git add .github/workflows/ingest-raw-data.yml .github/workflows/test-r2-connection.yml scripts/ingest_raw_data.py DATA_INGEST_FIRST_RUN.md
   ```

6. Commit (tiny message):

   ```
   git commit -m "Add parameterized ingest workflow + streaming script + test + first-run guide. Ready for first download data parameters."
   ```

7. Push (this is the one that lands it on GitHub):

   ```
   git push -u origin main
   ```

   - If it asks for login: use your GitHub username + a classic PAT (Personal Access Token) with "repo" scope, or the GitHub CLI `gh` if you have it installed.
   - After push succeeds you will see the commit on the repo.

**After push succeeds**, continue to Tiny Step 2.

## Tiny Step 2 — Verify the workflows are live on GitHub (no code change)

1. Go to your repo in browser: https://github.com/c2wbcnvnv6-netizen/narrative-forge
2. Click the **Actions** tab (top menu).
3. In the left sidebar you should now see two new workflows:
   - Test R2 Raw-Data Bucket Connection
   - Ingest Raw Data (for first download parameters)
4. If you don't see them yet, wait 10-30 seconds and refresh the page, or check the "All workflows" filter.

**Why this matters**: The workflows only become selectable after the yml files live on the default branch (main).

## Tiny Step 3 — Run the Test workflow first (zero parameters, proves the connection)

This is the safe "hello world" before feeding real data.

1. In the Actions tab, click **Test R2 Raw-Data Bucket Connection**.
2. On the right, click the big **Run workflow** button (it has a dropdown for branch — leave as main).
3. Click the green **Run workflow** button (no inputs to fill).
4. Wait for the run to start. Click into the running job.
5. Watch the steps:
   - "Configure R2 credentials"
   - "List contents of babylon-raw-data..."
6. It should succeed and show either "No objects" or a list of anything already in the bucket.

**If it fails**:
- Double-check the 4 secrets are spelled exactly as R2_*
- Make sure the bucket name in the yml matches what you created in R2 (babylon-raw-data).
- Re-run after fixing secrets if needed.

When the test turns green → you are ready for real data.

## Tiny Step 4 — Run your first real ingest with parameters (the "download data parameters")

1. In Actions, click **Ingest Raw Data (for first download parameters)**.
2. Click **Run workflow**.
3. Fill the three boxes exactly:

   - **arena**: congress   (or elections, finance, media, bureaucracy, scotus, migration, etc. — use lowercase short name)
   - **source_url**: a real direct public download link (example below)
   - **target_key**: something clear like `raw/congress/2024/test-awards.csv`

4. Click the green Run workflow.

### Safe first example parameters (pick one small-ish public file to start)

Good starter public direct URLs (these are real patterns; confirm a current one on the site):

- A small FEC file or USAspending awards summary (search "usaspending.gov bulk download" or "congress.gov bulk data" and grab a direct .csv or .zip link that is public).
- Example shape only (replace with a real current link you copy from the site):
  - arena: `congress`
  - source_url: `https://www.usaspending.gov/api/v2/download/awards/?...` (or the published static bulk files they link)
  - target_key: `raw/congress/2024/sample-awards.csv`

**Tip for huge initial dumps later**:
- Same workflow, just give it a much bigger source_url and a descriptive target_key.
- The script will print size + elapsed time.
- R2 is great here (zero egress when we later read the same objects many times for AI/NLP/embeddings across the 11 arenas).

After the run finishes green:
- Go to your Cloudflare R2 dashboard → babylon-raw-data bucket.
- You should see the object at the target_key path.
- Size should match what the workflow printed.

## A / B / C — What do you want to do right after the first successful ingest?

A) Tell me the exact source_url + arena + target_key you used for the first run (or a planned one) and I will walk you through what to expect in the logs + next tiny analysis steps.

B) Park the data pipeline for now. Tell me the next piece you want to tackle (for example: add the first analysis workflow that turns raw into processed docs/embeddings, improve the preview site, build the first thought bridge UI for one arena, directory data, etc.). Just say the letter or describe.

C) Run the Test + one small ingest right now and report back what you saw (success or any error message). I will help debug one line at a time.

## Quick reference — the three inputs again
- arena (string, required)
- source_url (full direct URL, required)
- target_key (string path in bucket, required)

You control the "first download data parameters" completely through the GitHub UI.

## Notes for later (only read when needed)
- Later we can add scheduled detection, more arenas, post-ingest jobs (NLP, graph building, etc.) that read from babylon-raw-data and write to processed/ or embeddings/ buckets.
- **Algorithmic continual monitoring is now implemented** (see scripts/monitor_and_ingest.py + .github/workflows/monitor-ingest.yml).
  - Cron-scheduled (daily + mid-week) discovery of *new* dumps from GDELT (daily), Common Crawl (new crawls), HF Pushshift/Reddit mirrors, IA Twitter streams, etc.
  - Uses R2 listing + manifests/ingested.json to only download what is actually new.
  - Idempotent streaming ingest re-uses the core script.
  - Supports --dry-run, --max-new, --sources, --arena from workflow_dispatch for manual control.
  - This builds the living archive automatically for easy access/referencing across all arenas (media/social especially).
- Add new discover_* functions in monitor_and_ingest.py for additional sources (FEC cycles, new Census releases, more IA/HF collections, rss_news feeds, etc.).
- Post-ingest (NLP/embeddings/graphs) can be chained by calling the Process Ingested Data workflow from the monitor after successful ingests.
- **RSS news liveness**: See new rss-monitor.yml (*/30 * * * *), rss_news in monitor/backfill sources. Use for raw/news/ + raw/media/rss-*. Health via scripts/check_r2_health.py --rss. Auto chains to process/analyze for news features.

You are doing great. One micro-step at a time.

When you finish Step 3 (the test run), come back and tell me the result (or paste any short output) and we pick A/B/C or the very next concrete thing.

— The pipeline team (ready when you are)

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

(End of catalog; cross-ref neural-map-holo-guts.md, holo.html, scripts/ for full mappers + R3F port. Use in first ingest follow-ups for arena-specific analysis.)
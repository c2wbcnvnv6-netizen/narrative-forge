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
- Add new discover_* functions in monitor_and_ingest.py for additional sources (FEC cycles, new Census releases, more IA/HF collections, etc.).
- Post-ingest (NLP/embeddings/graphs) can be chained by calling the Process Ingested Data workflow from the monitor after successful ingests.

You are doing great. One micro-step at a time.

When you finish Step 3 (the test run), come back and tell me the result (or paste any short output) and we pick A/B/C or the very next concrete thing.

— The pipeline team (ready when you are)
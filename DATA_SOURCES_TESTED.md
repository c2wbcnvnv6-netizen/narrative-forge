 # DATA SOURCES TESTED — The Breaker of Babylon (11 Arenas)

Curated, tested (where possible) public data sources for raw ingest + API pulls. Prioritizes **direct downloadable files** (for the streaming ingest script to R2 `babylon-raw-data`) and **keyless or easy API endpoints** for ongoing pulls/analysis.

**Local streaming test performed (2026-06-14):** Confirmed working for the first recommended download using the exact logic from `scripts/ingest_raw_data.py`.

All sources are public / official gov or well-known open data. Many support bulk/raw for the "huge initial dump" goal.

## Recommended FIRST Download (ready now)
- **arena**: `finance` (or `congress`)
- **source_url**: `https://files.usaspending.gov/reference_data/cfda.csv`
- **target_key**: `raw/finance/cfda-reference.csv` (or `raw/congress/usa-spending-cfda.csv`)
- **Why**:  ~32-34 MB direct CSV (Catalog of Federal Domestic Assistance / awards reference). Perfect for bill granulizer, appropriations, bureaucracy, finance arenas. Confirmed HTTP 200 + streaming works locally.
- **How to trigger**:
  1. GitHub → Actions → "Ingest Raw Data (for first download parameters)" → Run workflow.
  2. Paste the 3 values above.
  3. (Or after `gh auth login`: `gh workflow run ingest-raw-data.yml --repo c2wbcnvnv6-netizen/narrative-forge -f arena=finance -f source_url=https://files.usaspending.gov/reference_data/cfda.csv -f target_key=raw/finance/cfda-reference.csv`)

**Test workflow first (recommended)**: Run "Test R2 Raw-Data Bucket Connection" (no inputs) to verify bucket access.

## 11 Arenas + Sources (Tested / Researched)

**1. SCOTUS / Legal / Case + Lawfare** (Marc Elias, Norm Eisen patterns, Raskin etc.)
- Bulk opinions: govinfo or https://www.supremecourt.gov/opinions/ (XML/PDF per term)
- Better structured bulk: CourtListener (https://www.courtlistener.com/) or RECAP bulk archives (torrents/direct).
- API: Oyez or CourtListener API (some public endpoints).
- Ingest note: Start with small recent opinion XML from govinfo.

**2. Congressional Bill Granulizer** (appropriations → committees → lobbyists → outcomes)
- **Direct file (tested/confirmed)**: https://files.usaspending.gov/reference_data/cfda.csv (above)
- Bill Status XML bulk (keyless files): https://www.govinfo.gov/bulkdata/BILLSTATUS (per Congress folders, e.g. /119/ subpaths contain per-bill XMLs — pick individual or full packages).
- Congress.gov API (free key from api.data.gov): https://api.congress.gov/ (bills, amendments, summaries). GitHub docs: LibraryOfCongress/api.congress.gov.
- USAspending award downloads (API generates zips or published bulk on files.usaspending.gov).
- ProPublica Congress API (key needed).

**3. Foreign Nexus** (NGOs, malign influence)
- OFAC / Treasury sanctions lists (direct CSVs/JSON): https://sanctionssearch.ofac.treas.gov/ or data downloads.
- State Dept / USAID data.
- FARA (Foreign Agents Registration Act) filings (DOJ bulk).
- Research: Use open_page/web_search on specific reports + direct exports.

**4. Mass Migration**
- CBP / DHS stats & encounters (direct downloads or Excel/CSV on cbp.gov or dhs.gov).
- USCIS data tables.
- Census migration / ACS data (see #7).
- USAspending for related program spending (tie to #2).

**5. Societal Declination + Historical Mirrors** (Rome etc. parallels)
- Census, BLS, vital stats, trust/survey data (Pew, Gallup exports where public).
- Historical: Library of Congress, Census historical tables.
- Cross with modern metrics (crime, economy, education from multiple arenas).

**6. Bureaucracy / Administrative State / Agencies**
- **Federal Register API (keyless, tested sample successful)**: https://www.federalregister.gov/api/v1/documents (JSON/CSV, search, per-document). No key. Excellent for rules, notices, agencies.
- Bulk XML: https://www.govinfo.gov/bulkdata/FR
- USAspending agency profiles + awards (ties to finance).
- Regulations.gov bulk (newer downloads available).
- eCFR API.

**7. Elections / Voting / Census & Demographic Engineering**
- **FEC bulk data** (zips of .txt — current cycles on https://www.fec.gov/data/browse-data/ under Bulk Data section. Examples historically: indiv[yy].zip, cn[yy].zip, contributions. Note: exact current filenames change; browse the page for latest direct links).
- Census API (free key required now for queries): https://api.census.gov/data/... (ACS, decennial, redistricting). Bulk FTP direct zips/CSVs: https://www2.census.gov/ (no key for many summary files).
- Direct example patterns from research: state-level summary files, PL 94-171 redistricting.

**8. Media-Tech-Censorship & Disinformation Industrial Complex**
- Public bias charts / datasets (AllSides, Ad Fontes, Media Bias Chart exports if downloadable).
- News API samples or public archives.
- Censorship reports (e.g. Twitter Files primary sources, government reports via govinfo).
- Harder for pure bulk; use web tools + targeted pulls + crowdsourced later.

**9. Finance / Central Banking / Monetary & Economic Levers**
- **USAspending (tested direct)**: cfda.csv + full award downloads (api.usaspending.gov for generated zips or files.usaspending.gov).
- Treasury / Fed data (FRED API, direct CSVs).
- OpenSecrets / CRP bulk (some direct after registration or public files).
- IRS SOI tax stats (direct tables).

**10. Education / Academia / Cultural Institutions**
- Dept of Education (ED) data downloads (https://data.ed.gov/).
- NCES (National Center for Education Statistics) tables + API.
- IPEDS, NAEP bulk files (direct CSVs often available).

**11. Pharma / Medical-Industrial Complex + Nutritional Policy & Federal Ideological Health Capture**
- FDA open data / FAERS, device, drug approvals (direct downloads + API).
- CMS (Medicare/Medicaid) data files.
- NIH / clinicaltrials.gov (bulk downloads).
- USDA / nutritional policy (SNAP, school lunch data, etc.).
- Ties heavily to spending (USAspending "health" programs).

## How We Tested (Tools Used)
- web_search for discovery of bulk/API pages.
- open_page / browse_page attempts for page content extraction.
- run_terminal_command + curl (HEAD + range) + python requests (full streaming like the ingest script + API JSON samples).
- Confirmed: USAspending cfda.csv streams correctly (~32MB, 200, ranges supported).
- Federal Register API: Live sample pull (no key, JSON results returned).
- FEC / govinfo: Structure documented; direct file links require picking current from browse pages (some older examples still valid for pattern).
- Many gov sources are deliberately keyless for bulk files (great for our zero-egress R2 + repeated AI analysis).

## Next for Data Pipeline
- Trigger the first real ingest (params above) → object lands in R2.
- Future: Add post-ingest workflows (Python in Actions) for NLP (doublespeak/framing), embeddings (for RAG/search), graph building (nodes = politicians/agencies/media, edges = funding/narratives/timing).
- Scheduled detection on sources.
- Expand to more direct files per arena (pick from the lists).
- For APIs needing keys: Add optional secret handling later (never commit keys).

This gives a strong, data-driven foundation across the 11 arenas as one living system.

Run the test workflow + the first ingest with the cfda URL. Report back the run ID / logs / R2 object appearance and we'll do the next (analysis on the landed data, more sources, UI thought bridge for that arena, etc.).

One micro-step at a time. You now have tested, ready parameters and verified the download path works. 

— Ready for the first real R2 load.
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

## Expanded State/Local/Metro & Additional Citable Sources (for Maximum Extrapolation Points)
Added in latest research round for state/local (esp. metros) + more global for citable, longitudinal data. All official/gov sources for high credibility in narratives/extrapolation (e.g., consistent time-series for trends, correlations across policy domains).

**Census Metro (MSA/CBSA) - Core for local demographic extrapolation, harmonized geographies:**
- TIGER/Line CBSA shapefiles (direct ZIP for current metro boundaries): https://www2.census.gov/geo/tiger/TIGER2025/CBSA/tl_2025_us_cbsa.zip → raw/metro/census-tiger-cbsa-2025.zip
- ACS 5-Year Estimates for MSAs (nation, states, metros, counties, tracts, block groups): Via data.census.gov or bulk FTP. Highly citable (U.S. Census Bureau).
- NHGIS (IPUMS) time-series ACS + GIS boundaries (best for historical consistency/extrapolation over decades for same metro definitions): https://www.nhgis.org/ (Data Finder for bulk extracts; registration-free for many). Citable as IPUMS NHGIS. Includes 1790+ for long-term parallels.

**BLS QCEW (Metro/County Employment & Wages) - Gold standard for local labor/economic extrapolation by industry:**
- Quarterly Census of Employment and Wages bulk CSVs (county, MSA, state by 6-digit NAICS; open data slices + full historical): https://www.bls.gov/cew/downloadable-data-files.htm and https://www.bls.gov/cew/additional-resources/open-data/ (direct CSV via api/ or files, e.g. https://data.bls.gov/cew/data/api/2024/1/area/US000.csv). Updated quarterly, covers 95%+ jobs. Citable BLS source.

**Major State Open Data Portals (for policy, grants, health, environment at state level - citable .gov):**
- California (largest): https://data.ca.gov/ (Socrata/CKAN; direct CSVs for grants, health, water, etc., e.g. via catalog exports or /api/views/.../rows.csv?accessType=DOWNLOAD).
- New York: https://data.ny.gov/ (Open NY; 1500+ items, bulk via API/export).
- Texas: https://data.texas.gov/
- Colorado: https://data.colorado.gov/
- Illinois: https://data.illinois.gov/
- Maryland: https://opendata.maryland.gov/
- Full lists: data.gov (state section), dataportals.org, Forbes compilation of 50+ state portals (many Socrata/CKAN with bulk/API CSV). Add more states as needed for specific extrapolation.

**Major Metro/Local City/County Portals (for hyper-local services, 311, housing, crime - citable for urban narratives):**
- NYC Open Data (key metro): https://opendata.cityofnewyork.us/ (Socrata; direct CSV exports e.g. https://data.cityofnewyork.us/api/views/erm2-nwe9/rows.csv?accessType=DOWNLOAD for 311 historic; payroll, etc.).
- LA County: https://data.lacounty.gov/
- OpenDataPhilly: https://opendataphilly.org/
- Many others via data.gov local or city search (Chicago data.cityofchicago.org, SF datasf.org, etc.). Focus on top 20 metros for volume.

**Additional for Global Extrapolation (citable international/regional for parallels to US state/local):**
- Eurostat NUTS (EU subnational/regional - NUTS1/2/3 for metro-like): Bulk downloads via https://ec.europa.eu/eurostat/databrowser/bulk (GDP, population, labor by NUTS; TSV/CSV/SMDX). Complements US metros.
- data.europa.eu (EU + national open data, subnational).

**Notes for Pipeline & Citability:**
- Added as new discover_ functions (census_metro, bls_qcew, nyc_open, ca_open, nhgis_metro, eurostat_nuts) in monitor_and_ingest.py. Many use direct public ZIP/CSV (TIGER, BLS slices, Socrata exports, Census). Portals like state/CA/NYC use Socrata pattern for bulk CSV.
- NHGIS: Best for "extrapolation points" (harmonized time series + boundaries for consistent metro comparisons 1790-present; highly citable from IPUMS). May require Data Finder for exact bulk (not fully auto-direct like others); prioritize for key metros.
- Full state/local: 50 states + 1000s locals; script focuses on major/high-impact for volume (add specifics via manual ingest or extend discovers). Use data.gov US open data CSV list for more.
- Citable: All from .gov (Census, BLS, HUD/EPA via data.gov), state .gov portals, Eurostat (official EU stats). Cite as "U.S. Census Bureau, [Year] ACS 5-Year Estimates via [source]" or "Bureau of Labor Statistics, QCEW [Quarter]".
- This massively expands citable sources for the 11 arenas (e.g., local employment for finance/metro, health data for pharma/policy, legislative for congress). Enables strong extrapolation (time trends, cross-metro/state comparisons, historical mirrors like Rome parallels via long series).
- "Huge": With backfill + these, hundreds/thousands of files over time. R2 handles storage cheaply; use incremental runs (cron + manual). Monitor for new releases (many quarterly/annual). Test with small max_new first.

Dispatched new aggressive monitor runs (with expanded sources + backfill) + specific direct ingests (TIGER CBSA, BLS QCEW examples) to start downloading immediately. Check Actions for progress; new data will land in R2 under raw/metro/, raw/state/, raw/local/ etc. Local watcher will notify on completion.

Next: Review specific new runs/logs, extend for more states (e.g., via dataportals.org list), or refine NHGIS automation if API direct found. This gives the max citable base for the project.

## Documents Folder Sources (Court Rulings, Press Releases, CRS/GAO Reports, FOIA etc.)
Added dedicated discover functions (court_documents, press_releases, crs_gao_reports, foia_documents) + direct ingest support. All target `raw/documents/` (with subpaths courts/, press/, crs/, foia/, gao/ etc.) for primary text/PDF/HTML sources. These are the "documents" requested: official rulings, contemporaneous press (for framing/timing analysis), neutral expert reports (CRS), audits (GAO), and transparency releases (FOIA/transcripts).

**Key direct sources added (all public/official, citable, many verified HTTP 200 + direct bytes):**

**SCOTUS / Court Rulings (slip opinions - direct PDF from supremecourt.gov, October Term 2025/2026):**
- https://www.supremecourt.gov/opinions/25pdf/25-6_d1o2.pdf → raw/documents/courts/scotus-25-6-keathley-v-ayers.pdf (Keathley v. Buddy Ayers Construction, decided 2026-06-11)
- https://www.supremecourt.gov/opinions/25pdf/24-345_i42k.pdf → .../scotus-24-345-fs-credit-v-saba.pdf (2026-06-11)
- https://www.supremecourt.gov/opinions/25pdf/25-5146_e29f.pdf → .../scotus-25-5146-abouammo.pdf
- https://www.supremecourt.gov/opinions/25pdf/24-889_5i36.pdf → .../scotus-24-889-hikma-v-amarin.pdf (2026-06-04)
- https://www.supremecourt.gov/opinions/25pdf/25-406_nmip.pdf → .../scotus-25-406-fcc-v-att.pdf (2026-06-04)
- https://www.supremecourt.gov/opinions/25pdf/24-109_new_jifl.pdf → .../scotus-24-109-louisiana-v-callais.pdf (2026-04-29)
- https://www.supremecourt.gov/opinions/25pdf/24-781_pok0.pdf → .../scotus-24-781-first-choice-v-davenport.pdf
- https://www.supremecourt.gov/opinions/25pdf/24-539new_3fb4.pdf → .../scotus-24-539-chiles-v-salazar.pdf (2026-03-31)
- Additional older prelim prints available e.g. https://www.supremecourt.gov/opinions/preliminaryprint/592US1PP_web.pdf (for backfill). Citable: "Supreme Court of the United States, Slip Opinion No. XX-XXX (2026)".

**Press Releases & Briefings (full pages for narrative framing/timing/synthesis):**
- White House (current): https://www.whitehouse.gov/briefings-statements/2026/06/presidential-message-on-the-251st-birthday-of-the-united-states-army/ → raw/documents/press/wh-2026-06-army-251st-birthday.html
- https://www.whitehouse.gov/briefings-statements/2026/06/first-lady-melania-trumps-remarkable-week-empowering-youth-through-ai-challenge-and-fostering-the-future-accounts/
- DOJ/OPA recent: https://www.justice.gov/opa/pr/former-intelligence-community-contractor-pleads-guilty-accepting-kickbacks (2026-06-12) → .../doj-2026-06-12-duggin-kickbacks.html
- https://www.justice.gov/opa/pr/nevada-man-pleads-guilty-rigging-bids-healthcare-related-and-other-air-force-projects
- Historical: trumpwhitehouse.archives.gov (e.g. /briefings-statements/ index for 2017-2021 comparison). Citable: "The White House, Briefing Statement (2026-06-14)" or "U.S. Department of Justice, Office of Public Affairs Press Release (2026-06-12)".

**CRS Reports (EveryCRSReport.com direct PDFs/HTML - complete public archive mirror of Congressional Research Service non-confidential reports):**
- https://www.everycrsreport.com/files/2026-06-02_R48296_2b94164541695afb9bd851e9161df28b12d54978.pdf → raw/documents/crs/2026-06-02-improper-payments-ongoing-challenges.pdf (29p)
- https://www.everycrsreport.com/files/2025-05-21_R48544_496ef9d65a8dd51ed2a4ed3321f211f7fc9bdaa2.pdf
- https://www.everycrsreport.com/files/2025-01-16_R48360_0d9acfa5f0765cd6f4a51c4565edbe087a312535.pdf
- https://www.everycrsreport.com/files/2025-06-02_R45104_665a366a50148a021b27f266f82391f13da81562.pdf
- Index for discovery: https://www.everycrsreport.com/reports.csv + https://www.everycrsreport.com/all-reports.html (23k+ reports tracked). Citable: "Congressional Research Service, [Title] (RXXXXX, 2026)" via EveryCRSReport.com mirror of official CRS.

**GAO Reports (audits, high-risk, duplication reviews - citable for waste/fraud/efficiency narratives):**
- Example pages/PDFs via https://www.gao.gov/ (e.g. GAO-26-108610 "The Nation's Fiscal Health", GAO-26-108113 F-35, High-Risk Series GAO-25-107743). Direct assets like https://www.gao.gov/assets/gao-26-108742.pdf (some may require page context). Added via discover for reports pages + known PDFs. Citable: "U.S. Government Accountability Office, GAO-26-XXXX (2026)".

**FOIA / Transcripts / Released Documents:**
- https://www.govinfo.gov/bulkdata (courts/legislative bulk for released docs)
- https://www.justice.gov/foia (reading room + specific releases)
- Specific high-profile public releases (e.g. transcripts, dockets) to be added as direct PDFs surface (govinfo, agency FOIA libraries, or congressional). Extend discover with targeted e.g. Epstein-related public files or congressional hearing transcripts as identified.
- Citable: "U.S. Department of Justice FOIA Release" or "GovInfo [collection]".

**Notes for Pipeline & Citability:**
- Added as discover_court_documents_new, discover_press_releases_new, discover_crs_gao_reports_new, discover_foia_documents_new in monitor_and_ingest.py (and to SOURCE_MAP + broad defaults + workflow). Functions use HEAD probes on direct links for idempotency (skip if key exists in R2/manifest). Arena="documents" for all; keys under raw/documents/courts|press|crs|foia|gao/.
- Local mirror dirs created: raw-downloads/documents/{courts,press,crs,foia,gao,state-ag}.
- Ingest handles any bytes (PDF binary, full HTML pages with content, text). Post-ingest process-data can summarize (title, date, key excerpts via future NLP for doublespeak/framing).
- Why these: Primary sources for "exposing legacy media and political narrative tactics" - exact wording/timing of official releases vs. coverage; CRS/GAO for factual baselines to contrast spin; court docs for lawfare/SCOTUS patterns. All public, no keys, direct or near-direct, globally citable (gov + CRS mirrors).
- "At all times": New sources included in daily cron defaults + manual dispatch with --sources court_documents,press_releases,... --backfill true --max-new 50 --auto-process. Will continually catch new slip opinions (weekly), new releases (daily), new CRS (as posted).
- Volume: Dozens initial + ongoing (SCOTUS ~50-80/term, CRS thousands, press hundreds/week). Use backfill for historical depth. R2 + manifest tracks. Notifications fire on ingest (NOTIFY: marker watched by local script for phone + naomiseibt@gmx.de).
- Future extensions: CourtListener RECAP bulk/tar (if direct), full state AG portals (ag.ny.gov, oag.ca.gov press PDFs), more govinfo SCD/USCOURTS specific, congressional hearing transcripts, FOIA.gov releases. Add via new candidates in discovers or direct gh ingest-raw-data dispatches.

Dispatched initial document-focused monitor runs (broad + specific documents sources, backfill, high max_new, auto_process) + direct targeted ingests for verified SCOTUS/CRS/WH/DOJ URLs to begin filling raw/documents/ immediately. Check GitHub Actions (monitor-ingest.yml and ingest-raw-data.yml) for runs; local bg watchers will surface NOTIFYs and email+SMS. This directly continues the "all things at all times" + state/local expansion.

Citable, primary, "go deep" sources now live in the archive pipeline.

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

(End of catalog; cross-ref neural-map-holo-guts.md, holo.html, scripts/ for full mappers + R3F port.)

## RSS News Sources (rss_news) — for Liveness, Media Narrative, Current Events Signals
Added as first-class source ("rss_news") to SOURCE_MAP + defaults in monitor-ingest.yml / backfill.yml + new lightweight rss-monitor.yml.
- **Why liveness**: High-frequency (30min dedicated cron) RSS polling detects breaking releases from official + major outlets in near-real-time. Feeds into "new news features" in analyze (repeated language across coverage, framing tactics in media, entity timelines synced to events). Complements slower document/court/CRS (post-facto) with live media layer.
- **Sources list** (curated public RSS, extendable; all keyless):
  - Reuters: http://feeds.reuters.com/reuters/topNews , /worldNews
  - AP: https://feeds.apnews.com/rss/ap-top-news , /ap-politics
  - NYT: https://rss.nytimes.com/services/xml/rss/nyt/HomePage.xml , /Politics.xml
  - WSJ: https://feeds.a.dj.com/rss/RSSWorldNews.xml
  - BBC: http://feeds.bbci.co.uk/news/world/rss.xml
  - CNN: http://rss.cnn.com/rss/cnn_topstories.rss
  - Guardian: https://www.theguardian.com/world/rss
  - Gov/related (via discover patterns): whitehouse briefings, justice.gov opa, gao news (direct RSS endpoints)
- **Storage + processing paths**: raw/news/ (per-article HTML for full extract) + raw/media/rss-*.xml (feed snapshots for archive). Processed to processed/news/ , derived/ for analysis. Arena="news".
- **Liveness benefits + health**: Last-hour items detectable; check_r2_health.py --rss reports counts, samples, live items in window, R2 hits for news paths, verifies Cloudflare raw/media/ + raw/news/. NOTIFYs emitted on ingest/process/analyze. Use in master monitor status.
- **Backfill / efficiency**: Supports --backfill (deeper 30d+ windows for historical news context). Lightweight separate workflow (rss-monitor.yml) for 30min cadence avoids overhead of full monitor (which also supports rss_news in broad runs). Parallel (futures) feed fetching in discover_rss_news_new. Auto full chain supported.
- **How to use / dispatch**:
  - Liveness: GitHub Actions → rss-monitor.yml → Run workflow (or auto).
  - With others: monitor-ingest.yml dispatch with sources including rss_news.
  - Historical: backfill.yml with rss_news.
  - Direct health: python scripts/check_r2_health.py --rss (after R2 env).
  - Follow-on: process + analyze on the landed raw/news keys (or auto).
- **Citatability**: All public RSS from reputable outlets/gov. Cite "Reuters [title] (via RSS feed, [pubDate])" etc. Full HTML preserved in R2 for verification.
- **Coordination**: Workflows updated (monitor-ingest, backfill, process, analyze + new rss-monitor). Health script added. Docs (this + README + DATA_PROCESSING) updated. Ensures support for new discover across master + subagents. Paths raw/news/ + raw/media/ verified in health for Cloudflare.
- Extends the 11 arenas with live media-tech / narrative signals layer for "at all times" monitoring.

This completes high-velocity news ingestion while keeping the pipeline efficient and chained.
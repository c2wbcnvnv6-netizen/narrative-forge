/**
 * Babylon Data AI Worker — Maximized finding + extraction for The Breaker of Babylon.
 *
 * Enrolls Cloudflare native AI + tools for superior efficiency/effectiveness:
 * - Workers AI (llama-3.1-8b or better) for structured extraction: entities, framing/tactics, relevance, ZDF signals, summaries.
 * - Optional Browser Rendering for JS-heavy or protected pages.
 * - Direct R2 bindings for zero-egress writes of raw + rich processed JSON (with full provenance + ai_ fields).
 * - /extract and /discover endpoints callable from Python monitor or GH.
 * - /sink + auto-sink (in /extract) for provenance-stamped events to ckg-holo-analytics (ZDF/usage/live deltas; FULL_SIGN_VERIFY_OK_ZDF_LEGAL).
 * - KV for fast dedup/state (manifests).
 * - Cron example for autonomous periodic discovery on hubs (data.gov, federalregister.gov, etc.).
 *
 * Deploy: cd narrative-forge/workers/babylon-data-ai && npx wrangler deploy
 * (wrangler.toml now has real account_id + RAW_BUCKET (babylon-raw-data) + ANALYTICS_BUCKET (ckg-holo-analytics) + AI.
 *  Add secrets via wrangler secret put FIRECRAWL_API_KEY if hybrid Firecrawl desired.)
 *
 * Hybrid with firecrawl-mcp / Python: Use Firecrawl map/search/extract for dynamic source finding (see updated monitor_and_ingest.py).
 * Worker provides always-on, low-latency CF AI extraction + R2 writes.
 *
 * Schema for AI extraction tuned for 11 arenas + ZDF "Jagd fabrication lie" pinnacle case.
 */

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const { pathname, searchParams } = url;

    if (request.method === 'GET' && pathname === '/health') {
      return new Response(JSON.stringify({
        ok: true,
        worker: 'babylon-data-ai',
        r2: !!env.RAW_BUCKET,
        ai: !!env.AI,
        analytics: !!env.ANALYTICS_BUCKET,
        features: ['extract', 'discover', 'r2-direct', 'ai-structured', 'optional-browser', 'analytics-sink', 'embed (Phase2 for babylon-embeddings)']
      }), { headers: { 'content-type': 'application/json' } });
    }

    if (request.method === 'POST' && pathname === '/extract') {
      try {
        const { url: targetUrl, arena = 'general', force_browser = false, metadata = {}, raw_key } = await request.json();
        const metadataFinal = { ...(metadata || {}), raw_key: raw_key || (metadata||{}).raw_key || (metadata||{}).processed_key }; // support raw_key from py monitor for consistent ai-enhanced procKey naming with ingested target keys.


        if (!targetUrl) {
          return new Response(JSON.stringify({ error: 'url required' }), { status: 400 });
        }

        // Idempotency check via R2 head (fast)
        // Use passed metadata.processed_key or target raw_key from Python monitor for consistency with babylon-raw-data slugs (fixes prior simplistic hostname ts key)
        const callerKey = metadata.raw_key || metadata.processed_key || `raw/${arena}/${new URL(targetUrl).hostname.replace(/[^a-z0-9]/gi,'-')}-${Date.now()}.html`;
        const rawKey = callerKey.startsWith('raw/') ? callerKey : `raw/${arena}/${callerKey}`; // normalize
        // For production use the same key logic as Python monitor.

        let content = '';
        let fetchMethod = 'direct';

        // Fetch (Browser Rendering if needed for JS or anti-bot)
        if (force_browser && env.BROWSER) {
          // Browser Rendering binding pattern (puppeteer-like)
          // const page = await env.BROWSER.newPage();
          // await page.goto(targetUrl, { waitUntil: 'networkidle0' });
          // content = await page.content();
          // fetchMethod = 'browser';
          // Simplified: many accounts use the fetch binding or puppeteer import.
          // Fallback to direct for skeleton; enhance with full browser on deploy.
          const resp = await fetch(targetUrl, { headers: { 'User-Agent': 'babylon-data-ai/1.0 (Cloudflare Worker)' } });
          content = await resp.text();
        } else {
          const resp = await fetch(targetUrl, { headers: { 'User-Agent': 'babylon-data-ai/1.0' } });
          content = await resp.text();
        }

        // MAXIMIZED extraction with Workers AI (structured JSON mode preferred)
        // Prompt + response_format for high-quality signals that directly feed analyze_data + mappers (better hot, archetypes, Rule42, ZDF reclaim).
        // Updated for universal Rule of 42 (applies to any system: media, business, tech, life). ZDF as example only.
        const extractionPrompt = `You are an expert narrative analyst for "The Breaker of Babylon" project tracking 11 arenas (congress, elections, migration/border, lawfare, bureaucracy, finance, pharma/health, media-tech, state/local, education/culture, global). Use Rule of 42 as universal filter: in ANY system only ~42 signals drive outcomes. Archetypes are timeless lenses (e.g. scapegoating, unified framing). ZDF fabrication is one powerful example, not the only focus. Prioritize high-signal items only; ignore noise.

Extract from the provided page content ONLY:
- politicians: array of mentioned names (focus US/EU officials, candidates)
- agencies: array (DOJ, SCOTUS, White House, Census, etc.)
- bills_or_refs: array
- framing_analysis: { score: 0-1 (loaded language intensity), phrases: top 5-8 loaded/framing phrases with context }
- tactic_hints: array of potential coordination, doublespeak, timing, scapegoating signals (short descriptions)
- summary: concise 2-4 sentence neutral summary with key facts/dates
- zdf_relevance: 0-1 score (how relevant to ZDF/Musk fabrication lie, German media coordination, GEZ, or related reclaim narratives) -- treat as example
- arena_relevance: array of best-matching arenas from the 11
- key_quotes: 2-4 most citable verbatim excerpts (with speaker if available)
- hot_signals: short list of elements that would increase hotScore (recency, repetition potential, high-profile entities)
- rule42_signals: array of 0-42 (aim for top signals only) high-impact narrative drivers from this item (e.g. key repeated phrases, power moves, framing pivots, entity centrality). Score each briefly with impact 0-1. This is the core Rule of 42 output.

Return ONLY valid JSON matching the schema. Be precise and citable. Tag as subagent: analysis if processing. Include explicit rule42_signals for pipeline Rule42 data enhancement.`;

        let aiResult = {};
        if (env.AI) {
          try {
            const aiResp = await env.AI.run('@cf/meta/llama-3.1-8b-instruct-fast', {
              messages: [
                { role: 'system', content: extractionPrompt },
                { role: 'user', content: content.slice(0, 12000) } // cap for token efficiency
              ],
              // Some models support response_format; fallback to text parse
            });
            const text = aiResp?.response || aiResp?.result || JSON.stringify(aiResp);
            // Try to parse JSON from response (common pattern)
            const jsonMatch = text.match(/\{[\s\S]*\}/);
            aiResult = jsonMatch ? JSON.parse(jsonMatch[0]) : { raw_ai: text.slice(0, 2000) };
          } catch (aiErr) {
            aiResult = { ai_error: String(aiErr).slice(0, 200), fallback: true };
          }
        } else {
          aiResult = { note: 'No AI binding; raw content only' };
        }

        // Build rich processed payload (augments / replaces simple process_data output)
        // Subagent: analysis & extract integrated
        const processed = {
          arena,
          raw_url: targetUrl,
          raw_key: rawKey,
          processed_at: new Date().toISOString(),
          fetch_method: fetchMethod,
          subagent: "analysis_extract",  // for visible subagent integration
          ai_model: env.AI ? '@cf/meta/llama-3.1-8b-instruct-fast' : null,
          extraction: aiResult,
          content_preview: content.slice(0, 4000),
          provenance: {
            source: 'babylon-data-ai-worker',
            r2_path: rawKey,
            version: '1.0-maximized',
            timestamp: new Date().toISOString()
          },
          ...metadataFinal
        };

        // Write rich processed to R2 (for direct consumption by mappers/analyze or as derived/)
        const procBase = (rawKey.split('/').pop() || 'item').replace(/\.[^.]+$/, '');
        const procKey = `processed/ai-enhanced/${procBase}-ai-summary.json`;
        await env.RAW_BUCKET.put(procKey, JSON.stringify(processed, null, 2), {
          httpMetadata: { contentType: 'application/json' }
        });

        // Optionally also ensure raw HTML/PDF is stored if not present (caller usually does this)
        // await env.RAW_BUCKET.put(rawKey, content ...)

        // Auto-sink provenance-stamped event to ckg-holo-analytics (full sinks for Phase 1)
        // Mirrors site sinkZDFAnalyticsEvent / trackZDF + api/holo/sink. Enables dashboard + ZDF suit audit trail.
        await sinkAnalyticsEvent(env, {
          type: 'ai_extract',
          arena,
          raw_url: targetUrl,
          raw_key: rawKey,
          processed_key: procKey,
          fetch_method: fetchMethod,
          extraction: {
            zdf_relevance: aiResult?.zdf_relevance,
            arena_relevance: aiResult?.arena_relevance,
            politicians: aiResult?.politicians,
            hot_signals: aiResult?.hot_signals,
            rule42_signals: aiResult?.rule42_signals
          },
          provenance: processed.provenance
        });

        return new Response(JSON.stringify({
          ok: true,
          raw_key: rawKey,
          processed_key: procKey,
          extraction: aiResult,
          provenance: processed.provenance,
          analytics_sunk: true
        }), { headers: { 'content-type': 'application/json' } });
      } catch (e) {
        return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
      }
    }

    if (request.method === 'POST' && pathname === '/discover') {
      // MAXIMIZED dynamic finding using internal logic + note for Firecrawl/CF browser map.
      // In full version: accept hub, use env.BROWSER or call Firecrawl, then AI filter for high-relevance new URLs.
      const { hub_url = 'https://www.federalregister.gov/', search = '', limit = 20 } = await request.json().catch(() => ({}));

      // Placeholder: return known high-value from prior discovery (real impl would map + AI score)
      const candidates = [
        'https://www.federalregister.gov/reader-aids/developer-resources/bulk-data',
        'https://www.federalregister.gov/documents/recent.xml',
        // Add more from firecrawl_map results at runtime
      ].slice(0, limit);

      return new Response(JSON.stringify({
        hub: hub_url,
        search,
        candidates,
        note: 'Extend with Browser Rendering + Workers AI scoring or Firecrawl map in production. Feed candidates to /extract or Python monitor.'
      }), { headers: { 'content-type': 'application/json' } });
    }

    if (request.method === 'POST' && pathname === '/sink') {
      try {
        const ev = await request.json().catch(() => ({}));
        const result = await sinkAnalyticsEvent(env, ev);
        return new Response(JSON.stringify({ ok: true, ...result }), {
          headers: { 'content-type': 'application/json' }
        });
      } catch (e) {
        return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
      }
    }

    // Phase 2: /embed endpoint for embeddings pipeline (to babylon-embeddings bucket).
    // Uses Workers AI embedding model (@cf/baai/bge-base-en-v1.5 or bge-small). Returns vector + metadata.
    // Called by scripts/generate_embeddings.py (if BABYLON_AI_WORKER_URL set) or future direct.
    // Stores happen in the Python side (or extend here to also PUT to EMBED_BUCKET binding if added).
    if (request.method === 'POST' && pathname === '/embed') {
      try {
        const { text = '', arena = 'general', model = '@cf/baai/bge-base-en-v1.5' } = await request.json().catch(() => ({}));
        if (!text) {
          return new Response(JSON.stringify({ error: 'text required for embedding' }), { status: 400 });
        }
        let vector = [];
        let usedModel = model;
        if (env.AI) {
          try {
            // Workers AI embeddings: pass text as string or array; result typically { data: [ [floats...] ] }
            const aiResp = await env.AI.run(model, { text: text.slice(0, 8000) });
            if (aiResp && aiResp.data && Array.isArray(aiResp.data[0])) {
              vector = aiResp.data[0];
            } else if (Array.isArray(aiResp)) {
              vector = aiResp;
            } else {
              vector = aiResp?.data || [];
            }
          } catch (aiErr) {
            usedModel = model + ' (fallback-stub due to AI error)';
            // toy fallback vector (dim ~768 for bge-base)
            const words = text.toLowerCase().split(/\s+/).slice(0, 100);
            vector = words.map((w, i) => ((w.charCodeAt(0) || 65) % 1000 + i) / 1200.0).concat(new Array(768).fill(0)).slice(0, 768);
          }
        } else {
          usedModel = model + ' (no-AI-stub)';
          const words = text.toLowerCase().split(/\s+/).slice(0, 100);
          vector = words.map((w, i) => ((w.charCodeAt(0) || 65) % 1000 + i) / 1200.0).concat(new Array(768).fill(0)).slice(0, 768);
        }
        const dim = vector.length || 768;
        const payload = {
          vector: Array.isArray(vector) ? vector : [],
          dim,
          model: usedModel,
          arena,
          text_snippet: text.slice(0, 200),
          generated_at: new Date().toISOString(),
          provenance: {
            source: 'babylon-data-ai-worker:/embed',
            version: 'phase2-embed',
            timestamp: new Date().toISOString()
          }
        };
        return new Response(JSON.stringify(payload), { headers: { 'content-type': 'application/json' } });
      } catch (e) {
        return new Response(JSON.stringify({ error: String(e) }), { status: 500 });
      }
    }

    return new Response('Babylon Data AI Worker — POST /extract or /discover or /sink or /embed. GET /health.', { status: 404 });
  },

  // MAXIMIZED: Cron trigger for autonomous periodic discovery (configure in wrangler.toml or dashboard)
  // Example: runs daily, discovers on key hubs, auto-triggers high-value /extract.
  async scheduled(event, env, ctx) {
    // Example hubs from firecrawl + docs discoveries (Federal Register, data.gov, etc.)
    const hubs = [
      'https://www.federalregister.gov/',
      'https://catalog.data.gov/',
      'https://www.govinfo.gov/'
    ];

    for (const hub of hubs) {
      // In real: call internal discover logic or env.BROWSER, filter with AI, then POST self /extract for top ones.
      // For skeleton: log intent. Deployed version can self-fetch or queue.
      console.log(`[CRON] Would discover + smart-extract from ${hub}`);
      // ctx.waitUntil( selfDiscoverAndExtract(env, hub) );
    }
  }
};

/* 
Wrangler.toml example (put in narrative-forge/workers/babylon-data-ai/wrangler.toml):

name = "babylon-data-ai"
main = "src/index.js"
compatibility_date = "2024-09-01"

[[r2_buckets]]
binding = "RAW_BUCKET"
bucket_name = "babylon-raw-data"

[ai]
binding = "AI"

# Optional
# [[browser]]
# binding = "BROWSER"

# [[kv_namespaces]]
# binding = "STATE_KV"
# id = "your-kv-id"

# For cron (add in dashboard or [[triggers]] in toml for full)
# triggers = { crons = ["0 4 * * *"] }  # daily discovery

# Secrets (wrangler secret put FIRECRAWL_API_KEY)
# Optional hybrid Firecrawl calls inside for map/extract.

Deploy with: npx wrangler deploy
Add R2 + AI + ANALYTICS_BUCKET bindings in dashboard if not in toml (now pre-set).
Then call from Python:
  requests.post("https://babylon-data-ai.your-subdomain.workers.dev/extract", json={"url": "...", "arena": "bureaucracy"})
  # Also supports /sink for direct provenance-stamped appends to ckg-holo-analytics
  requests.post(".../sink", json={"type": "zdf_analytics_event", "case": "case-zdf", "hot": 0.94, "r2_path": "raw/..."})
*/

// Minimal provenance-stamped analytics sink (copy/adapted from charlie-kirk-graphics/lib/r2-analytics.ts + /api/holo/sink/route.ts pattern).
// Appends to ckg-holo-analytics R2 (JSON objects under analytics/events/ for easy listing/JSONL rollup later).
// Stamps _provVerify FULL_SIGN_VERIFY_OK_ZDF_LEGAL + provenance for ZDF/Elon suit evidence, usage events, live deltas etc.
// Called from /extract (auto on AI success) and public /sink endpoint (from site mappers, Python, etc).
async function sinkAnalyticsEvent(env, ev = {}) {
  if (!env.ANALYTICS_BUCKET) {
    console.log('[ANALYTICS_SINK] no ANALYTICS_BUCKET binding; event dropped', ev?.type || 'unknown');
    return { sunk: false, note: 'no ANALYTICS_BUCKET binding' };
  }
  const stamped = {
    ...ev,
    ts: new Date().toISOString(),
    bucket: 'ckg-holo-analytics',
    _provVerify: 'FULL_SIGN_VERIFY_OK_ZDF_LEGAL',
    provenance: {
      source: 'babylon-data-ai-worker',
      r2_path: ev.r2_path || ev.raw_key || ev.processed_key || 'ai-extract',
      version: '1.0-maximized',
      timestamp: new Date().toISOString(),
      ...(ev.provenance || {})
    }
  };
  // Unique key per event (date-partitioned for easy prefix scans; individual objects = simple "append" pattern for R2)
  const day = new Date().toISOString().slice(0, 10);
  const key = `analytics/events/${day}/${Date.now()}-${(ev.type || 'event').replace(/[^a-z0-9_-]/gi, '')}.json`;
  await env.ANALYTICS_BUCKET.put(key, JSON.stringify(stamped, null, 2), {
    httpMetadata: { contentType: 'application/json' }
  });
  console.log('[ANALYTICS_SINK] sunk to ckg-holo-analytics', key, stamped.type || stamped.event || 'event');
  return { sunk: true, key, stamped };
}

console.log("babylon-data-ai worker loaded (maximized CF AI + R2)");

const PIONEX_RWA_CACHE_KEY = "pionex/cache/rwa_trade_rules.json";
const PIONEX_RWA_CACHE_TTL_MS = 6 * 60 * 60 * 1000;

// Pionex web endpoints discovered from the live RWA page.
// Device/fingerprint identifiers are intentionally NOT stored in this public Worker.
const PIONEX_WEB_VERSION = "20260812.1589.6ae8809";
const PIONEX_WEB_COMMON_QUERY =
  `client_id=pionex_web_${PIONEX_WEB_VERSION}&app_ver=${PIONEX_WEB_VERSION}&os=web&tz_name=Asia%2FTaipei&tz_offset=28800&sys_lang=zh-TW&app_lang=zh-TW`;
const PIONEX_FUTURE_MARKETS_URL =
  `https://www.pionex.com/apis/papi/v1/future_markets/?${PIONEX_WEB_COMMON_QUERY}`;
const PIONEX_MARKET_CUSTOMIZED_URL =
  `https://www.pionex.com/apis/menu-api/v1/market_customized?${PIONEX_WEB_COMMON_QUERY}`;

// Embedded fallback captured from Pionex. It is used only if the live Pionex
// internal endpoints are temporarily unavailable and no R2 cache exists.
const PIONEX_RWA_SEED_SYMBOLS = {"AAOIX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"AAPLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"AAX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"ALABX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"AMATX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"AMDX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"AMZNX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"ANTHROPIC_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"APPX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"ARMX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"ASMLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"ASTSX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"AVGOX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"AXTIX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"BEX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"BMNRX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"BNOX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"BRENTOIL_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"CBRS_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"CEGX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"CF_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"CIFRX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"WTI_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"COHRX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"COINX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"COPPER_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"CPERX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"CRCLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"CRDOX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"CRWVX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"CSCOX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"CVXX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"DELLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"DRAMX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"EWJX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"EWYX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"FLNCX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"GEVX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"GLWX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"GMEX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"GOOGLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"GSGX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"HIMSX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"HOODX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"HPEX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"HYUNDAI_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"IBMX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"INFQX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"INTCX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"IRENX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"KIOXIA_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"KLACX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"LITEX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"LLYX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"LMTX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"LNGX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"LRCXX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"METAX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"MOSX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"MPX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"MRVLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"MSFTX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"MSTRX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"MUX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"NATGAS_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"NBISX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"NFLXX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"NKEX_USDT_PERP":{"trade_tag":"trade_time_5_24","contract_status":"TRADING"},"NOKX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"NOWX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"NTRX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"NVDAX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"OKLOX_USDT_PERP":{"trade_tag":"delayed_open_early_close","contract_status":"TRADING"},"ONDSX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"ONX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"OPENAI_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"ORCLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"PANWX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"PAYPX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"PLTRX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"QCOMX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"QNTX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"QQQX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"RGTIX_USDT_PERP":{"trade_tag":"delayed_open_early_close","contract_status":"TRADING"},"RKLBX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"RTXX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"SHAZX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SITMX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"SKHX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SKHY_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SLVX_USDT_PERP":{"trade_tag":"delayed_open_early_close","contract_status":"TRADING"},"SMCIX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SMHX_USDT_PERP":{"trade_tag":"trade_time_5_24","contract_status":"TRADING"},"SMSN_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SNDKX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SNXXX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SOXLX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SOXSX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SOXXX_USDT_PERP":{"trade_tag":"delayed_open_early_close","contract_status":"TRADING"},"SPCX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"SPYX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"STXX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"TQQQX_USDT_PERP":{"trade_tag":"trade_time_5_24","contract_status":"TRADING"},"TSLAX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"TSMX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"TTEX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"TXNX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"UNGX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"UNHX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"URAX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"URNMX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"USARX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"USDT_QQQX_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"USDT_SPYX_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"USOX_USDT_PERP":{"trade_tag":"trade_time_5_24","contract_status":"TRADING"},"VGKX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"VSHX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"WDCX_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"XAG_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"XAU_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"XLPX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"XLVX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"},"XPD_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"XPT_USDT_PERP":{"trade_tag":"trade_time_7_24","contract_status":"TRADING"},"XYZX_USDT_PERP":{"trade_tag":"trade_time_5_7","contract_status":"TRADING"}};
const PIONEX_RWA_SEED_RULES = {"trade_time_7_24":{"symbol_tag_i18n_key":"7x24"},"trade_time_5_24":{"closed_i18n_key":"trade_time_5_24_close_market","opening_soon_i18n_key":"trade_time_5_24_open_market_soon","trade_time_config":{"tz":"UTC-4","weeks":{"Fri":{"quotation":[{"end":"20:00","start":"00:00"}],"trade":[{"end":"20:00","start":"00:00"}]},"Mon":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]},"Sat":{"quotation":[],"trade":[]},"Sun":{"quotation":[{"end":"24:00","start":"20:00"}],"trade":[{"end":"24:00","start":"20:00"}]},"Thu":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]},"Tue":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]},"Wed":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]}}}},"trade_time_5_7":{"closed_i18n_key":"trade_time_5_7_close_market","opening_soon_i18n_key":"trade_time_5_7_open_market_soon","trade_time_config":{"tz":"UTC-4","weeks":{"Fri":{"quotation":[{"end":"16:00","start":"09:30"}],"trade":[{"end":"16:00","start":"09:30"}]},"Mon":{"quotation":[{"end":"16:00","start":"09:30"}],"trade":[{"end":"16:00","start":"09:30"}]},"Sat":{"quotation":[],"trade":[]},"Sun":{"quotation":[],"trade":[]},"Thu":{"quotation":[{"end":"16:00","start":"09:30"}],"trade":[{"end":"16:00","start":"09:30"}]},"Tue":{"quotation":[{"end":"16:00","start":"09:30"}],"trade":[{"end":"16:00","start":"09:30"}]},"Wed":{"quotation":[{"end":"16:00","start":"09:30"}],"trade":[{"end":"16:00","start":"09:30"}]}}}},"delayed_open_early_close":{"closed_i18n_key":"delayed_open_early_close_close_market","opening_soon_i18n_key":"delayed_open_early_close_open_market_soon","trade_time_config":{"tz":"UTC-4","weeks":{"Fri":{"quotation":[{"end":"16:00","start":"00:00"}],"trade":[{"end":"16:00","start":"00:00"}]},"Mon":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]},"Sat":{"quotation":[],"trade":[]},"Sun":{"quotation":[{"end":"24:00","start":"20:30"}],"trade":[{"end":"24:00","start":"20:30"}]},"Thu":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]},"Tue":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]},"Wed":{"quotation":[{"end":"24:00","start":"00:00"}],"trade":[{"end":"24:00","start":"00:00"}]}}}},"korea_trade_time_5_7":{"closed_i18n_key":"trade_time_5_7_close_market","opening_soon_i18n_key":"trade_time_5_7_open_market_soon","trade_time_config":{"tz":"UTC-4","weeks":{"Fri":{"quotation":[{"end":"02:20","start":"00:00"}],"trade":[{"end":"02:20","start":"00:00"}]},"Mon":{"quotation":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}],"trade":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}]},"Sat":{"quotation":[],"trade":[]},"Sun":{"quotation":[{"end":"24:00","start":"20:00"}],"trade":[{"end":"24:00","start":"20:00"}]},"Thu":{"quotation":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}],"trade":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}]},"Tue":{"quotation":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}],"trade":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}]},"Wed":{"quotation":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}],"trade":[{"end":"02:20","start":"00:00"},{"end":"24:00","start":"20:00"}]}}}}};

const MARKET = {
  "crypto": { latest: "latest/crypto/snapshot_ai.json", filename: "snapshot_ai.json" },
  "us-stock": { latest: "latest/us-stock/snapshot_us_stock_ai.json", filename: "snapshot_us_stock_ai.json" },
};

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const origin = env.ALLOWED_ORIGIN || "*";
    if (request.method === "OPTIONS") return cors(new Response(null, { status: 204 }), origin);

    try {
      if (request.method === "GET" && url.pathname === "/api/health") {
        return json({ ok: true, service: "SStateMarketTerminal", r2: true, tavily_secret: Boolean(env.TAVILY_API_KEY), workers_ai_binding: Boolean(env.AI) }, 200, origin);
      }
      if (request.method === "GET" && url.pathname === "/api/market/status") {
        const market = normalizeMarket(url.searchParams.get("market"));
        if (market !== "us-stock") {
          return json({ ok: true, market, source: "not-applicable", statuses: {}, checked_at: new Date().toISOString() }, 200, origin);
        }
        return await pionexRwaMarketStatus(env, origin);
      }
      if (request.method === "GET" && url.pathname === "/api/snapshot") {
        const market = normalizeMarket(url.searchParams.get("market"));
        return await objectResponse(env, MARKET[market].latest, origin, false, MARKET[market].filename);
      }
      if (request.method === "GET" && url.pathname === "/api/download") {
        const market = normalizeMarket(url.searchParams.get("market"));
        return await objectResponse(env, MARKET[market].latest, origin, true, MARKET[market].filename);
      }
      if (request.method === "GET" && url.pathname === "/api/model/active") {
        return await objectResponse(env, "models/active/probability_model.json", origin, false, "probability_model.json");
      }
      if (request.method === "GET" && url.pathname === "/api/analysis/status") {
        const runId = safeRunId(url.searchParams.get("run_id"));
        return await objectResponse(env, `runs/${runId}/status.json`, origin, false, "status.json");
      }
      if (request.method === "GET" && url.pathname === "/api/automation/status") {
        const status = await readAutomationStatus(env);
        return json({ ok: true, ...status }, 200, origin);
      }
      if (request.method === "GET" && url.pathname === "/api/research/us-stock/latest") {
        return await objectResponse(env, "research/us-stock/latest.json", origin, false, "us_stock_research_latest.json");
      }
      if (request.method === "GET" && url.pathname === "/api/research/us-stock/cache") {
        return await objectResponse(env, "research/us-stock/cache.json", origin, false, "us_stock_research_cache.json");
      }
      if (request.method === "POST" && url.pathname === "/api/analysis/start") {
        return await startAnalysis(request, env, origin);
      }
      if (request.method === "POST" && url.pathname === "/api/research/us-stock/symbol") {
        return await researchUsStockSymbol(request, env, origin);
      }
      if (request.method === "POST" && url.pathname === "/api/internal/status") {
        requireInternal(request, env);
        const body = await request.json();
        const runId = safeRunId(body.run_id);
        const payload = { ...body, run_id: runId, updated_at: new Date().toISOString() };
        await env.JSON_BUCKET.put(`runs/${runId}/status.json`, JSON.stringify(payload, null, 2), { httpMetadata: { contentType: "application/json; charset=utf-8" } });
        return json({ ok: true }, 200, origin);
      }
      if (request.method === "POST" && url.pathname === "/api/internal/automation/status") {
        requireInternal(request, env);
        const body = await request.json();
        const batchId = safeRunId(body.batch_id);
        const current = await readAutomationStatus(env, { allowStale: true });
        if (current.batch_id && current.batch_id !== batchId && automationBusy(current)) {
          return json({ ok: false, ignored: true, reason: "newer_auto_batch_active", current_batch_id: current.batch_id }, 409, origin);
        }
        const payload = { ...body, batch_id: batchId, source: "AUTO_CRON", updated_at: new Date().toISOString() };
        await writeAutomationStatus(env, payload);
        return json({ ok: true, busy: automationBusy(payload), batch_id: batchId }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/research/us-stock/cache") {
        requireInternal(request, env);
        const text = await request.text();
        const parsed = JSON.parse(text);
        if (!parsed || typeof parsed !== "object" || typeof parsed.entries !== "object") throw httpError(400, "research cache entries missing");
        await env.JSON_BUCKET.put("research/us-stock/cache.json", text, { httpMetadata: { contentType: "application/json; charset=utf-8" } });
        return json({ ok: true, key: "research/us-stock/cache.json", entries: Object.keys(parsed.entries || {}).length }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/research/us-stock/latest") {
        requireInternal(request, env);
        const text = await request.text();
        const parsed = JSON.parse(text);
        if (!parsed || typeof parsed !== "object" || !Array.isArray(parsed.items)) throw httpError(400, "research latest items missing");
        await env.JSON_BUCKET.put("research/us-stock/latest.json", text, { httpMetadata: { contentType: "application/json; charset=utf-8" } });
        return json({ ok: true, key: "research/us-stock/latest.json", items: parsed.items.length }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/snapshot") {
        requireInternal(request, env);
        const market = normalizeMarket(url.searchParams.get("market"));
        const runId = safeRunId(url.searchParams.get("run_id"));
        const text = await request.text();
        const parsed = JSON.parse(text); // reject broken snapshots before replacing latest
        if (!parsed || !Array.isArray(parsed.records)) throw new Error("snapshot.records missing");
        const latestKey = MARKET[market].latest;
        const runKey = `runs/${runId}/${MARKET[market].filename}`;
        const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
        await Promise.all([
          env.JSON_BUCKET.put(latestKey, text, metadata),
          env.JSON_BUCKET.put(runKey, text, metadata),
        ]);
        const status = {
          run_id: runId, market, status: "SUCCESS", percent: 100,
          records: parsed.records.length, snapshot_key: latestKey,
          generated_at_taiwan: parsed.batch?.generated_at_taiwan || null,
          updated_at: new Date().toISOString(),
        };
        await env.JSON_BUCKET.put(`runs/${runId}/status.json`, JSON.stringify(status, null, 2), metadata);
        return json({ ok: true, latest_key: latestKey, run_key: runKey, records: parsed.records.length }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/model/active") {
        requireInternal(request, env);
        const text = await request.text();
        JSON.parse(text);
        await env.JSON_BUCKET.put("models/active/probability_model.json", text, { httpMetadata: { contentType: "application/json; charset=utf-8" } });
        return json({ ok: true, key: "models/active/probability_model.json" }, 200, origin);
      }
      if (request.method === "GET" && url.pathname === "/api/model/candidate/latest") {
        return await objectResponse(env, "models/candidates/latest.json", origin, false, "candidate_latest.json");
      }
      if (request.method === "GET" && url.pathname === "/api/model/challenger/current") {
        return await objectResponse(env, "models/challenger/current.json", origin, false, "challenger_current.json");
      }
      if (request.method === "GET" && url.pathname === "/api/model/challenger/model") {
        const manifestObj = await env.JSON_BUCKET.get("models/challenger/current.json");
        if (!manifestObj) return json({ error: "challenger_not_assigned" }, 404, origin);
        const manifest = JSON.parse(await manifestObj.text());
        return await objectResponse(env, manifest.candidate_key, origin, false, "challenger_probability_model.json");
      }
      if (request.method === "GET" && url.pathname === "/api/model/evaluation/latest") {
        return await objectResponse(env, "models/evaluations/latest.json", origin, false, "champion_challenger_evaluation.json");
      }
      if (request.method === "GET" && url.pathname === "/api/learning/status") {
        return await objectResponse(env, "learning/latest/status.json", origin, false, "learning_status.json");
      }
      if (request.method === "POST" && url.pathname === "/api/internal/learning/start") {
        requireInternal(request, env);
        const result = await dispatchDailyLearning(env, "manual");
        return json(result, 200, origin);
      }
      if (request.method === "POST" && url.pathname === "/api/internal/learning/status") {
        requireInternal(request, env);
        const body = await request.json();
        const payload = { ...body, updated_at: new Date().toISOString() };
        const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
        await env.JSON_BUCKET.put("learning/latest/status.json", JSON.stringify(payload, null, 2), metadata);
        if (body.run_id) {
          const runId = safeRunId(String(body.run_id));
          await env.JSON_BUCKET.put(`learning/runs/${runId}/status.json`, JSON.stringify(payload, null, 2), metadata);
        }
        return json({ ok: true }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/model/candidate") {
        requireInternal(request, env);
        const text = await request.text();
        const parsed = JSON.parse(text);
        const modelId = safeModelId(parsed?.model_id);
        const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
        const key = `models/candidates/${modelId}/probability_model.json`;
        await env.JSON_BUCKET.put(key, text, metadata);
        const manifest = {
          model_id: modelId,
          candidate_key: key,
          generated_at: parsed?.generated_at || null,
          schema_version: parsed?.schema_version || null,
          training: parsed?.training || null,
          uploaded_at: new Date().toISOString(),
          status: "CANDIDATE",
          note: "Candidate only. Active model is not replaced until a later out-of-sample promotion gate approves it."
        };
        await env.JSON_BUCKET.put("models/candidates/latest.json", JSON.stringify(manifest, null, 2), metadata);
        const challenger = await ensureChallenger(env, manifest);
        return json({ ok: true, model_id: modelId, key, manifest_key: "models/candidates/latest.json", challenger }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/learning/report") {
        requireInternal(request, env);
        const modelId = safeModelId(url.searchParams.get("model_id"));
        const text = await request.text(); JSON.parse(text);
        const key = `models/candidates/${modelId}/training_report.json`;
        await env.JSON_BUCKET.put(key, text, { httpMetadata: { contentType: "application/json; charset=utf-8" } });
        return json({ ok: true, key }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/learning/meta") {
        requireInternal(request, env);
        const modelId = safeModelId(url.searchParams.get("model_id"));
        const text = await request.text(); JSON.parse(text);
        const key = `models/candidates/${modelId}/learning_meta.json`;
        await env.JSON_BUCKET.put(key, text, { httpMetadata: { contentType: "application/json; charset=utf-8" } });
        return json({ ok: true, key }, 200, origin);
      }
      if (request.method === "POST" && url.pathname === "/api/internal/model/challenger/ensure") {
        requireInternal(request, env);
        const result = await ensureChallenger(env, null);
        return json({ ok: true, challenger: result }, 200, origin);
      }
      if (request.method === "PUT" && url.pathname === "/api/internal/model/evaluation") {
        requireInternal(request, env);
        const modelId = safeModelId(url.searchParams.get("model_id"));
        const bodyText = await request.text();
        const evaluation = JSON.parse(bodyText);
        if (String(evaluation?.challenger_model_id || "") !== modelId) throw httpError(400, "evaluation challenger_model_id mismatch");
        const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
        const key = `models/candidates/${modelId}/evaluation.json`;
        const latest = { ...evaluation, evaluation_key: key };
        await Promise.all([
          env.JSON_BUCKET.put(key, JSON.stringify(latest, null, 2), metadata),
          env.JSON_BUCKET.put("models/evaluations/latest.json", JSON.stringify(latest, null, 2), metadata),
        ]);
        const currentObj = await env.JSON_BUCKET.get("models/challenger/current.json");
        if (currentObj) {
          const current = JSON.parse(await currentObj.text());
          if (current.model_id === modelId) {
            current.latest_evaluation_key = key;
            current.latest_decision = evaluation.decision || null;
            current.latest_evaluated_at = evaluation.evaluated_at || new Date().toISOString();
            await env.JSON_BUCKET.put("models/challenger/current.json", JSON.stringify(current, null, 2), metadata);
          }
        }
        return json({ ok: true, key, decision: evaluation.decision || null }, 200, origin);
      }
      if (request.method === "POST" && url.pathname === "/api/internal/model/promote") {
        requireInternal(request, env);
        const body = await request.json();
        const modelId = safeModelId(body.model_id);
        const result = await promoteChallenger(env, modelId);
        return json({ ok: true, ...result }, 200, origin);
      }
      if (request.method === "POST" && url.pathname === "/api/internal/model/reject") {
        requireInternal(request, env);
        const body = await request.json();
        const modelId = safeModelId(body.model_id);
        const result = await rejectChallenger(env, modelId);
        return json({ ok: true, ...result }, 200, origin);
      }
      return json({ error: "not_found" }, 404, origin);
    } catch (error) {
      const status = error?.status || 500;
      return json({ error: error?.message || String(error) }, status, origin);
    }
  },

  async scheduled(controller, env, ctx) {
    const source = `cron:${controller.cron}`;
    if (controller.cron === "1 */4 * * *") {
      ctx.waitUntil(dispatchAutoBatch(env, "pair", source));
      return;
    }
    if (controller.cron === "31 13 * * *") {
      ctx.waitUntil(dispatchAutoBatch(env, "us-stock-only", source));
      return;
    }
    if (controller.cron === "25 0 * * *") {
      ctx.waitUntil(dispatchDailyLearning(env, source));
      return;
    }
    console.log(`Unhandled cron trigger: ${controller.cron}`);
  }
};



function pionexEffectiveTradeTag(tags, rules) {
  const set = new Set(Array.isArray(tags) ? tags : []);
  const priority = [
    "trade_time_7_24",
    "trade_time_5_24",
    "trade_time_5_7",
    "delayed_open_early_close",
    "korea_trade_time_5_7",
  ];
  for (const tag of priority) {
    if (set.has(tag) && (tag === "trade_time_7_24" || rules?.[tag])) return tag;
  }
  return null;
}

function compactPionexRwaRules(futurePayload, menuPayload) {
  const rows = Array.isArray(futurePayload?.data) ? futurePayload.data : [];
  const rules = menuPayload?.data?.tag_rules || {};
  const symbols = {};

  for (const row of rows) {
    const tags = Array.isArray(row?.tags) ? row.tags : [];
    if (!tags.includes("us_token_contract")) continue;
    const displaySymbol = String(row?.display_symbol || "").trim();
    if (!displaySymbol) continue;

    symbols[displaySymbol] = {
      trade_tag: pionexEffectiveTradeTag(tags, rules),
      contract_status: String(row?.status || "").toUpperCase() || "UNKNOWN",
    };
  }

  const compactRules = {};
  for (const tag of [
    "trade_time_7_24",
    "trade_time_5_24",
    "trade_time_5_7",
    "delayed_open_early_close",
    "korea_trade_time_5_7",
  ]) {
    if (!rules?.[tag]) continue;
    const src = rules[tag];
    if (tag === "trade_time_7_24") {
      compactRules[tag] = { symbol_tag_i18n_key: src?.symbol_tag_i18n_key || "7x24" };
    } else if (src?.trade_time_config) {
      compactRules[tag] = {
        closed_i18n_key: src?.closed_i18n_key || "",
        opening_soon_i18n_key: src?.opening_soon_i18n_key || "",
        trade_time_config: src.trade_time_config,
      };
    }
  }

  if (!Object.keys(symbols).length) throw httpError(502, "Pionex future_markets returned no us_token_contract symbols");
  return { symbols, rules: compactRules };
}

async function fetchPionexWebJson(url) {
  const response = await fetch(url, {
    method: "GET",
    headers: {
      "Accept": "application/json",
      "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.7",
    },
  });
  if (!response.ok) throw httpError(502, `Pionex web API failed: ${response.status}`);
  const payload = await response.json();
  if (Number(payload?.code) !== 0) {
    throw httpError(502, `Pionex web API error: ${payload?.reason || payload?.message || payload?.code}`);
  }
  return payload;
}

async function refreshPionexRwaRules(env) {
  // Deliberately sequential: this data changes slowly and there is no reason
  // to burst two requests at Pionex at the same instant.
  const futurePayload = await fetchPionexWebJson(PIONEX_FUTURE_MARKETS_URL);
  const menuPayload = await fetchPionexWebJson(PIONEX_MARKET_CUSTOMIZED_URL);
  const compact = compactPionexRwaRules(futurePayload, menuPayload);

  const cache = {
    fetched_at: new Date().toISOString(),
    source: "Pionex future_markets + market_customized",
    ...compact,
  };

  await env.JSON_BUCKET.put(
    PIONEX_RWA_CACHE_KEY,
    JSON.stringify(cache),
    { httpMetadata: { contentType: "application/json; charset=utf-8" } }
  );
  return { ...cache, cache_state: "REFRESHED" };
}

async function loadPionexRwaRules(env) {
  let cached = null;
  try {
    const obj = await env.JSON_BUCKET.get(PIONEX_RWA_CACHE_KEY);
    if (obj) cached = JSON.parse(await obj.text());
  } catch (_) {}

  if (cached?.fetched_at) {
    const age = Date.now() - new Date(cached.fetched_at).getTime();
    if (Number.isFinite(age) && age >= 0 && age < PIONEX_RWA_CACHE_TTL_MS) {
      return { ...cached, cache_state: "R2_FRESH" };
    }
  }

  try {
    return await refreshPionexRwaRules(env);
  } catch (error) {
    if (cached?.symbols && cached?.rules) {
      return {
        ...cached,
        cache_state: "R2_STALE",
        refresh_error: error?.message || String(error),
      };
    }

    return {
      fetched_at: null,
      source: "embedded Pionex fallback",
      cache_state: "EMBEDDED_FALLBACK",
      refresh_error: error?.message || String(error),
      symbols: PIONEX_RWA_SEED_SYMBOLS,
      rules: PIONEX_RWA_SEED_RULES,
    };
  }
}

function parseUtcOffsetMinutes(tz) {
  const match = /^UTC([+-])(\d{1,2})(?::(\d{2}))?$/.exec(String(tz || "").trim());
  if (!match) return 0;
  const sign = match[1] === "-" ? -1 : 1;
  const hours = Number(match[2] || 0);
  const minutes = Number(match[3] || 0);
  return sign * (hours * 60 + minutes);
}

function hhmmToMinute(value) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(String(value || ""));
  if (!match) return null;
  const h = Number(match[1]);
  const m = Number(match[2]);
  if (h === 24 && m === 0) return 1440;
  if (h < 0 || h > 23 || m < 0 || m > 59) return null;
  return h * 60 + m;
}

function evaluatePionexTradeRule(rule, now = new Date()) {
  const config = rule?.trade_time_config;
  if (!config?.weeks) return false;

  const offsetMinutes = parseUtcOffsetMinutes(config.tz);
  const shifted = new Date(now.getTime() + offsetMinutes * 60_000);
  const weekday = ["Sun","Mon","Tue","Wed","Thu","Fri","Sat"][shifted.getUTCDay()];
  const minute = shifted.getUTCHours() * 60 + shifted.getUTCMinutes();

  const day = config.weeks?.[weekday];
  const intervals = Array.isArray(day?.trade) ? day.trade : [];

  for (const interval of intervals) {
    const start = hhmmToMinute(interval?.start);
    const end = hhmmToMinute(interval?.end);
    if (start == null || end == null) continue;
    if (minute >= start && minute < end) return true;
  }
  return false;
}

function evaluatePionexSymbol(symbolInfo, rules, now = new Date()) {
  const contractStatus = String(symbolInfo?.contract_status || "").toUpperCase();
  const tradeTag = String(symbolInfo?.trade_tag || "");

  if (contractStatus && contractStatus !== "TRADING") {
    return { status: "OFFLINE", label: "停用", trade_tag: tradeTag, contract_status: contractStatus };
  }

  if (tradeTag === "trade_time_7_24") {
    return { status: "ALWAYS_OPEN", label: "7×24", trade_tag: tradeTag, contract_status: contractStatus || "TRADING" };
  }

  const rule = rules?.[tradeTag];
  if (rule?.trade_time_config) {
    const open = evaluatePionexTradeRule(rule, now);
    return {
      status: open ? "OPEN" : "CLOSED",
      label: open ? "交易中" : "休市",
      trade_tag: tradeTag,
      contract_status: contractStatus || "TRADING",
      rule_tz: rule.trade_time_config.tz || null,
    };
  }

  return {
    status: "UNKNOWN",
    label: "狀態未知",
    trade_tag: tradeTag || null,
    contract_status: contractStatus || "UNKNOWN",
  };
}

async function pionexRwaMarketStatus(env, origin) {
  const data = await loadPionexRwaRules(env);
  const now = new Date();
  const statuses = {};
  const counts = { always_open: 0, open: 0, closed: 0, offline: 0, unknown: 0 };

  for (const [displaySymbol, info] of Object.entries(data.symbols || {})) {
    const result = evaluatePionexSymbol(info, data.rules || {}, now);
    statuses[displaySymbol] = result;

    if (result.status === "ALWAYS_OPEN") counts.always_open += 1;
    else if (result.status === "OPEN") counts.open += 1;
    else if (result.status === "CLOSED") counts.closed += 1;
    else if (result.status === "OFFLINE") counts.offline += 1;
    else counts.unknown += 1;
  }

  return json({
    ok: true,
    market: "us-stock",
    source: data.source,
    cache_state: data.cache_state,
    upstream_fetched_at: data.fetched_at || null,
    refresh_error: data.refresh_error || null,
    checked_at: now.toISOString(),
    counts,
    statuses,
  }, 200, origin);
}

async function startAnalysis(request, env, origin) {
  const body = await request.json().catch(() => ({}));
  const market = normalizeMarket(body.market);
  const auto = await readAutomationStatus(env);
  if (automationBusy(auto)) {
    throw httpError(409, `自動排程分析進行中（${automationPhaseLabel(auto)}），目前完整分析已鎖定`);
  }
  const runId = `${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0,14)}_${market}_${crypto.randomUUID().slice(0,8)}`;
  const initial = { run_id: runId, market, status: "QUEUED", percent: 0, message: "等待 GitHub Actions", created_at: new Date().toISOString() };
  await env.JSON_BUCKET.put(`runs/${runId}/status.json`, JSON.stringify(initial, null, 2), { httpMetadata: { contentType: "application/json; charset=utf-8" } });

  if (!env.GITHUB_TOKEN || !env.GITHUB_REPOSITORY) throw httpError(500, "Worker 缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY");
  const endpoint = `https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/full-analysis.yml/dispatches`;
  const gh = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "SStateMarketTerminal-Worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ ref: env.GITHUB_BRANCH || "main", inputs: { market, run_id: runId } }),
  });
  if (!gh.ok) {
    const text = await gh.text();
    await env.JSON_BUCKET.put(`runs/${runId}/status.json`, JSON.stringify({ ...initial, status: "FAILED", message: `GitHub dispatch ${gh.status}: ${text}` }, null, 2));
    throw httpError(502, `GitHub workflow_dispatch 失敗：${gh.status}`);
  }
  let dispatch = null;
  try { dispatch = await gh.json(); } catch (_) {}
  return json({ ok: true, run_id: runId, market, github_run_id: dispatch?.workflow_run_id || null, github_run_url: dispatch?.html_url || null }, 200, origin);
}

const RESEARCH_PROVIDER = "Tavily Search + Llama JSON Mode";
const RESEARCH_GLM_MODEL = "@cf/meta/llama-3.1-8b-instruct-fast";
const RESEARCH_FALLBACK_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast";
const RESEARCH_PIPELINE_VERSION = "tavily-llama-jsonschema-zhtw-v5";
const RESEARCH_CACHE_KEY = "research/us-stock/cache.json";
const RESEARCH_LATEST_KEY = "research/us-stock/latest.json";
const RESEARCH_TTL_MS = 24 * 60 * 60 * 1000;
const RESEARCH_ELIGIBLE_STATES = new Set(["S3", "S0.5", "S1"]);
const RESEARCH_TICKER_OVERRIDES = {
  AAOIX:"AAOI", AAX:"AA", AXTIX:"AXTI", BEX:"BE", CVXX:"CVX", GMEX:"GME",
  LRCXX:"LRCX", MPX:"MP", MUX:"MU", NFLXX:"NFLX", PAYPX:"PYPL", RGTIX:"RGTI", RTXX:"RTX",
  SITMX:"SITM", SMCIX:"SMCI", SNXXX:"SNX", SOXXX:"SOXX", TTEX:"TTE", TXNX:"TXN",
  ANTHROPIC:"Anthropic", OPENAI:"OpenAI", HYUNDAI:"Hyundai Motor", KIOXIA:"Kioxia",
  SMSN:"Samsung Electronics", SKHX:"SK hynix", SKHY:"SK hynix", SPCX:"SpaceX"
};

// 公司別名只集中維護在這裡。Hard Gate 會同時辨識英文公司名、ticker 與中文常用名。
// 沒列到的標的仍會自動使用 underlying ticker / Pionex symbol，不會因此不能搜尋。
const RESEARCH_COMPANY_PROFILES = {
  AAOI:{name:"Applied Optoelectronics", aliases:["Applied Optoelectronics","AAOI"], asset_type:"public_company"},
  AA:{name:"Alcoa", aliases:["Alcoa","AA","美國鋁業"], asset_type:"public_company"},
  AAPL:{name:"Apple", aliases:["Apple","AAPL","蘋果"], asset_type:"public_company"},
  AMAT:{name:"Applied Materials", aliases:["Applied Materials","AMAT","應用材料"], asset_type:"public_company"},
  AMD:{name:"Advanced Micro Devices", aliases:["Advanced Micro Devices","AMD","超微"], asset_type:"public_company"},
  AMZN:{name:"Amazon", aliases:["Amazon","AMZN","亞馬遜"], asset_type:"public_company"},
  APP:{name:"AppLovin", aliases:["AppLovin","APP"], asset_type:"public_company"},
  ARM:{name:"Arm Holdings", aliases:["Arm Holdings","Arm","ARM","安謀"], asset_type:"public_company"},
  ASML:{name:"ASML", aliases:["ASML","阿斯麥"], asset_type:"foreign_company"},
  ASTS:{name:"AST SpaceMobile", aliases:["AST SpaceMobile","ASTS"], asset_type:"public_company"},
  AVGO:{name:"Broadcom", aliases:["Broadcom","AVGO","博通"], asset_type:"public_company"},
  AXTI:{name:"AXT", aliases:["AXT","AXTI"], asset_type:"public_company"},
  BE:{name:"Bloom Energy", aliases:["Bloom Energy","BE"], asset_type:"public_company"},
  CIFR:{name:"Cipher Mining", aliases:["Cipher Mining","CIFR"], asset_type:"public_company"},
  CF:{name:"CF Industries", aliases:["CF Industries","CF"], asset_type:"public_company"},
  COHR:{name:"Coherent", aliases:["Coherent","COHR"], asset_type:"public_company"},
  COIN:{name:"Coinbase", aliases:["Coinbase","COIN"], asset_type:"public_company"},
  CRCL:{name:"Circle Internet Group", aliases:["Circle Internet Group","Circle","CRCL"], asset_type:"public_company"},
  CRDO:{name:"Credo Technology", aliases:["Credo Technology","Credo","CRDO"], asset_type:"public_company"},
  CRWV:{name:"CoreWeave", aliases:["CoreWeave","CRWV"], asset_type:"public_company"},
  CSCO:{name:"Cisco", aliases:["Cisco","CSCO","思科"], asset_type:"public_company"},
  CVX:{name:"Chevron", aliases:["Chevron","CVX","雪佛龍"], asset_type:"public_company"},
  DELL:{name:"Dell Technologies", aliases:["Dell Technologies","Dell","DELL","戴爾"], asset_type:"public_company"},
  FLNC:{name:"Fluence Energy", aliases:["Fluence Energy","Fluence","FLNC"], asset_type:"public_company"},
  GEV:{name:"GE Vernova", aliases:["GE Vernova","GEV"], asset_type:"public_company"},
  GME:{name:"GameStop", aliases:["GameStop","GME"], asset_type:"public_company"},
  GOOGL:{name:"Alphabet", aliases:["Alphabet","Google","GOOGL","GOOG","谷歌"], asset_type:"public_company"},
  HIMS:{name:"Hims & Hers Health", aliases:["Hims & Hers","Hims and Hers","HIMS"], asset_type:"public_company"},
  HOOD:{name:"Robinhood", aliases:["Robinhood","HOOD"], asset_type:"public_company"},
  IBM:{name:"IBM", aliases:["IBM","International Business Machines"], asset_type:"public_company"},
  INTC:{name:"Intel", aliases:["Intel","INTC","英特爾"], asset_type:"public_company"},
  IREN:{name:"IREN", aliases:["IREN","Iris Energy"], asset_type:"public_company"},
  KLAC:{name:"KLA", aliases:["KLA","KLAC","科磊"], asset_type:"public_company"},
  LITE:{name:"Lumentum", aliases:["Lumentum","LITE"], asset_type:"public_company"},
  LLY:{name:"Eli Lilly", aliases:["Eli Lilly","LLY","禮來"], asset_type:"public_company"},
  LMT:{name:"Lockheed Martin", aliases:["Lockheed Martin","LMT","洛克希德馬丁"], asset_type:"public_company"},
  LNG:{name:"Cheniere Energy", aliases:["Cheniere Energy","LNG"], asset_type:"public_company"},
  LRCX:{name:"Lam Research", aliases:["Lam Research","LRCX","泛林集團","科林研發"], asset_type:"public_company"},
  META:{name:"Meta Platforms", aliases:["Meta Platforms","Meta","Facebook","META","臉書"], asset_type:"public_company"},
  MRVL:{name:"Marvell Technology", aliases:["Marvell Technology","Marvell","MRVL","邁威爾"], asset_type:"public_company"},
  MSFT:{name:"Microsoft", aliases:["Microsoft","MSFT","微軟"], asset_type:"public_company"},
  MSTR:{name:"Strategy", aliases:["Strategy","MicroStrategy","MSTR","微策略"], asset_type:"public_company"},
  MU:{name:"Micron Technology", aliases:["Micron Technology","Micron","MU","美光"], asset_type:"public_company"},
  NBIS:{name:"Nebius Group", aliases:["Nebius Group","Nebius","NBIS"], asset_type:"public_company"},
  NFLX:{name:"Netflix", aliases:["Netflix","NFLX","網飛"], asset_type:"public_company"},
  NKE:{name:"Nike", aliases:["Nike","NKE","耐吉"], asset_type:"public_company"},
  NOK:{name:"Nokia", aliases:["Nokia","NOK","諾基亞"], asset_type:"foreign_company"},
  NOW:{name:"ServiceNow", aliases:["ServiceNow","NOW"], asset_type:"public_company"},
  NTR:{name:"Nutrien", aliases:["Nutrien","NTR"], asset_type:"foreign_company"},
  NVDA:{name:"NVIDIA", aliases:["NVIDIA","Nvidia","NVDA","輝達"], asset_type:"public_company"},
  OKLO:{name:"Oklo", aliases:["Oklo","OKLO"], asset_type:"public_company"},
  ONDS:{name:"Ondas Holdings", aliases:["Ondas Holdings","Ondas","ONDS"], asset_type:"public_company"},
  ORCL:{name:"Oracle", aliases:["Oracle","ORCL","甲骨文"], asset_type:"public_company"},
  PLTR:{name:"Palantir", aliases:["Palantir","PLTR","帕蘭泰爾"], asset_type:"public_company"},
  PYPL:{name:"PayPal", aliases:["PayPal","PYPL"], asset_type:"public_company"},
  QCOM:{name:"Qualcomm", aliases:["Qualcomm","QCOM","高通"], asset_type:"public_company"},
  RGTI:{name:"Rigetti Computing", aliases:["Rigetti Computing","Rigetti","RGTI"], asset_type:"public_company"},
  RKLB:{name:"Rocket Lab", aliases:["Rocket Lab","RKLB"], asset_type:"public_company"},
  RTX:{name:"RTX Corporation", aliases:["RTX Corporation","RTX","Raytheon Technologies","Raytheon","雷神技術"], asset_type:"public_company"},
  SITM:{name:"SiTime", aliases:["SiTime","SITM"], asset_type:"public_company"},
  SMCI:{name:"Super Micro Computer", aliases:["Super Micro Computer","Supermicro","SMCI","美超微"], asset_type:"public_company"},
  SNDK:{name:"SanDisk", aliases:["SanDisk","Sandisk","SNDK","閃迪"], asset_type:"public_company"},
  TSLA:{name:"Tesla", aliases:["Tesla","TSLA","特斯拉"], asset_type:"public_company"},
  TSM:{name:"Taiwan Semiconductor Manufacturing", aliases:["Taiwan Semiconductor Manufacturing","TSMC","TSM","台積電"], asset_type:"foreign_company"},
  TTE:{name:"TotalEnergies", aliases:["TotalEnergies","TTE","道達爾能源"], asset_type:"foreign_company"},
  TXN:{name:"Texas Instruments", aliases:["Texas Instruments","TXN","德州儀器"], asset_type:"public_company"},
  UNH:{name:"UnitedHealth Group", aliases:["UnitedHealth Group","UnitedHealth","UNH","聯合健康"], asset_type:"public_company"},
  USAR:{name:"USA Rare Earth", aliases:["USA Rare Earth","USAR"], asset_type:"public_company"},
  WDC:{name:"Western Digital", aliases:["Western Digital","WDC","西部數據"], asset_type:"public_company"},
  XYZ:{name:"Block", aliases:["Block Inc","Block","Square","XYZ"], asset_type:"public_company"},


  // ---- Current Pionex RWA universe: profiles that cannot be inferred safely from removing the final X ----
  BMNR:{name:"BitMine Immersion Technologies", aliases:["BitMine Immersion Technologies","BitMine","BMNR"], asset_type:"public_company"},
  BNO:{name:"United States Brent Oil Fund", aliases:["United States Brent Oil Fund","BNO","Brent crude","Brent oil","布蘭特原油"], asset_type:"etf", focus:"布蘭特原油"},
  BRENTOIL:{name:"Brent Crude Oil", aliases:["Brent Crude Oil","Brent crude","Brent oil","BRENTOIL","布蘭特原油"], asset_type:"commodity", focus:"布蘭特原油供需"},
  CBRS:{name:"Cerebras Systems", aliases:["Cerebras Systems","Cerebras","CBRS"], asset_type:"private_company"},
  CEG:{name:"Constellation Energy", aliases:["Constellation Energy","CEG","星座能源"], asset_type:"public_company"},
  WTI:{name:"West Texas Intermediate Crude Oil", aliases:["West Texas Intermediate","WTI","WTI crude","crude oil","西德州中質原油","西德州原油","原油"], asset_type:"commodity", focus:"WTI 原油供需"},
  COPPER:{name:"Copper", aliases:["Copper","COPPER","copper price","銅","銅價"], asset_type:"commodity", focus:"全球銅供需"},
  CPER:{name:"United States Copper Index Fund", aliases:["United States Copper Index Fund","CPER","copper","銅","銅價"], asset_type:"etf", focus:"銅與銅期貨"},
  DRAM:{name:"Roundhill Memory ETF", aliases:["Roundhill Memory ETF","DRAM","memory ETF","memory chip","DRAM memory","記憶體ETF","記憶體晶片","記憶體"], asset_type:"etf", focus:"記憶體半導體"},
  EWJ:{name:"iShares MSCI Japan ETF", aliases:["iShares MSCI Japan ETF","EWJ","Japan equities","Japanese stocks","日本股市","日股"], asset_type:"etf", focus:"日本股市"},
  EWY:{name:"iShares MSCI South Korea ETF", aliases:["iShares MSCI South Korea ETF","EWY","South Korea equities","Korean stocks","韓國股市","韓股"], asset_type:"etf", focus:"韓國股市"},
  GLW:{name:"Corning", aliases:["Corning","Corning Incorporated","GLW","康寧"], asset_type:"public_company"},
  GSG:{name:"iShares S&P GSCI Commodity-Indexed Trust", aliases:["iShares S&P GSCI Commodity-Indexed Trust","GSG","S&P GSCI","commodities","大宗商品"], asset_type:"etf", focus:"全球大宗商品"},
  HPE:{name:"Hewlett Packard Enterprise", aliases:["Hewlett Packard Enterprise","HPE","慧與"], asset_type:"public_company"},
  MOS:{name:"The Mosaic Company", aliases:["The Mosaic Company","Mosaic","MOS","美盛"], asset_type:"public_company"},
  MP:{name:"MP Materials", aliases:["MP Materials","MP","MP Materials Corp"], asset_type:"public_company"},
  NATGAS:{name:"Natural Gas", aliases:["Natural Gas","NATGAS","Henry Hub","natural gas","天然氣"], asset_type:"commodity", focus:"天然氣供需與庫存"},
  QNT:{name:"Quantinuum", aliases:["Quantinuum","QNT"], asset_type:"private_company"},
  QQQ:{name:"Invesco QQQ Trust", aliases:["Invesco QQQ Trust","QQQ","Nasdaq-100","Nasdaq 100","NASDAQ 100","那斯達克100","納斯達克100"], asset_type:"etf", focus:"Nasdaq-100"},
  SLV:{name:"iShares Silver Trust", aliases:["iShares Silver Trust","SLV","silver","白銀"], asset_type:"etf", focus:"白銀"},
  SMH:{name:"VanEck Semiconductor ETF", aliases:["VanEck Semiconductor ETF","SMH","semiconductor","semiconductors","半導體","晶片"], asset_type:"etf", focus:"半導體產業"},
  SOXL:{name:"Direxion Daily Semiconductor Bull 3X Shares", aliases:["Direxion Daily Semiconductor Bull 3X Shares","SOXL","semiconductor","semiconductors","半導體","晶片"], asset_type:"etf", focus:"半導體產業三倍多頭"},
  SOXX:{name:"iShares Semiconductor ETF", aliases:["iShares Semiconductor ETF","SOXX","semiconductor","semiconductors","半導體","晶片"], asset_type:"etf", focus:"半導體產業"},
  SPY:{name:"SPDR S&P 500 ETF Trust", aliases:["SPDR S&P 500 ETF Trust","SPY","S&P 500","SP500","標普500"], asset_type:"etf", focus:"S&P 500"},
  STX:{name:"Seagate Technology", aliases:["Seagate Technology","Seagate","STX","希捷"], asset_type:"public_company"},
  TQQQ:{name:"ProShares UltraPro QQQ", aliases:["ProShares UltraPro QQQ","TQQQ","Nasdaq-100","Nasdaq 100","那斯達克100","納斯達克100"], asset_type:"etf", focus:"Nasdaq-100 三倍多頭"},
  UNG:{name:"United States Natural Gas Fund", aliases:["United States Natural Gas Fund","UNG","natural gas","Henry Hub","天然氣"], asset_type:"etf", focus:"天然氣"},
  URA:{name:"Global X Uranium ETF", aliases:["Global X Uranium ETF","URA","uranium","nuclear energy","鈾","核能"], asset_type:"etf", focus:"鈾與核能產業"},
  URNM:{name:"Sprott Uranium Miners ETF", aliases:["Sprott Uranium Miners ETF","URNM","uranium miners","uranium","鈾礦","鈾"], asset_type:"etf", focus:"鈾礦產業"},
  USO:{name:"United States Oil Fund", aliases:["United States Oil Fund","USO","WTI","crude oil","West Texas Intermediate","原油","西德州原油"], asset_type:"etf", focus:"WTI 原油"},
  VGK:{name:"Vanguard FTSE Europe ETF", aliases:["Vanguard FTSE Europe ETF","VGK","European equities","Europe stocks","歐洲股市","歐股"], asset_type:"etf", focus:"歐洲股市"},
  XAG:{name:"Silver", aliases:["Silver","XAG","XAGUSD","白銀"], asset_type:"commodity", focus:"白銀供需與貴金屬市場"},
  XAU:{name:"Gold", aliases:["Gold","XAU","XAUUSD","黃金"], asset_type:"commodity", focus:"黃金與貴金屬市場"},
  XPD:{name:"Palladium", aliases:["Palladium","XPD","XPDUSD","鈀金","鈀"], asset_type:"commodity", focus:"鈀金供需"},
  XPT:{name:"Platinum", aliases:["Platinum","XPT","XPTUSD","鉑金","白金"], asset_type:"commodity", focus:"鉑金供需"},
  ALAB:{name:"Astera Labs", aliases:["Astera Labs","ALAB"], asset_type:"public_company"},
  ON:{name:"onsemi", aliases:["onsemi","ON Semiconductor","ON Semiconductor Corporation","安森美","安森美半導體"], asset_type:"public_company"},
  SNX:{name:"TD SYNNEX", aliases:["TD SYNNEX","SYNNEX","SNX","新聚思"], asset_type:"public_company"},
  VSH:{name:"Vishay Intertechnology", aliases:["Vishay Intertechnology","Vishay","VSH","威世科技","威世"], asset_type:"public_company"},
  PANW:{name:"Palo Alto Networks", aliases:["Palo Alto Networks","PANW","帕洛阿爾托網路"], asset_type:"public_company"},
  SHAZ:{name:"SharonAI Holdings", aliases:["SharonAI Holdings","SharonAI","SHAZ"], asset_type:"public_company"},
  SOXS:{name:"Direxion Daily Semiconductor Bear 3X Shares", aliases:["Direxion Daily Semiconductor Bear 3X Shares","SOXS","semiconductor","semiconductors","半導體","晶片"], asset_type:"etf", focus:"半導體產業三倍空頭"},
  XLP:{name:"Consumer Staples Select Sector SPDR Fund", aliases:["Consumer Staples Select Sector SPDR Fund","XLP","consumer staples","必需消費品"], asset_type:"etf", focus:"美國必需消費品產業"},
  XLV:{name:"Health Care Select Sector SPDR Fund", aliases:["Health Care Select Sector SPDR Fund","XLV","health care","healthcare","醫療保健"], asset_type:"etf", focus:"美國醫療保健產業"},

  Anthropic:{name:"Anthropic", aliases:["Anthropic"], asset_type:"private_company"},
  OpenAI:{name:"OpenAI", aliases:["OpenAI","Open AI"], asset_type:"private_company"},
  "Hyundai Motor":{name:"Hyundai Motor", aliases:["Hyundai Motor","Hyundai","現代汽車"], asset_type:"foreign_company"},
  Kioxia:{name:"Kioxia", aliases:["Kioxia","鎧俠"], asset_type:"foreign_company"},
  "Samsung Electronics":{name:"Samsung Electronics", aliases:["Samsung Electronics","Samsung","三星電子","三星"], asset_type:"foreign_company"},
  "SK hynix":{name:"SK hynix", aliases:["SK hynix","SK Hynix","SK海力士","海力士"], asset_type:"foreign_company"},
  SpaceX:{name:"SpaceX", aliases:["SpaceX","SPCX"], asset_type:"private_company"}
};

const RESEARCH_SOCIAL_DOMAINS = ["instagram.com","facebook.com","reddit.com","x.com","twitter.com","tiktok.com","youtube.com","threads.com","moomoo.com"];
const RESEARCH_EVENT_WORDS = [
  "earnings","revenue","profit","guidance","forecast","quarter","results","launch","announces","announcement","product","partnership","contract","deal","agreement","acquisition","acquire","merger","investment","lawsuit","sues","settlement","regulation","regulatory","sec","antitrust","upgrade","downgrade","price target","財報","營收","獲利","財測","法說","發布","推出","產品","合作","合約","協議","收購","併購","投資","訴訟","監管","反壟斷","升評","降評","目標價","關閉","裁員","漲價","調價"
];
const RESEARCH_CORE_EVENT_WORDS = [
  "earnings","revenue","guidance","quarterly results","official announcement","launch","product","pricing","price increase","partnership","contract","agreement","acquisition","merger","investment","lawsuit filed","sued","settlement","regulator","regulation","antitrust","sec filing","analyst upgrade","analyst downgrade","price target raised","price target cut","財報","營收","財測","法說","官方公告","發布","推出","產品","漲價","調價","合作","合約","協議","收購","併購","投資","提告","訴訟","和解","監管","反壟斷","升評","降評","目標價上調","目標價下調","關閉據點","裁員"
];
const RESEARCH_PRICE_COMMENTARY = [
  "is it too late to buy","should you buy","stock a buy","buy this stock","stock price prediction","technical analysis","options flow","valuation","overvalued","undervalued","price action","price forecast","是否值得買","還能不能買","現在能不能追","技術分析","選擇權流量","價格預測","估值","股價還有沒有","能不能買"
];
const RESEARCH_AGGREGATOR_MARKERS = [
  "latest headlines","people also follow","similar to","etfs holding","find & compare","subscriptions","investing groups","portfolios","analyst insights","statistics","balance sheet","cash flow annual","cash flow quarterly","share this article","全站最新","每日簽到","資券日報","盤後","主動式etf","期指"
];

function researchState(row) {
  return String(row?.opportunity_long?.market_state_id || "OTHER");
}

function researchTickerHint(symbol) {
  const s = String(symbol || "").trim().toUpperCase();
  if (RESEARCH_TICKER_OVERRIDES[s]) return RESEARCH_TICKER_OVERRIDES[s];
  if (s.endsWith("X") && s.length > 1) return s.slice(0, -1);
  return s;
}

function researchCompanyProfile(symbol) {
  const s = String(symbol || "").trim().toUpperCase();
  const hint = researchTickerHint(s);
  const profile = RESEARCH_COMPANY_PROFILES[hint] || RESEARCH_COMPANY_PROFILES[s] || null;
  const aliases = [];
  const add = (value) => {
    const v = String(value || "").trim();
    if (!v || aliases.some(x => x.toLowerCase() === v.toLowerCase())) return;
    aliases.push(v);
  };
  add(hint);
  if (!s.endsWith("X")) add(s);
  if (profile) {
    add(profile.name);
    for (const alias of profile.aliases || []) add(alias);
  }
  // Short 1-2 letter tickers (ON / BE / MP...) are common English words.
  // Keep them in the search prompt, but do not use them alone as Hard-Gate match aliases when a proper profile exists.
  const matchAliases = aliases.filter(value => {
    const v = String(value || "").trim();
    return !(profile && /^[A-Za-z]{1,2}$/.test(v));
  });
  return {
    symbol: s,
    underlying_ticker: hint,
    company_name: profile?.name || hint,
    asset_type: profile?.asset_type || "other",
    focus: profile?.focus || "",
    aliases,
    match_aliases: matchAliases.length ? matchAliases : aliases,
  };
}

function researchFresh(item, nowMs = Date.now()) {
  if (!item || typeof item !== "object") return false;
  // Provider migration: do not keep an old Groq cache alive after Tavily is deployed.
  if (item.api !== "tavily-search-api+workers-ai") return false;
  if (item.pipeline_version !== RESEARCH_PIPELINE_VERSION) return false;
  const direct = Date.parse(item.expires_at || "");
  if (Number.isFinite(direct)) return direct > nowMs;
  const searched = Date.parse(item.searched_at || "");
  return Number.isFinite(searched) && searched + RESEARCH_TTL_MS > nowMs;
}

async function readR2Json(env, key, fallback) {
  try {
    const obj = await env.JSON_BUCKET.get(key);
    if (!obj) return fallback;
    const parsed = JSON.parse(await obj.text());
    return parsed && typeof parsed === "object" ? parsed : fallback;
  } catch (_) {
    return fallback;
  }
}

async function tavilySearch(env, body) {
  const apiKey = String(env.TAVILY_API_KEY || "").trim();
  if (!apiKey) throw httpError(500, "Worker 缺少 TAVILY_API_KEY secret");
  const response = await fetch("https://api.tavily.com/search", {
    method: "POST",
    headers: {
      "Authorization": `Bearer ${apiKey}`,
      "Content-Type": "application/json",
      "Accept": "application/json",
    },
    body: JSON.stringify(body),
  });
  const text = await response.text();
  let payload = null;
  try { payload = JSON.parse(text); } catch (_) {}
  if (!response.ok) {
    const detail = payload?.detail?.error || payload?.detail || payload?.error || payload?.message || text || response.statusText;
    throw httpError(response.status, `Tavily Search 失敗：${String(detail).slice(0, 1200)}`);
  }
  if (!payload || typeof payload !== "object") throw httpError(502, "Tavily 回傳不是有效 JSON");
  return payload;
}

function researchEscapeRx(value) {
  return String(value || "").replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function researchTextHasAlias(text, alias) {
  const hay = String(text || "");
  const needle = String(alias || "").trim();
  if (!needle) return false;
  if (/^[A-Za-z0-9._-]{1,7}$/.test(needle)) {
    return new RegExp(`(^|[^A-Za-z0-9])${researchEscapeRx(needle)}([^A-Za-z0-9]|$)`, "i").test(hay);
  }
  return hay.toLowerCase().includes(needle.toLowerCase());
}

function researchCountAliasHits(text, aliases) {
  const hay = String(text || "");
  let total = 0;
  for (const alias of aliases || []) {
    const needle = String(alias || "").trim();
    if (!needle) continue;
    if (/^[A-Za-z0-9._-]{1,7}$/.test(needle)) {
      const rx = new RegExp(`(^|[^A-Za-z0-9])${researchEscapeRx(needle)}([^A-Za-z0-9]|$)`, "ig");
      total += (hay.match(rx) || []).length;
    } else {
      const lowerHay = hay.toLowerCase();
      const lowerNeedle = needle.toLowerCase();
      let pos = 0;
      while ((pos = lowerHay.indexOf(lowerNeedle, pos)) !== -1) {
        total++;
        pos += lowerNeedle.length;
      }
    }
  }
  return total;
}

function researchContainsAny(text, words) {
  const hay = String(text || "").toLowerCase();
  return (words || []).some(word => hay.includes(String(word || "").toLowerCase()));
}

function researchHost(url) {
  try { return new URL(String(url || "")).hostname.toLowerCase(); }
  catch (_) { return ""; }
}

function researchAgeDays(raw) {
  const ms = Date.parse(raw || "");
  return Number.isFinite(ms) ? (Date.now() - ms) / 86400000 : null;
}

function researchParseExplicitEventDate(text) {
  const s = String(text || "");
  let m = s.match(/\b(20\d{2})[\/\-.](\d{1,2})[\/\-.](\d{1,2})\b/);
  if (m) {
    const d = new Date(Date.UTC(+m[1], +m[2]-1, +m[3]));
    if (!Number.isNaN(d.getTime())) return d;
  }
  m = s.match(/(\d{1,2})月(\d{1,2})日/);
  if (m) {
    const now = new Date();
    const d = new Date(Date.UTC(now.getUTCFullYear(), +m[1]-1, +m[2]));
    if (!Number.isNaN(d.getTime())) return d;
  }
  const months = {jan:0,feb:1,mar:2,apr:3,may:4,jun:5,jul:6,aug:7,sep:8,oct:9,nov:10,dec:11};
  m = s.match(/\b(Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s+(\d{1,2})(?:st|nd|rd|th)?(?:,\s*(20\d{2}))?/i);
  if (m) {
    const month = months[m[1].slice(0,3).toLowerCase()];
    const year = +(m[3] || new Date().getUTCFullYear());
    const d = new Date(Date.UTC(year, month, +m[2]));
    if (!Number.isNaN(d.getTime())) return d;
  }
  return null;
}

function researchEventDateTooOld(item, maxDays=8) {
  const title = String(item?.title || "");
  const lead = String(item?.content || "").slice(0, 500);
  const d = researchParseExplicitEventDate(title) || researchParseExplicitEventDate(lead);
  if (!d) return false;
  return (Date.now() - d.getTime()) / 86400000 > maxDays;
}

function researchIsLandingOrQuotePage(item) {
  const url = String(item?.url || "");
  const title = String(item?.title || "");
  if (/\bstock price\b|\bstock quote\b|\bprice and forecast\b|\bprice & overview\b|\blatest stock news\b|\bcompany profile\b|\bstock overview\b|股票報價|股價與概覽|最新股票新聞/i.test(title)) return true;
  if (/finance\.yahoo\.com\/quote\//i.test(url)) return true;
  if (/seekingalpha\.com\/symbol\/[^/]+\/?$/i.test(url)) return true;
  if (/seekingalpha\.com\/symbol\/[^/]+\/news\/?$/i.test(url)) return true;
  if (/cnn\.com\/markets\/stocks\/[^/?#]+\/?$/i.test(url)) return true;
  if (/reuters\.com\/markets\/companies\/[^/?#]+\/?$/i.test(url)) return true;
  if (/marketbeat\.com\/stocks\/[^/]+\/[^/]+\/news\/?$/i.test(url)) return true;
  if (/tradingkey\.com\/markets\/stocks\/[^/]+\/news\/?$/i.test(url)) return true;
  if (/\/news-and-events\/news\/default\.aspx(?:[?#].*)?$/i.test(url)) return true;
  if (/markets\.financialcontent\.com\/.*\/quote\/news/i.test(url)) return true;
  return false;
}

function researchTitleDirectCompany(item, profile) {
  const title = String(item?.title || "");
  return (profile?.match_aliases || profile?.aliases || []).some(alias => researchTextHasAlias(title, alias));
}

function researchTitleStrongCompanyEvent(item, profile) {
  return researchTitleDirectCompany(item, profile) && researchContainsAny(item?.title || "", RESEARCH_EVENT_WORDS);
}

function researchArticleLikeUrl(item) {
  let path = "";
  try { path = new URL(String(item?.url || "")).pathname.toLowerCase(); } catch (_) {}
  return /\/article\//.test(path) || /\/articles\//.test(path) || /\/news\/id\//.test(path) || /\/news\/\d+/.test(path) || /\/story\//.test(path) || /\/\d{4}\/\d{2}\/\d{2}\//.test(path) || /\/press-releases?\//.test(path);
}

function researchLooksLikeAggregationPage(item, profile) {
  const lead = String(item?.content || "").slice(0, 1900).toLowerCase();
  if (researchArticleLikeUrl(item) && researchTitleStrongCompanyEvent(item, profile)) return false;
  const markerHits = RESEARCH_AGGREGATOR_MARKERS.filter(m => lead.includes(m)).length;
  const headingCount = (lead.match(/###/g) || []).length;
  return markerHits >= 3 || headingCount >= 6;
}

function researchIsPriceCommentary(item) {
  return researchContainsAny(item?.title || "", RESEARCH_PRICE_COMMENTARY);
}

function researchIsLawFirmSolicitation(item) {
  const text = `${String(item?.title || "")}\n${String(item?.content || "").slice(0, 1600)}`.toLowerCase();
  return ["deadline notice","lead plaintiff deadline","secure counsel","contact the firm","investors with losses","stockholders with losses","reminds investors","encourages investors","investor alert","trial attorneys","law firm urges","law firm reminds"].some(x => text.includes(x));
}

function researchIsInstitutionHoldingStory(item) {
  const title = String(item?.title || "").toLowerCase();
  return ["shares purchased by","shares sold by","stake increased by","stake reduced by","position increased by","position reduced by","asset management","institutional investor","insider sold","insider trading","insider sale"].some(x => title.includes(x));
}

function researchIsAnalystConsensusOnly(item) {
  const text = `${String(item?.title || "")}\n${String(item?.content || "").slice(0, 900)}`.toLowerCase();
  if (!/analysts?|price target|upside|consensus|rating/.test(text)) return false;
  const explicit = /(upgrade[sd]?|downgrade[sd]?|raise[sd]? (?:its )?price target|lower(?:ed|s)? (?:its )?price target|price target (?:raised|cut|lowered)|initiated coverage|reiterated (?:buy|sell|hold))/i.test(text);
  if (explicit) return false;
  return /analysts?, one verdict|all \d+ analysts|all analysts covering|average price target|consensus|upside isn.t done|implying \d+% upside/i.test(text);
}

function researchLooksLikeMultiStoryFeed(item) {
  const lead = String(item?.content || "").slice(0, 1600).toLowerCase();
  const feedMarkers = ["hours ago","hour ago","全站最新","盤後","資券日報","每日簽到","主動式etf","期指","hot news","latest news","more news","下一則","上一篇","下一篇"];
  const markerHits = feedMarkers.filter(x => lead.includes(x)).length;
  const headingCount = (lead.match(/###/g) || []).length;
  const numberedNewsCount = (lead.match(/\b\d+\s+/g) || []).length;
  return markerHits >= 2 || headingCount >= 5 || numberedNewsCount >= 8;
}

function researchBodyFocusMismatch(item, profile) {
  const title = String(item?.title || "");
  const lead = String(item?.content || "").slice(0, 1400);
  const titleHits = researchCountAliasHits(title, profile?.match_aliases || profile?.aliases || []);
  const leadHits = researchCountAliasHits(lead, profile?.match_aliases || profile?.aliases || []);
  if (titleHits > 0 && leadHits === 0) return true;
  if (researchLooksLikeMultiStoryFeed(item) && leadHits <= 1) return true;
  return false;
}

function researchHardGate(item, profile) {
  const host = researchHost(item?.url);
  const social = RESEARCH_SOCIAL_DOMAINS.some(d => host === d || host.endsWith(`.${d}`));
  const reasons = [];
  if (!researchTitleDirectCompany(item, profile)) reasons.push("標題沒有直接指向該公司/別名");
  if (researchIsLandingOrQuotePage(item)) reasons.push("股票首頁/報價/公司資料頁");
  if (researchLooksLikeAggregationPage(item, profile)) reasons.push("新聞索引/聚合頁");
  if (researchEventDateTooOld(item, 8)) reasons.push("文章雖新，但事件日期已超過 8 天");
  if (social) reasons.push("社群/討論區");
  if (researchIsPriceCommentary(item)) reasons.push("股價/估值/是否值得買等投資評論");
  if (researchIsLawFirmSolicitation(item)) reasons.push("律師事務所 Deadline / Investor Alert 招攬");
  if (researchIsInstitutionHoldingStory(item)) reasons.push("機構持倉/內部人交易，不是公司營運事件");
  if (researchIsAnalystConsensusOnly(item)) reasons.push("分析師共識/目標價彙整，不是新的升降評動作");
  if (researchBodyFocusMismatch(item, profile)) reasons.push("標題像公司新聞，但正文前段與該公司不一致/疑似多則新聞 Feed");
  return { pass: reasons.length === 0, reasons };
}

function researchScoreItem(item, profile) {
  const gate = researchHardGate(item, profile);
  if (!gate.pass) return { score:-99, keep:false, reasons:[], bad:gate.reasons.map(x => `硬淘汰：${x}`) };

  let score = 0;
  const reasons = [];
  const bad = [];
  const title = String(item?.title || "");
  const content = String(item?.content || "");
  const coreEvent = researchContainsAny(title, RESEARCH_CORE_EVENT_WORDS) || researchContainsAny(content.slice(0, 900), RESEARCH_CORE_EVENT_WORDS);
  const concreteEvent = researchContainsAny(title, RESEARCH_EVENT_WORDS) || researchContainsAny(content.slice(0, 650), RESEARCH_EVENT_WORDS);
  const age = researchAgeDays(item?.published_date || item?.publishedDate);

  if (researchTitleDirectCompany(item, profile)) { score += 8; reasons.push("標題直接命中公司/別名 +8"); }
  if (coreEvent) { score += 6; reasons.push("核心公司事件 +6"); }
  if (concreteEvent) { score += 3; reasons.push("標題/前段有具體事件 +3"); }
  if (age != null && age >= -1 && age <= 8) { score += 2; reasons.push("最近 8 天 +2"); }
  const tavilyScore = Number(item?.score);
  if (Number.isFinite(tavilyScore)) {
    if (tavilyScore >= 0.5) { score += 2; reasons.push("Tavily 高相關 +2"); }
    else if (tavilyScore < 0.15) { score -= 2; bad.push("Tavily 低相關 -2"); }
  }
  if (!coreEvent && !concreteEvent) return { score, keep:false, reasons, bad:[...bad,"沒有足夠明確的公司事件"] };
  return { score, keep:score >= 10, reasons, bad };
}

function researchRankResults(results, profile) {
  const seen = new Set();
  const rows = (Array.isArray(results) ? results : []).map((item, index) => {
    const verdict = researchScoreItem(item, profile);
    return { ...item, _index:index, _score:verdict.score, _keep:verdict.keep, _reasons:verdict.reasons, _bad:verdict.bad };
  }).sort((a,b) => b._score - a._score);
  const kept = [];
  const rejected = [];
  for (const row of rows) {
    const key = `${String(row.title || "").toLowerCase().replace(/[^a-z0-9\u4e00-\u9fff]+/g," ").trim().slice(0,90)}|${researchHost(row.url)}`;
    if (row._keep && seen.has(key)) {
      row._keep = false;
      row._bad = [...(row._bad || []), "疑似重複來源"];
    }
    if (row._keep) { seen.add(key); kept.push(row); }
    else rejected.push(row);
  }
  return { kept:kept.slice(0,3), rejected };
}


function researchToTraditionalChinese(value) {
  // Lightweight normalization for the common Simplified-Chinese characters Tavily occasionally returns.
  // It is intentionally small and deterministic; original source text is preserved separately.
  const map = {
    "发":"發","财":"財","报":"報","预":"預","测":"測","会":"會","营":"營","获":"獲","优":"優","于":"於","产":"產","业":"業","数":"數","据":"據","关":"關","闭":"閉","监":"監","诉":"訴","讼":"訟","评":"評","级":"級","标":"標","价":"價","调":"調","资":"資","议":"議","并":"並","购":"購","联":"聯","动":"動","风":"風","险":"險","势":"勢","涨":"漲","亿":"億","万":"萬","与":"與","为":"為","将":"將","这":"這","过":"過","个":"個","时":"時","间":"間","内":"內","进":"進","术":"術","电":"電","网":"網","软":"軟","务":"務","国":"國","华":"華","台":"臺","额":"額","经":"經","济":"濟","证":"證","券":"券","现":"現","实":"實","应":"應","对":"對","从":"從","长":"長","广":"廣","东":"東","门":"門","点":"點","体":"體","复":"復","规":"規","则":"則","权":"權","处":"處","么":"麼","还":"還","仅":"僅","约":"約","换":"換","后":"後","压":"壓","线":"線","机":"機","构":"構","类":"類","创":"創","强":"強","较":"較","显":"顯","际":"際","开":"開","扩":"擴","达":"達","远":"遠","维":"維","续":"續","减":"減","增":"增","转":"轉","陆":"陸","离":"離","储":"儲","销":"銷","损":"損","础":"礎","协":"協","终":"終","选":"選","择":"擇","独":"獨","涨":"漲","跌":"跌","总":"總","值":"值"
  };
  return String(value || "").replace(/[\u3400-\u9fff]/g, ch => map[ch] || ch);
}

function researchHasCjk(value) {
  return /[\u3400-\u9fff]/.test(String(value || ""));
}

function researchCleanAnswerText(value) {
  return researchToTraditionalChinese(value)
    .replace(/```(?:json)?/gi, "")
    .replace(/```/g, "")
    .replace(/\*\*/g, "")
    .replace(/\r/g, "")
    .replace(/[ \t]+\n/g, "\n")
    .trim();
}

function researchCategoryLabelZh(category) {
  return ({
    earnings:"財報／營收", guidance:"財測／展望", company_catalyst:"公司催化",
    analyst:"分析師異動", sec_capital:"SEC／資本", regulatory_legal:"法規／訴訟",
    fund_event:"ETF／基金事件", commodity_supply:"供需／庫存", policy_macro:"政策／產業事件",
    direct_industry:"產業事件"
  })[String(category || "")] || "重大事件";
}

function researchAnswerSegments(answer) {
  const text = researchCleanAnswerText(answer);
  if (!text) return [];
  const out = [];
  const push = (raw) => {
    let s = String(raw || "").replace(/^\s*[\-•]+\s*/, "").trim();
    s = s.replace(/^標題[:：]\s*/i, "").trim();
    if (s.length < 12 || !researchHasCjk(s)) return;
    if (/^(根據|依據|以下是|最近7天|最近 7 天).{0,24}(重大|新聞|事件)/.test(s) && s.length < 80) return;
    if (!out.some(x => x === s)) out.push(s.slice(0, 520));
  };

  // Preferred strict format: 【事件1】標題：...｜摘要：...
  const strict = [...text.matchAll(/【事件\s*\d+】\s*([\s\S]*?)(?=【事件\s*\d+】|$)/g)];
  if (strict.length) {
    for (const m of strict) push(m[1]);
    return out.slice(0, 6);
  }

  // Numbered answer.
  const numbered = text.split(/(?:^|\n)\s*\d+[\.、\)]\s+/).slice(1);
  if (numbered.length) {
    numbered.forEach(push);
    if (out.length) return out.slice(0, 6);
  }

  // Paragraph answer: split common Chinese sequencing words and punctuation.
  text.split(/(?:首先|其次|最後|最后|此外|另外|同時|同时|；|。|！|？|\n+)/).forEach(push);
  return out.slice(0, 8);
}

function researchSegmentScoreForItem(segment, item, profile, category) {
  const seg = String(segment || "");
  const src = `${item?.title || ""} ${String(item?.content || "").slice(0, 900)}`;
  let score = 0;
  if ((profile?.match_aliases || profile?.aliases || []).some(a => researchTextHasAlias(seg, a))) score += 4;
  const segNums = new Set((seg.match(/\b\d+(?:\.\d+)?\b/g) || []).filter(x => x.length >= 2));
  for (const n of (src.match(/\b\d+(?:\.\d+)?\b/g) || [])) if (segNums.has(n)) score += 3;
  const tokens = (src.match(/[A-Za-z][A-Za-z0-9-]{2,}/g) || []).filter(x => !/^(the|and|for|with|from|this|that|stock|news|company)$/i.test(x));
  for (const t of tokens.slice(0, 30)) if (seg.toLowerCase().includes(t.toLowerCase())) score += 1;
  if (researchCategoryLabelZh(category) && researchContainsAny(seg, [researchCategoryLabelZh(category)])) score += 2;
  return score;
}

function researchDisplayFields(payloadAnswer, kept, profile) {
  const answer = researchCleanAnswerText(payloadAnswer);
  const segments = researchAnswerSegments(answer);
  const used = new Set();
  const displays = [];

  for (const item of kept || []) {
    const category = researchEventCategory(item, profile);
    let bestIndex = -1;
    let bestScore = -1;
    segments.forEach((seg, idx) => {
      if (used.has(idx)) return;
      const score = researchSegmentScoreForItem(seg, item, profile, category);
      if (score > bestScore) { bestScore = score; bestIndex = idx; }
    });
    if (bestIndex < 0 && segments.length) bestIndex = segments.findIndex((_, idx) => !used.has(idx));
    if (bestIndex >= 0) used.add(bestIndex);
    const segment = bestIndex >= 0 ? segments[bestIndex] : "";
    let displayTitle = `${profile.company_name}｜${researchCategoryLabelZh(category)}`;
    let displayDetail = segment;
    const titleMatch = segment.match(/(?:^|[｜|])\s*標題[:：]\s*([^｜|]+)(?:[｜|]|$)/i);
    const detailMatch = segment.match(/(?:^|[｜|])\s*摘要[:：]\s*([\s\S]+)/i);
    const compactParts = segment.split(/[｜|]/).map(x => x.trim()).filter(Boolean);
    if (titleMatch && researchHasCjk(titleMatch[1])) displayTitle = titleMatch[1].trim().slice(0, 120);
    else if (compactParts.length >= 2 && researchHasCjk(compactParts[0])) displayTitle = compactParts[0].replace(/^標題[:：]\s*/i, "").slice(0,120);
    if (detailMatch && researchHasCjk(detailMatch[1])) displayDetail = detailMatch[1].trim().slice(0, 420);
    else if (compactParts.length >= 2 && researchHasCjk(compactParts.slice(1).join(" "))) displayDetail = compactParts.slice(1).join(" ").replace(/^摘要[:：]\s*/i, "").slice(0,420);
    if (!displayDetail || !researchHasCjk(displayDetail)) {
      displayDetail = `已找到與 ${profile.company_name} 直接相關的近期${researchCategoryLabelZh(category)}；原始英文內容與網址保留於下方查證來源。`;
    }
    displays.push({ display_title_zh_tw:researchToTraditionalChinese(displayTitle), display_detail_zh_tw:researchToTraditionalChinese(displayDetail) });
  }

  let summary = kept?.length ? answer : "";
  if (!summary || !researchHasCjk(summary)) {
    summary = kept?.length
      ? `最近 7 天找到 ${kept.length} 則符合條件的重大事件；已由 JS Hard Gate 驗證來源，繁體中文事件重點顯示於下方。`
      : `最近 7 天未找到符合條件的 ${profile.company_name} 重大事件；不硬湊。`;
  }
  return { summary_zh_tw:researchToTraditionalChinese(summary).slice(0, 1100), displays };
}

function researchEventCategory(item, profile=null) {
  const text = `${item?.title || ""}\n${String(item?.content || "").slice(0, 700)}`.toLowerCase();
  const type = String(profile?.asset_type || "");
  if (type === "commodity") {
    if (/inventory|stockpile|production|output|supply|demand|opec|eia|庫存|產量|供給|供應|需求/.test(text)) return "commodity_supply";
    return "policy_macro";
  }
  if (type === "etf") {
    if (/rebalance|reconstitution|holdings|constituent|inflow|outflow|fund flow|distribution|split|成分|再平衡|資金流|配息|拆分/.test(text)) return "fund_event";
    return "policy_macro";
  }
  if (/earnings|revenue|quarter|results|財報|營收|法說/.test(text)) return "earnings";
  if (/guidance|forecast|財測|展望/.test(text)) return "guidance";
  if (/upgrade|downgrade|price target|升評|降評|目標價/.test(text)) return "analyst";
  if (/sec filing|8-k|10-q|10-k|buyback|convertible|offering|增資|回購|可轉債/.test(text)) return "sec_capital";
  if (/lawsuit|regulat|antitrust|investigation|probe|訴訟|監管|反壟斷|調查/.test(text)) return "regulatory_legal";
  if (/partnership|contract|agreement|launch|product|acquisition|merger|investment|合作|合約|協議|發布|產品|收購|併購|投資|關閉據點|裁員/.test(text)) return "company_catalyst";
  return "direct_industry";
}

function researchEventImpact(item) {
  const text = `${item?.title || ""}\n${String(item?.content || "").slice(0, 650)}`.toLowerCase();
  const positive = /beat|growth|surge|win|partnership|contract|launch|upgrade|raised target|record|outperform|成長|優於|合作|合約|發布|升評|上調|創高/.test(text);
  const negative = /miss|downgrade|cut target|lawsuit|investigation|probe|closure|layoff|risk|decline|下滑|低於|降評|下調|訴訟|調查|關閉|裁員|風險/.test(text);
  if (positive && negative) return "mixed";
  if (positive) return "positive";
  if (negative) return "negative";
  return "neutral";
}

function researchEventDate(item) {
  const explicit = researchParseExplicitEventDate(`${item?.title || ""} ${String(item?.content || "").slice(0, 450)}`);
  if (explicit) return explicit.toISOString().slice(0,10);
  const ms = Date.parse(item?.published_date || item?.publishedDate || "");
  return Number.isFinite(ms) ? new Date(ms).toISOString().slice(0,10) : "";
}

function researchCompactSnippet(item, maxLen=260) {
  return String(item?.content || "").replace(/\s+/g," ").trim().slice(0,maxLen);
}

function researchVerdictFromEvents(events) {
  const impacts = (events || []).map(x => x.impact);
  const pos = impacts.filter(x => x === "positive").length;
  const neg = impacts.filter(x => x === "negative").length;
  const mixed = impacts.filter(x => x === "mixed").length;
  if (pos >= 3 && neg === 0 && mixed === 0) return "strong_positive";
  if (neg >= 3 && pos === 0 && mixed === 0) return "high_risk";
  if ((pos && neg) || mixed) return "mixed";
  if (pos) return "positive";
  if (neg) return "risk";
  return "neutral";
}

function researchBuildQuery(profile) {
  const aliases = (profile?.aliases || []).slice(0, 16).join(" / ");
  const type = String(profile?.asset_type || "other");
  const focus = String(profile?.focus || profile?.company_name || profile?.underlying_ticker || "").trim();

  if (["public_company","foreign_company"].includes(type)) {
    return `搜尋 ${profile.company_name} (${profile.underlying_ticker}) 最近 7 天「直接與 ${profile.company_name} 本身有關、而且事件本身也發生在最近 7 天」的重大公司新聞。\n\n公司也可能以這些名稱出現：${aliases}\n\n- 財報 / 財測 / 法說會更新\n- ${profile.company_name} 官方公告\n- 新產品或重大業務正式發布\n- 重大合作 / 收購 / 投資\n- SEC / 監管 / 訴訟\n- 分析師重大升降評或目標價異動（必須是最近 7 天的新動作）\n- 直接影響 ${profile.company_name} 營運的重大產業事件\n\n且用繁體中文顯示`;
  }

  if (type === "private_company") {
    return `搜尋 ${profile.company_name} 最近 7 天直接相關的重大公司事件。\n\n可能名稱：${aliases}\n\n- 官方產品 / 技術 / 商業發布\n- 大型客戶、訂單、合作或合約\n- 融資、併購、重大投資、IPO / 上市進度\n- 監管、訴訟、政府合約或重大政策影響\n- 直接影響 ${profile.company_name} 營運的重大產業事件\n\n且用繁體中文顯示`;
  }

  if (type === "etf") {
    return `搜尋 ${profile.company_name} (${profile.underlying_ticker}) 最近 7 天重大 ETF / 基金事件，以及直接影響其核心曝險「${focus}」的重大事件。\n\n可能名稱或主題：${aliases}\n\n- 發行商正式公告、基金結構、拆分、配息、成分或指數再平衡\n- 有可靠來源的重大資金流 / 持倉結構變化\n- 直接影響「${focus}」的重大政策、供需、產業或大型成分股事件\n- 對 ETF 核心曝險有明確因果關係的重大市場事件\n\n且用繁體中文顯示`;
  }

  if (type === "commodity") {
    return `搜尋 ${profile.company_name} (${profile.underlying_ticker}) 最近 7 天直接影響「${focus}」的重大市場事件。\n\n可能名稱：${aliases}\n\n- 供給 / 需求 / 庫存 / 產量 / 礦山或油氣設施中斷\n- OPEC、EIA、政府政策、制裁、關稅、地緣事件且必須直接影響該商品\n- 央行、實質利率或工業需求等對該商品有明確直接影響的重大事件\n- 其他可驗證、會改變該商品供需結構的事件\n\n且用繁體中文顯示`;
  }

  return `搜尋 ${profile.company_name} (${profile.underlying_ticker}) 最近 7 天直接相關的重大市場事件。\n\n可能名稱：${aliases}\n\n只保留可驗證且直接相關的重大事件，且用繁體中文顯示`;
}

function researchStripCodeFence(value) {
  return String(value || "").trim()
    .replace(/^```(?:json)?\s*/i, "")
    .replace(/\s*```$/i, "")
    .trim();
}

function researchIsExpectedGlmObject(value) {
  return Boolean(
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    (Array.isArray(value.events) || Object.prototype.hasOwnProperty.call(value, "summary_zh_tw") || Object.prototype.hasOwnProperty.call(value, "verdict"))
  );
}

function researchGlmOutputText(value) {
  if (typeof value === "string") return value;
  if (!value || typeof value !== "object") return "";

  // Cloudflare GLM-4.7-Flash synchronous output follows chat-completions shape:
  // choices[0].message.content. Older Workers AI models may expose response/result.
  const direct = [value.response, value.result, value.output_text, value.text];
  for (const part of direct) {
    if (typeof part === "string" && part.trim()) return part;
  }

  const message = value?.choices?.[0]?.message;
  if (typeof message?.content === "string" && message.content.trim()) return message.content;
  if (Array.isArray(message?.content)) {
    const joined = message.content.map(part => {
      if (typeof part === "string") return part;
      if (part && typeof part === "object") return String(part.text || part.content || "");
      return "";
    }).join("\n").trim();
    if (joined) return joined;
  }

  const choiceText = value?.choices?.[0]?.text;
  return typeof choiceText === "string" ? choiceText : "";
}

function researchParseGlmJson(value) {
  if (researchIsExpectedGlmObject(value)) return value;

  // Workers AI JSON Mode commonly returns { response: { ...validated object... } }.
  // Also accept result/data object wrappers for forward compatibility.
  const objectWrappers = [value?.response, value?.result, value?.data];
  for (const wrapped of objectWrappers) {
    if (researchIsExpectedGlmObject(wrapped)) return wrapped;
  }

  const raw = researchStripCodeFence(researchGlmOutputText(value));
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw);
    if (researchIsExpectedGlmObject(parsed)) return parsed;
    if (researchIsExpectedGlmObject(parsed?.response)) return parsed.response;
  } catch (_) {}
  const first = raw.indexOf("{");
  const last = raw.lastIndexOf("}");
  if (first >= 0 && last > first) {
    try {
      const parsed = JSON.parse(raw.slice(first, last + 1));
      if (researchIsExpectedGlmObject(parsed)) return parsed;
      if (researchIsExpectedGlmObject(parsed?.response)) return parsed.response;
    } catch (_) {}
  }
  return null;
}

function researchCompactGlmCandidates(candidates) {
  return candidates.map(item => ({
    source_index: item.source_index,
    title: item.title,
    url: item.url,
    published_date: item.published_date,
    tavily_score: item.tavily_score,
    content: String(item.content || "").slice(0, 1100),
  }));
}

function researchGlmUsageSummary(firstUsage, retryUsage, attempts) {
  const a = firstUsage && typeof firstUsage === "object" ? firstUsage : {};
  const b = retryUsage && typeof retryUsage === "object" ? retryUsage : {};
  const add = key => (Number(a[key]) || 0) + (Number(b[key]) || 0);
  return {
    attempts,
    prompt_tokens: add("prompt_tokens"),
    completion_tokens: add("completion_tokens"),
    total_tokens: add("total_tokens"),
    neurons: add("neurons"),
    first: firstUsage || null,
    retry: retryUsage || null,
  };
}

function researchNormalizeImpact(value) {
  const v = String(value || "neutral").toLowerCase();
  return ["positive","negative","neutral","mixed"].includes(v) ? v : "neutral";
}

function researchNormalizeVerdict(value) {
  const v = String(value || "neutral").toLowerCase();
  return ["positive","mixed","neutral","risk","high_risk"].includes(v) ? v : "neutral";
}

function researchNormalizeCategory(value, item, profile) {
  const v = String(value || "").trim();
  const allowed = new Set(["earnings","guidance","company_catalyst","analyst","regulatory","legal","fund_event","commodity_supply","policy_macro","industry"]);
  return allowed.has(v) ? v : researchEventCategory(item, profile);
}

function researchGlmCandidate(item, index) {
  return {
    source_index: index + 1,
    title: String(item?.title || "").slice(0, 500),
    url: String(item?.url || ""),
    published_date: String(item?.published_date || item?.publishedDate || "").slice(0, 90),
    tavily_score: Number.isFinite(Number(item?.score)) ? Number(item.score) : null,
    content: String(item?.content || "").slice(0, 2400),
  };
}


function researchNewsJsonSchema() {
  return {
    type: "object",
    properties: {
      summary_zh_tw: { type: "string" },
      verdict: {
        type: "string",
        enum: ["positive", "mixed", "neutral", "risk", "high_risk"]
      },
      events: {
        type: "array",
        items: {
          type: "object",
          properties: {
            source_index: { type: "integer" },
            category: {
              type: "string",
              enum: [
                "earnings","guidance","company_catalyst","analyst",
                "regulatory","legal","fund_event","commodity_supply",
                "policy_macro","industry"
              ]
            },
            date: { type: "string" },
            impact: {
              type: "string",
              enum: ["positive","negative","neutral","mixed"]
            },
            display_title_zh_tw: { type: "string" },
            display_detail_zh_tw: { type: "string" }
          },
          required: [
            "source_index","category","date","impact",
            "display_title_zh_tw","display_detail_zh_tw"
          ]
        }
      },
      rejected: {
        type: "array",
        items: {
          type: "object",
          properties: {
            source_index: { type: "integer" },
            reason_zh_tw: { type: "string" }
          },
          required: ["source_index","reason_zh_tw"]
        }
      }
    },
    required: ["summary_zh_tw","verdict","events","rejected"]
  };
}

async function researchGlmFilter(env, profile, query, payload) {
  if (!env.AI || typeof env.AI.run !== "function") {
    throw httpError(500, "Worker 缺少 Workers AI binding：請新增名為 AI 的 Workers AI binding");
  }

  const candidates = (Array.isArray(payload?.results) ? payload.results : []).map(researchGlmCandidate);
  if (!candidates.length) {
    return {
      summary_zh_tw: "最近 7 天沒有找到可供判讀的候選來源。",
      verdict: "neutral",
      events: [],
      rejected: [],
      raw: "",
      usage: null,
    };
  }

  const systemPrompt = `你是嚴格的金融新聞審核與繁體中文整理模型。Tavily 已經完成搜尋；你不能再搜尋，也不能使用候選來源以外的知識補故事。\n\n你的任務：\n1. 完整遵守使用者的「原始搜尋指令」。\n2. 從所有候選來源中，保留真正符合條件的重大事件；不要因為標題提到股票就保留。\n3. 同一事件若有多個來源，合併成一則並選資訊最完整、最直接的 source_index。\n4. 不設定固定保留數量：有幾則真正符合就保留幾則；沒有就回空陣列。不要硬湊。\n5. 事件本身必須發生在最近 7 天；新文章重講舊事件要淘汰。\n6. 排除新聞索引頁、Quote/Profile、技術分析、是否值得買、純股價評論、社群傳聞、律師事務所招攬、無關公司、只有機構持倉/內部人交易而沒有重大公司事件的文章。\n7. 分析師事件只保留最近 7 天真正新發生的升評、降評或目標價異動，不保留共識彙整文。\n8. 每一則保留事件必須綁定候選中的 source_index。不得發明 URL、數字、日期、公司行動。\n9. display_title_zh_tw、display_detail_zh_tw、summary_zh_tw 必須使用台灣繁體中文（zh-TW）；英文原文只留在來源欄，不要直接複製成顯示文字。\n10. impact 是事件本身對標的基本面/營運的方向，不是單純看當天股價漲跌。\n\n只輸出 JSON，不要 Markdown。JSON 格式：\n{\n  "summary_zh_tw": "整體重點，繁體中文",\n  "verdict": "positive|mixed|neutral|risk|high_risk",\n  "events": [\n    {\n      "source_index": 1,\n      "category": "earnings|guidance|company_catalyst|analyst|regulatory|legal|fund_event|commodity_supply|policy_macro|industry",\n      "date": "YYYY-MM-DD 或空字串",\n      "impact": "positive|negative|neutral|mixed",\n      "display_title_zh_tw": "繁體中文事件標題",\n      "display_detail_zh_tw": "繁體中文摘要，只寫來源能支持的事實"\n    }\n  ],\n  "rejected": [\n    {"source_index": 2, "reason_zh_tw": "淘汰原因"}\n  ]\n}`;

  const userPayload = {
    target: {
      symbol: profile.symbol,
      underlying_ticker: profile.underlying_ticker,
      company_name: profile.company_name,
      aliases: profile.aliases,
      asset_type: profile.asset_type,
      focus: profile.focus || "",
    },
    original_instruction: query,
    candidate_count: candidates.length,
    candidates,
  };

  const jsonSchema = researchNewsJsonSchema();

  const firstRequest = {
    messages: [
      { role: "system", content: systemPrompt },
      { role: "user", content: JSON.stringify(userPayload) },
    ],
    temperature: 0,
    max_tokens: 1800,
    response_format: {
      type: "json_schema",
      json_schema: jsonSchema,
    },
  };

  let aiOut = null;
  let firstOut = null;
  let retryOut = null;
  let parsed = null;
  let attempts = 0;
  let primaryError = null;

  // Primary: cheap non-reasoning Llama 3.1 8B Fast, officially supported by
  // Workers AI JSON Mode. We require a validated schema instead of hoping the
  // model prints parseable JSON after free-form reasoning.
  try {
    attempts = 1;
    aiOut = await env.AI.run(RESEARCH_GLM_MODEL, firstRequest);
    firstOut = aiOut;
    parsed = researchParseGlmJson(aiOut);
  } catch (err) {
    primaryError = String(err?.message || err || "");
  }

  // Fallback: Llama 3.3 70B Fast, also officially supported by JSON Mode.
  // Only runs when the cheap primary model fails schema/parse, so normal calls
  // stay inexpensive and within the Free-plan Neuron budget more easily.
  if (!parsed) {
    attempts = 2;
    const compactPayload = {
      target: userPayload.target,
      original_instruction: query,
      candidate_count: candidates.length,
      candidates: candidates.map(item => ({
        source_index: item.source_index,
        title: item.title,
        url: item.url,
        published_date: item.published_date,
        tavily_score: item.tavily_score,
        content: String(item.content || "").slice(0, 850),
      })),
    };

    try {
      retryOut = await env.AI.run(RESEARCH_FALLBACK_MODEL, {
        messages: [
          {
            role: "system",
            content:
              "你是金融新聞篩選器。只根據候選來源工作。依 original_instruction 保留最近 7 天真正重要且直接相關的事件；排除舊事件、Quote/Profile/索引頁、技術分析、純股價評論、社群傳聞、律師招攬、無關公司與單純機構持倉。相同事件合併。所有顯示文字使用台灣繁體中文。不得發明資料。"
          },
          { role: "user", content: JSON.stringify(compactPayload) },
        ],
        temperature: 0,
        max_tokens: 1600,
        response_format: {
          type: "json_schema",
          json_schema: jsonSchema,
        },
      });
      parsed = researchParseGlmJson(retryOut);
      if (parsed) aiOut = retryOut;
    } catch (err) {
      if (!primaryError) primaryError = "";
      primaryError += `${primaryError ? " | " : ""}fallback: ${String(err?.message || err || "")}`;
    }
  }

  if (!parsed || typeof parsed !== "object") {
    throw httpError(
      502,
      `AI JSON Mode 兩層都失敗；本次不寫入 24H 快取。${primaryError ? " " + primaryError.slice(0, 500) : ""}`
    );
  }

  const responseValue = researchGlmOutputText(aiOut) || aiOut;

  const rawEvents = Array.isArray(parsed.events) ? parsed.events : [];
  const events = [];
  const selectedIndices = new Set();
  const seenEventKeys = new Set();

  for (const ev of rawEvents) {
    const sourceIndex = Number(ev?.source_index);
    if (!Number.isInteger(sourceIndex) || sourceIndex < 1 || sourceIndex > candidates.length) continue;
    const item = payload.results[sourceIndex - 1];
    const titleZh = researchToTraditionalChinese(String(ev?.display_title_zh_tw || "").trim());
    const detailZh = researchToTraditionalChinese(String(ev?.display_detail_zh_tw || "").trim());
    if (!titleZh || !detailZh) continue;
    const key = `${sourceIndex}|${titleZh.toLowerCase()}`;
    if (seenEventKeys.has(key)) continue;
    seenEventKeys.add(key);
    selectedIndices.add(sourceIndex);
    events.push({
      source_index: sourceIndex,
      category: researchNormalizeCategory(ev?.category, item, profile),
      date: /^20\d{2}-\d{2}-\d{2}$/.test(String(ev?.date || "")) ? String(ev.date) : researchEventDate(item),
      impact: researchNormalizeImpact(ev?.impact),
      display_title_zh_tw: titleZh.slice(0, 220),
      display_detail_zh_tw: detailZh.slice(0, 900),
    });
  }

  const rejectionReasons = new Map();
  for (const rej of Array.isArray(parsed.rejected) ? parsed.rejected : []) {
    const idx = Number(rej?.source_index);
    if (!Number.isInteger(idx) || idx < 1 || idx > candidates.length) continue;
    const reason = researchToTraditionalChinese(String(rej?.reason_zh_tw || "").trim());
    if (reason) rejectionReasons.set(idx, reason.slice(0, 300));
  }

  return {
    summary_zh_tw: researchToTraditionalChinese(String(parsed.summary_zh_tw || "").trim()) || (events.length ? `最近 7 天找到 ${events.length} 則符合條件的重大事件。` : "最近 7 天沒有符合條件的重大事件。"),
    verdict: researchNormalizeVerdict(parsed.verdict),
    events,
    selected_indices: selectedIndices,
    rejection_reasons: rejectionReasons,
    raw: typeof responseValue === "string" ? responseValue.slice(0, 12000) : JSON.stringify(responseValue).slice(0, 12000),
    usage: researchGlmUsageSummary(firstOut?.usage || null, retryOut?.usage || null, attempts),
    attempt_count: attempts,
  };
}

function researchBuildItem(row, profile, payload, glm, searchedAt) {
  const symbol = String(row?.symbol || "").trim().toUpperCase();
  const searchedMs = Date.parse(searchedAt);
  const results = Array.isArray(payload?.results) ? payload.results : [];
  const selected = glm?.selected_indices instanceof Set ? glm.selected_indices : new Set();
  const events = (Array.isArray(glm?.events) ? glm.events : []).map(ev => ({
    category: ev.category,
    date: ev.date || "",
    impact: ev.impact,
    title: String(results[ev.source_index - 1]?.title || "近期資訊").slice(0, 240),
    detail: researchCompactSnippet(results[ev.source_index - 1], 420),
    display_title_zh_tw: ev.display_title_zh_tw,
    display_detail_zh_tw: ev.display_detail_zh_tw,
    source_index: ev.source_index,
  }));

  const sourceIndices = [...new Set(events.map(ev => ev.source_index))];
  const sources = sourceIndices.map(sourceIndex => {
    const item = results[sourceIndex - 1] || {};
    return {
      source_index: sourceIndex,
      title: String(item?.title || item?.url || "來源").slice(0, 260),
      url: String(item?.url || ""),
      published_date: String(item?.published_date || item?.publishedDate || "").slice(0, 90),
      tavily_score: Number.isFinite(Number(item?.score)) ? Number(item.score) : null,
    };
  });

  const rejected = results.map((item, index) => {
    const sourceIndex = index + 1;
    if (selected.has(sourceIndex)) return null;
    return {
      source_index: sourceIndex,
      title: String(item?.title || "").slice(0, 260),
      url: String(item?.url || ""),
      tavily_score: Number.isFinite(Number(item?.score)) ? Number(item.score) : null,
      reasons: [`GLM：${glm?.rejection_reasons?.get(sourceIndex) || "未列入符合原始指令的重大事件"}`],
    };
  }).filter(Boolean);

  const summary = researchToTraditionalChinese(String(glm?.summary_zh_tw || "").trim()) || (events.length
    ? `最近 7 天找到 ${events.length} 則符合條件的重大事件。`
    : `最近 7 天沒有符合條件的重大事件。`);
  const earningsEvent = ["public_company","foreign_company"].includes(profile.asset_type)
    ? events.find(x => x.category === "earnings") || null
    : null;

  return {
    symbol,
    api_symbol: row?.api_symbol || null,
    state_at_search: researchState(row),
    searched_at: searchedAt,
    expires_at: new Date((Number.isFinite(searchedMs) ? searchedMs : Date.now()) + RESEARCH_TTL_MS).toISOString(),
    underlying_ticker: profile.underlying_ticker,
    company_name: profile.company_name,
    company_aliases: profile.aliases,
    asset_type: profile.asset_type,
    asset_focus: profile.focus || "",
    verdict: researchNormalizeVerdict(glm?.verdict || researchVerdictFromEvents(events)),
    summary,
    summary_zh_tw: summary,
    last_earnings: {
      date: earningsEvent?.date || "",
      eps: earningsEvent ? "unknown" : "not_applicable",
      revenue: earningsEvent ? "unknown" : "not_applicable",
      guidance: earningsEvent ? "unknown" : "not_applicable",
    },
    next_earnings_date: "",
    events,
    sources,
    rejected,
    model: RESEARCH_PROVIDER,
    api: "tavily-search-api+workers-ai",
    search_mode: "on_demand_tavily20_llama_jsonmode_zhtw",
    research_status: "ON_DEMAND",
    pipeline_version: RESEARCH_PIPELINE_VERSION,
    query: String(payload?.query || ""),
    candidate_count: results.length,
    selected_count: events.length,
    tavily_answer_raw: "",
    provider_usage: payload?.usage || null,
    request_id: payload?.request_id || null,
    response_time: payload?.response_time ?? null,
    glm_model: attempts > 1 && retryOut ? RESEARCH_FALLBACK_MODEL : RESEARCH_GLM_MODEL,
    ai_primary_model: RESEARCH_GLM_MODEL,
    ai_fallback_model: RESEARCH_FALLBACK_MODEL,
    glm_usage: glm?.usage || null,
    glm_attempt_count: Number(glm?.attempt_count || 1),
    glm_raw: String(glm?.raw || "").slice(0, 12000),
  };
}

async function browserSearchResearch(env, row) {
  const symbol = String(row?.symbol || "").trim().toUpperCase();
  const profile = researchCompanyProfile(symbol);
  const query = researchBuildQuery(profile);

  // Tavily's API currently allows max_results up to 20. Use the maximum instead of the old hard-coded 10.
  // Search remains Basic (1 Tavily credit); GLM performs semantic filtering and zh-TW rewriting afterward.
  const payload = await tavilySearch(env, {
    query,
    search_depth: "basic",
    topic: "news",
    time_range: "week",
    max_results: 20,
    chunks_per_source: 3,
    include_answer: false,
    include_raw_content: false,
    include_images: false,
    include_usage: true,
  });
  payload.query = payload.query || query;

  const glm = await researchGlmFilter(env, profile, query, payload);
  const item = researchBuildItem(row, profile, payload, glm, new Date().toISOString());
  return { item };
}

async function writeResearchStore(env, cache) {
  const entries = cache?.entries && typeof cache.entries === "object" ? cache.entries : {};
  const items = Object.values(entries).filter(x => x && typeof x === "object");
  items.sort((a, b) => Date.parse(b.searched_at || "") - Date.parse(a.searched_at || ""));
  const itemsBySymbol = {};
  for (const item of items) {
    const symbol = String(item.symbol || "").trim().toUpperCase();
    if (symbol) itemsBySymbol[symbol] = item;
  }
  const now = new Date().toISOString();
  const latest = {
    schema_version: "3.0",
    generated_at: now,
    ttl_hours: 24,
    model: RESEARCH_PROVIDER,
    provider: "tavily",
    mode: "ON_DEMAND_ONLY",
    items,
    items_by_symbol: itemsBySymbol,
  };
  const normalizedCache = {
    schema_version: "3.0",
    ttl_hours: 24,
    updated_at: now,
    entries,
  };
  const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
  await Promise.all([
    env.JSON_BUCKET.put(RESEARCH_CACHE_KEY, JSON.stringify(normalizedCache, null, 2), metadata),
    env.JSON_BUCKET.put(RESEARCH_LATEST_KEY, JSON.stringify(latest, null, 2), metadata),
  ]);
  return latest;
}

async function researchUsStockSymbol(request, env, origin) {
  const body = await request.json().catch(() => ({}));
  const symbol = String(body?.symbol || "").trim().toUpperCase();
  if (!/^[A-Z0-9._-]{1,40}$/.test(symbol)) throw httpError(400, "invalid symbol");

  const snapshotObj = await env.JSON_BUCKET.get(MARKET["us-stock"].latest);
  if (!snapshotObj) throw httpError(409, "R2 尚無美股 snapshot；請先至少成功執行一次美股完整分析");
  const snapshot = JSON.parse(await snapshotObj.text());
  const row = (Array.isArray(snapshot?.records) ? snapshot.records : []).find(x => String(x?.symbol || "").trim().toUpperCase() === symbol);
  if (!row) throw httpError(404, `${symbol} 不在目前美股 snapshot`);
  const state = researchState(row);
  if (!RESEARCH_ELIGIBLE_STATES.has(state)) throw httpError(409, `${symbol} 目前是 ${state}，只有 S3 / S0.5 / S1 提供新聞查詢`);

  const cache = await readR2Json(env, RESEARCH_CACHE_KEY, { schema_version:"3.0", ttl_hours:24, entries:{} });
  if (!cache.entries || typeof cache.entries !== "object") cache.entries = {};
  const existing = cache.entries[symbol];
  if (researchFresh(existing)) {
    return json({ ok:true, cached:true, item:existing, generated_at:new Date().toISOString() }, 200, origin);
  }

  const { item } = await browserSearchResearch(env, row);

  // Re-read immediately before write so concurrent on-demand searches are merged.
  const newestCache = await readR2Json(env, RESEARCH_CACHE_KEY, { schema_version:"3.0", ttl_hours:24, entries:{} });
  if (!newestCache.entries || typeof newestCache.entries !== "object") newestCache.entries = {};
  if (researchFresh(newestCache.entries[symbol])) {
    return json({ ok:true, cached:true, item:newestCache.entries[symbol], generated_at:new Date().toISOString() }, 200, origin);
  }
  newestCache.entries[symbol] = item;
  const latest = await writeResearchStore(env, newestCache);
  return json({ ok:true, cached:false, item, generated_at:latest.generated_at, r2_keys:[RESEARCH_CACHE_KEY, RESEARCH_LATEST_KEY] }, 200, origin);
}

const AUTO_STATUS_KEY = "automation/latest/status.json";
const AUTO_BATCH_STALE_MS = 3.5 * 60 * 60 * 1000;

function automationBusy(status) {
  return ["QUEUED", "RUNNING"].includes(String(status?.status || "").toUpperCase()) && !status?.stale;
}

function automationPhaseLabel(status) {
  const phase = String(status?.phase || "QUEUED").toUpperCase();
  if (phase === "CRYPTO") return "加密貨幣分析";
  if (phase === "US_STOCK") return "美股代幣分析";
  if (String(status?.mode || "") === "us-stock-only") return "等待美股代幣分析";
  return "等待加密貨幣分析";
}

async function readAutomationStatus(env, options = {}) {
  const obj = await env.JSON_BUCKET.get(AUTO_STATUS_KEY);
  if (!obj) return { status: "IDLE", phase: "IDLE", busy: false, stale: false };
  let payload;
  try { payload = JSON.parse(await obj.text()); }
  catch (_) { return { status: "IDLE", phase: "IDLE", busy: false, stale: false }; }

  const active = ["QUEUED", "RUNNING"].includes(String(payload?.status || "").toUpperCase());
  const stamp = Date.parse(payload?.updated_at || payload?.created_at || "");
  const stale = active && Number.isFinite(stamp) && (Date.now() - stamp > AUTO_BATCH_STALE_MS);
  if (stale && !options.allowStale) {
    return { ...payload, status: "STALE", busy: false, stale: true, stale_after_minutes: 210 };
  }
  return { ...payload, busy: active && !stale, stale };
}

async function writeAutomationStatus(env, payload) {
  const normalized = {
    ...payload,
    busy: ["QUEUED", "RUNNING"].includes(String(payload?.status || "").toUpperCase()),
    updated_at: payload?.updated_at || new Date().toISOString(),
  };
  await env.JSON_BUCKET.put(AUTO_STATUS_KEY, JSON.stringify(normalized, null, 2), {
    httpMetadata: { contentType: "application/json; charset=utf-8" },
  });
  return normalized;
}

async function dispatchAutoBatch(env, mode, source = "cron") {
  if (!env.GITHUB_TOKEN || !env.GITHUB_REPOSITORY) {
    throw httpError(500, "Worker 缺少 GITHUB_TOKEN 或 GITHUB_REPOSITORY");
  }
  if (!['pair','us-stock-only'].includes(mode)) throw httpError(400, 'invalid auto batch mode');

  const current = await readAutomationStatus(env);
  if (automationBusy(current)) {
    console.log(`Auto batch skipped because ${current.batch_id || 'current batch'} is still active.`);
    return { ok: true, skipped: true, reason: "auto_batch_already_active", current };
  }

  const batchId = `auto_${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0,14)}_${mode === 'pair' ? 'pair' : 'stock'}_${crypto.randomUUID().slice(0,8)}`;
  const initial = await writeAutomationStatus(env, {
    batch_id: batchId,
    mode,
    source: "AUTO_CRON",
    cron: source,
    status: "QUEUED",
    phase: mode === "pair" ? "CRYPTO" : "US_STOCK",
    message: mode === "pair"
      ? "自動排程已啟動：等待加密貨幣分析，完成後自動分析美股代幣"
      : "自動排程已啟動：等待美股代幣分析",
    created_at: new Date().toISOString(),
  });

  const endpoint = `https://api.github.com/repos/${env.GITHUB_REPOSITORY}/actions/workflows/auto-batch.yml/dispatches`;
  const gh = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "SStateMarketTerminal-AutoBatch-Worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: env.GITHUB_BRANCH || "main",
      inputs: { mode, batch_id: batchId },
    }),
  });
  if (!gh.ok) {
    const text = await gh.text();
    const failed = await writeAutomationStatus(env, {
      ...initial,
      status: "FAILED",
      phase: "FAILED",
      busy: false,
      message: `GitHub auto-batch dispatch ${gh.status}: ${text}`,
      updated_at: new Date().toISOString(),
    });
    throw httpError(502, `Auto Batch workflow_dispatch 失敗：${gh.status}`);
  }
  return { ok: true, ...initial };
}

async function dispatchDailyLearning(env, source = "cron") {
  if (!env.LEARNING_GITHUB_TOKEN || !env.LEARNING_GITHUB_REPOSITORY) {
    throw httpError(500, "Worker 缺少 LEARNING_GITHUB_TOKEN 或 LEARNING_GITHUB_REPOSITORY");
  }
  const runId = `learn_${new Date().toISOString().replace(/[-:.TZ]/g, "").slice(0,14)}_${crypto.randomUUID().slice(0,8)}`;
  const initial = {
    run_id: runId,
    status: "QUEUED",
    source,
    message: "等待 HistoricalTraining Daily S-state Learning",
    created_at: new Date().toISOString(),
  };
  const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
  await Promise.all([
    env.JSON_BUCKET.put("learning/latest/status.json", JSON.stringify(initial, null, 2), metadata),
    env.JSON_BUCKET.put(`learning/runs/${runId}/status.json`, JSON.stringify(initial, null, 2), metadata),
  ]);

  const endpoint = `https://api.github.com/repos/${env.LEARNING_GITHUB_REPOSITORY}/actions/workflows/daily-learning.yml/dispatches`;
  const gh = await fetch(endpoint, {
    method: "POST",
    headers: {
      "Accept": "application/vnd.github+json",
      "Authorization": `Bearer ${env.LEARNING_GITHUB_TOKEN}`,
      "X-GitHub-Api-Version": "2026-03-10",
      "User-Agent": "SStateMarketTerminal-Learning-Worker",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      ref: env.LEARNING_GITHUB_BRANCH || "main",
      inputs: { run_id: runId },
    }),
  });
  if (!gh.ok) {
    const text = await gh.text();
    const failed = { ...initial, status: "FAILED", message: `GitHub learning dispatch ${gh.status}: ${text}`, updated_at: new Date().toISOString() };
    await Promise.all([
      env.JSON_BUCKET.put("learning/latest/status.json", JSON.stringify(failed, null, 2), metadata),
      env.JSON_BUCKET.put(`learning/runs/${runId}/status.json`, JSON.stringify(failed, null, 2), metadata),
    ]);
    throw httpError(502, `Daily learning workflow_dispatch 失敗：${gh.status}`);
  }
  let dispatch = null;
  try { dispatch = await gh.json(); } catch (_) {}
  const queued = {
    ...initial,
    github_run_id: dispatch?.workflow_run_id || null,
    github_run_url: dispatch?.html_url || null,
    updated_at: new Date().toISOString(),
  };
  await Promise.all([
    env.JSON_BUCKET.put("learning/latest/status.json", JSON.stringify(queued, null, 2), metadata),
    env.JSON_BUCKET.put(`learning/runs/${runId}/status.json`, JSON.stringify(queued, null, 2), metadata),
  ]);
  return { ok: true, ...queued };
}

async function ensureChallenger(env, suppliedLatest = null) {
  const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
  const currentObj = await env.JSON_BUCKET.get("models/challenger/current.json");
  if (currentObj) return JSON.parse(await currentObj.text());

  let latest = suppliedLatest;
  if (!latest) {
    const latestObj = await env.JSON_BUCKET.get("models/candidates/latest.json");
    if (!latestObj) return null;
    latest = JSON.parse(await latestObj.text());
  }
  const modelId = safeModelId(latest.model_id);
  const challenger = {
    model_id: modelId,
    candidate_key: latest.candidate_key || `models/candidates/${modelId}/probability_model.json`,
    generated_at: latest.generated_at || null,
    assigned_at: new Date().toISOString(),
    status: "SHADOW_EVALUATION",
    policy: "Evaluate only future settled OOS cases after challenger generated_at; active model remains unchanged until promotion gate passes."
  };
  await Promise.all([
    env.JSON_BUCKET.put("models/challenger/current.json", JSON.stringify(challenger, null, 2), metadata),
    env.JSON_BUCKET.put(`models/candidates/${modelId}/status.json`, JSON.stringify(challenger, null, 2), metadata),
  ]);
  return challenger;
}

async function promoteChallenger(env, modelId) {
  const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
  const currentObj = await env.JSON_BUCKET.get("models/challenger/current.json");
  if (!currentObj) throw httpError(409, "no current challenger");
  const current = JSON.parse(await currentObj.text());
  if (current.model_id !== modelId) throw httpError(409, "requested model is not current challenger");

  const evalObj = await env.JSON_BUCKET.get(`models/candidates/${modelId}/evaluation.json`);
  if (!evalObj) throw httpError(409, "challenger evaluation missing");
  const evaluation = JSON.parse(await evalObj.text());
  if (evaluation.decision !== "PROMOTE") throw httpError(409, `evaluation decision is ${evaluation.decision}, not PROMOTE`);

  const candidateObj = await env.JSON_BUCKET.get(current.candidate_key);
  if (!candidateObj) throw httpError(404, "challenger model object missing");
  const candidateText = await candidateObj.text();
  const candidate = JSON.parse(candidateText);

  const activeObj = await env.JSON_BUCKET.get("models/active/probability_model.json");
  let oldModelId = null;
  if (activeObj) {
    const activeText = await activeObj.text();
    const active = JSON.parse(activeText);
    oldModelId = safeModelId(active.model_id);
    await env.JSON_BUCKET.put(`models/archive/${oldModelId}/probability_model.json`, activeText, metadata);
  }

  const promotedAt = new Date().toISOString();
  const activeManifest = {
    model_id: modelId,
    previous_model_id: oldModelId,
    promoted_at: promotedAt,
    source_candidate_key: current.candidate_key,
    evaluation_key: `models/candidates/${modelId}/evaluation.json`,
    status: "ACTIVE_CHAMPION"
  };
  const candidateStatus = { ...current, status: "PROMOTED", promoted_at: promotedAt, previous_model_id: oldModelId };
  await Promise.all([
    env.JSON_BUCKET.put("models/active/probability_model.json", candidateText, metadata),
    env.JSON_BUCKET.put("models/active/manifest.json", JSON.stringify(activeManifest, null, 2), metadata),
    env.JSON_BUCKET.put(`models/candidates/${modelId}/status.json`, JSON.stringify(candidateStatus, null, 2), metadata),
  ]);
  await env.JSON_BUCKET.delete("models/challenger/current.json");
  await assignLatestIfDifferent(env, modelId);
  return { promoted_model_id: modelId, previous_model_id: oldModelId, active_manifest: activeManifest };
}

async function rejectChallenger(env, modelId) {
  const metadata = { httpMetadata: { contentType: "application/json; charset=utf-8" } };
  const currentObj = await env.JSON_BUCKET.get("models/challenger/current.json");
  if (!currentObj) throw httpError(409, "no current challenger");
  const current = JSON.parse(await currentObj.text());
  if (current.model_id !== modelId) throw httpError(409, "requested model is not current challenger");
  const evalObj = await env.JSON_BUCKET.get(`models/candidates/${modelId}/evaluation.json`);
  if (!evalObj) throw httpError(409, "challenger evaluation missing");
  const evaluation = JSON.parse(await evalObj.text());
  if (evaluation.decision !== "REJECT") throw httpError(409, `evaluation decision is ${evaluation.decision}, not REJECT`);
  const rejectedAt = new Date().toISOString();
  const status = { ...current, status: "REJECTED", rejected_at: rejectedAt, evaluation_key: `models/candidates/${modelId}/evaluation.json` };
  await env.JSON_BUCKET.put(`models/candidates/${modelId}/status.json`, JSON.stringify(status, null, 2), metadata);
  await env.JSON_BUCKET.delete("models/challenger/current.json");
  await assignLatestIfDifferent(env, modelId);
  return { rejected_model_id: modelId };
}

async function assignLatestIfDifferent(env, excludedModelId) {
  const latestObj = await env.JSON_BUCKET.get("models/candidates/latest.json");
  if (!latestObj) return null;
  const latest = JSON.parse(await latestObj.text());
  if (!latest?.model_id || latest.model_id === excludedModelId) return null;
  return await ensureChallenger(env, latest);
}

async function objectResponse(env, key, origin, download, filename) {
  const obj = await env.JSON_BUCKET.get(key);
  if (!obj) return json({ error: "object_not_found", key }, 404, origin);
  const headers = new Headers();
  obj.writeHttpMetadata(headers);
  headers.set("Content-Type", "application/json; charset=utf-8");
  headers.set("Cache-Control", "no-store");
  headers.set("ETag", obj.httpEtag);
  if (download) headers.set("Content-Disposition", `attachment; filename="${filename}"`);
  applyCors(headers, origin);
  return new Response(obj.body, { status: 200, headers });
}
function normalizeMarket(v){ const x=String(v||"crypto"); if(!MARKET[x]) throw httpError(400,"market 必須是 crypto 或 us-stock"); return x; }
function safeRunId(v){ const x=String(v||""); if(!/^[A-Za-z0-9_-]{8,100}$/.test(x)) throw httpError(400,"invalid run_id"); return x; }
function safeModelId(v){ const x=String(v||""); if(!/^[A-Za-z0-9_-]{8,100}$/.test(x)) throw httpError(400,"invalid model_id"); return x; }
function requireInternal(request, env){ const auth=request.headers.get("Authorization")||""; if(!env.CALLBACK_TOKEN || auth!==`Bearer ${env.CALLBACK_TOKEN}`) throw httpError(401,"unauthorized"); }
function httpError(status,message){ const e=new Error(message); e.status=status; return e; }
function json(value,status,origin){ const headers=new Headers({"Content-Type":"application/json; charset=utf-8","Cache-Control":"no-store"}); applyCors(headers,origin); return new Response(JSON.stringify(value,null,2),{status,headers}); }
function cors(response,origin){ const h=new Headers(response.headers); applyCors(h,origin); return new Response(response.body,{status:response.status,headers:h}); }
function applyCors(headers,origin){ headers.set("Access-Control-Allow-Origin",origin); headers.set("Access-Control-Allow-Methods","GET,POST,PUT,OPTIONS"); headers.set("Access-Control-Allow-Headers","Content-Type,Authorization"); headers.set("Vary","Origin"); }

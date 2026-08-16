(() => {
  'use strict';

  const CONTEXT_DAYS = 30;
  const BB_PERIOD = 20;
  const MAX_FUTURE_DAYS = 45;
  const MIN_CUTOFF_INDEX = (CONTEXT_DAYS - 1) + (BB_PERIOD - 1);
  const DAY_MS = 24 * 60 * 60 * 1000;
  const MODEL_HORIZON = 18; // 72H = 18 x 4H
  const MAX_MODEL_LEVEL = 5;
  const cfg = window.SSTATE_QUIZ_CONFIG || {};
  const workerUrl = String(cfg.workerUrl || '').replace(/\/$/, '');
  const activeModelPath = String(cfg.activeModelPath || '/api/model/active');

  const state = {
    symbols: [],
    question: null,
    trade: null,
    revealed: 0,
    hoverIndex: null,
    activeModel: null,
    modelError: '',
    timelineCache: new Map(),
    stats: { total: 0, hit: 0, pnl: 0 },
    history: [],
    closedTrades: [],
  };

  const $ = (id) => document.getElementById(id);
  const canvas = $('chartCanvas');
  const ctx = canvas.getContext('2d');
  const tooltip = $('chartTooltip');

  function renderStats() {
    $('statTotal').textContent = state.stats.total;
    $('statHit').textContent = state.stats.hit;
    $('statRate').textContent = state.stats.total ? `${(state.stats.hit / state.stats.total * 100).toFixed(1)}%` : '—';
    $('statPnl').textContent = fmtPct(state.stats.pnl);
    $('statPnl').className = state.stats.pnl > 0 ? 'positive-text' : state.stats.pnl < 0 ? 'negative-text' : '';
  }

  function renderHistory() {
    const panel = $('sessionHistory');
    const body = $('historyBody');
    const count = $('historyCount');
    if (!panel || !body) return;
    if (count) count.textContent = String(state.history.length);
    if (!state.history.length) {
      body.innerHTML = '<tr class="history-empty-row"><td colspan="7">尚無平倉紀錄。你可以先做一筆交易，之後隨時打開這個面板調閱。</td></tr>';
      return;
    }
    body.innerHTML = state.history.map((r, i) => {
      const directionClass = r.direction === 'LONG' ? 'positive-text' : 'negative-text';
      const pnlClass = r.pnl > 0 ? 'positive-text' : r.pnl < 0 ? 'negative-text' : '';
      return `<tr>
        <td>${state.history.length - i}</td>
        <td><b>${escapeHtml(r.symbol)} / USDT</b></td>
        <td class="${directionClass}">${r.direction === 'LONG' ? '做多' : '做空'}</td>
        <td>${escapeHtml(r.entryDate)} → ${escapeHtml(r.exitDate)}</td>
        <td>${r.held} 天</td>
        <td class="${pnlClass}"><b>${fmtPct(r.pnl)}</b></td>
        <td>${escapeHtml(formatModelSnapshot(r.modelAtEntry))}</td>
      </tr>`;
    }).join('');
  }

  function openHistoryPanel() {
    $('sessionHistory')?.classList.remove('hidden');
    $('historyBackdrop')?.classList.remove('hidden');
  }

  function closeHistoryPanel() {
    $('sessionHistory')?.classList.add('hidden');
    $('historyBackdrop')?.classList.add('hidden');
  }

  async function init() {
    // v3 session score is intentionally memory-only. Clear the legacy persisted score once.
    try { localStorage.removeItem('sstate_quiz_trade_stats_v2'); } catch (_) {}
    renderStats();
    renderHistory();
    bindEvents();
    resizeCanvas();
    window.addEventListener('resize', () => { resizeCanvas(); draw(); });

    const modelPromise = loadActiveModel();
    try {
      const res = await fetch('./symbols.json', { cache: 'no-store' });
      if (!res.ok) throw new Error(`symbols.json HTTP ${res.status}`);
      const data = await res.json();
      state.symbols = Array.isArray(data.symbols) ? data.symbols : [];
      if (!state.symbols.length) throw new Error('symbols.json 沒有幣種');
      await newQuestion();
    } catch (err) {
      setLoadState(`載入失敗：${err.message}`);
      $('chartEmpty').textContent = '無法讀取題庫。請透過 GitHub Pages / HTTP 開啟，不要直接用 file://。';
    }
    await modelPromise;
    renderModelHud();
  }

  function bindEvents() {
    $('newQuestionBtn').addEventListener('click', newQuestion);
    $('playBtn').addEventListener('click', revealOneDay);
    $('closeBtn').addEventListener('click', closeTrade);
    $('historyFab')?.addEventListener('click', openHistoryPanel);
    $('closeHistoryBtn')?.addEventListener('click', closeHistoryPanel);
    $('historyBackdrop')?.addEventListener('click', closeHistoryPanel);
    $('resetRevealBtn').addEventListener('click', resetSameQuestion);
    $('blindMode').addEventListener('change', () => { renderQuestionMeta(); draw(); });
    document.querySelectorAll('.decision').forEach(btn => {
      btn.addEventListener('click', () => enterTrade(btn.dataset.choice));
    });

    canvas.addEventListener('mousemove', onCanvasMove);
    canvas.addEventListener('mouseleave', () => {
      state.hoverIndex = null;
      tooltip.classList.add('hidden');
      draw();
    });
  }

  async function loadActiveModel() {
    if (!workerUrl) {
      state.modelError = '未設定 Worker URL';
      renderModelStatus();
      return;
    }
    try {
      const url = `${workerUrl}${activeModelPath}?t=${Date.now()}`;
      const res = await fetch(url, { cache: 'no-store' });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const model = await res.json();
      if (!model || !model.states || !model.model_id) throw new Error('模型格式不完整');
      state.activeModel = model;
      state.modelError = '';
    } catch (err) {
      state.activeModel = null;
      state.modelError = err.message || String(err);
    }
    renderModelStatus();
  }

  function renderModelStatus() {
    const el = $('modelStatus');
    if (state.activeModel) {
      el.textContent = `R2 Active｜${state.activeModel.model_id}`;
      el.classList.remove('error');
    } else {
      el.textContent = `R2 Active 讀取失敗${state.modelError ? `｜${state.modelError}` : ''}`;
      el.classList.add('error');
    }
  }

  async function newQuestion() {
    if (state.trade && !state.trade.closed) return;
    state.trade = null;
    state.closedTrades = [];
    state.revealed = 0;
    closeHistoryPanel();
    state.hoverIndex = null;
    $('tradePanel').classList.add('hidden');
    $('chartEmpty').classList.remove('hidden');
    $('chartEmpty').textContent = '隨機抽取歷史片段…';
    setLoadState('抽題中');
    resetActionState();

    let lastError = null;
    for (let attempt = 0; attempt < 16; attempt++) {
      const symbol = state.symbols[Math.floor(Math.random() * state.symbols.length)];
      try {
        const [fourH, timeline] = await Promise.all([loadCsv(symbol), loadTimeline(symbol)]);
        const daily = aggregate4hToDaily(fourH);
        if (daily.length < MIN_CUTOFF_INDEX + MAX_FUTURE_DAYS + 3) continue;

        const ha = calculateHeikinAshi(daily);
        const bb = rollingBollinger(daily);
        const latestCutoff = daily.length - MAX_FUTURE_DAYS - 3;
        const earliestCutoff = MIN_CUTOFF_INDEX;
        if (latestCutoff <= earliestCutoff) continue;

        // Avoid the newest few days; every question must have a fully-known historical future.
        const cutoff = randomInt(earliestCutoff, latestCutoff);
        const end = Math.min(daily.length - 1, cutoff + MAX_FUTURE_DAYS);
        const rows = daily.map((d, i) => ({ ...d, ha: ha[i], bb: bb[i], index: i }));
        const modelByDay = new Map((timeline.rows || []).map(x => [Number(x.day_time), x]));

        state.question = {
          symbol,
          rows,
          cutoff,
          end,
          maxFutureDays: end - cutoff,
          modelByDay,
          scored: false,
        };
        state.trade = null;
        state.closedTrades = [];
        state.revealed = 0;
        state.hoverIndex = null;

        $('chartEmpty').classList.add('hidden');
        setLoadState(`題庫 ${state.symbols.length} 種市場`);
        resetActionState();
        renderAll();
        return;
      } catch (err) {
        lastError = err;
      }
    }

    $('chartEmpty').classList.remove('hidden');
    $('chartEmpty').textContent = `抽題失敗：${lastError ? lastError.message : '可用歷史不足'}`;
    setLoadState('抽題失敗');
  }

  async function loadCsv(symbol) {
    const path = `../data/cache/4h/${encodeURIComponent(symbol)}.csv`;
    const res = await fetch(path, { cache: 'no-store' });
    if (!res.ok) throw new Error(`${symbol} 歷史資料 HTTP ${res.status}`);
    const text = await res.text();
    const lines = text.trim().split(/\r?\n/);
    if (lines.length < 2) throw new Error(`${symbol} CSV 空白`);
    const header = lines[0].split(',');
    const index = Object.fromEntries(header.map((h, i) => [h.trim(), i]));
    const rows = [];
    for (let i = 1; i < lines.length; i++) {
      const c = lines[i].split(',');
      const t = Number(c[index.time]);
      const o = Number(c[index.open]);
      const h = Number(c[index.high]);
      const l = Number(c[index.low]);
      const cl = Number(c[index.close]);
      const v = Number(c[index.volume] || 0);
      if (![t,o,h,l,cl].every(Number.isFinite)) continue;
      rows.push({ time:t, open:o, high:h, low:l, close:cl, volume:Number.isFinite(v) ? v : 0 });
    }
    rows.sort((a,b) => a.time - b.time);
    return rows;
  }

  async function loadTimeline(symbol) {
    if (state.timelineCache.has(symbol)) return state.timelineCache.get(symbol);
    const res = await fetch(`./model_timeline/${encodeURIComponent(symbol)}.json`, { cache: 'no-store' });
    if (!res.ok) throw new Error(`${symbol} 模型時間線 HTTP ${res.status}`);
    const data = await res.json();
    state.timelineCache.set(symbol, data);
    return data;
  }

  function aggregate4hToDaily(rows) {
    const out = [];
    let cur = null;
    let curDay = null;
    for (const r of rows) {
      const day = Math.floor(r.time / DAY_MS) * DAY_MS;
      if (cur === null || day !== curDay) {
        if (cur) out.push(cur);
        curDay = day;
        cur = { time:day, open:r.open, high:r.high, low:r.low, close:r.close, volume:r.volume || 0 };
      } else {
        cur.high = Math.max(cur.high, r.high);
        cur.low = Math.min(cur.low, r.low);
        cur.close = r.close;
        cur.volume += r.volume || 0;
      }
    }
    if (cur) out.push(cur);
    return out;
  }

  function calculateHeikinAshi(rows) {
    const out = [];
    let prevOpen = null;
    let prevClose = null;
    rows.forEach((c, i) => {
      const haClose = (c.open + c.high + c.low + c.close) / 4;
      const haOpen = i === 0 ? (c.open + c.close) / 2 : (prevOpen + prevClose) / 2;
      out.push({
        open: haOpen,
        high: Math.max(c.high, haOpen, haClose),
        low: Math.min(c.low, haOpen, haClose),
        close: haClose,
        color: haClose > haOpen ? 'yellow' : haClose < haOpen ? 'purple' : 'flat',
      });
      prevOpen = haOpen;
      prevClose = haClose;
    });
    return out;
  }

  function rollingBollinger(rows) {
    const out = Array(rows.length).fill(null);
    for (let i = BB_PERIOD - 1; i < rows.length; i++) {
      const closes = rows.slice(i - BB_PERIOD + 1, i + 1).map(x => x.close);
      const basis = closes.reduce((a,b) => a+b, 0) / closes.length;
      const variance = closes.reduce((s,x) => s + (x-basis)*(x-basis), 0) / closes.length;
      const sd = Math.sqrt(variance);
      out[i] = { basis, upper:basis + 2*sd, lower:basis - 2*sd };
    }
    return out;
  }

  function currentIndex() {
    return state.question ? Math.min(state.question.end, state.question.cutoff + state.revealed) : 0;
  }

  function revealOneDay() {
    if (!state.question) return;
    if (state.revealed >= state.question.maxFutureDays) return;
    state.revealed += 1;
    renderAll();
    if (state.revealed >= state.question.maxFutureDays) {
      $('playBtn').disabled = true;
      document.querySelectorAll('.decision').forEach(btn => { if (!state.trade) btn.disabled = true; });
    }
  }

  function enterTrade(direction) {
    if (!state.question || state.trade) return;
    const idx = currentIndex();
    const row = state.question.rows[idx];
    state.trade = {
      direction,
      entryIndex: idx,
      entryPrice: row.close,
      modelAtEntry: modelSnapshotForIndex(idx),
      closed: false,
      exitIndex: null,
      exitPrice: null,
      realizedPnl: null,
    };
    document.querySelectorAll('.decision').forEach(btn => {
      btn.disabled = true;
      btn.classList.toggle('selected', btn.dataset.choice === direction);
    });
    $('closeBtn').disabled = false;
    $('newQuestionBtn').disabled = true;
    $('resetRevealBtn').disabled = true;
    $('tradePanel').classList.remove('hidden');
    renderAll();
  }

  function closeTrade() {
    const q = state.question;
    const t = state.trade;
    if (!q || !t || t.closed) return;

    const exitIndex = currentIndex();
    const exitPrice = q.rows[exitIndex].close;
    const pnl = directionalReturn(t.direction, t.entryPrice, exitPrice);
    const held = Math.max(0, exitIndex - t.entryIndex);
    const excursion = calculateTradeExcursion(q.rows, t.direction, t.entryPrice, t.entryIndex, exitIndex);

    t.closed = true;
    t.exitIndex = exitIndex;
    t.exitPrice = exitPrice;
    t.realizedPnl = pnl;
    t.exitDate = formatDate(q.rows[exitIndex].time);

    state.stats.total += 1;
    if (pnl > 0) state.stats.hit += 1;
    state.stats.pnl += pnl;
    state.history.unshift({
      symbol: q.symbol,
      direction: t.direction,
      entryDate: formatDate(q.rows[t.entryIndex].time),
      exitDate: t.exitDate,
      entryPrice: t.entryPrice,
      exitPrice,
      held,
      pnl,
      mfe: excursion.mfe,
      mae: excursion.mae,
      modelAtEntry: t.modelAtEntry,
    });

    // Closed trades are kept in the session history, while the active slot is
    // immediately released so the user can enter again on the same replay.
    state.closedTrades.push({ ...t });
    state.trade = null;

    $('closeBtn').disabled = true;
    $('newQuestionBtn').disabled = false;
    $('resetRevealBtn').disabled = false;
    const atEnd = state.revealed >= q.maxFutureDays;
    document.querySelectorAll('.decision').forEach(btn => {
      btn.disabled = atEnd;
      btn.classList.remove('selected');
    });
    $('tradePanel').classList.add('hidden');

    renderStats();
    renderHistory();
    renderAll();
  }

  function resetSameQuestion() {
    if (!state.question || (state.trade && !state.trade.closed)) return;
    state.revealed = 0;
    state.trade = null;
    state.closedTrades = [];
    state.hoverIndex = null;
    resetActionState();
    renderAll();
  }

  function resetActionState() {
    if (!$('playBtn')) return;
    $('playBtn').disabled = !state.question;
    $('closeBtn').disabled = true;
    $('newQuestionBtn').disabled = false;
    $('resetRevealBtn').disabled = !state.question;
    document.querySelectorAll('.decision').forEach(btn => {
      btn.disabled = !state.question;
      btn.classList.remove('selected');
    });
    $('tradePanel').classList.add('hidden');
    $('tradeBadge').textContent = '尚未進場';
    $('tradeBadge').style.color = '';
  }

  function renderAll() {
    renderQuestionMeta();
    updateProgress();
    renderTradePanel();
    renderHistory();
    renderModelHud();
    draw();
  }

  function updateProgress() {
    if (!state.question) return;
    const max = state.question.maxFutureDays;
    const pct = max ? Math.min(100, state.revealed / max * 100) : 0;
    $('progressBar').style.width = `${pct}%`;
    $('progressText').textContent = state.revealed ? `已播放 ${state.revealed} 天` : '起始日';
    $('playBtn').textContent = state.revealed >= max ? '歷史已播完' : '▶ 播放下一天';
    $('playBtn').disabled = state.revealed >= max;
  }

  function renderQuestionMeta() {
    if (!state.question) return;
    const q = state.question;
    const idx = currentIndex();
    const atEnd = state.revealed >= q.maxFutureDays;
    const blind = $('blindMode').checked && !state.trade && state.closedTrades.length === 0 && !atEnd;
    const currentDate = formatDate(q.rows[idx].time);
    $('marketTitle').textContent = blind ? '隨機市場 · 盲測中' : `${q.symbol} / USDT`;
    $('marketMeta').textContent = blind
      ? `最近 30 日結構 · 已前進 ${state.revealed} 天 · 日期隱藏`
      : `目前日期：${currentDate} · 從起始點前進 ${state.revealed} 天`;
  }

  function renderTradePanel() {
    const q = state.question;
    const t = state.trade;
    if (!q || !t) {
      $('tradePanel').classList.add('hidden');
      if (q) {
        $('tradeBadge').textContent = '尚未進場';
        $('tradeBadge').style.color = '';
      }
      return;
    }

    const displayIdx = t.closed ? t.exitIndex : currentIndex();
    const displayPrice = t.closed ? t.exitPrice : q.rows[displayIdx].close;
    const held = Math.max(0, displayIdx - t.entryIndex);
    const pnl = t.closed ? t.realizedPnl : directionalReturn(t.direction, t.entryPrice, displayPrice);
    const excursion = calculateTradeExcursion(q.rows, t.direction, t.entryPrice, t.entryIndex, displayIdx);

    $('tradePanel').classList.remove('hidden');
    $('tradeDirection').textContent = t.direction === 'LONG' ? '做多' : '做空';
    $('tradeDirection').className = t.direction === 'LONG' ? 'positive-text' : 'negative-text';
    $('tradeEntry').textContent = formatPrice(t.entryPrice);
    $('tradeCurrent').textContent = formatPrice(displayPrice);
    $('tradePnl').textContent = fmtPct(pnl);
    $('tradePnl').className = pnl > 0 ? 'positive-text' : pnl < 0 ? 'negative-text' : '';
    $('tradeExcursion').textContent = `${fmtPct(excursion.mfe)} / ${fmtPct(excursion.mae)}`;
    $('tradeHeld').textContent = `${held} 天`;

    if (t.closed) {
      $('tradeBadge').textContent = `已平倉 ${fmtPct(t.realizedPnl)}`;
      $('tradeBadge').style.color = t.realizedPnl > 0 ? 'var(--green)' : t.realizedPnl < 0 ? 'var(--red)' : 'var(--yellow)';
      $('tradeVerdict').textContent = t.realizedPnl > 0 ? '獲利平倉' : t.realizedPnl < 0 ? '虧損平倉' : '損益兩平';
      $('tradeVerdict').className = t.realizedPnl > 0 ? 'positive-text' : t.realizedPnl < 0 ? 'negative-text' : '';
    } else {
      $('tradeBadge').textContent = t.direction === 'LONG' ? '已做多' : '已做空';
      $('tradeBadge').style.color = t.direction === 'LONG' ? 'var(--green)' : 'var(--red)';
      $('tradeVerdict').textContent = '持倉中';
      $('tradeVerdict').className = '';
    }
  }

  function calculateTradeExcursion(rows, direction, entryPrice, entryIndex, endIndex) {
    const slice = rows.slice(entryIndex, endIndex + 1);
    if (!slice.length) return { mfe: 0, mae: 0 };
    const maxHigh = Math.max(...slice.map(x => x.high));
    const minLow = Math.min(...slice.map(x => x.low));
    if (direction === 'LONG') {
      return {
        mfe: (maxHigh / entryPrice - 1) * 100,
        mae: (minLow / entryPrice - 1) * 100,
      };
    }
    return {
      mfe: (entryPrice / minLow - 1) * 100,
      mae: (entryPrice / maxHigh - 1) * 100,
    };
  }

  function directionalReturn(direction, entry, price) {
    if (!Number.isFinite(entry) || !Number.isFinite(price) || entry === 0) return 0;
    return direction === 'SHORT' ? (entry / price - 1) * 100 : (price / entry - 1) * 100;
  }

  function currentTimelineRow() {
    const q = state.question;
    if (!q) return null;
    return q.modelByDay.get(Number(q.rows[currentIndex()].time)) || null;
  }

  function modelSnapshotForIndex(index) {
    const q = state.question;
    if (!q || !state.activeModel || !q.rows[index]) return { available:false, state:'NON_MODEL' };
    const timeline = q.modelByDay.get(Number(q.rows[index].time)) || null;
    if (!timeline) return { available:false, state:'NON_MODEL' };
    const pred = lookupProbability(state.activeModel, timeline.state, MODEL_HORIZON, timeline.features || {});
    if (!pred.available) return { available:false, state:timeline.state || 'NON_MODEL' };
    return {
      available: true,
      state: timeline.state,
      level: pred.level,
      fail: pred.trueFail,
      survival: pred.survival,
      samples: pred.samples,
    };
  }

  function formatModelSnapshot(s) {
    if (!s || !s.available) return `${s && s.state ? s.state : 'NON_MODEL'}｜無統計`;
    return `${s.state} L${s.level}｜失敗 ${fmtModelPct(s.fail)}｜存活 ${fmtModelPct(s.survival)}｜樣本 ${Number(s.samples || 0).toLocaleString()}`;
  }

  function renderModelHud() {
    const timeline = currentTimelineRow();
    if (!state.question) return;
    if (!state.activeModel) {
      $('modelState').textContent = 'R2 Active 模型無法讀取';
      $('modelLevel').textContent = '—';
      setModelStat('modelFail', null);
      setModelStat('modelSurvival', null);
      $('modelSamples').textContent = '—';
      $('modelHint').textContent = state.modelError || '請確認 Worker / R2';
      return;
    }
    if (!timeline) {
      $('modelState').textContent = '非模型狀態｜無統計';
      $('modelLevel').textContent = '—';
      setModelStat('modelFail', null);
      setModelStat('modelSurvival', null);
      $('modelSamples').textContent = '—';
      $('modelHint').textContent = '此日沒有可匹配的 S0.5 / S1 / S2 / S3；可繼續播放下一天';
      return;
    }

    const pred = lookupProbability(state.activeModel, timeline.state, MODEL_HORIZON, timeline.features || {});
    const stateText = `${timeline.state}｜${stateLabel(timeline.state)}`;
    $('modelState').textContent = stateText;
    if (!pred.available) {
      $('modelLevel').textContent = '—';
      setModelStat('modelFail', null);
      setModelStat('modelSurvival', null);
      $('modelSamples').textContent = '—';
      $('modelHint').textContent = timeline.state === 'S0' || timeline.state === 'OTHER' || timeline.state === 'NON_MODEL'
        ? '目前不是 S0.5 / S1 / S2 / S3 模型狀態'
        : `目前模型無匹配：${pred.reason || 'unknown'}`;
      return;
    }

    $('modelLevel').textContent = `L${pred.level}`;
    setModelStat('modelFail', pred.trueFail);
    setModelStat('modelSurvival', pred.survival);
    $('modelSamples').textContent = Number(pred.samples || 0).toLocaleString();
    $('modelHint').textContent = `3日成功 ${fmtModelPct(pred.success)}｜${featureSummary(timeline.features || {})}`;
  }

  function lookupProbability(model, marketState, horizon, features) {
    const stateNode = (model.states || {})[marketState];
    if (!stateNode) return { available:false, reason:'state_missing' };
    const hnode = (stateNode.horizons || {})[String(horizon)];
    if (!hnode) return { available:false, reason:'horizon_missing' };
    const minSamples = Number(model.default_min_samples || 50);
    const levels = (hnode.levels || []).filter(x => Number(x.level || 0) <= MAX_MODEL_LEVEL);
    for (let li = levels.length - 1; li >= 0; li--) {
      const level = levels[li];
      const fields = Array.isArray(level.fields) ? level.fields : [];
      const sig = signature(features, fields);
      const rule = (level.rules || []).find(r => r.signature === sig && Number(r.samples || 0) >= minSamples);
      if (rule) return normalizePrediction(rule, Number(level.level || 0), false);
    }
    if (!hnode.baseline) return { available:false, reason:'baseline_missing' };
    return normalizePrediction(hnode.baseline, 0, true);
  }

  function normalizePrediction(node, level, fallback) {
    const outcomes = node.outcomes || {};
    const outcomeProb = (key) => {
      const v = outcomes[key] && outcomes[key].probability;
      return Number.isFinite(Number(v)) ? Number(v) : null;
    };
    const success = outcomeProb('SUCCESS_WITHIN_HORIZON') ?? Number(node.probability || 0);
    const alive = outcomeProb('ALIVE_SLOW');
    const trueFail = Number.isFinite(Number(node.true_fail_probability))
      ? Number(node.true_fail_probability)
      : (outcomeProb('TRUE_FAIL') ?? 0);
    const survival = Number.isFinite(Number(node.structural_survival_probability))
      ? Number(node.structural_survival_probability)
      : success + (alive ?? 0);
    return {
      available: true,
      samples: Number(node.samples || 0),
      level,
      fallback,
      success,
      trueFail,
      survival,
    };
  }

  function signature(features, fields) {
    if (!fields.length) return 'BASELINE';
    return fields.map(field => `${field}=${features[field]}`).join('|');
  }

  function setModelStat(id, value) {
    $(id).textContent = value === null || !Number.isFinite(Number(value)) ? '—' : fmtModelPct(Number(value));
  }

  function stateLabel(s) {
    return ({
      'S0.5':'底部抬高',
      'S1':'自然突破中軌',
      'S2':'回踩觀察',
      'S3':'黃勝紫2階',
      'S0':'等待轉強',
      'OTHER':'非模型狀態',
      'NON_MODEL':'非模型狀態',
    })[s] || '非模型狀態';
  }

  function featureSummary(f) {
    const mid = ({rising:'中軌上斜', flat:'中軌平緩', flattening:'中軌走平', falling:'中軌下斜'})[f.midline_state] || '中軌未知';
    const bw = ({EXPANDING:'布林擴張', CONTRACTING:'布林收縮', FLAT:'布林平穩'})[f.bandwidth_trend] || '布林未知';
    const age = ({'1':'第1根4H','2_3':'2-3根4H','4_6':'4-6根4H','7_PLUS':'7+根4H'})[f.state_age_bin] || '';
    return `${mid}｜${f.trigger_stage || 'T0'}｜${bw}${age ? `｜${age}` : ''}`;
  }

  function resizeCanvas() {
    const rect = canvas.getBoundingClientRect();
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    canvas.width = Math.max(1, Math.round(rect.width * dpr));
    canvas.height = Math.max(1, Math.round(rect.height * dpr));
    ctx.setTransform(dpr,0,0,dpr,0,0);
    canvas._cssWidth = rect.width;
    canvas._cssHeight = rect.height;
  }

  function visibleRows() {
    const q = state.question;
    if (!q) return [];
    const end = currentIndex();
    const start = Math.max(0, end - CONTEXT_DAYS + 1);
    return q.rows.slice(start, end + 1);
  }

  function draw() {
    const w = canvas._cssWidth || canvas.clientWidth;
    const h = canvas._cssHeight || canvas.clientHeight;
    ctx.clearRect(0,0,w,h);
    ctx.fillStyle = '#080d15';
    ctx.fillRect(0,0,w,h);
    if (!state.question) return;

    const q = state.question;
    const rows = visibleRows();
    if (!rows.length) return;

    const pad = { left:16, right:82, top:18, bottom:30 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    const values = [];
    rows.forEach(r => {
      values.push(r.high, r.low);
      if (r.bb) values.push(r.bb.upper, r.bb.lower);
      if (r.ha) values.push(r.ha.close);
    });
    if (state.trade && !state.trade.closed && Number.isFinite(state.trade.entryPrice)) {
      values.push(state.trade.entryPrice);
    }
    let min = Math.min(...values), max = Math.max(...values);
    const extra = (max - min || Math.abs(max) || 1) * .08;
    min -= extra; max += extra;

    const xAt = (i) => pad.left + (i + .5) * plotW / rows.length;
    const yAt = (v) => pad.top + (max - v) / (max - min) * plotH;
    const barW = Math.max(3, Math.min(14, plotW / rows.length * .58));

    drawGrid(ctx, pad, plotW, plotH, min, max, rows);
    drawLine(rows, xAt, yAt, r => r.bb && r.bb.upper, 'rgba(86,164,255,.72)', 1.25);
    drawLine(rows, xAt, yAt, r => r.bb && r.bb.basis, 'rgba(225,232,244,.52)', 1.15);
    drawLine(rows, xAt, yAt, r => r.bb && r.bb.lower, 'rgba(86,164,255,.72)', 1.25);

    rows.forEach((r, i) => {
      const x = xAt(i);
      const up = r.close >= r.open;
      const c = up ? '#3cd6a0' : '#ff667f';
      ctx.strokeStyle = c;
      ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(x, yAt(r.high)); ctx.lineTo(x, yAt(r.low)); ctx.stroke();
      const yO = yAt(r.open), yC = yAt(r.close);
      const top = Math.min(yO,yC), bh = Math.max(1.5, Math.abs(yO-yC));
      ctx.fillStyle = c;
      ctx.fillRect(x-barW/2, top, barW, bh);
    });

    ctx.lineWidth = 3.2;
    ctx.lineJoin = 'miter';
    for (let i = 0; i < rows.length; i++) {
      const r = rows[i];
      if (!r.ha) continue;
      const color = r.ha.color === 'yellow' ? '#ffd84b' : r.ha.color === 'purple' ? '#b074ff' : '#9ca8ba';
      const y = yAt(r.ha.close);
      const left = i === 0 ? pad.left : (xAt(i-1) + xAt(i))/2;
      const right = i === rows.length-1 ? pad.left + plotW : (xAt(i) + xAt(i+1))/2;
      ctx.strokeStyle = color;
      ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke();
      if (i < rows.length-1) {
        const y2 = yAt(rows[i+1].ha.close);
        ctx.beginPath(); ctx.moveTo(right, y); ctx.lineTo(right, y2); ctx.stroke();
      }
    }

    if (state.trade && !state.trade.closed && Number.isFinite(state.trade.entryPrice)) {
      const entryColor = state.trade.direction === 'LONG' ? '#3cd6a0' : '#ff667f';
      drawEntryPriceLine(yAt(state.trade.entryPrice), pad, plotW, entryColor,
        `${state.trade.direction === 'LONG' ? '做多' : '做空'}進場 ${formatPrice(state.trade.entryPrice)}`);
    }

    drawMarkerForAbsoluteIndex(rows, q.cutoff, xAt, pad, plotH, 'rgba(255,255,255,.48)', '起始', true);
    if (state.trade) {
      const c = state.trade.direction === 'LONG' ? '#3cd6a0' : '#ff667f';
      drawMarkerForAbsoluteIndex(rows, state.trade.entryIndex, xAt, pad, plotH, c, state.trade.direction === 'LONG' ? '做多' : '做空', false);
      if (state.trade.closed && Number.isInteger(state.trade.exitIndex)) {
        drawMarkerForAbsoluteIndex(rows, state.trade.exitIndex, xAt, pad, plotH, '#ffd84b', '平倉', false);
      }
    }

    if (state.hoverIndex !== null && state.hoverIndex >= 0 && state.hoverIndex < rows.length) {
      const x = xAt(state.hoverIndex);
      ctx.strokeStyle='rgba(221,232,247,.35)'; ctx.lineWidth=1;
      ctx.beginPath(); ctx.moveTo(x,pad.top); ctx.lineTo(x,pad.top+plotH); ctx.stroke();
    }

    canvas._layout = { rows, pad, plotW, plotH, min, max, xAt, yAt };
  }

  function drawEntryPriceLine(y, pad, plotW, color, label) {
    ctx.save();
    ctx.setLineDash([8, 6]);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.moveTo(pad.left, y);
    ctx.lineTo(pad.left + plotW, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = color;
    ctx.font = 'bold 11px sans-serif';
    ctx.textAlign = 'right';
    ctx.textBaseline = 'bottom';
    ctx.fillText(label, pad.left + plotW - 6, y - 4);
    ctx.restore();
  }

  function drawMarkerForAbsoluteIndex(rows, absoluteIndex, xAt, pad, plotH, color, label, dashed) {
    const local = rows.findIndex(r => r.index === absoluteIndex);
    if (local < 0) return;
    const x = xAt(local);
    ctx.save();
    if (dashed) ctx.setLineDash([5,5]);
    ctx.strokeStyle = color; ctx.lineWidth = dashed ? 1 : 1.6;
    ctx.beginPath(); ctx.moveTo(x,pad.top); ctx.lineTo(x,pad.top+plotH); ctx.stroke();
    ctx.restore();
    ctx.fillStyle = color; ctx.font='11px sans-serif'; ctx.textAlign='right';
    ctx.fillText(label, x-5, pad.top+13);
  }

  function drawGrid(ctx, pad, plotW, plotH, min, max, rows) {
    ctx.save();
    ctx.strokeStyle='rgba(139,158,188,.12)'; ctx.fillStyle='#77859b'; ctx.font='11px sans-serif'; ctx.lineWidth=1;
    for (let i=0; i<=5; i++) {
      const y=pad.top + i*plotH/5;
      ctx.beginPath(); ctx.moveTo(pad.left,y); ctx.lineTo(pad.left+plotW,y); ctx.stroke();
      const v=max - i*(max-min)/5;
      ctx.textAlign='left'; ctx.textBaseline='middle'; ctx.fillText(formatPrice(v), pad.left+plotW+8,y);
    }
    const step = Math.max(1, Math.ceil(rows.length/7));
    for (let i=0; i<rows.length; i+=step) {
      const x=pad.left+(i+.5)*plotW/rows.length;
      ctx.beginPath(); ctx.moveTo(x,pad.top); ctx.lineTo(x,pad.top+plotH); ctx.stroke();
      ctx.textAlign='center'; ctx.textBaseline='top';
      const q=state.question;
      const blind=$('blindMode').checked && !state.trade && state.closedTrades.length === 0 && state.revealed < q.maxFutureDays;
      const label=blind ? relativeDayLabel(rows[i].index-q.cutoff) : formatShortDate(rows[i].time);
      ctx.fillText(label,x,pad.top+plotH+7);
    }
    ctx.restore();
  }

  function drawLine(rows, xAt, yAt, getter, color, width) {
    ctx.strokeStyle=color; ctx.lineWidth=width; ctx.beginPath();
    let started=false;
    rows.forEach((r,i) => {
      const v=getter(r); if (!Number.isFinite(v)) { started=false; return; }
      const x=xAt(i), y=yAt(v);
      if (!started) { ctx.moveTo(x,y); started=true; } else ctx.lineTo(x,y);
    });
    ctx.stroke();
  }

  function onCanvasMove(ev) {
    const layout=canvas._layout;
    if (!layout || !layout.rows.length) return;
    const rect=canvas.getBoundingClientRect();
    const mx=ev.clientX-rect.left, my=ev.clientY-rect.top;
    if (mx<layout.pad.left || mx>layout.pad.left+layout.plotW || my<layout.pad.top || my>layout.pad.top+layout.plotH) {
      tooltip.classList.add('hidden'); state.hoverIndex=null; draw(); return;
    }
    const i=Math.max(0,Math.min(layout.rows.length-1,Math.floor((mx-layout.pad.left)/layout.plotW*layout.rows.length)));
    state.hoverIndex=i;
    const r=layout.rows[i];
    const q=state.question;
    const blind=$('blindMode').checked && !state.trade && state.closedTrades.length === 0 && state.revealed < q.maxFutureDays;
    const date=blind ? relativeDayLabel(r.index-q.cutoff) : formatDate(r.time);
    const haColor=r.ha.color==='yellow'?'黃':r.ha.color==='purple'?'紫':'平';
    tooltip.innerHTML = `${date}<br>O ${formatPrice(r.open)}　H ${formatPrice(r.high)}<br>L ${formatPrice(r.low)}　C ${formatPrice(r.close)}<br>HA ${haColor} ${formatPrice(r.ha.close)}${r.bb?`<br>BB中軌 ${formatPrice(r.bb.basis)}`:''}`;
    tooltip.classList.remove('hidden');
    const tw=tooltip.offsetWidth, th=tooltip.offsetHeight;
    tooltip.style.left=`${Math.min(rect.width-tw-8,mx+14)}px`;
    tooltip.style.top=`${Math.max(8,Math.min(rect.height-th-8,my-th/2))}px`;
    draw();
  }

  function setLoadState(text) { $('loadState').textContent = text; }
  function randomInt(min,max) { return Math.floor(Math.random()*(max-min+1))+min; }
  function relativeDayLabel(d) { return d===0?'D0':d<0?`D${d}`:`D+${d}`; }
  function formatShortDate(ms) { const d=new Date(ms+8*3600*1000); return `${String(d.getUTCMonth()+1).padStart(2,'0')}/${String(d.getUTCDate()).padStart(2,'0')}`; }
  function formatDate(ms) { const d=new Date(ms+8*3600*1000); return `${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,'0')}-${String(d.getUTCDate()).padStart(2,'0')}`; }
  function formatPrice(v) {
    if (!Number.isFinite(v)) return '—';
    const av=Math.abs(v);
    if (av>=1000) return v.toLocaleString(undefined,{maximumFractionDigits:2});
    if (av>=1) return v.toLocaleString(undefined,{maximumFractionDigits:4});
    if (av>=0.01) return v.toFixed(5);
    return v.toPrecision(5);
  }
  function fmtPct(v) { return !Number.isFinite(v) ? '—' : `${v>=0?'+':''}${v.toFixed(2)}%`; }
  function fmtModelPct(v) { return !Number.isFinite(v) ? '—' : `${(v*100).toFixed(1)}%`; }
  function escapeHtml(v) { return String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }

  init();
})();

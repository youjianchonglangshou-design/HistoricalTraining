(() => {
  'use strict';

  const CONTEXT_DAYS = 30;
  const BB_PERIOD = 20;
  const MAX_FUTURE_DAYS = 45;
  const MIN_CUTOFF_INDEX = (CONTEXT_DAYS - 1) + (BB_PERIOD - 1);
  const DAY_MS = 24 * 60 * 60 * 1000;
  const MODEL_HORIZON = 18; // 72H = 18 x 4H
  const MAX_MODEL_LEVEL = 5;
  const DMI_AXIS = 20;
  const OUTCOME_SUCCESS = 'SUCCESS_WITHIN_HORIZON';
  const OUTCOME_ALIVE = 'ALIVE_SLOW';
  const OUTCOME_FAIL = 'TRUE_FAIL';
  const OUTCOME_OTHER = 'OTHER';
  const OUTCOME_KEYS = [OUTCOME_SUCCESS, OUTCOME_ALIVE, OUTCOME_FAIL, OUTCOME_OTHER];
  const DMI_QUANTILE_FIELDS = {
    di_abs_gap: 'di_abs_gap_q',
    di_axis_distance: 'di_axis_distance_q',
    di_plus_slope_3d: 'di_plus_slope_q',
    di_minus_slope_3d: 'di_minus_slope_q',
    di_gap_slope_3d: 'di_gap_slope_q',
    adx: 'adx_q',
    adx_slope_3d: 'adx_slope_q',
  };
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
    historyUi: { open: false, x: 12, y: 84, dragging: false, pointerId: null, startX: 0, startY: 0, originX: 12, originY: 84 },
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
    state.historyUi.open = true;
    const panel = $('sessionHistory');
    if (panel) panel.classList.remove('hidden');
    applyHistoryPanelPosition();
  }

  function closeHistoryPanel() {
    state.historyUi.open = false;
    $('sessionHistory')?.classList.add('hidden');
  }

  function initHistoryDrag() {
    const handle = $('historyDragHandle');
    const panel = $('sessionHistory');
    if (!handle || !panel) return;
    handle.addEventListener('pointerdown', onHistoryDragStart);
    window.addEventListener('pointermove', onHistoryDragMove);
    window.addEventListener('pointerup', onHistoryDragEnd);
    window.addEventListener('pointercancel', onHistoryDragEnd);
  }

  function onHistoryDragStart(ev) {
    if (ev.target && ev.target.closest('#closeHistoryBtn')) return;
    const panel = $('sessionHistory');
    if (!panel || panel.classList.contains('hidden')) return;
    state.historyUi.dragging = true;
    state.historyUi.pointerId = ev.pointerId;
    state.historyUi.startX = ev.clientX;
    state.historyUi.startY = ev.clientY;
    state.historyUi.originX = state.historyUi.x;
    state.historyUi.originY = state.historyUi.y;
    panel.classList.add('dragging');
    if (panel.setPointerCapture) { try { panel.setPointerCapture(ev.pointerId); } catch (_) {} }
    ev.preventDefault();
  }

  function onHistoryDragMove(ev) {
    if (!state.historyUi.dragging || ev.pointerId !== state.historyUi.pointerId) return;
    const dx = ev.clientX - state.historyUi.startX;
    const dy = ev.clientY - state.historyUi.startY;
    state.historyUi.x = state.historyUi.originX + dx;
    state.historyUi.y = state.historyUi.originY + dy;
    clampHistoryPanelPosition();
    applyHistoryPanelPosition();
  }

  function onHistoryDragEnd(ev) {
    if (!state.historyUi.dragging || (ev && ev.pointerId !== state.historyUi.pointerId)) return;
    state.historyUi.dragging = false;
    state.historyUi.pointerId = null;
    $('sessionHistory')?.classList.remove('dragging');
  }

  function clampHistoryPanelPosition() {
    const wrap = document.querySelector('.chart-wrap');
    const panel = $('sessionHistory');
    if (!wrap || !panel) return;
    const wrapRect = wrap.getBoundingClientRect();
    const maxX = Math.max(8, wrapRect.width - panel.offsetWidth - 8);
    const maxY = Math.max(46, wrapRect.height - panel.offsetHeight - 8);
    state.historyUi.x = Math.max(8, Math.min(maxX, state.historyUi.x));
    state.historyUi.y = Math.max(46, Math.min(maxY, state.historyUi.y));
  }

  function applyHistoryPanelPosition() {
    const panel = $('sessionHistory');
    if (!panel) return;
    clampHistoryPanelPosition();
    panel.style.left = `${Math.round(state.historyUi.x)}px`;
    panel.style.top = `${Math.round(state.historyUi.y)}px`;
  }

  async function init() {
    // v3 session score is intentionally memory-only. Clear the legacy persisted score once.
    try { localStorage.removeItem('sstate_quiz_trade_stats_v2'); } catch (_) {}
    renderStats();
    renderHistory();
    bindEvents();
    resizeCanvas();
    window.addEventListener('resize', () => { resizeCanvas(); applyHistoryPanelPosition(); draw(); });

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
    initHistoryDrag();
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
    state.historyUi.x = 12;
    state.historyUi.y = 84;
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
    if (state.historyUi.open) applyHistoryPanelPosition();
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
      dmiFacets: pred.dmiExpert ? Number(pred.dmiExpert.matchedFacetCount || 0) : 0,
      dmiVersion: pred.dmiExpert ? String(pred.dmiExpert.version || '') : '',
    };
  }

  function formatModelSnapshot(s) {
    if (!s || !s.available) return `${s && s.state ? s.state : 'NON_MODEL'}｜無統計`;
    const dmi = Number(s.dmiFacets || 0) > 0 ? `｜DMI×${Number(s.dmiFacets)}` : '';
    return `${s.state} L${s.level}${dmi}｜失敗 ${fmtModelPct(s.fail)}｜存活 ${fmtModelPct(s.survival)}｜樣本 ${Number(s.samples || 0).toLocaleString()}`;
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
    const dmiText = pred.dmiExpert && pred.dmiExpert.available
      ? `DMI×${pred.dmiExpert.matchedFacetCount}｜Blend ${(Number(pred.dmiExpert.blendStrength || 0) * 100).toFixed(0)}%`
      : 'DMI未匹配';
    $('modelHint').textContent = `3日成功 ${fmtModelPct(pred.success)}｜${dmiText}｜${featureSummary(timeline.features || {})}`;
  }

  function lookupProbability(model, marketState, horizon, features) {
    const stateNode = (model.states || {})[marketState];
    if (!stateNode) return { available:false, reason:'state_missing' };
    const hnode = (stateNode.horizons || {})[String(horizon)];
    if (!hnode) return { available:false, reason:'horizon_missing' };
    const minSamples = Number(model.default_min_samples || 50);

    const base = lookupBaseRule(hnode, features, minSamples, MAX_MODEL_LEVEL);
    if (!base || !base.node) return { available:false, reason:'baseline_missing' };
    const basePred = normalizePrediction(base.node, base.level, base.fallback);

    // Schema v1/v2 remains backward compatible. Schema v3 DMI Expert is an
    // independent correction layer on top of the legacy BB/HA Level 1-5 rule.
    const dmi = lookupDmiFacets(stateNode, hnode, features, minSamples);
    const dmiVersion = String(((model.dmi_expert_contract || {}).version) || '');
    if (!dmi.matches.length || !hnode.baseline) {
      return {
        ...basePred,
        dmiExpert: {
          available: false,
          version: dmiVersion,
          matchedFacetCount: 0,
          blendStrength: 0,
          matchedFacets: [],
          bins: dmi.enriched,
        },
      };
    }

    const combined = combineWithDmi(
      base.node,
      hnode.baseline,
      dmi.matches,
      Number(model.prior_strength || 20),
    );
    return {
      ...basePred,
      success: combined.probabilities[OUTCOME_SUCCESS],
      survival: combined.probabilities[OUTCOME_SUCCESS] + combined.probabilities[OUTCOME_ALIVE],
      trueFail: combined.probabilities[OUTCOME_FAIL],
      other: combined.probabilities[OUTCOME_OTHER],
      dmiExpert: {
        available: true,
        version: dmiVersion,
        matchedFacetCount: combined.audit.length,
        blendStrength: combined.blendStrength,
        matchedFacets: combined.audit,
        bins: dmi.enriched,
      },
    };
  }

  function lookupBaseRule(hnode, features, minSamples, maxLevel) {
    const levels = (hnode.levels || []).filter(x => Number(x.level || 0) <= Number(maxLevel));
    for (let li = levels.length - 1; li >= 0; li--) {
      const level = levels[li];
      const fields = Array.isArray(level.fields) ? level.fields : [];
      const sig = signature(features, fields);
      const rule = findRule(level.rules || [], sig, minSamples);
      if (rule) return { node:rule, level:Number(level.level || 0), fields, signature:sig, fallback:false };
    }
    return hnode.baseline
      ? { node:hnode.baseline, level:0, fields:[], signature:'BASELINE', fallback:true }
      : null;
  }

  function normalizePrediction(node, level, fallback) {
    const probs = outcomeProbs(node);
    return {
      available: true,
      samples: Number(node.samples || 0),
      level,
      fallback,
      success: probs[OUTCOME_SUCCESS],
      trueFail: probs[OUTCOME_FAIL],
      survival: probs[OUTCOME_SUCCESS] + probs[OUTCOME_ALIVE],
      other: probs[OUTCOME_OTHER],
    };
  }

  function enrichDmiRawFeatures(features) {
    const out = { ...(features || {}) };
    const plus = finiteNumber(out.di_plus);
    const minus = finiteNumber(out.di_minus);
    const gap = finiteNumber(out.di_gap);
    if (finiteNumber(out.di_abs_gap) === null) {
      const rawGap = gap !== null ? gap : (plus !== null && minus !== null ? plus - minus : null);
      out.di_abs_gap = rawGap === null ? null : Math.abs(rawGap);
    }
    if (finiteNumber(out.di_axis_distance) === null) {
      out.di_axis_distance = plus !== null && minus !== null
        ? (Math.abs(plus - DMI_AXIS) + Math.abs(minus - DMI_AXIS)) / 2
        : null;
    }
    return out;
  }

  function applyDmiBinning(features, binning) {
    const out = enrichDmiRawFeatures(features);
    Object.entries(DMI_QUANTILE_FIELDS).forEach(([rawField, qField]) => {
      const value = finiteNumber(out[rawField]);
      const node = (binning || {})[rawField] || {};
      const q33 = finiteNumber(node.q33);
      const q67 = finiteNumber(node.q67);
      if (value === null || q33 === null || q67 === null) out[qField] = 'UNKNOWN';
      else if (value <= q33) out[qField] = 'LOW';
      else if (value <= q67) out[qField] = 'MID';
      else out[qField] = 'HIGH';
    });
    return out;
  }

  function lookupDmiFacets(stateNode, hnode, features, minSamples) {
    const expert = hnode.dmi_expert || null;
    const enriched = applyDmiBinning(features, stateNode.dmi_binning || {});
    if (!expert) return { matches:[], enriched };
    const matches = [];
    for (const facet of (expert.facets || [])) {
      const name = String(facet.name || 'facet');
      const fields = Array.isArray(facet.fields) ? facet.fields : [];
      // Quiz model_timeline comes directly from HistoricalTraining replay, so
      // dmi_cross_age_bin is the exact 4H relation-age feature. If an older
      // timeline lacks it, skip cross-age facets rather than fabricate data.
      if ((name === 'cross_momentum' || name === 'adx_turn_handover') && !enriched.dmi_cross_age_bin) continue;
      const sig = signature(enriched, fields);
      const rule = findRule(facet.rules || [], sig, minSamples);
      if (!rule) continue;
      matches.push({ name, fields, signature:sig, rule });
    }
    return { matches, enriched };
  }

  function combineWithDmi(baseNode, baselineNode, matches, priorStrength) {
    const base = outcomeProbs(baseNode);
    if (!matches.length) return { probabilities:base, blendStrength:0, audit:[] };
    const baseline = outcomeProbs(baselineNode);
    const eps = 1e-9;
    const weightedLogs = Object.fromEntries(OUTCOME_KEYS.map(k => [k, 0]));
    const weights = [];
    const audit = [];

    for (const match of matches) {
      const n = Number(match.rule.samples || 0);
      const reliability = n / (n + Math.max(1, Number(priorStrength || 20)));
      weights.push(reliability);
      const facet = outcomeProbs(match.rule);
      OUTCOME_KEYS.forEach(key => {
        const ratio = Math.max(eps, facet[key]) / Math.max(eps, baseline[key]);
        weightedLogs[key] += reliability * Math.log(ratio);
      });
      audit.push({
        name: match.name,
        fields: match.fields,
        signature: match.signature,
        samples: n,
        reliability,
        success: facet[OUTCOME_SUCCESS],
        survival: facet[OUTCOME_SUCCESS] + facet[OUTCOME_ALIVE],
        trueFail: facet[OUTCOME_FAIL],
      });
    }

    const weightSum = weights.reduce((a,b) => a + b, 0);
    if (!(weightSum > 0)) return { probabilities:base, blendStrength:0, audit };
    const blendStrength = Math.min(1, weightSum / weights.length);
    const logs = {};
    OUTCOME_KEYS.forEach(key => {
      const avgLogRatio = weightedLogs[key] / weightSum;
      logs[key] = Math.log(Math.max(eps, base[key])) + blendStrength * avgLogRatio;
    });
    const peak = Math.max(...OUTCOME_KEYS.map(k => logs[k]));
    const expValues = Object.fromEntries(OUTCOME_KEYS.map(k => [k, Math.exp(logs[k] - peak)]));
    const total = OUTCOME_KEYS.reduce((sum,k) => sum + expValues[k], 0);
    const probabilities = Object.fromEntries(OUTCOME_KEYS.map(k => [k, expValues[k] / total]));
    return { probabilities, blendStrength, audit };
  }

  function outcomeProbs(node) {
    const outcomes = (node && node.outcomes) || {};
    const values = {};
    OUTCOME_KEYS.forEach(key => {
      const item = outcomes[key] || {};
      const v = finiteNumber(item.probability);
      values[key] = Math.max(0, v === null ? 0 : v);
    });
    const total = OUTCOME_KEYS.reduce((sum,key) => sum + values[key], 0);
    if (!(total > 0)) {
      const p = Math.max(0, Math.min(1, Number((node && node.probability) || 0)));
      return {
        [OUTCOME_SUCCESS]: p,
        [OUTCOME_ALIVE]: 0,
        [OUTCOME_FAIL]: 0,
        [OUTCOME_OTHER]: 1 - p,
      };
    }
    return Object.fromEntries(OUTCOME_KEYS.map(key => [key, values[key] / total]));
  }

  function findRule(rules, sig, minSamples) {
    return (rules || []).find(r => r.signature === sig && Number(r.samples || 0) >= Number(minSamples || 0)) || null;
  }

  function finiteNumber(value) {
    if (value === null || value === undefined || value === '') return null;
    const n = Number(value);
    return Number.isFinite(n) ? n : null;
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


  function timelineFeaturesForRow(row) {
    const q = state.question;
    if (!q || !row) return null;
    const timeline = q.modelByDay.get(Number(row.time)) || null;
    return timeline && timeline.features ? timeline.features : null;
  }

  function dmiPointForRow(row) {
    const f = timelineFeaturesForRow(row);
    if (!f) return null;
    const diPlus = Number(f.di_plus);
    const diMinus = Number(f.di_minus);
    const adx = Number(f.adx);
    return {
      diPlus: Number.isFinite(diPlus) ? diPlus : NaN,
      diMinus: Number.isFinite(diMinus) ? diMinus : NaN,
      adx: Number.isFinite(adx) ? adx : NaN,
      relation: String(f.dmi_relation || ''),
      stepDirection: String(f.adx_step_direction || ''),
      regime: String(f.dmi_adx_regime || ''),
      axisZone: String(f.adx_axis_zone || ''),
      turnEvent: String(f.adx_turn_event || ''),
      stepAgeBin: String(f.adx_step_age_bin || ''),
    };
  }

  function adxDominanceStateFromPoint(point) {
    if (!point || !Number.isFinite(point.diPlus) || !Number.isFinite(point.diMinus) || point.diPlus === point.diMinus) {
      return { text:'方向膠著｜ADX待確認', controllerClass:'adx-controller-neutral', trendClass:'adx-trend-neutral' };
    }
    const plus = point.diPlus > point.diMinus;
    const controllerClass = plus ? 'adx-controller-plus' : 'adx-controller-minus';
    const rising = point.stepDirection === 'RISING';
    const falling = point.stepDirection === 'FALLING';
    if (!rising && !falling) {
      return { text:`${plus?'多方':'空方'}控制｜力道持平 ←→`, controllerClass, trendClass:'adx-trend-neutral' };
    }
    if (plus && rising) return { text:'多方控制｜趨勢強度增強 ↗↗', controllerClass, trendClass:'adx-trend-rising' };
    if (plus && falling) return { text:'多方仍控制｜力量衰退 ↘↘', controllerClass, trendClass:'adx-trend-falling' };
    if (!plus && rising) return { text:'空方控制｜趨勢強度增強 ↗↗', controllerClass, trendClass:'adx-trend-rising' };
    return { text:'空方仍控制｜力量衰退 ↘↘', controllerClass, trendClass:'adx-trend-falling' };
  }

  function updateAdxHud(rows) {
    const hud = $('adxHud');
    if (!hud || !Array.isArray(rows) || !rows.length) return;
    const index = state.hoverIndex !== null && state.hoverIndex >= 0 && state.hoverIndex < rows.length ? state.hoverIndex : rows.length - 1;
    const point = dmiPointForRow(rows[index]);
    if (!point || (!Number.isFinite(point.diPlus) && !Number.isFinite(point.diMinus) && !Number.isFinite(point.adx))) {
      hud.classList.add('hidden');
      return;
    }
    hud.classList.remove('hidden');
    const dominance = adxDominanceStateFromPoint(point);
    const statePill = $('adxStatePill');
    statePill.className = `adx-state-pill ${dominance.controllerClass} ${dominance.trendClass}`;
    $('adxStateText').textContent = dominance.text;
    $('adxPlusValue').textContent = Number.isFinite(point.diPlus) ? point.diPlus.toFixed(1) : '—';
    $('adxMinusValue').textContent = Number.isFinite(point.diMinus) ? point.diMinus.toFixed(1) : '—';
    const plusPill = $('adxPlusPill');
    const minusPill = $('adxMinusPill');
    plusPill.className = 'adx-live-pill adx-pill-plus adx-pill-neutral';
    minusPill.className = 'adx-live-pill adx-pill-minus adx-pill-neutral';
    if (Number.isFinite(point.diPlus) && Number.isFinite(point.diMinus) && point.diPlus !== point.diMinus) {
      if (point.diPlus > point.diMinus) plusPill.className = 'adx-live-pill adx-pill-plus adx-pill-strong-plus';
      else minusPill.className = 'adx-live-pill adx-pill-minus adx-pill-strong-minus';
    }
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

    const dmiHeight = Math.max(124, Math.min(158, h * 0.29));
    const gap = 26;
    const pad = { left:16, right:82, top:18, bottom:28 };
    const dmi = {
      left: pad.left,
      right: pad.right,
      top: Math.max(170, h - pad.bottom - dmiHeight),
      bottom: pad.bottom,
    };
    const priceBottom = dmi.top - gap;
    const plotW = w - pad.left - pad.right;
    const plotH = Math.max(120, priceBottom - pad.top);
    const values = [];
    rows.forEach(r => {
      values.push(r.high, r.low);
      if (r.bb) values.push(r.bb.upper, r.bb.lower);
      if (r.ha) values.push(r.ha.close);
    });
    if (state.trade && !state.trade.closed && Number.isFinite(state.trade.entryPrice)) values.push(state.trade.entryPrice);
    let min = Math.min(...values), max = Math.max(...values);
    const extra = (max - min || Math.abs(max) || 1) * .08;
    min -= extra; max += extra;

    const xAt = (i) => pad.left + (i + .5) * plotW / rows.length;
    const yAt = (v) => pad.top + (max - v) / (max - min) * plotH;
    const barW = Math.max(3, Math.min(14, plotW / rows.length * .58));

    drawPriceGrid(ctx, pad, plotW, plotH, min, max);
    drawLine(rows, xAt, yAt, r => r.bb && r.bb.upper, 'rgba(86,164,255,.72)', 1.25);
    drawLine(rows, xAt, yAt, r => r.bb && r.bb.basis, 'rgba(225,232,244,.52)', 1.15);
    drawLine(rows, xAt, yAt, r => r.bb && r.bb.lower, 'rgba(86,164,255,.72)', 1.25);

    rows.forEach((r, i) => {
      const x = xAt(i);
      const up = r.close >= r.open;
      const c = up ? '#3cd6a0' : '#ff667f';
      ctx.strokeStyle = c; ctx.lineWidth = 1.2;
      ctx.beginPath(); ctx.moveTo(x, yAt(r.high)); ctx.lineTo(x, yAt(r.low)); ctx.stroke();
      const yO = yAt(r.open), yC = yAt(r.close);
      const top = Math.min(yO,yC), bh = Math.max(1.5, Math.abs(yO-yC));
      ctx.fillStyle = c; ctx.fillRect(x-barW/2, top, barW, bh);
    });

    ctx.lineWidth = 3.2; ctx.lineJoin = 'miter';
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
      drawEntryPriceLine(yAt(state.trade.entryPrice), pad, plotW, entryColor, `${state.trade.direction === 'LONG' ? '做多' : '做空'}進場 ${formatPrice(state.trade.entryPrice)}`);
    }

    drawMarkerForAbsoluteIndex(rows, q.cutoff, xAt, pad, plotH, 'rgba(255,255,255,.48)', '起始', true);
    if (state.trade) {
      const c = state.trade.direction === 'LONG' ? '#3cd6a0' : '#ff667f';
      drawMarkerForAbsoluteIndex(rows, state.trade.entryIndex, xAt, pad, plotH, c, state.trade.direction === 'LONG' ? '做多' : '做空', false);
      if (state.trade.closed && Number.isInteger(state.trade.exitIndex)) drawMarkerForAbsoluteIndex(rows, state.trade.exitIndex, xAt, pad, plotH, '#ffd84b', '平倉', false);
    }

    const dmiLayout = drawDmiPanel(rows, xAt, dmi, plotW);

    if (state.hoverIndex !== null && state.hoverIndex >= 0 && state.hoverIndex < rows.length) {
      const x = xAt(state.hoverIndex);
      ctx.strokeStyle='rgba(221,232,247,.38)'; ctx.lineWidth=1; ctx.setLineDash([5,5]);
      ctx.beginPath(); ctx.moveTo(x,pad.top); ctx.lineTo(x,dmiLayout.bottomY); ctx.stroke(); ctx.setLineDash([]);
    }

    canvas._layout = { rows, pad, plotW, plotH, min, max, xAt, yAt, dmiLayout, hoverTop:pad.top, hoverBottom:dmiLayout.bottomY };
    updateAdxHud(rows);
    const hud = $('adxHud');
    if (hud && !hud.classList.contains('hidden')) hud.style.top = `${Math.round(canvas.offsetTop + dmi.top - 2)}px`;
    const modelHud = $('modelHud');
    if (modelHud) modelHud.style.bottom = `${Math.round(h - priceBottom + 10)}px`;
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

  function drawPriceGrid(ctx, pad, plotW, plotH, min, max) {
    ctx.save();
    ctx.strokeStyle='rgba(139,158,188,.12)'; ctx.fillStyle='#77859b'; ctx.font='11px sans-serif'; ctx.lineWidth=1;
    for (let i=0; i<=5; i++) {
      const y=pad.top + i*plotH/5;
      ctx.beginPath(); ctx.moveTo(pad.left,y); ctx.lineTo(pad.left+plotW,y); ctx.stroke();
      const v=max - i*(max-min)/5;
      ctx.textAlign='left'; ctx.textBaseline='middle'; ctx.fillText(formatPrice(v), pad.left+plotW+8,y);
    }
    ctx.restore();
  }

  function drawDmiPanel(rows, xAt, dmi, plotW) {
    const points = rows.map(r => dmiPointForRow(r));
    const vals = [20, 40];
    points.forEach(p => {
      if (!p) return;
      if (Number.isFinite(p.diPlus)) vals.push(p.diPlus);
      if (Number.isFinite(p.diMinus)) vals.push(p.diMinus);
      if (Number.isFinite(p.adx)) vals.push(p.adx);
    });
    const maxVal = Math.max(40, Math.ceil(Math.max(...vals) / 10) * 10);
    const topY = dmi.top + 22;
    const bottomY = (canvas._cssHeight || canvas.clientHeight) - dmi.bottom;
    const innerH = Math.max(76, bottomY - topY);
    const y = v => topY + (maxVal - Number(v)) / maxVal * innerH;

    ctx.save();
    ctx.strokeStyle='rgba(139,158,188,.14)'; ctx.fillStyle='#77859b'; ctx.font='9px sans-serif'; ctx.lineWidth=1;
    [0, maxVal/2, maxVal].forEach(v => {
      const yy=y(v); ctx.beginPath(); ctx.moveTo(dmi.left,yy); ctx.lineTo(dmi.left+plotW,yy); ctx.stroke();
      ctx.textAlign='left'; ctx.textBaseline='middle'; ctx.fillText(String(Math.round(v)), dmi.left+plotW+8, yy);
    });
    const y20=y(20);
    ctx.setLineDash([7,7]); ctx.strokeStyle='rgba(248,250,252,.82)'; ctx.lineWidth=1.15;
    ctx.beginPath(); ctx.moveTo(dmi.left,y20); ctx.lineTo(dmi.left+plotW,y20); ctx.stroke(); ctx.setLineDash([]);
    ctx.fillStyle='#e2e8f0'; ctx.font='bold 9px sans-serif'; ctx.textAlign='right'; ctx.fillText('20', dmi.left-5, y20+3);

    // ADX stepline: color comes from the same replay feature used by HistoricalTraining.
    for (let i=1;i<points.length;i++) {
      const prev=points[i-1], curr=points[i];
      if (!prev || !curr || !Number.isFinite(prev.adx) || !Number.isFinite(curr.adx)) continue;
      const step = curr.stepDirection || (curr.adx>prev.adx?'RISING':curr.adx<prev.adx?'FALLING':'FLAT');
      ctx.strokeStyle = step==='RISING' ? '#26A69A' : step==='FALLING' ? '#EF5350' : '#64748b';
      ctx.lineWidth=2; ctx.lineJoin='miter';
      ctx.beginPath(); ctx.moveTo(xAt(i-1),y(prev.adx)); ctx.lineTo(xAt(i),y(prev.adx)); ctx.lineTo(xAt(i),y(curr.adx)); ctx.stroke();
    }

    const drawIndicatorLine = (key,color) => {
      ctx.strokeStyle=color; ctx.lineWidth=1.35; ctx.beginPath(); let started=false;
      points.forEach((p,i) => {
        const v=p && p[key];
        if (!Number.isFinite(v)) { started=false; return; }
        const xx=xAt(i), yy=y(v);
        if (!started) { ctx.moveTo(xx,yy); started=true; } else ctx.lineTo(xx,yy);
      });
      ctx.stroke();
    };
    drawIndicatorLine('diPlus','#fde047');
    drawIndicatorLine('diMinus','#bba4e8');

    const last=points[points.length-1];
    if (last) {
      if (Number.isFinite(last.diPlus)) { ctx.fillStyle='#fde047';ctx.strokeStyle='#f8fafc';ctx.lineWidth=1.2;ctx.beginPath();ctx.arc(xAt(points.length-1),y(last.diPlus),3.5,0,Math.PI*2);ctx.fill();ctx.stroke(); }
      if (Number.isFinite(last.diMinus)) { ctx.fillStyle='#bba4e8';ctx.strokeStyle='#f8fafc';ctx.lineWidth=1.2;ctx.beginPath();ctx.arc(xAt(points.length-1),y(last.diMinus),3.5,0,Math.PI*2);ctx.fill();ctx.stroke(); }
    }

    // Dates belong to the lowest panel, matching Terminal/TradingView reading order.
    const step=Math.max(1,Math.ceil(rows.length/7));
    for(let i=0;i<rows.length;i+=step){
      const xx=xAt(i);
      const q=state.question;
      const blind=$('blindMode').checked && !state.trade && state.closedTrades.length===0 && state.revealed<q.maxFutureDays;
      const label=blind?relativeDayLabel(rows[i].index-q.cutoff):formatShortDate(rows[i].time);
      ctx.save();ctx.translate(xx,bottomY+7);ctx.rotate(-Math.PI/5);ctx.fillStyle='#77859b';ctx.font='9px sans-serif';ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText(label,0,0);ctx.restore();
    }
    ctx.restore();
    return { topY, bottomY, y, maxVal, points };
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
    if (mx<layout.pad.left || mx>layout.pad.left+layout.plotW || my<layout.hoverTop || my>layout.hoverBottom) {
      tooltip.classList.add('hidden'); state.hoverIndex=null; draw(); return;
    }
    const i=Math.max(0,Math.min(layout.rows.length-1,Math.floor((mx-layout.pad.left)/layout.plotW*layout.rows.length)));
    state.hoverIndex=i;
    const r=layout.rows[i];
    const q=state.question;
    const blind=$('blindMode').checked && !state.trade && state.closedTrades.length === 0 && state.revealed < q.maxFutureDays;
    const date=blind ? relativeDayLabel(r.index-q.cutoff) : formatDate(r.time);
    const haColor=r.ha.color==='yellow'?'黃':r.ha.color==='purple'?'紫':'平';
    const point=dmiPointForRow(r);
    const dominance=adxDominanceStateFromPoint(point);
    const dmiText=point ? `<br>DI+ ${Number.isFinite(point.diPlus)?point.diPlus.toFixed(1):'—'}　DI− ${Number.isFinite(point.diMinus)?point.diMinus.toFixed(1):'—'}　ADX ${Number.isFinite(point.adx)?point.adx.toFixed(1):'—'}<br>${escapeHtml(dominance.text)}` : '';
    tooltip.innerHTML = `${date}<br>O ${formatPrice(r.open)}　H ${formatPrice(r.high)}<br>L ${formatPrice(r.low)}　C ${formatPrice(r.close)}<br>HA ${haColor} ${formatPrice(r.ha.close)}${r.bb?`<br>BB中軌 ${formatPrice(r.bb.basis)}`:''}${dmiText}`;
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

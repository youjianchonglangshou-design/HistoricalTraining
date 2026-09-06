(() => {
  'use strict';

  const CONTEXT_DAYS = 30;
  const BB_PERIOD = 20;
  const MAX_FUTURE_DAYS = 45;
  const MIN_CUTOFF_INDEX = (CONTEXT_DAYS - 1) + (BB_PERIOD - 1);
  const DAY_MS = 24 * 60 * 60 * 1000;
  const MODEL_HORIZON = 18; // 72H = 18 x 4H
  const MAX_MODEL_LEVEL = 6;
  const OUTCOME_SUCCESS = 'SUCCESS_WITHIN_HORIZON';
  const OUTCOME_ALIVE = 'ALIVE_SLOW';
  const OUTCOME_FAIL = 'TRUE_FAIL';
  const OUTCOME_OTHER = 'OTHER';
  const OUTCOME_KEYS = [OUTCOME_SUCCESS, OUTCOME_ALIVE, OUTCOME_FAIL, OUTCOME_OTHER];
  // Must match HistoricalTraining/training/model_builder.py PATH_QUANTILE_FIELDS.
  const PATH_QUANTILE_FIELDS = {
    cci_sma_gap: 'cci_sma_gap_q',
    cci_gap_velocity_1d: 'cci_gap_velocity_q',
    cci_gap_acceleration: 'cci_gap_acceleration_q',
    cci_slope_1d: 'cci_slope_1d_q',
    cci_slope_3d: 'cci_slope_3d_q',
    cci_acceleration: 'cci_acceleration_q',
    cci_smoothing_slope_1d: 'cci_smoothing_slope_1d_q',
    cci_smoothing_slope_3d: 'cci_smoothing_slope_3d_q',
    cci_distance_to_neg100: 'cci_distance_to_neg100_q',
    cci_distance_to_zero: 'cci_distance_to_zero_q',
    midline_slope_1d: 'midline_slope_1d_q',
    midline_slope_3d: 'midline_slope_3d_q',
    midline_slope_change_3d: 'midline_slope_change_q',
    price_high_delta_pct: 'price_high_delta_q',
    cci_high_delta: 'cci_high_delta_q',
    price_low_delta_pct: 'price_low_delta_q',
    cci_low_delta: 'cci_low_delta_q',
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
      el.textContent = `R2 Champion｜${state.activeModel.model_id}｜Schema ${state.activeModel.schema_version || '?'} CCI PRIMARY`;
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
      success: pred.success,
      samples: pred.samples,
      pathSignature: pred.pathSignature || 'STATE_BASELINE',
      modelId: state.activeModel.model_id || '',
    };
  }

  function formatModelSnapshot(s) {
    if (!s || !s.available) return `${s && s.state ? s.state : 'NON_MODEL'}｜無統計`;
    return `${s.state} L${s.level}｜成功 ${fmtModelPct(s.success)}｜失敗 ${fmtModelPct(s.fail)}｜存活 ${fmtModelPct(s.survival)}｜樣本 ${Number(s.samples || 0).toLocaleString()}`;
  }

  function renderModelHud() {
    const timeline = currentTimelineRow();
    if (!state.question) return;
    if (!state.activeModel) {
      $('modelState').textContent = 'R2 Champion 模型無法讀取';
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
      $('modelHint').textContent = '此日沒有 replay 特徵；可繼續播放下一天';
      return;
    }

    const pred = lookupProbability(state.activeModel, timeline.state, MODEL_HORIZON, timeline.features || {});
    $('modelState').textContent = `${timeline.state}｜${stateLabel(timeline.state)}`;
    if (!pred.available) {
      $('modelLevel').textContent = '—';
      setModelStat('modelFail', null);
      setModelStat('modelSurvival', null);
      $('modelSamples').textContent = '—';
      $('modelHint').textContent = timeline.state === 'S0' || timeline.state === 'OTHER' || timeline.state === 'NON_MODEL'
        ? '目前不是 S0.5 / S1 / S2 / S3 正式機率考題；CCI 結構評語仍可閱讀'
        : `目前 Champion 無匹配：${pred.reason || 'unknown'}`;
      return;
    }

    $('modelLevel').textContent = `L${pred.level}`;
    setModelStat('modelFail', pred.trueFail);
    setModelStat('modelSurvival', pred.survival);
    $('modelSamples').textContent = Number(pred.samples || 0).toLocaleString();
    const path = pred.matchedPath?.length
      ? `CCI Path ${pred.matchedPath.length}層`
      : 'State baseline';
    $('modelHint').textContent = `3日成功 ${fmtModelPct(pred.success)}｜${path}｜${featureSummary(timeline.features || {})}`;
  }

  function applyPathBinning(features, binning) {
    const out = { ...(features || {}) };
    Object.entries(PATH_QUANTILE_FIELDS).forEach(([rawField, qField]) => {
      const value = finiteNumber(out[rawField]);
      const node = (binning || {})[rawField] || {};
      const q25 = finiteNumber(node.q25), q50 = finiteNumber(node.q50), q75 = finiteNumber(node.q75);
      if (value === null || q25 === null || q50 === null || q75 === null) out[qField] = 'UNKNOWN';
      else if (value <= q25) out[qField] = 'Q1';
      else if (value <= q50) out[qField] = 'Q2';
      else if (value <= q75) out[qField] = 'Q3';
      else out[qField] = 'Q4';
    });
    return out;
  }

  function walkPathTree(tree, features) {
    let node = tree || {};
    const path = [];
    while (node && typeof node === 'object' && !Boolean(node.leaf ?? true)) {
      const field = String(node.split_field || '');
      if (!field) break;
      const raw = features[field];
      const value = String(raw === null || raw === undefined || raw === '' ? 'UNKNOWN' : raw);
      const child = (node.children || {})[value];
      if (!child || typeof child !== 'object') break;
      path.push({ field, value });
      node = child;
    }
    return { node, path };
  }

  function lookupProbability(model, marketState, horizon, features) {
    const stateNode = (model.states || {})[marketState];
    if (!stateNode) return { available:false, reason:'state_missing' };
    const hnode = (stateNode.horizons || {})[String(horizon)];
    if (!hnode) return { available:false, reason:'horizon_missing' };

    // Schema 5 CCI PRIMARY: S-state selects the question; the CCI/BB/HA path tree
    // directly supplies the four probabilities. No legacy ADX/DMI correction layer.
    if (Number(model.schema_version || 0) >= 5 && (hnode.path_tree || hnode.baseline)) {
      const enriched = applyPathBinning(features || {}, stateNode.path_binning || {});
      const tree = hnode.path_tree || hnode.baseline || {};
      const walked = walkPathTree(tree, enriched);
      const node = walked.node || tree;
      const probs = nodeOutcomeProbabilities(node);
      const depth = Number(node.depth ?? walked.path.length ?? 0);
      const pathSignature = walked.path.map(x => `${x.field}=${x.value}`).join('|') || 'STATE_BASELINE';
      return {
        available: true,
        samples: Number(node.samples || 0),
        level: depth,
        fallback: walked.path.length === 0,
        success: probs[OUTCOME_SUCCESS],
        trueFail: probs[OUTCOME_FAIL],
        survival: probs[OUTCOME_SUCCESS] + probs[OUTCOME_ALIVE],
        other: probs[OUTCOME_OTHER],
        enrichedFeatures: enriched,
        matchedPath: walked.path,
        pathSignature,
        cciPrimaryVersion: String((model.cci_primary_contract || {}).version || ''),
      };
    }

    return { available:false, reason:`unsupported_model_schema_${model.schema_version || 'unknown'}` };
  }

  function nodeOutcomeProbabilities(node) {
    const outcomes = (node && node.outcomes) || {};
    const success = finiteNumber((outcomes[OUTCOME_SUCCESS] || {}).probability);
    const alive = finiteNumber((outcomes[OUTCOME_ALIVE] || {}).probability);
    const fail = finiteNumber((outcomes[OUTCOME_FAIL] || {}).probability);
    const other = finiteNumber((outcomes[OUTCOME_OTHER] || {}).probability);
    return {
      [OUTCOME_SUCCESS]: success === null ? Number(node?.probability || 0) : success,
      [OUTCOME_ALIVE]: alive === null ? 0 : alive,
      [OUTCOME_FAIL]: fail === null ? Number(node?.true_fail_probability || 0) : fail,
      [OUTCOME_OTHER]: other === null ? Number(node?.other_probability || 0) : other,
    };
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


  function timelineRowForRow(row) {
    const q = state.question;
    if (!q || !row) return null;
    return q.modelByDay.get(Number(row.time)) || null;
  }

  function timelineFeaturesForRow(row) {
    const timeline = timelineRowForRow(row);
    return timeline && timeline.features ? timeline.features : null;
  }

  function cciPointForRow(row) {
    const f = timelineFeaturesForRow(row);
    if (!f) return null;
    const cci = finiteNumber(f.cci);
    const sma = finiteNumber(f.cci_smoothing_ma);
    return {
      cci: cci === null ? NaN : cci,
      sma: sma === null ? NaN : sma,
      smoothingDirection: String(f.cci_smoothing_direction || 'UNKNOWN').toUpperCase(),
      relation: String(f.cci_sma_relation || 'UNKNOWN').toUpperCase(),
      features: f,
    };
  }

  function cciRelationClass(cci, sma) {
    if (!Number.isFinite(cci) || !Number.isFinite(sma) || cci === sma) return 'cci-pill-neutral';
    return cci > sma ? 'cci-pill-above' : 'cci-pill-below';
  }

  function cciSmaClass(direction) {
    const d = String(direction || '').toUpperCase();
    if (d === 'YELLOW') return 'cci-sma-yellow';
    if (d === 'PURPLE') return 'cci-sma-purple';
    return 'cci-sma-neutral';
  }

  function buildCciPathCommentary(marketState, features, pred=null) {
    const f = features || {};
    const st = String(marketState || 'OTHER');
    const mid = String(f.midline_path_phase || 'UNKNOWN');
    const cycle = String(f.cci_cross_cycle || 'NO_CROSS_30D');
    const retest = String(f.cci_retest_state || 'UNKNOWN');
    const gapMotion = String(f.cci_gap_motion || 'UNKNOWN');
    const divergence = String(f.cci_divergence || 'NONE');
    const sma = String(f.cci_smoothing_direction || 'UNKNOWN').toUpperCase();
    const ha = String(f.ha_color || 'unknown').toLowerCase();
    const relation = String(f.cci_sma_relation || 'UNKNOWN').toUpperCase();
    const lastCrossZone = String(f.cci_last_cross_zone || 'UNKNOWN');
    const upCount = Number(f.cci_up_cross_count_21d || 0);
    const downCount = Number(f.cci_down_cross_count_21d || 0);

    const risingMid = ['RISING_ACCEL','RISING_DECEL'].includes(mid);
    const improvingMid = ['FLAT','FALLING_IMPROVE','RISING_ACCEL','RISING_DECEL'].includes(mid);
    const weakMid = ['FLAT','FALLING_IMPROVE','FALLING_WORSEN'].includes(mid);
    const hardFalling = mid === 'FALLING_WORSEN';
    const secondUp = cycle === 'UP_SECOND_PLUS_21D' || (upCount >= 2 && cycle.startsWith('POST_UP'));
    const firstUp = cycle === 'UP_FIRST_21D' || (upCount === 1 && cycle.startsWith('POST_UP'));
    const secondDown = cycle === 'DOWN_SECOND_PLUS_21D' || (downCount >= 2 && cycle.startsWith('POST_DOWN'));
    const firstDown = cycle === 'DOWN_FIRST_21D' || (downCount === 1 && cycle.startsWith('POST_DOWN'));
    const deepLowCross = ['LT_NEG150','NEG150_NEG120','NEG120_NEG80'].includes(lastCrossZone);
    const nearZeroCross = ['NEG80_0','0_100'].includes(lastCrossZone);
    const bullishHa = ['yellow','green','bullish'].includes(ha);

    let label='結構觀察｜等待CCI路徑確認', tone='neutral';
    if (st === 'S0.5') {
      if (retest === 'YELLOW_RECLAIM_AFTER_BREAK' && risingMid) [label,tone]=['假跌破回收｜多方結構仍在','positive'];
      else if (retest === 'YELLOW_RETEST_NEAR_SMA' && improvingMid) [label,tone]=['黃階梯承接｜右側回踩守住','positive'];
      else if (secondUp && improvingMid && (sma === 'YELLOW' || bullishHa)) [label,tone]=['右V共振｜二次上穿・中軌改善','strong'];
      else if (secondUp && improvingMid) [label,tone]=['右V確認｜二次上穿・中軌改善','positive'];
      else if (firstUp && hardFalling && deepLowCross) [label,tone]=['左V反彈｜首次低位上穿','caution'];
      else if (firstUp && improvingMid) [label,tone]=['首次上穿｜反轉仍待二次確認','setup'];
      else if (gapMotion === 'BELOW_APPROACHING' && improvingMid) [label,tone]=['右V醞釀｜CCI快速逼近SMA','setup'];
      else if (sma === 'YELLOW' && relation === 'ABOVE') [label,tone]=['黃階梯建立｜多方動能接管','positive'];
      else if (hardFalling) [label,tone]=['築底反彈｜中軌仍有下壓','caution'];
      else [label,tone]=['築底觀察｜等待右V共振','setup'];
    } else if (st === 'S1') {
      if (retest === 'YELLOW_RECLAIM_AFTER_BREAK' && risingMid) [label,tone]=['回踩收復｜趨勢結構延續','positive'];
      else if (retest === 'YELLOW_RETEST_NEAR_SMA' && risingMid) [label,tone]=['健康回踩｜CCI守住黃階梯','positive'];
      else if (divergence === 'BEARISH_PRICE_HH_CCI_LH' && ['RISING_DECEL','FLAT'].includes(mid)) [label,tone]=['動能放緩｜留意頂背離','caution'];
      else if (sma === 'YELLOW' && relation === 'ABOVE' && risingMid) [label,tone]=['趨勢建立｜黃階梯延伸','strong'];
      else if (gapMotion === 'BELOW_APPROACHING' && improvingMid) [label,tone]=['動能重整｜等待CCI再上穿','setup'];
      else if (mid === 'RISING_DECEL') [label,tone]=['趨勢續行｜中軌升勢放緩','setup'];
      else [label,tone]=['趨勢建立｜觀察CCI延伸','neutral'];
    } else if (st === 'S2') {
      if (secondDown && divergence === 'BEARISH_PRICE_HH_CCI_LH' && weakMid) [label,tone]=['二次衰竭｜頂背離・中軌降速','risk'];
      else if (secondDown && ['FLAT','FALLING_IMPROVE','FALLING_WORSEN'].includes(mid)) [label,tone]=['二次死叉｜轉弱風險升高','risk'];
      else if (firstDown && risingMid) [label,tone]=['二浪回踩｜中軌仍上斜','positive'];
      else if (['UP_FIRST_21D','UP_SECOND_PLUS_21D'].includes(cycle) && nearZeroCross && improvingMid) [label,tone]=['再蓄力｜CCI零軸附近重上穿','strong'];
      else if (['YELLOW_RETEST_NEAR_SMA','YELLOW_RECLAIM_AFTER_BREAK'].includes(retest) && risingMid) [label,tone]=['二浪承接｜三浪仍有空間','positive'];
      else if (risingMid) [label,tone]=['回踩整理｜上升結構未破','setup'];
      else if (mid === 'FLAT') [label,tone]=['高檔整理｜等待再啟動或衰竭','neutral'];
      else [label,tone]=['結構轉弱｜留意二次死叉','caution'];
    } else if (st === 'S3') {
      if (secondDown && divergence === 'BEARISH_PRICE_HH_CCI_LH') [label,tone]=['末浪衰竭｜二次死叉・頂背離','risk'];
      else if (divergence === 'BEARISH_PRICE_HH_CCI_LH' && ['RISING_DECEL','FLAT'].includes(mid)) [label,tone]=['高檔背離｜末浪動能降速','caution'];
      else if (['YELLOW_RETEST_NEAR_SMA','YELLOW_RECLAIM_AFTER_BREAK'].includes(retest) && risingMid) [label,tone]=['趨勢續航｜黃階梯回踩承接','positive'];
      else if (sma === 'YELLOW' && relation === 'ABOVE' && gapMotion === 'ABOVE_EXPANDING') [label,tone]=['三浪延伸｜CCI動能仍擴張','strong'];
      else if (sma === 'PURPLE' && risingMid) [label,tone]=['高檔回踩｜中軌仍上斜','setup'];
      else if (['FLAT','FALLING_IMPROVE','FALLING_WORSEN'].includes(mid) && sma === 'PURPLE') [label,tone]=['高檔降速｜保護既有趨勢成果','caution'];
      else [label,tone]=['趨勢成熟｜觀察CCI衰竭訊號','neutral'];
    } else if (st === 'S0') {
      if (firstUp && hardFalling && deepLowCross) [label,tone]=['左V反彈｜中軌仍明顯下壓','caution'];
      else if (secondUp && improvingMid) [label,tone]=['底部反轉醞釀｜等待升級S0.5','setup'];
      else if (gapMotion === 'BELOW_APPROACHING') [label,tone]=['超賣修復｜CCI逼近SMA','setup'];
      else [label,tone]=['反彈區｜結構尚未升級','neutral'];
    } else {
      if (divergence === 'BEARISH_PRICE_HH_CCI_LH' && weakMid) [label,tone]=['未分類弱化｜CCI背離・中軌失速','risk'];
      else if (sma === 'YELLOW' && risingMid) [label,tone]=['趨勢存在｜尚未符合S-state考題','setup'];
      else if (gapMotion === 'BELOW_APPROACHING' || gapMotion === 'ABOVE_PULLBACK') [label,tone]=['整理等待｜CCI正在接近關鍵交叉','neutral'];
      else [label,tone]=['結構未分類｜等待有效S-state','neutral'];
    }
    return { label, tone, level:pred?.level || 0, samples:pred?.samples || 0 };
  }

  function updateCciHud(rows) {
    const hud = $('cciHud');
    if (!hud || !Array.isArray(rows) || !rows.length) return;
    const index = state.hoverIndex !== null && state.hoverIndex >= 0 && state.hoverIndex < rows.length ? state.hoverIndex : rows.length - 1;
    const row = rows[index];
    const timeline = timelineRowForRow(row);
    const point = cciPointForRow(row);
    if (!timeline || !point || (!Number.isFinite(point.cci) && !Number.isFinite(point.sma))) {
      hud.classList.add('hidden');
      return;
    }
    hud.classList.remove('hidden');
    const pred = state.activeModel ? lookupProbability(state.activeModel, timeline.state, MODEL_HORIZON, timeline.features || {}) : null;
    const comment = buildCciPathCommentary(timeline.state, timeline.features || {}, pred);
    const statePill = $('cciStatePill');
    statePill.className = `cci-state-pill cci-path-${comment.tone}`;
    $('cciStateText').textContent = comment.label;
    $('cciSmaValue').textContent = Number.isFinite(point.sma) ? point.sma.toFixed(1) : '—';
    $('cciValue').textContent = Number.isFinite(point.cci) ? point.cci.toFixed(1) : '—';
    $('cciSmaPill').className = `cci-live-pill cci-sma-pill ${cciSmaClass(point.smoothingDirection)}`;
    $('cciValuePill').className = `cci-live-pill cci-value-pill ${cciRelationClass(point.cci, point.sma)}`;
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

    const cciHeight = Math.max(124, Math.min(158, h * 0.29));
    const gap = 26;
    const pad = { left:16, right:82, top:18, bottom:28 };
    const cci = {
      left: pad.left,
      right: pad.right,
      top: Math.max(170, h - pad.bottom - cciHeight),
      bottom: pad.bottom,
    };
    const priceBottom = cci.top - gap;
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

    const cciLayout = drawCciPanel(rows, xAt, cci, plotW);

    if (state.hoverIndex !== null && state.hoverIndex >= 0 && state.hoverIndex < rows.length) {
      const x = xAt(state.hoverIndex);
      ctx.strokeStyle='rgba(221,232,247,.38)'; ctx.lineWidth=1; ctx.setLineDash([5,5]);
      ctx.beginPath(); ctx.moveTo(x,pad.top); ctx.lineTo(x,cciLayout.bottomY); ctx.stroke(); ctx.setLineDash([]);
    }

    canvas._layout = { rows, pad, plotW, plotH, min, max, xAt, yAt, cciLayout, hoverTop:pad.top, hoverBottom:cciLayout.bottomY };
    updateCciHud(rows);
    const hud = $('cciHud');
    if (hud && !hud.classList.contains('hidden')) hud.style.top = `${Math.round(canvas.offsetTop + cci.top - 2)}px`;
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

  function drawCciPanel(rows, xAt, cciLayout, plotW) {
    const points = rows.map(r => cciPointForRow(r));
    const vals = [-100, 0, 100];
    points.forEach(p => {
      if (!p) return;
      if (Number.isFinite(p.cci)) vals.push(p.cci);
      if (Number.isFinite(p.sma)) vals.push(p.sma);
    });
    const rawMin = Math.min(...vals), rawMax = Math.max(...vals);
    const range = Math.max(1, rawMax - rawMin);
    const minVal = Math.min(-150, Math.floor((rawMin - range * .08) / 50) * 50);
    const maxVal = Math.max(150, Math.ceil((rawMax + range * .08) / 50) * 50);
    const topY = cciLayout.top + 22;
    const bottomY = (canvas._cssHeight || canvas.clientHeight) - cciLayout.bottom;
    const innerH = Math.max(76, bottomY - topY);
    const y = v => topY + (maxVal - Number(v)) / (maxVal - minVal) * innerH;

    ctx.save();
    ctx.strokeStyle='rgba(139,158,188,.10)'; ctx.fillStyle='#77859b'; ctx.font='9px sans-serif'; ctx.lineWidth=1;
    [100,0,-100].forEach(v => {
      const yy=y(v);
      ctx.setLineDash(v===0 ? [4,6] : [7,7]);
      ctx.strokeStyle=v===0?'rgba(100,116,139,.48)':'rgba(148,163,184,.66)';
      ctx.beginPath(); ctx.moveTo(cciLayout.left,yy); ctx.lineTo(cciLayout.left+plotW,yy); ctx.stroke();
      ctx.setLineDash([]);
      ctx.fillStyle='#7890ad'; ctx.textAlign='right'; ctx.textBaseline='middle'; ctx.fillText(String(v), cciLayout.left-5, yy);
    });

    // SMA14 stepline: yellow when smoothing rises, purple when it falls.
    for (let i=1;i<points.length;i++) {
      const prev=points[i-1], curr=points[i];
      if (!prev || !curr || !Number.isFinite(prev.sma) || !Number.isFinite(curr.sma)) continue;
      const d=String(curr.smoothingDirection || '').toUpperCase();
      ctx.strokeStyle=d==='YELLOW'?'#fde047':d==='PURPLE'?'#bba4e8':'#64748b';
      ctx.lineWidth=2.1; ctx.lineJoin='miter';
      ctx.beginPath(); ctx.moveTo(xAt(i-1),y(prev.sma)); ctx.lineTo(xAt(i),y(prev.sma)); ctx.lineTo(xAt(i),y(curr.sma)); ctx.stroke();
    }

    // CCI20 white line.
    ctx.strokeStyle='#f8fafc'; ctx.lineWidth=1.55; ctx.lineJoin='round'; ctx.lineCap='round';
    ctx.beginPath(); let started=false;
    points.forEach((p,i) => {
      if (!p || !Number.isFinite(p.cci)) { started=false; return; }
      const xx=xAt(i), yy=y(p.cci);
      if (!started) { ctx.moveTo(xx,yy); started=true; } else ctx.lineTo(xx,yy);
    });
    ctx.stroke();

    const last=points[points.length-1];
    if (last) {
      if (Number.isFinite(last.cci)) { ctx.fillStyle='#f8fafc';ctx.strokeStyle='#cbd5e1';ctx.lineWidth=1.1;ctx.beginPath();ctx.arc(xAt(points.length-1),y(last.cci),3.5,0,Math.PI*2);ctx.fill();ctx.stroke(); }
      if (Number.isFinite(last.sma)) {
        const d=String(last.smoothingDirection || '').toUpperCase();
        ctx.fillStyle=d==='YELLOW'?'#fde047':d==='PURPLE'?'#bba4e8':'#94a3b8';ctx.strokeStyle='#f8fafc';ctx.lineWidth=1.1;ctx.beginPath();ctx.arc(xAt(points.length-1),y(last.sma),3.5,0,Math.PI*2);ctx.fill();ctx.stroke();
      }
    }

    // Dates live on the lowest CCI panel.
    const step=Math.max(1,Math.ceil(rows.length/7));
    for(let i=0;i<rows.length;i+=step){
      const xx=xAt(i);
      const q=state.question;
      const blind=$('blindMode').checked && !state.trade && state.closedTrades.length===0 && state.revealed<q.maxFutureDays;
      const label=blind?relativeDayLabel(rows[i].index-q.cutoff):formatShortDate(rows[i].time);
      ctx.save();ctx.translate(xx,bottomY+7);ctx.rotate(-Math.PI/5);ctx.fillStyle='#77859b';ctx.font='9px sans-serif';ctx.textAlign='right';ctx.textBaseline='top';ctx.fillText(label,0,0);ctx.restore();
    }
    ctx.restore();
    return { topY, bottomY, y, minVal, maxVal, points };
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
    const point=cciPointForRow(r);
    const timeline=timelineRowForRow(r);
    const pred=(timeline && state.activeModel) ? lookupProbability(state.activeModel, timeline.state, MODEL_HORIZON, timeline.features || {}) : null;
    const comment=timeline ? buildCciPathCommentary(timeline.state, timeline.features || {}, pred) : null;
    const cciText=point ? `<br>CCI ${Number.isFinite(point.cci)?point.cci.toFixed(1):'—'}　SMA14 ${Number.isFinite(point.sma)?point.sma.toFixed(1):'—'}${comment?`<br>${escapeHtml(comment.label)}`:''}` : '';
    tooltip.innerHTML = `${date}<br>O ${formatPrice(r.open)}　H ${formatPrice(r.high)}<br>L ${formatPrice(r.low)}　C ${formatPrice(r.close)}<br>HA ${haColor} ${formatPrice(r.ha.close)}${r.bb?`<br>BB中軌 ${formatPrice(r.bb.basis)}`:''}${cciText}`;
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

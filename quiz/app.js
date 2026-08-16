(() => {
  'use strict';

  const CONTEXT_DAYS = 30;
  const BB_PERIOD = 20;
  const MIN_CUTOFF_INDEX = (CONTEXT_DAYS - 1) + (BB_PERIOD - 1); // first visible day also has a full BB20
  const DAY_MS = 24 * 60 * 60 * 1000;

  const state = {
    symbols: [],
    question: null,
    choice: null,
    revealed: 0,
    playing: false,
    timer: null,
    hoverIndex: null,
    stats: loadStats(),
  };

  const $ = (id) => document.getElementById(id);
  const canvas = $('chartCanvas');
  const ctx = canvas.getContext('2d');
  const tooltip = $('chartTooltip');

  function loadStats() {
    try {
      const raw = JSON.parse(localStorage.getItem('sstate_quiz_stats') || '{}');
      return { total: Number(raw.total) || 0, hit: Number(raw.hit) || 0 };
    } catch (_) {
      return { total: 0, hit: 0 };
    }
  }

  function saveStats() {
    localStorage.setItem('sstate_quiz_stats', JSON.stringify(state.stats));
    renderStats();
  }

  function renderStats() {
    $('statTotal').textContent = state.stats.total;
    $('statHit').textContent = state.stats.hit;
    $('statRate').textContent = state.stats.total ? `${(state.stats.hit / state.stats.total * 100).toFixed(1)}%` : '—';
  }

  async function init() {
    renderStats();
    bindEvents();
    resizeCanvas();
    window.addEventListener('resize', () => { resizeCanvas(); draw(); });

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
  }

  function bindEvents() {
    $('newQuestionBtn').addEventListener('click', newQuestion);
    $('playBtn').addEventListener('click', togglePlay);
    $('stepBtn').addEventListener('click', revealOne);
    $('resetRevealBtn').addEventListener('click', resetReveal);
    $('futureDaysSelect').addEventListener('change', () => state.question && newQuestion());
    $('blindMode').addEventListener('change', renderQuestionMeta);
    document.querySelectorAll('.decision').forEach(btn => {
      btn.addEventListener('click', () => choose(btn.dataset.choice));
    });

    canvas.addEventListener('mousemove', onCanvasMove);
    canvas.addEventListener('mouseleave', () => {
      state.hoverIndex = null;
      tooltip.classList.add('hidden');
      draw();
    });
  }

  async function newQuestion() {
    stopPlayback();
    resetDecisionUI();
    $('resultPanel').classList.add('hidden');
    $('chartEmpty').classList.remove('hidden');
    $('chartEmpty').textContent = '隨機抽取歷史片段…';
    setLoadState('抽題中');

    const futureDays = Number($('futureDaysSelect').value) || 7;
    let lastError = null;

    for (let attempt = 0; attempt < 12; attempt++) {
      const symbol = state.symbols[Math.floor(Math.random() * state.symbols.length)];
      try {
        const fourH = await loadCsv(symbol);
        const daily = aggregate4hToDaily(fourH);
        if (daily.length < MIN_CUTOFF_INDEX + futureDays + 2) continue;

        const ha = calculateHeikinAshi(daily);
        const bb = rollingBollinger(daily);
        const latestCutoff = daily.length - futureDays - 1;
        const earliestCutoff = MIN_CUTOFF_INDEX;
        if (latestCutoff <= earliestCutoff) continue;

        // Avoid the newest 2 days so a daily update cannot turn the answer into a still-forming edge case.
        const cappedLatest = Math.max(earliestCutoff, latestCutoff - 2);
        const cutoff = randomInt(earliestCutoff, cappedLatest);
        const contextStart = cutoff - CONTEXT_DAYS + 1;
        const end = Math.min(daily.length - 1, cutoff + futureDays);

        const rows = daily.map((d, i) => ({ ...d, ha: ha[i], bb: bb[i], index: i }));
        state.question = { symbol, rows, contextStart, cutoff, end, futureDays };
        state.choice = null;
        state.revealed = 0;
        state.hoverIndex = null;

        $('chartEmpty').classList.add('hidden');
        setLoadState(`題庫 ${state.symbols.length} 種市場`);
        renderQuestionMeta();
        draw();
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

  // Matches engine/runtime_core.py aggregate_4h_to_daily(): group by UTC day first.
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

  // Matches engine/runtime_core.py calculate_heikin_ashi().
  function calculateHeikinAshi(rows) {
    const out = [];
    let prevOpen = null;
    let prevClose = null;
    rows.forEach((c, i) => {
      const haClose = (c.open + c.high + c.low + c.close) / 4;
      const haOpen = i === 0 ? (c.open + c.close) / 2 : (prevOpen + prevClose) / 2;
      const item = {
        open: haOpen,
        high: Math.max(c.high, haOpen, haClose),
        low: Math.min(c.low, haOpen, haClose),
        close: haClose,
        color: haClose > haOpen ? 'yellow' : haClose < haOpen ? 'purple' : 'flat',
      };
      out.push(item);
      prevOpen = haOpen;
      prevClose = haClose;
    });
    return out;
  }

  // Matches engine/runtime_core.py BB20: ordinary daily close, population std (ddof=0), basis ± 2σ.
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

  function choose(choice) {
    if (!state.question || state.choice) return;
    state.choice = choice;
    document.querySelectorAll('.decision').forEach(btn => {
      btn.disabled = true;
      btn.classList.toggle('selected', btn.dataset.choice === choice);
    });
    $('playBtn').disabled = false;
    $('stepBtn').disabled = false;
    $('resetRevealBtn').disabled = false;
    $('choiceBadge').textContent = choice === 'LONG' ? '你的判斷：做多' : choice === 'SHORT' ? '你的判斷：做空' : '你的判斷：觀望';
    $('choiceBadge').style.color = choice === 'LONG' ? 'var(--green)' : choice === 'SHORT' ? 'var(--red)' : '#d4dceb';
    renderQuestionMeta();
    updateProgress();
    draw();
  }

  function resetDecisionUI() {
    state.choice = null;
    state.revealed = 0;
    document.querySelectorAll('.decision').forEach(btn => { btn.disabled = false; btn.classList.remove('selected'); });
    $('playBtn').disabled = true;
    $('stepBtn').disabled = true;
    $('resetRevealBtn').disabled = true;
    $('playBtn').textContent = '▶ 播放結果';
    $('choiceBadge').textContent = '尚未選擇';
    $('choiceBadge').style.color = '';
    updateProgress();
  }

  function resetReveal() {
    stopPlayback();
    state.revealed = 0;
    $('resultPanel').classList.add('hidden');
    $('playBtn').textContent = '▶ 播放結果';
    updateProgress();
    draw();
  }

  function togglePlay() {
    if (!state.choice || !state.question) return;
    if (state.playing) {
      stopPlayback();
      return;
    }
    if (state.revealed >= availableFutureBars()) resetReveal();
    state.playing = true;
    $('playBtn').textContent = '⏸ 暫停';
    const tick = () => {
      if (!state.playing) return;
      revealOne();
      if (state.revealed >= availableFutureBars()) {
        stopPlayback();
        return;
      }
      state.timer = setTimeout(tick, Number($('speedSelect').value) || 650);
    };
    tick();
  }

  function stopPlayback() {
    state.playing = false;
    if (state.timer) clearTimeout(state.timer);
    state.timer = null;
    if ($('playBtn')) $('playBtn').textContent = '▶ 播放結果';
  }

  function availableFutureBars() {
    if (!state.question) return 0;
    return state.question.end - state.question.cutoff;
  }

  function revealOne() {
    if (!state.question || !state.choice) return;
    const max = availableFutureBars();
    if (state.revealed < max) state.revealed += 1;
    updateProgress();
    renderQuestionMeta();
    draw();
    if (state.revealed >= max) finishQuestion();
  }

  function updateProgress() {
    const max = availableFutureBars();
    const pct = max ? Math.min(100, state.revealed / max * 100) : 0;
    $('progressBar').style.width = `${pct}%`;
    $('progressText').textContent = state.choice ? `${state.revealed} / ${max} 天` : '尚未作答';
  }

  function finishQuestion() {
    if (!state.question || !state.choice) return;
    renderResults();
    if (!state.question.scored && state.choice !== 'WAIT') {
      const r3 = returnAt(3);
      if (r3 !== null) {
        state.stats.total += 1;
        const hit = (state.choice === 'LONG' && r3 > 0) || (state.choice === 'SHORT' && r3 < 0);
        if (hit) state.stats.hit += 1;
        state.question.scored = true;
        saveStats();
      }
    }
  }

  function returnAt(days) {
    if (!state.question) return null;
    const q = state.question;
    const idx = q.cutoff + days;
    if (idx > q.end || idx <= q.cutoff) return null;
    return (q.rows[idx].close / q.rows[q.cutoff].close - 1) * 100;
  }

  function renderResults() {
    const q = state.question;
    const entry = q.rows[q.cutoff].close;
    const future = q.rows.slice(q.cutoff + 1, q.end + 1);
    const ret = (n) => returnAt(n);
    const maxHigh = Math.max(...future.map(x => x.high));
    const minLow = Math.min(...future.map(x => x.low));
    const mfeLong = (maxHigh / entry - 1) * 100;
    const maeLong = (minLow / entry - 1) * 100;

    setMetric('ret1', ret(1));
    setMetric('ret3', ret(3));
    setMetric('ret7', ret(7));

    let mfe = mfeLong, mae = maeLong;
    if (state.choice === 'SHORT') {
      mfe = (entry / minLow - 1) * 100;
      mae = (entry / maxHigh - 1) * 100;
    }
    if (state.choice === 'WAIT') {
      mfe = mfeLong;
      mae = maeLong;
    }
    setMetric('mfe', mfe);
    setMetric('mae', mae);

    const r3 = ret(3);
    const verdict = $('verdict');
    const note = $('verdictNote');
    const card = verdict.closest('.metric');
    card.classList.remove('positive','negative','neutral');

    if (state.choice === 'WAIT') {
      verdict.textContent = '已觀望';
      note.textContent = `3D 實際 ${fmtPct(r3)}；不計入命中率`;
      card.classList.add('neutral');
    } else {
      const hit = (state.choice === 'LONG' && r3 > 0) || (state.choice === 'SHORT' && r3 < 0);
      verdict.textContent = hit ? '方向命中' : '方向錯誤';
      note.textContent = `以第 3 天收盤 ${fmtPct(r3)} 判定`;
      card.classList.add(hit ? 'positive' : 'negative');
    }
    $('resultPanel').classList.remove('hidden');
  }

  function setMetric(id, value) {
    const el = $(id);
    el.textContent = value === null ? '—' : fmtPct(value);
    const card = el.closest('.metric');
    card.classList.remove('positive','negative','neutral');
    if (value === null || Math.abs(value) < 1e-10) card.classList.add('neutral');
    else card.classList.add(value > 0 ? 'positive' : 'negative');
  }

  function renderQuestionMeta() {
    if (!state.question) return;
    const q = state.question;
    const blind = $('blindMode').checked && !state.choice;
    const cutoffDate = formatDate(q.rows[q.cutoff].time);
    $('marketTitle').textContent = blind ? '隨機市場 · 盲測中' : `${q.symbol} / USDT`;
    $('marketMeta').textContent = blind ? `30 日結構 · 截止日已隱藏 · 未來 ${q.futureDays} 天未顯示` : `判斷截止：${cutoffDate} · 已揭曉 ${state.revealed}/${availableFutureBars()} 天`;
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

  function draw() {
    const w = canvas._cssWidth || canvas.clientWidth;
    const h = canvas._cssHeight || canvas.clientHeight;
    ctx.clearRect(0,0,w,h);
    ctx.fillStyle = '#080d15';
    ctx.fillRect(0,0,w,h);
    if (!state.question) return;

    const q = state.question;
    const lastVisible = Math.min(q.end, q.cutoff + state.revealed);
    const rows = q.rows.slice(q.contextStart, lastVisible + 1);
    if (!rows.length) return;

    const pad = { left:16, right:82, top:22, bottom:34 };
    const plotW = w - pad.left - pad.right;
    const plotH = h - pad.top - pad.bottom;
    const values = [];
    rows.forEach(r => {
      values.push(r.high, r.low);
      if (r.bb) values.push(r.bb.upper, r.bb.lower);
      if (r.ha) values.push(r.ha.close);
    });
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

    // Ordinary daily candlesticks.
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

    // HA yellow/purple staircase. Height is HA close; color comes from HA close vs HA open.
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

    const cutoffLocal = q.cutoff - q.contextStart;
    if (cutoffLocal >= 0 && cutoffLocal < rows.length) {
      const boundary = cutoffLocal === rows.length-1 ? pad.left + plotW - plotW/rows.length/2 : (xAt(cutoffLocal) + xAt(cutoffLocal+1))/2;
      ctx.save();
      ctx.setLineDash([5,5]); ctx.strokeStyle = 'rgba(255,255,255,.6)'; ctx.lineWidth=1;
      ctx.beginPath(); ctx.moveTo(boundary,pad.top); ctx.lineTo(boundary,pad.top+plotH); ctx.stroke();
      ctx.restore();
      ctx.fillStyle='rgba(235,242,255,.78)'; ctx.font='11px sans-serif'; ctx.textAlign='right';
      ctx.fillText('判斷點', boundary-6, pad.top+14);
    }

    if (state.hoverIndex !== null && state.hoverIndex >= 0 && state.hoverIndex < rows.length) {
      const x = xAt(state.hoverIndex);
      ctx.strokeStyle='rgba(221,232,247,.35)'; ctx.lineWidth=1;
      ctx.beginPath(); ctx.moveTo(x,pad.top); ctx.lineTo(x,pad.top+plotH); ctx.stroke();
    }

    canvas._layout = { rows, pad, plotW, plotH, min, max, xAt, yAt };
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
      const absoluteIndex=rows[i].index;
      const blind=$('blindMode').checked && !state.choice;
      const label=blind ? relativeDayLabel(absoluteIndex-q.cutoff) : formatShortDate(rows[i].time);
      ctx.fillText(label,x,pad.top+plotH+8);
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
    const blind=$('blindMode').checked && !state.choice;
    const date=blind ? relativeDayLabel(r.index-q.cutoff) : formatDate(r.time);
    const haColor=r.ha.color==='yellow'?'黃':'紫';
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
  function fmtPct(v) { return v===null || !Number.isFinite(v) ? '—' : `${v>=0?'+':''}${v.toFixed(2)}%`; }

  init();
})();

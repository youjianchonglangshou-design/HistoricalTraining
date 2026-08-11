"""HA 階梯型態旗標、型態名稱與機械分數。

本地版保留正式 snapshot 使用的欄位名稱、三燈語意及分數封頂。
"""
from __future__ import annotations
import math
from typing import Any


def _f(v: Any, default=0.0) -> float:
    try:
        return float(v)
    except Exception:
        return float(default)


def _round(v, n=6):
    return round(_f(v), n)


def _transition_count(colors: list[str]) -> int:
    return sum(1 for a, b in zip(colors, colors[1:]) if a != b)


def _current_run(history: list[dict]) -> dict:
    if not history:
        return {"color": "unknown", "start_index": 0, "length": 0}
    color = history[-1].get("color", "unknown")
    i = len(history) - 1
    while i > 0 and history[i - 1].get("color") == color:
        i -= 1
    return {"color": color, "start_index": i, "length": len(history) - i}


def _build_ladder_trigger_light(latest_color: str, yellow_run_length: int, r: dict) -> dict:
    series = list(r.get("_ha4h_color_series") or [])
    current_pair_red_green = len(series) >= 2 and series[-2:] == ["🔴", "🟢"]
    current_pair_green_green = len(series) >= 2 and series[-2:] == ["🟢", "🟢"]
    previous_pair_red_green = len(series) >= 3 and series[-3:-1] == ["🔴", "🟢"]
    green_extension_after_rg = current_pair_green_green and previous_pair_red_green
    is_yellow = latest_color == "yellow"
    mature = bool(is_yellow and yellow_run_length >= 2)

    if mature and (current_pair_red_green or green_extension_after_rg):
        state = "green"
        label = "L2+ 啟動" if current_pair_red_green else "L2+ 延續"
    elif mature:
        state = "yellow"
        if r.get("4H前") == "🟢" and r.get("4H當") == "🔴":
            label = "L2+ 轉弱"
        elif current_pair_green_green:
            label = "L2+ 綠綠未觸發"
        else:
            label = "L2+ 待4H"
    else:
        state = "red"
        label = "L1 未成熟" if is_yellow and yellow_run_length == 1 else "Reset"

    return {
        "ladder_trigger_state": state,
        "ladder_trigger_label": label,
        "ladder_trigger_light": state,
        "ladder_trigger_active": state == "green",
        "yellow_run_length": yellow_run_length,
        "ladder_trigger_mature": mature,
        "current_4h_pair_red_green": current_pair_red_green,
        "current_4h_pair_green_green": current_pair_green_green,
        "previous_4h_pair_red_green": previous_pair_red_green,
        "green_extension_after_red_green": green_extension_after_rg,
        "four_h_color_series_tail": series[-6:],
    }


def build_pattern_flags(r: dict, ladder_history: list[dict]) -> dict:
    ready = len(ladder_history) >= 5
    latest = ladder_history[-1] if ladder_history else {}
    latest_color = latest.get("color", "unknown")
    latest_pct = _f(latest.get("pct_vs_midline"), 0.0)
    run = _current_run(ladder_history)
    start = int(run.get("start_index", 0))
    yellow_run_length = run["length"] if latest_color == "yellow" else 0
    light = _build_ladder_trigger_light(latest_color, yellow_run_length, r)

    before = ladder_history[:start]
    had_yellow_above = any(x.get("color") == "yellow" and _f(x.get("pct_vs_midline")) >= 0 for x in before)
    had_any_above = any(_f(x.get("pct_vs_midline")) >= 0 for x in before)
    recent_before = before[-8:]
    recent_above = any(_f(x.get("pct_vs_midline")) >= 0 for x in recent_before)
    bars_since_last_above = None
    for idx in range(len(ladder_history) - 2, -1, -1):
        if _f(ladder_history[idx].get("pct_vs_midline")) >= 0:
            bars_since_last_above = len(ladder_history) - 1 - idx
            break

    prev_run = []
    if start > 0:
        prev_color = ladder_history[start - 1].get("color")
        j = start - 1
        while j >= 0 and ladder_history[j].get("color") == prev_color:
            prev_run.append(ladder_history[j])
            j -= 1
        prev_run.reverse()
    prev_purple_run = prev_run if prev_run and prev_run[-1].get("color") == "purple" else []
    purple_near = bool(prev_purple_run and any(abs(_f(x.get("pct_vs_midline"))) <= 3.0 for x in prev_purple_run))
    purple_not_deep = bool(prev_purple_run and min(_f(x.get("pct_vs_midline")) for x in prev_purple_run) >= -5.0)
    breakout_restart = bool(latest_color == "yellow" and had_yellow_above and purple_near and purple_not_deep)

    previous_purples = [x for x in before if x.get("color") == "purple"][-3:]
    previous_purple_pcts = [_round(x.get("pct_vs_midline")) for x in previous_purples]
    yellow_ref = _f(ladder_history[start].get("pct_vs_midline"), latest_pct) if latest_color == "yellow" else _f(next((x.get("pct_vs_midline") for x in reversed(before) if x.get("color") == "yellow"), latest_pct))
    over_count = sum(1 for x in previous_purple_pcts if yellow_ref > x)

    colors8 = [x.get("color") for x in ladder_history[-8:]]
    colors6 = [x.get("color") for x in ladder_history[-6:]]
    colors5 = [x.get("color") for x in ladder_history[-5:]]
    transitions8 = _transition_count(colors8)
    transitions6 = _transition_count(colors6)
    transitions5 = _transition_count(colors5)
    recent_yellow = sum(c == "yellow" for c in colors8)
    recent_purple = sum(c == "purple" for c in colors8)

    previous_step = _f(ladder_history[-2].get("pct_vs_midline"), latest_pct) if len(ladder_history) >= 2 else latest_pct
    first_run_pct = _f(ladder_history[start].get("pct_vs_midline"), latest_pct)
    lift_previous = latest_pct - previous_step
    run_lift = latest_pct - first_run_pct
    if previous_purple_pcts:
        margins = [latest_pct - p for p in previous_purple_pcts]
        avg_margin = sum(margins) / len(margins)
        max_margin = max(margins)
        min_margin = min(margins)
        rebound_low = latest_pct - min(previous_purple_pcts)
    else:
        avg_margin = max_margin = min_margin = rebound_low = 0.0

    below_candidate = bool(latest_color == "yellow" and latest_pct < 0 and over_count >= 2)
    clean_fast = bool(below_candidate and yellow_run_length <= 3 and transitions6 <= 1)
    interrupted = transitions6 >= 2
    rapid = bool(rebound_low >= 3.0 or run_lift >= 3.0)
    strong = bool(below_candidate and over_count >= 2 and clean_fast and rapid)
    w_bottom = bool(below_candidate and not strong and over_count >= 2 and (interrupted or yellow_run_length >= 2))
    early = bool(latest_color == "yellow" and latest_pct < 0 and yellow_run_length == 1 and over_count >= 1 and rebound_low < 3.0)
    quality = "strong_fast_reclaim" if strong else ("w_bottom_candidate" if w_bottom else ("early_weak_rebound" if early else "none"))

    four_h_rg = r.get("4H前") == "🔴" and r.get("4H當") == "🟢"
    four_h_gg = r.get("4H前") == "🟢" and r.get("4H當") == "🟢"
    four_h_label = "4H前紅→4H當綠：最佳啟動" if four_h_rg else ("4H綠→綠：偏多延續" if four_h_gg else "4H未啟動或偏弱")

    flags = {
        **light,
        "analysis_ready": ready,
        "latest_color": latest_color,
        "latest_color_emoji": {"yellow": "🟡", "purple": "🟣", "flat": "⚫"}.get(latest_color, "—"),
        "latest_pct_vs_midline": _round(latest_pct),
        "latest_above_midline": latest_pct >= 0,
        "latest_near_midline": abs(latest_pct) <= 3.0,
        "current_color_run": run,
        "had_yellow_above_midline_before_current_run": had_yellow_above,
        "had_any_above_midline_before_current_run": had_any_above,
        "recent_above_midline_before_current_run": recent_above,
        "bars_since_last_above_midline": bars_since_last_above,
        "prior_breakout_then_pullback_reclaim": bool(latest_color == "yellow" and latest_pct >= 0 and had_any_above and start > 0),
        "structurally_suppressed_never_touched_midline": not any(_f(x.get("pct_vs_midline")) >= 0 for x in ladder_history),
        "purple_pullback_near_midline_after_breakout": purple_near,
        "purple_pullback_not_deep_broken": purple_not_deep,
        "breakout_pullback_yellow_restart": breakout_restart,
        "previous_purple_pcts_for_po3": previous_purple_pcts,
        "yellow_ref_pct_for_po3": _round(yellow_ref),
        "yellow_over_previous_purple_count": over_count,
        "yellow_over_2_previous_purple_steps": over_count >= 2,
        "yellow_over_3_previous_purple_steps": over_count >= 3,
        "below_midline_po3_amd_candidate": below_candidate,
        "po3_amd_quality_label": quality,
        "po3_amd_strong_reversal": strong,
        "po3_amd_w_bottom_candidate": w_bottom,
        "po3_amd_early_weak_rebound": early,
        "recent_color_transitions_8d": transitions8,
        "recent_color_transitions_6d": transitions6,
        "recent_color_transitions_5d": transitions5,
        "clean_fast_reclaim_run": clean_fast,
        "interrupted_reclaim_by_color_mix": interrupted,
        "rapid_reclaim_magnitude": rapid,
        "strong_reclaim_run_length_days": run.get("length", 0),
        "recent_yellow_count_8d": recent_yellow,
        "recent_purple_count_8d": recent_purple,
        "lift_from_previous_step_pct": _round(lift_previous),
        "current_yellow_run_lift_pct": _round(run_lift),
        "avg_reclaim_margin_vs_prev3_purple_pct": _round(avg_margin),
        "max_reclaim_margin_vs_prev3_purple_pct": _round(max_margin),
        "min_reclaim_margin_vs_prev3_purple_pct": _round(min_margin),
        "rebound_from_recent_purple_low_pct": _round(rebound_low),
        "four_h_red_to_green": four_h_rg,
        "four_h_green_green": four_h_gg,
        "four_h_trigger_label": four_h_label,
    }
    return flags


def classify_pattern(flags: dict) -> str:
    if flags.get("breakout_pullback_yellow_restart"):
        return "中軌突破回踩轉黃型"
    if flags.get("po3_amd_strong_reversal"):
        return "中軌下方 PO3/AMD 強反轉型"
    if flags.get("po3_amd_w_bottom_candidate"):
        return "中軌下方 PO3/AMD 反轉候選型"
    if flags.get("po3_amd_early_weak_rebound"):
        return "中軌下方 PO3/AMD 轉黃早期觀察型"
    if flags.get("latest_color") == "yellow" and flags.get("latest_near_midline"):
        return "中軌附近磨合轉黃型"
    if flags.get("latest_color") == "purple":
        return "紫線未轉黃觀察型"
    return "一般觀察型"


def score_hint(flags: dict, item: dict) -> int:
    pattern = classify_pattern(flags)
    latest = _f(flags.get("latest_pct_vs_midline"))
    abs_dev = abs(_f(item.get("abs_dev", item.get("_abs_dev", 999))))
    over = int(flags.get("yellow_over_previous_purple_count") or 0)
    rg = bool(flags.get("four_h_red_to_green"))
    gg = bool(flags.get("four_h_green_green"))
    near = abs(latest) <= 3
    above = latest >= 0

    if pattern == "中軌突破回踩轉黃型":
        score = 76 + (10 if near else 0) + (8 if above else 0) + (2 if over >= 2 else 0) + (4 if rg else 0)
        if latest < 0: score = min(score, 80)
        if not rg and not gg: score = min(score, 90)
        if abs_dev > 7: score = min(score, 76)
        elif abs_dev > 5: score = min(score, 82)
        elif abs_dev > 3: score = min(score, 90)
        return max(0, min(100, int(score)))

    if pattern == "中軌下方 PO3/AMD 強反轉型":
        score = 66 + (8 if over >= 3 else 4) + (8 if flags.get("rapid_reclaim_magnitude") else 0) + (6 if rg else 3 if gg else 0)
        return min(88, int(score))

    if pattern == "中軌下方 PO3/AMD 反轉候選型":
        score = 52 + (14 if over >= 3 else 8) + (8 if flags.get("rapid_reclaim_magnitude") else 0) + (8 if rg else 4 if gg else 0) + (4 if near else 0)
        return min(80, int(score))

    if pattern == "中軌下方 PO3/AMD 轉黃早期觀察型":
        score = 36 + (8 if rg else 4 if gg else 0) + (6 if near else 0) + (4 if over >= 2 else 0)
        return min(55, int(score))

    if pattern == "中軌附近磨合轉黃型":
        score = 58 + (10 if near else 0) + (8 if above else 0) + (8 if rg else 4 if gg else 0)
        return min(84, int(score))

    if pattern == "紫線未轉黃觀察型":
        score = 0
        if abs(latest) <= 3: score += 18
        if abs(latest) <= 1: score += 6
        if rg: score += 18
        elif gg: score += 8
        if latest >= 0: score += 6
        return min(42, int(score))

    score = 14
    if flags.get("latest_color") == "yellow": score += 18
    if near: score += 15
    if above: score += 10
    if rg: score += 12
    elif gg: score += 8
    return min(75, int(score))

# ==================== Opportunity Geometry（做多機會掃描 v3） ====================
# 星級只代表「現在還有多少做多進場價值」，不是趨勢強弱。
# v3.3：Purple-2 先做結構世代，再做 L/R；Coffee 用 0.618，W 失效用 1.236，並加入真實日K structural break。

OPPORTUNITY_ENGINE_VERSION = "OG v4.8｜30D-STRUCT-BB20"
PURPLE2_RULE_VERSION = "DP2-v11-state-scoped-30d"
ENGINE_API_VERSION = "opportunity-state-v4.8-30d-structure"

# 星級只代表「現在還有多少做多進場價值」，不是趨勢強弱。
# v2 重點：自適應中軌距離、真正中軌突破事件、Dynamic Purple-2 Anchor（V/V + Fib）。

MIDLINE_RISING_SLOPE_PCT_PER_DAY = 0.12
MIDLINE_FLAT_FLOOR_PCT_PER_DAY = -0.25
MIDLINE_FLATTENING_MAX_FALL_PCT_PER_DAY = -0.65
MIDLINE_FLATTENING_IMPROVEMENT_MIN = 0.12

# 不再固定用「距中軌 ±3%」。0.5 是中軌；以下用每顆幣自己的 BB 寬度正規化。
MIDLINE_NEAR_BANDPOS_DISTANCE = 0.18       # 約 band_pos 0.32 ~ 0.68
MIDLINE_SWEET_UPPER_BANDPOS = 0.68
MIDLINE_ALREADY_MOVED_BANDPOS = 0.85
S1_ACTIVE_MAX_BANDPOS = 0.75
S2_ACTIVE_MAX_BANDPOS = 0.78
S3_ACTIVE_MAX_BANDPOS = 0.75
S2_BREAKDOWN_FLOOR_BANDPOS = 0.38
S2_FIRST_WAVE_PEAK_MIN_BANDPOS = 0.62
BASE_BRIDGE_MIN_BANDPOS_LIFT = 0.08
MATURE_UPPER_BANDPOS = 0.88
MATURE_LOWER_BANDPOS = 0.14

BREAKOUT_CONFIRM_BANDPOS = 0.72
BREAKOUT_INVALIDATE_BANDPOS = 0.15
RETEST_FAKE_BREAK_BANDPOS = 0.32
FIB_CUP_RIGHT_MIN = 0.000
FIB_CUP_RIGHT_MAX = 0.618
FIB_W_RIGHT_MIN = 1.000
FIB_W_RIGHT_MAX = 1.236
FIB_W_GENERATION_MAX = 1.236


def _opportunity_points(r: dict) -> list[dict[str, Any]]:
    """從 main.py 的 30 日原始序列，或 snapshot chart_30d，建立統一幾何點。舊 chart_20d 仍可回放。"""
    existing = r.get("chart_30d") or r.get("chart_20d")
    if isinstance(existing, list) and existing:
        out = []
        for idx, point in enumerate(existing[-30:]):
            out.append({
                "index": idx,
                "date": str(point.get("date") or idx),
                "open": _f(point.get("ha_open")),
                "close": _f(point.get("ha_close")),
                "color": str(point.get("ha_color") or "unknown"),
                "pct": _f(point.get("ha_vs_midline_pct")),
                "mid": _f(point.get("bb_midline")),
                "upper": _f(point.get("bb_upper")),
                "lower": _f(point.get("bb_lower")),
                "width": _f(point.get("band_width_pct")),
                "band_pos": _f(point.get("ha_band_position"), 0.5),
                "real_open": _f(point.get("real_open"), float("nan")),
                "real_high": _f(point.get("real_high"), float("nan")),
                "real_low": _f(point.get("real_low"), float("nan")),
                "real_close": _f(point.get("real_close"), float("nan")),
            })
        return out

    opens = list(r.get("_ha_opens_last30") or r.get("_ha_opens_last20") or [])
    closes = list(r.get("_ha_closes_last30") or r.get("_ha_closes_last20") or [])
    pcts = list(r.get("_ha_pct_series") or [])
    mids = list(r.get("_bb_basis_series") or [])
    uppers = list(r.get("_bb_upper_series") or [])
    lowers = list(r.get("_bb_lower_series") or [])
    times = list(r.get("_ha_times_last30") or r.get("_ha_times_last20") or [])
    raw_opens = list(r.get("_raw_opens_last30") or r.get("_raw_opens_last20") or [])
    raw_highs = list(r.get("_raw_highs_last30") or r.get("_raw_highs_last20") or [])
    raw_lows = list(r.get("_raw_lows_last30") or r.get("_raw_lows_last20") or [])
    raw_closes = list(r.get("_raw_closes_last30") or r.get("_raw_closes_last20") or [])
    count = min(30, len(opens), len(closes), len(pcts), len(mids), len(uppers), len(lowers))
    if count <= 0:
        return []
    opens = opens[-count:]
    closes = closes[-count:]
    pcts = pcts[-count:]
    mids = mids[-count:]
    uppers = uppers[-count:]
    lowers = lowers[-count:]
    times = times[-count:] if times else list(range(count))
    raw_opens = raw_opens[-count:] if len(raw_opens) >= count else []
    raw_highs = raw_highs[-count:] if len(raw_highs) >= count else []
    raw_lows = raw_lows[-count:] if len(raw_lows) >= count else []
    raw_closes = raw_closes[-count:] if len(raw_closes) >= count else []

    out = []
    for idx in range(count):
        open_v = _f(opens[idx])
        close_v = _f(closes[idx])
        upper_v = _f(uppers[idx])
        lower_v = _f(lowers[idx])
        mid_v = _f(mids[idx])
        color = "yellow" if close_v > open_v else "purple" if close_v < open_v else "flat"
        width = ((upper_v-lower_v)/abs(mid_v)*100.0) if abs(mid_v) > 1e-18 else 0.0
        band_pos = ((close_v-lower_v)/(upper_v-lower_v)) if abs(upper_v-lower_v) > 1e-18 else 0.5
        try:
            from datetime import datetime, timezone
            date_text = datetime.fromtimestamp(float(times[idx])/1000.0, tz=timezone.utc).strftime("%m/%d")
        except Exception:
            date_text = str(idx)
        out.append({
            "index": idx,
            "date": date_text,
            "open": open_v,
            "close": close_v,
            "color": color,
            "pct": _f(pcts[idx]),
            "mid": mid_v,
            "upper": upper_v,
            "lower": lower_v,
            "width": width,
            "band_pos": band_pos,
            "real_open": _f(raw_opens[idx], float("nan")) if raw_opens else float("nan"),
            "real_high": _f(raw_highs[idx], float("nan")) if raw_highs else float("nan"),
            "real_low": _f(raw_lows[idx], float("nan")) if raw_lows else float("nan"),
            "real_close": _f(raw_closes[idx], float("nan")) if raw_closes else float("nan"),
        })
    return out


def _slope_pct_per_day(values: list[float]) -> float:
    vals = [_f(v) for v in values]
    if len(vals) < 2:
        return 0.0
    mean = sum(vals) / len(vals)
    if abs(mean) < 1e-18:
        return 0.0
    n = len(vals)
    x_mean = (n - 1) / 2.0
    denom = sum((i - x_mean) ** 2 for i in range(n))
    if denom <= 0:
        return 0.0
    slope = sum((i - x_mean) * (vals[i] - mean) for i in range(n)) / denom
    return slope / abs(mean) * 100.0


def _midline_regime(points: list[dict[str, Any]]) -> dict[str, Any]:
    mids = [_f(p.get("mid")) for p in points]
    recent = mids[-5:]
    previous = mids[-10:-5] if len(mids) >= 10 else mids[:-5]
    recent_slope = _slope_pct_per_day(recent)
    previous_slope = _slope_pct_per_day(previous) if len(previous) >= 2 else recent_slope
    improvement = recent_slope - previous_slope

    # BNB 這類肉眼明顯微微上斜，不再被 +0.25%/日硬切成平緩。
    if recent_slope >= MIDLINE_RISING_SLOPE_PCT_PER_DAY:
        state, symbol, label = "rising", "↑", "上斜"
    elif recent_slope > MIDLINE_FLAT_FLOOR_PCT_PER_DAY:
        state, symbol, label = "flat", "→", "平緩"
    elif (
        recent_slope >= MIDLINE_FLATTENING_MAX_FALL_PCT_PER_DAY
        and improvement >= MIDLINE_FLATTENING_IMPROVEMENT_MIN
    ):
        state, symbol, label = "flattening", "↘", "下降走平中"
    else:
        state, symbol, label = "falling", "↓", "下斜"

    return {
        "state": state,
        "symbol": symbol,
        "label": label,
        "recent_5d_slope_pct_per_day": _round(recent_slope),
        "previous_5d_slope_pct_per_day": _round(previous_slope),
        "slope_improvement_pct_per_day": _round(improvement),
        "long_friendly": state in {"rising", "flat", "flattening"},
    }


def _run_start(points: list[dict[str, Any]], end_idx: int) -> int:
    if not points or end_idx < 0:
        return 0
    color = points[end_idx].get("color")
    idx = end_idx
    while idx > 0 and points[idx-1].get("color") == color:
        idx -= 1
    return idx


def _near_midline(point: dict[str, Any]) -> bool:
    """用 BB 幾何距離而非固定百分比判斷是否貼近中軌。"""
    return abs(_f(point.get("band_pos"), 0.5) - 0.5) <= MIDLINE_NEAR_BANDPOS_DISTANCE


def _purple_runs(points: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs: list[dict[str, Any]] = []
    i = 0
    run_id = 0
    while i < len(points):
        if points[i].get("color") != "purple":
            i += 1
            continue
        start = i
        while i + 1 < len(points) and points[i+1].get("color") == "purple":
            i += 1
        end = i
        indices = list(range(start, end + 1))
        # 同價最低點採第一個，避免平台底最後一根讓「紫2」變得過度容易。
        low_idx = min(indices, key=lambda j: (_f(points[j].get("close")), j))
        p2_idx = low_idx - 1 if low_idx > start and points[low_idx-1].get("color") == "purple" else None
        runs.append({
            "run_id": run_id,
            "start": start,
            "end": end,
            "length": end - start + 1,
            "low_idx": low_idx,
            "low_price": _f(points[low_idx].get("close")),
            "low_pct": _f(points[low_idx].get("pct")),
            "purple2_idx": p2_idx,
            "eligible_purple2": p2_idx is not None,
        })
        run_id += 1
        i += 1
    return runs


def _active_purple_run_id(points: list[dict[str, Any]], runs: list[dict[str, Any]]) -> int | None:
    if not runs:
        return None
    latest_idx = len(points) - 1
    if points[latest_idx].get("color") == "purple":
        for run in reversed(runs):
            if run["end"] == latest_idx:
                return int(run["run_id"])
    # 最新是黃：取目前黃 run 前一段紫作為右 V。
    if points[latest_idx].get("color") == "yellow":
        y_start = _run_start(points, latest_idx)
        for run in reversed(runs):
            if run["end"] < y_start:
                return int(run["run_id"])
    return int(runs[-1]["run_id"])


def _point_ref(points: list[dict[str, Any]], idx: int | None) -> dict[str, Any] | None:
    if idx is None or idx < 0 or idx >= len(points):
        return None
    p = points[idx]
    return {
        "date": p.get("date"),
        "index": int(idx),
        "ha_price": _round(p.get("close"), 10),
        "pct_vs_midline": _round(p.get("pct"), 6),
        "band_position": _round(p.get("band_pos"), 6),
    }


STRUCT_UPPER_ZONE_BANDPOS = 0.58
STRUCT_LOWER_ZONE_BANDPOS = 0.42
STRUCT_STRONG_UPPER_BANDPOS = 0.72


def _has_meaningful_upper_phase(points: list[dict[str, Any]], end_idx: int) -> tuple[bool, int | None]:
    # 找出 end_idx 之前最後一個有效的中軌上方價格層。
    if end_idx <= 0:
        return False, None
    last_idx = None
    for i in range(0, min(end_idx, len(points))):
        bp = _f(points[i].get("band_pos"), 0.5)
        strong = bp >= STRUCT_STRONG_UPPER_BANDPOS
        clustered = False
        if bp >= STRUCT_UPPER_ZONE_BANDPOS:
            left_ok = i > 0 and _f(points[i-1].get("band_pos"), 0.5) >= STRUCT_UPPER_ZONE_BANDPOS
            right_ok = i + 1 < end_idx and _f(points[i+1].get("band_pos"), 0.5) >= STRUCT_UPPER_ZONE_BANDPOS
            clustered = left_ok or right_ok
        if strong or clustered:
            last_idx = i
    return last_idx is not None, last_idx


def _structural_generation_start(points: list[dict[str, Any]], active_run: dict[str, Any]) -> dict[str, Any]:
    # 中軌上方舊 V 若之後深跌到中軌下方，視為新結構世代，active V 重新當 L。
    low_idx = int(active_run.get("low_idx", 0))
    low_bp = _f(points[low_idx].get("band_pos"), 0.5)
    if low_bp > STRUCT_LOWER_ZONE_BANDPOS:
        return {
            "start_index": 0,
            "reset": False,
            "reason": "active_v_not_materially_below_midline",
            "upper_phase_index": None,
            "breakdown_index": None,
        }

    has_upper, upper_idx = _has_meaningful_upper_phase(points, int(active_run.get("start", low_idx)))
    if not has_upper or upper_idx is None:
        return {
            "start_index": 0,
            "reset": False,
            "reason": "no_prior_meaningful_upper_phase",
            "upper_phase_index": None,
            "breakdown_index": None,
        }

    breakdown_idx = None
    for i in range(upper_idx + 1, low_idx + 1):
        if _f(points[i].get("band_pos"), 0.5) <= STRUCT_LOWER_ZONE_BANDPOS:
            breakdown_idx = i
            break

    if breakdown_idx is None:
        return {
            "start_index": 0,
            "reset": False,
            "reason": "upper_phase_without_material_breakdown",
            "upper_phase_index": upper_idx,
            "breakdown_index": None,
        }

    return {
        "start_index": int(breakdown_idx),
        "reset": True,
        "reason": "midline_break_resets_new_left_v",
        "upper_phase_index": int(upper_idx),
        "breakdown_index": int(breakdown_idx),
    }


def _finite_number(value: Any) -> float | None:
    try:
        x = float(value)
    except Exception:
        return None
    if not math.isfinite(x):
        return None
    return x


def _run_real_low(points: list[dict[str, Any]], run: dict[str, Any]) -> float | None:
    values = [
        _finite_number(points[i].get("real_low"))
        for i in range(int(run.get("start", 0)), int(run.get("end", -1)) + 1)
    ]
    values = [x for x in values if x is not None]
    return min(values) if values else None


def _bridge_metrics(
    points: list[dict[str, Any]],
    left_run: dict[str, Any],
    right_run: dict[str, Any],
) -> dict[str, Any]:
    indices = list(range(int(left_run.get("low_idx", 0)) + 1, int(right_run.get("start", 0))))
    yellow = [i for i in indices if points[i].get("color") == "yellow"]
    bridge_high_idx = max(yellow, key=lambda i: _f(points[i].get("close"))) if yellow else None
    bridge_high = _f(points[bridge_high_idx].get("close")) if bridge_high_idx is not None else None

    real_high_values = [(_finite_number(points[i].get("real_high")), i) for i in indices]
    real_high_values = [(x, i) for x, i in real_high_values if x is not None]
    real_high = max(real_high_values, key=lambda t: t[0])[0] if real_high_values else None
    real_high_idx = max(real_high_values, key=lambda t: t[0])[1] if real_high_values else None

    left_p2_idx = left_run.get("purple2_idx")
    left_p2_price = _f(points[int(left_p2_idx)].get("close")) if left_p2_idx is not None else None
    bridge_beats_left_p2 = bool(
        bridge_high is not None
        and left_p2_price is not None
        and bridge_high >= left_p2_price
    )
    return {
        "yellow_indices": yellow,
        "yellow_days": len(yellow),
        "bridge_high_idx": bridge_high_idx,
        "bridge_high": bridge_high,
        "real_bridge_high_idx": real_high_idx,
        "real_bridge_high": real_high,
        # 肉眼等價：中間反彈至少吃掉左 V 的 Purple-2，才算真的分出第二個 V。
        "bridge_beats_left_purple2": bridge_beats_left_p2,
        "bridge_qualified": bool(yellow and bridge_beats_left_p2),
    }


def _pair_fib_metrics(
    points: list[dict[str, Any]],
    left_run: dict[str, Any],
    right_run: dict[str, Any],
    bridge: dict[str, Any],
) -> dict[str, Any]:
    left_low = _f(left_run.get("low_price"))
    right_low = _f(right_run.get("low_price"))
    bridge_high = bridge.get("bridge_high")
    ha_fib = None
    if bridge_high is not None and float(bridge_high) > left_low + 1e-18:
        ha_fib = (float(bridge_high) - right_low) / (float(bridge_high) - left_low)

    left_real_low = _run_real_low(points, left_run)
    right_real_low = _run_real_low(points, right_run)
    real_bridge_high = bridge.get("real_bridge_high")
    real_fib = None
    if (
        left_real_low is not None
        and right_real_low is not None
        and real_bridge_high is not None
        and real_bridge_high > left_real_low + 1e-18
    ):
        real_fib = (real_bridge_high - right_real_low) / (real_bridge_high - left_real_low)

    available = [x for x in (ha_fib, real_fib) if x is not None and math.isfinite(x)]
    structural_extension = max(available) if available else None
    return {
        "ha_fib_retracement": ha_fib,
        "real_kline_fib_retracement": real_fib,
        "structural_extension_ratio": structural_extension,
        "left_real_low": left_real_low,
        "right_real_low": right_real_low,
    }


def _fib_role_zone(ha_fib: float | None) -> str:
    """人眼等價的非單調 Fib 分區。

    同一結構世代、且已先證明真的存在兩個獨立 V 時：
    - 0.000~0.618：Higher-Low / Cup 右 V（越小代表右 V 抬得越高）
    - 0.618~1.000：太深，不掛在舊 L 後面，重新視為 L
    - 1.000~1.236：W 底右腳，可略破左 V
    - >1.236：舊結構失效，重新視為 L
    Fib 不負責創造 V，也不能跨越中軌結構世代 Reset。
    """
    if ha_fib is None or not math.isfinite(ha_fib):
        return "unavailable"
    if ha_fib < 0:
        # 右側低點已高過中間 swing high，已不是正常回撤 V；交回結構世代邏輯處理。
        return "above_swing_high"
    if ha_fib <= FIB_CUP_RIGHT_MAX:
        return "higher_low_R_0_0_618"
    if ha_fib < FIB_W_RIGHT_MIN:
        return "middle_0_618_1_0_new_L"
    if ha_fib <= FIB_W_RIGHT_MAX:
        return "W_R_1_0_1_236"
    return "generation_break_gt_1_236"


def _upward_midline_generation_reset(
    points: list[dict[str, Any]],
    left_run: dict[str, Any],
    right_run: dict[str, Any],
    bridge: dict[str, Any],
) -> bool:
    """
    下方舊 V 已被一段真正的黃色推升帶過中軌，而新的紫 V 仍守在中軌上方：
    這是中軌上方的新價格世代，右邊這個 V 應重新命名為 L。
    """
    left_low_idx = int(left_run.get("low_idx", 0))
    right_low_idx = int(right_run.get("low_idx", 0))
    left_bp = _f(points[left_low_idx].get("band_pos"), 0.5)
    right_bp = _f(points[right_low_idx].get("band_pos"), 0.5)
    bridge_high_idx = bridge.get("bridge_high_idx")
    if bridge_high_idx is None:
        return False
    bridge_high_bp = _f(points[int(bridge_high_idx)].get("band_pos"), 0.5)
    return bool(
        left_bp < 0.5
        and bridge_high_bp >= STRUCT_UPPER_ZONE_BANDPOS
        and right_bp >= 0.5
        and bridge.get("bridge_qualified")
    )


def _dynamic_purple_structure(points: list[dict[str, Any]]) -> dict[str, Any]:
    """DP2-v7：先切結構世代與 V 資格，再用 Fib 判 L/R。

    R 的有效區：0~0.618（Higher Low）與 1.0~1.236（W 右腳）。
    0.618~1.0 與 >1.236 都重新視為 L；中軌世代 Reset 優先於 Fib。
    """
    runs = _purple_runs(points)
    active_id = _active_purple_run_id(points, runs)
    if not runs or active_id is None:
        return {
            "engine_rule": PURPLE2_RULE_VERSION,
            "active_purple2": None,
            "anchor_side": None,
            "anchor_reason": "no_purple_run",
            "anchor_source": "none",
            "fib_retracement": None,
            "self_audit": {"integrity_ok": True, "violations": []},
        }

    active_run = next((r for r in runs if int(r["run_id"]) == int(active_id)), runs[-1])
    active_idx = int(active_run["run_id"])
    runs = [r for r in runs if int(r["run_id"]) <= active_idx]

    all_purple_indices = [i for i, p in enumerate(points) if p.get("color") == "purple"]
    structural_low_idx = (
        min(all_purple_indices, key=lambda j: (_f(points[j].get("close")), j))
        if all_purple_indices else None
    )

    def _build_p2(chosen: dict[str, Any] | None, quality: str) -> dict[str, Any] | None:
        if not chosen or chosen.get("purple2_idx") is None:
            return None
        p2 = _point_ref(points, int(chosen["purple2_idx"]))
        if p2:
            p2.update({
                "reference_quality": quality,
                "purple_run_length": int(chosen.get("length", 0)),
                "anchor_run_id": int(chosen.get("run_id", -1)),
            })
        return p2

    eligible = [r for r in runs if r.get("eligible_purple2")]
    if not eligible:
        return {
            "engine_rule": PURPLE2_RULE_VERSION,
            "structural_low": _point_ref(points, structural_low_idx),
            "active_swing_low": _point_ref(points, int(active_run.get("low_idx", 0))),
            "active_purple2": None,
            "anchor_side": None,
            "anchor_source": "none",
            "anchor_reason": "no_v_has_own_purple2",
            "fib_retracement": None,
            "self_audit": {"integrity_ok": True, "violations": []},
        }

    # 逐 V 迭代：程式自己把每個新低問一次「若是人眼，這還是同一個 W / Cup 嗎？」
    anchor = eligible[0]
    anchor_side = "L"
    anchor_reason = "first_valid_v_is_left"
    relation = "single_left_v"
    last_bridge: dict[str, Any] | None = None
    last_fib: dict[str, Any] | None = None
    generation_resets: list[dict[str, Any]] = []
    pair_history: list[dict[str, Any]] = []

    for curr in eligible[1:]:
        pair_left_run_id = int(anchor.get("run_id", -1))
        bridge = _bridge_metrics(points, anchor, curr)
        fibm = _pair_fib_metrics(points, anchor, curr, bridge)
        left_bp = _f(points[int(anchor.get("low_idx", 0))].get("band_pos"), 0.5)
        right_bp = _f(points[int(curr.get("low_idx", 0))].get("band_pos"), 0.5)
        cross_midline_generation = bool(
            left_bp >= STRUCT_UPPER_ZONE_BANDPOS
            and right_bp <= STRUCT_LOWER_ZONE_BANDPOS
        )
        extension = fibm.get("structural_extension_ratio")
        extension_break = bool(extension is not None and extension > FIB_W_GENERATION_MAX)
        right_low = _f(curr.get("low_price"))
        left_low = _f(anchor.get("low_price"))
        ha_fib = fibm.get("ha_fib_retracement")

        decision = "keep_left"
        upward_midline_generation = _upward_midline_generation_reset(points, anchor, curr, bridge)
        fib_role_zone = _fib_role_zone(ha_fib)

        if cross_midline_generation:
            # 舊世代在中軌上方，新的 V 已跌到中軌下方：重新從 L 開始。
            anchor = curr
            anchor_side = "L"
            relation = "new_generation_midline_break_down"
            anchor_reason = "downward_midline_generation_reset_as_new_left"
            decision = "reset_L_midline_down"
            generation_resets.append({"run_id": int(curr["run_id"]), "reason": "midline_break_down"})
        elif upward_midline_generation:
            # DOT 類：舊 L 在中軌下，黃階已穿越並建立中軌上方價格層；
            # 第一個守在中軌上方的新紫 V 是新世代 L，不再掛在舊 L 後面當 R。
            anchor = curr
            anchor_side = "L"
            relation = "new_generation_midline_break_up"
            anchor_reason = "upward_midline_generation_reset_as_new_left"
            decision = "reset_L_midline_up"
            generation_resets.append({"run_id": int(curr["run_id"]), "reason": "midline_break_up"})
        elif extension_break:
            # HA 或真實 K 任一跌穿 1.236，舊 W 結構失效。
            anchor = curr
            anchor_side = "L"
            relation = "new_generation_beyond_1_236"
            anchor_reason = "right_leg_beyond_1_236_reset_as_new_left"
            decision = "reset_L_1.236"
            generation_resets.append({"run_id": int(curr["run_id"]), "reason": "fib_gt_1_236"})
        elif not bridge.get("bridge_qualified"):
            # 中間黃色沒有真正吃掉左 V 的 Purple-2，只是雜訊；不能創造 R。
            if right_low < left_low:
                anchor = curr
                anchor_side = "L"
                relation = "downtrend_continuation_new_left"
                anchor_reason = "bridge_failed_purple2_and_new_low_reset_left"
                decision = "reset_L_failed_bridge"
            else:
                anchor_side = "L"
                relation = "unqualified_bridge_keep_left"
                anchor_reason = "bridge_did_not_beat_left_purple2_keep_left"
                decision = "keep_L_failed_bridge"
        elif fib_role_zone == "higher_low_R_0_0_618":
            # Coffee / Higher-Low：0~0.618 都是有效右 V；越小代表右 V 抬得越高。
            # 前提仍是：同一結構世代 + 兩個獨立 V + qualified bridge。
            anchor = curr
            anchor_side = "R"
            relation = "higher_low_right_v"
            anchor_reason = "valid_higher_low_right_v_fib_0_to_0_618"
            decision = "use_R_higher_low_0.0_0.618"
        elif fib_role_zone == "W_R_1_0_1_236":
            # W 右腳可以略低於左 V，但只允許 1.0~1.236。
            anchor = curr
            anchor_side = "R"
            relation = "w_right_v_1_0_to_1_236"
            anchor_reason = "valid_w_right_v_fib_1_0_to_1_236"
            decision = "use_R_W_1.0_1.236"
        else:
            # 0.618~1.0 太深但尚未形成 W 右腳；或其他非正常回撤區。
            # 既然已形成一個新紫 V，就把它當目前世代的新 L，等待下一個真正右 V。
            anchor = curr
            anchor_side = "L"
            relation = fib_role_zone
            anchor_reason = f"fib_zone_{fib_role_zone}_reset_as_new_left"
            decision = "reset_L_non_R_fib_zone"

        pair_history.append({
            "from_run_id": pair_left_run_id,
            "candidate_run_id": int(curr.get("run_id", -1)),
            "decision": decision,
            "upward_midline_generation_reset": bool(upward_midline_generation),
            "fib_role_zone": fib_role_zone,
            "bridge_yellow_days": int(bridge.get("yellow_days", 0)),
            "bridge_beats_left_purple2": bool(bridge.get("bridge_beats_left_purple2")),
            "ha_fib_retracement": _round(fibm.get("ha_fib_retracement"), 6),
            "real_kline_fib_retracement": _round(fibm.get("real_kline_fib_retracement"), 6),
            "structural_extension_ratio": _round(extension, 6),
        })
        last_bridge = bridge
        last_fib = fibm

    # Active run 若沒有自己的 Purple-2，不能被標成 R；沿用目前 anchor 的 P2。
    if int(active_run.get("run_id", -1)) != int(anchor.get("run_id", -1)) and not active_run.get("eligible_purple2"):
        anchor_side = "L"
        relation = "active_right_has_no_own_purple2"
        anchor_reason = "active_right_has_no_own_purple2_fallback_anchor"

    p2 = _build_p2(anchor, "dynamic_purple2_v5")
    active_is_anchor = int(anchor.get("run_id", -1)) == int(active_run.get("run_id", -1))

    # 最後一層 invariant：即使未來有人改條件，違反人眼規則也強制退回 L。
    violations: list[str] = []
    if anchor_side == "R":
        if not anchor.get("eligible_purple2"):
            violations.append("R_without_own_purple2")
        if last_fib and last_fib.get("structural_extension_ratio") is not None and last_fib["structural_extension_ratio"] > FIB_W_GENERATION_MAX:
            violations.append("R_beyond_1_236")
        if last_bridge is not None and not last_bridge.get("bridge_qualified"):
            violations.append("R_without_qualified_bridge")
        role_zone = _fib_role_zone(last_fib.get("ha_fib_retracement") if last_fib else None)
        if role_zone not in {"higher_low_R_0_0_618", "W_R_1_0_1_236"}:
            violations.append("R_outside_allowed_fib_windows")
    if violations:
        anchor_side = "L"
        relation = "self_audit_forced_left"
        anchor_reason = "self_audit_violation_forced_left"

    ha_fib = last_fib.get("ha_fib_retracement") if last_fib else None
    real_fib = last_fib.get("real_kline_fib_retracement") if last_fib else None
    extension = last_fib.get("structural_extension_ratio") if last_fib else None
    fib_zone = _fib_role_zone(ha_fib)

    return {
        "engine_rule": PURPLE2_RULE_VERSION,
        "structural_low": _point_ref(points, structural_low_idx),
        "left_structural_v_low": _point_ref(points, int(eligible[0].get("low_idx", 0))),
        "active_swing_low": _point_ref(points, int(active_run.get("low_idx", 0))),
        "anchor_low": _point_ref(points, int(anchor.get("low_idx", 0))),
        "active_purple2": p2,
        "anchor_side": anchor_side,
        "anchor_source": "active_generation_anchor" if active_is_anchor else "prior_generation_anchor",
        "anchor_reason": anchor_reason,
        "active_right_run_id": int(active_run.get("run_id", -1)),
        "active_right_purple_count": int(active_run.get("length", 0)),
        "active_right_has_own_purple2": bool(active_run.get("eligible_purple2")),
        "low_relation": relation,
        "fib_retracement": _round(ha_fib, 6),
        "ha_fib_retracement": _round(ha_fib, 6),
        "real_kline_fib_retracement": _round(real_fib, 6),
        "structural_extension_ratio": _round(extension, 6),
        "fib_zone": fib_zone,
        "fib_higher_low_right_window": [FIB_CUP_RIGHT_MIN, FIB_CUP_RIGHT_MAX],
        "fib_w_right_window": [FIB_W_RIGHT_MIN, FIB_W_RIGHT_MAX],
        "fib_threshold_w_generation": FIB_W_GENERATION_MAX,
        "bridge_yellow_days": int(last_bridge.get("yellow_days", 0)) if last_bridge else 0,
        "bridge_high_price": _round(last_bridge.get("bridge_high"), 10) if last_bridge else None,
        "bridge_high_index": last_bridge.get("bridge_high_idx") if last_bridge else None,
        "bridge_beats_left_purple2": bool(last_bridge.get("bridge_beats_left_purple2")) if last_bridge else False,
        "left_run_id": int(eligible[0].get("run_id", -1)),
        "right_run_id": int(active_run.get("run_id", -1)) if len(eligible) > 1 else None,
        "generation_resets": generation_resets,
        "pair_history": pair_history,
        "self_audit": {
            "integrity_ok": not violations,
            "violations": violations,
            "rules": [
                "R_requires_own_purple2",
                "R_requires_bridge_that_beats_left_purple2",
                "R_only_allowed_in_fib_0.0_0.618_or_1.0_1.236",
                "R_forbidden_if_midline_generation_break_up_or_down",
                "R_forbidden_if_structural_extension_gt_1.236",
            ],
        },
        "all_purple_runs": [
            {
                "run_id": int(x["run_id"]),
                "start": int(x["start"]),
                "end": int(x["end"]),
                "length": int(x["length"]),
                "low": _point_ref(points, int(x["low_idx"])),
                "purple2": _point_ref(points, x.get("purple2_idx")),
                "real_low": _round(_run_real_low(points, x), 10),
            }
            for x in runs
        ],
    }

def _breakout_context(points: list[dict[str, Any]]) -> dict[str, Any]:
    """找真正的『由中軌下穿到中軌上』波段；若 30 日左緣已在上方，允許 left-censored 推定。"""
    if len(points) < 4:
        return {"confirmed": False}

    crossings: list[tuple[int, str]] = []
    # 30 日視窗可能剛好從已突破後開始；只有早段確實在上半部才允許推定。
    if _f(points[0].get("band_pos"), 0.5) >= 0.5:
        crossings.append((0, "left_censored"))
    for i in range(1, len(points)):
        prev_pos = _f(points[i-1].get("band_pos"), 0.5)
        cur_pos = _f(points[i].get("band_pos"), 0.5)
        if prev_pos < 0.5 <= cur_pos and _f(points[i].get("close")) >= _f(points[i-1].get("close")):
            crossings.append((i, "actual_cross"))

    candidates = []
    for cross_idx, cross_type in crossings:
        search_end = len(points) - 1
        peak_idx = max(range(cross_idx, search_end + 1), key=lambda i: _f(points[i].get("band_pos"), 0.5))
        peak_pos = _f(points[peak_idx].get("band_pos"), 0.5)
        confirm_threshold = 0.80 if cross_type == "left_censored" else BREAKOUT_CONFIRM_BANDPOS
        if peak_pos < confirm_threshold:
            continue
        after_peak = points[peak_idx+1:]
        min_pos = min((_f(p.get("band_pos"), 0.5) for p in after_peak), default=peak_pos)
        min_idx = None
        if after_peak:
            min_idx = peak_idx + 1 + min(range(len(after_peak)), key=lambda j: _f(after_peak[j].get("band_pos"), 0.5))
        invalidated = bool(after_peak and min_pos < BREAKOUT_INVALIDATE_BANDPOS)
        near_retest = any(_near_midline(p) for p in after_peak)
        candidates.append({
            "cross_index": cross_idx,
            "cross_type": cross_type,
            "cross_date": points[cross_idx].get("date"),
            "peak_index": peak_idx,
            "peak_date": points[peak_idx].get("date"),
            "peak_band_position": _round(peak_pos),
            "peak_pct_vs_midline": _round(points[peak_idx].get("pct")),
            "pullback_min_band_position": _round(min_pos),
            "pullback_min_index": min_idx,
            "pullback_near_midline": bool(near_retest),
            "cycle_invalidated": invalidated,
        })

    valid = [c for c in candidates if not c.get("cycle_invalidated")]
    if not valid:
        return {
            "confirmed": False,
            "cross_type": "none",
            "pullback_near_midline": False,
            "cycle_invalidated": bool(candidates),
            "candidates": candidates,
        }

    # 取最近形成的有效高點波段；避免很早以前的突破永遠綁住現在。
    chosen = max(valid, key=lambda c: (int(c.get("peak_index", -1)), int(c.get("cross_index", -1))))
    latest_pos = _f(points[-1].get("band_pos"), 0.5)
    min_pos = _f(chosen.get("pullback_min_band_position"), 0.5)
    chosen = dict(chosen)
    chosen.update({
        "confirmed": True,
        "retest_normal": bool(chosen.get("pullback_near_midline") and min_pos >= RETEST_FAKE_BREAK_BANDPOS),
        "retest_fake_break": bool(
            chosen.get("pullback_near_midline")
            and BREAKOUT_INVALIDATE_BANDPOS <= min_pos < RETEST_FAKE_BREAK_BANDPOS
            and latest_pos >= 0.5
        ),
        "bars_since_peak": len(points) - 1 - int(chosen.get("peak_index", len(points)-1)),
    })
    return chosen


def _failed_reclaim_attempts(points: list[dict[str, Any]], lookback: int = 12) -> int:
    """只作弱勢輔助：黃 run 未吃掉該紫 run 的『最低紫前一紫』，之後又轉紫。"""
    start_limit = max(0, len(points) - lookback)
    failures = 0
    i = start_limit
    while i < len(points):
        if points[i].get("color") != "yellow":
            i += 1
            continue
        y_start = i
        while i + 1 < len(points) and points[i+1].get("color") == "yellow":
            i += 1
        y_end = i
        p_end = y_start - 1
        if p_end >= 0 and points[p_end].get("color") == "purple":
            p_start = _run_start(points, p_end)
            run_indices = list(range(p_start, p_end + 1))
            low_idx = min(run_indices, key=lambda j: _f(points[j].get("close"))) if run_indices else None
            ref_idx = low_idx - 1 if low_idx is not None and low_idx > p_start else None
            if ref_idx is not None:
                max_yellow = max(_f(points[j].get("close")) for j in range(y_start, y_end+1))
                if max_yellow < _f(points[ref_idx].get("close")) and y_end + 1 < len(points) and points[y_end+1].get("color") == "purple":
                    failures += 1
        i += 1
    return failures


def _first_midline_test(points: list[dict[str, Any]], latest: dict[str, Any], breakout: dict[str, Any]) -> bool:
    if breakout.get("confirmed"):
        return False
    if not _near_midline(latest):
        return False
    recent = points[-12:]
    offset = len(points) - len(recent)
    low_local = min(range(len(recent)), key=lambda i: _f(recent[i].get("band_pos"), 0.5))
    low_idx = offset + low_local
    low_pos = _f(points[low_idx].get("band_pos"), 0.5)
    if low_pos > 0.25:
        return False
    # 前低後尚未真正站到明顯的中軌上方，視為第一次攻均衡區的同一段過程。
    after_low_before_latest = points[low_idx+1:-1]
    already_broke = any(_f(p.get("band_pos"), 0.5) >= 0.58 for p in after_low_before_latest)
    return not already_broke


def _below_midline_base_quality(points: list[dict[str, Any]]) -> dict[str, Any]:
    """判斷中軌下方是否已經不是單邊下殺，而是形成第二隻腳/抬高底/W/Cup。

    這個判斷只服務 S0 vs S0.5，不負責決定全域 Purple-2 Anchor。
    人眼等價：
    - S0：一整段紫色單邊下殺後，第一次黃階反彈。
    - S0.5：至少有兩個中軌下紫色谷，中間有黃階反攻，而且第二谷沒有崩壞到前谷 1.236 以下。
      第二谷可以更高、近似雙底、或略破前低，只要仍屬可辨識的底部結構。
    """
    if not points:
        return {"qualified": False, "shape": "none", "reason": "no_points"}

    runs = _purple_runs(points)
    candidates: list[dict[str, Any]] = []
    for run in runs:
        low_idx = int(run.get("low_idx", run.get("start", 0)))
        if 0 <= low_idx < len(points) and _f(points[low_idx].get("band_pos"), 0.5) < 0.5:
            candidates.append(run)
    if len(candidates) < 2:
        return {"qualified": False, "shape": "single_leg", "reason": "only_one_below_midline_valley"}

    active = candidates[-1]
    # 往左找最近一個真的能與 active 構成第二隻腳的谷。
    for prev in reversed(candidates[:-1]):
        bridge_points = points[int(prev["end"])+1:int(active["start"])]
        yellow_points = [x for x in bridge_points if x.get("color") == "yellow"]
        if not yellow_points:
            continue
        li = int(prev.get("low_idx"))
        ri = int(active.get("low_idx"))
        left_low = _f(points[li].get("close"))
        right_low = _f(points[ri].get("close"))
        bridge_high_point = max(yellow_points, key=lambda x: _f(x.get("close")))
        bridge_high = _f(bridge_high_point.get("close"))
        if bridge_high <= max(left_low, right_low):
            continue
        denom = bridge_high - left_low
        if denom <= 1e-18:
            continue
        fib = (bridge_high - right_low) / denom
        left_bp = _f(points[li].get("band_pos"), 0.5)
        right_bp = _f(points[ri].get("band_pos"), 0.5)
        bridge_peak_bp = max(_f(x.get("band_pos"), 0.5) for x in yellow_points)
        bridge_lift = bridge_peak_bp - min(left_bp, right_bp)
        if bridge_lift < BASE_BRIDGE_MIN_BANDPOS_LIFT:
            continue

        # 對 S0.5 而言，0~1.236 都可視為「有第二隻腳的底部建構」。
        # 這裡刻意比 Purple-2 的 L/R Anchor 規則寬，因為我們只是在判斷是不是單邊下殺。
        qualified = bool(fib >= 0.0 and fib <= FIB_W_GENERATION_MAX)
        if not qualified:
            continue

        if fib <= 0.618:
            shape = "higher_low_or_cup"
        elif fib < 1.0:
            shape = "raised_or_deep_second_leg"
        elif fib <= 1.08:
            shape = "double_bottom"
        else:
            shape = "w_slight_undercut"
        return {
            "qualified": True,
            "shape": shape,
            "reason": "multi_leg_bottom_structure",
            "left_low": _point_ref(points, li),
            "right_low": _point_ref(points, ri),
            "bridge_high": _point_ref(points, int(bridge_high_point.get("index", 0))),
            "bridge_yellow_days": len(yellow_points),
            "bridge_lift_bandpos": _round(bridge_lift, 6),
            "fib_retracement": _round(fib, 6),
            "right_low_above_left": bool(right_low > left_low),
        }

    return {"qualified": False, "shape": "single_leg", "reason": "no_valid_second_leg"}


def _color_runs(points: list[dict[str, Any]], color: str, end_idx: int | None = None) -> list[dict[str, int]]:
    """回傳指定顏色的連續 run。只描述事實，不直接判斷市場狀態。"""
    if not points:
        return []
    last = len(points) - 1 if end_idx is None else min(int(end_idx), len(points) - 1)
    runs: list[dict[str, int]] = []
    i = 0
    while i <= last:
        if points[i].get("color") != color:
            i += 1
            continue
        j = i
        while j + 1 <= last and points[j + 1].get("color") == color:
            j += 1
        runs.append({"start": i, "end": j, "length": j - i + 1})
        i = j + 1
    return runs


def _purple2_from_run(points: list[dict[str, Any]], p_start: int, p_end: int) -> dict[str, Any]:
    """已完成紫 run 的局部 Purple-2：最低紫之前的那一階紫。

    紫 run 尚未完成時，不用這個函式猜底；S2 live 狀態會直接延後到轉黃後再凍結。
    """
    p_start, p_end = int(p_start), int(p_end)
    if p_start < 0 or p_end < p_start or p_end >= len(points):
        return {"qualified": False, "reason": "invalid_purple_run"}
    idxs = list(range(p_start, p_end + 1))
    low_idx = min(idxs, key=lambda j: (_f(points[j].get("close")), j))
    p2_idx = low_idx - 1 if low_idx > p_start and points[low_idx - 1].get("color") == "purple" else None
    p2 = _point_ref(points, p2_idx) if p2_idx is not None else None
    if p2:
        p2.update({
            "reference_quality": "state_scoped_purple2",
            "purple_run_length": len(idxs),
            "anchor_run_id": -2,
        })
    return {
        "qualified": p2 is not None,
        "purple_start": p_start,
        "purple_end": p_end,
        "purple_run_length": len(idxs),
        "purple_low_index": low_idx,
        "purple_low": _point_ref(points, low_idx),
        "purple2": p2,
    }


def _yellow_run_wave1_candidate(points: list[dict[str, Any]], y_start: int, y_end: int) -> dict[str, Any]:
    """判斷一段黃 run 是否足以當作可見的第一浪背景。

    兩種來源都接受：
    1) 20 根內看得到它從中軌下自然穿上來；
    2) 起點已在 20 根視窗之外，但畫面內已有很清楚的上方黃色推升（UNI 類）。
    """
    run = points[y_start:y_end + 1]
    if not run:
        return {"qualified": False}
    before_pos = _f(points[y_start - 1].get("band_pos"), 0.5) if y_start > 0 else 0.5
    min_pos = min(_f(p.get("band_pos"), 0.5) for p in run)
    peak_pos = max(_f(p.get("band_pos"), 0.5) for p in run)
    originated_from_below = bool(min_pos < 0.5 or before_pos < 0.5)
    inferred_visible_wave = bool(not originated_from_below and len(run) >= 2 and peak_pos >= 0.85)
    crossed = any(_f(p.get("band_pos"), 0.5) >= 0.5 for p in run)
    qualified = bool(
        crossed and (
            (originated_from_below and peak_pos >= S2_FIRST_WAVE_PEAK_MIN_BANDPOS)
            or inferred_visible_wave
        )
    )
    return {
        "qualified": qualified,
        "yellow_start": y_start,
        "yellow_end": y_end,
        "yellow_days": len(run),
        "originated_from_below": originated_from_below,
        "inferred_visible_wave": inferred_visible_wave,
        "before_yellow_band_position": _round(before_pos, 6),
        "yellow_min_band_position": _round(min_pos, 6),
        "peak_band_position": _round(peak_pos, 6),
    }


def _find_wave1_before(points: list[dict[str, Any]], before_idx: int) -> dict[str, Any]:
    """找 before_idx 之前最近的有效第一浪。

    找到後再用整段後續價格檢查是否曾深跌破中軌世代；因此不會把很久以前的上漲硬延伸到現在。
    """
    if before_idx < 0:
        return {"qualified": False}
    runs = _color_runs(points, "yellow", before_idx)
    for run in reversed(runs):
        candidate = _yellow_run_wave1_candidate(points, run["start"], run["end"])
        if candidate.get("qualified"):
            return candidate
    return {"qualified": False}


def _wave2_pullback_context(points: list[dict[str, Any]], *, yellow_start: int | None = None) -> dict[str, Any]:
    """辨識 S2 / S3 所用的第一浪→第二浪背景。

    v4.3 關鍵：S2 是一個「持續狀態」，不是只看緊鄰前一段黃色。
    因此 UNI 這種 2 浪中間偶爾反黃、但沒有完成 S3 的案例，之後再轉紫仍維持 S2。
    ROSE 那種只有一根紫、隔天立刻恢復原本黃階，轉黃後不會被硬掛 S2。
    """
    if not points:
        return {"qualified": False}

    if yellow_start is None:
        p_end = len(points) - 1
        if points[p_end].get("color") != "purple":
            return {"qualified": False}
        p_start = _run_start(points, p_end)
        live = True
    else:
        p_end = int(yellow_start) - 1
        if p_end < 0 or points[p_end].get("color") != "purple":
            return {"qualified": False}
        p_start = _run_start(points, p_end)
        live = False

    purple_ctx = _purple2_from_run(points, p_start, p_end)
    wave1 = _find_wave1_before(points, p_start - 1)
    if not wave1.get("qualified"):
        return {
            **purple_ctx,
            "qualified": False,
            "reason": "no_valid_first_wave_before_pullback",
        }

    w1_end = int(wave1.get("yellow_end", -1))
    cycle_slice = points[w1_end + 1:p_end + 1]
    cycle_min = min((_f(p.get("band_pos"), 0.5) for p in cycle_slice), default=0.5)
    purple_min = min((_f(points[i].get("band_pos"), 0.5) for i in range(p_start, p_end + 1)), default=0.5)
    end_pos = _f(points[p_end].get("band_pos"), 0.5)

    # 真正深跌破中軌後，舊第一浪世代失效；小幅 undercut 仍可當正常 2 浪。
    generation_intact = bool(cycle_min >= S2_BREAKDOWN_FLOOR_BANDPOS)
    if live:
        # 使用者的快速掃描目的：紫色已進入中軌上方的可交易回踩區才顯示 S2。
        # 高位剛轉紫但離中軌仍很遠（BNB 類）先不列入。
        qualified = bool(generation_intact and end_pos >= 0.5 and end_pos <= S2_ACTIVE_MAX_BANDPOS)
    else:
        # 已轉黃後，必須至少有兩階紫才承認「真的形成過一個可凍結的 2 浪」。
        # 一階紫隔天立刻轉黃（ROSE 類）只是第一浪中的顏色雜訊，不掛 S2。
        qualified = bool(generation_intact and purple_ctx.get("purple_run_length", 0) >= 2)

    if end_pos > MIDLINE_SWEET_UPPER_BANDPOS:
        phase = "early_upper_pullback"
    elif end_pos >= 0.5:
        phase = "midline_retest_zone"
    else:
        phase = "minor_midline_undercut"

    return {
        **purple_ctx,
        "qualified": qualified,
        "generation_intact": generation_intact,
        "cycle_min_band_position": _round(cycle_min, 6),
        "pullback_phase": phase,
        "pullback_low_band_position": _round(purple_min, 6),
        "pullback_end_band_position": _round(end_pos, 6),
        "first_wave": wave1,
    }


def _yellow_run_origin_below_midline(points: list[dict[str, Any]], yellow_start: int) -> dict[str, Any]:
    """重建 S0/S0.5 → S1 的同一段黃 run。

    不要求 Purple-2 一定在「突破中軌之前」先被吃掉。ETH 類可以先穿中軌、下一階黃才勝 P2；
    只要同一段黃 run 同時完成「從中軌下起跑 + 勝 P2 + 穿越中軌」，就屬 S1。
    """
    if yellow_start <= 0 or points[yellow_start].get("color") != "yellow":
        return {"qualified": False}
    p_end = yellow_start - 1
    if points[p_end].get("color") != "purple":
        return {"qualified": False}
    p_start = _run_start(points, p_end)
    prev_purple = _purple2_from_run(points, p_start, p_end)
    p2 = prev_purple.get("purple2")
    if not p2:
        # 右腳只有一階紫時，仍允許沿用狀態化 Dynamic P2；但不憑空造 P2。
        pstruct = _dynamic_purple_structure(points[:yellow_start])
        p2 = pstruct.get("active_purple2")
    else:
        pstruct = {
            "engine_rule": PURPLE2_RULE_VERSION,
            "scope": "immediate_pre_yellow_purple_run",
            "anchor_side": "LOCAL",
            "active_purple2": p2,
        }

    base_quality = _below_midline_base_quality(points[:yellow_start])
    prev_low_pos = min((_f(points[i].get("band_pos"), 0.5) for i in range(p_start, p_end + 1)), default=0.5)
    if prev_low_pos >= 0.5:
        return {
            "qualified": False,
            "reason": "current_yellow_did_not_originate_from_below_midline",
            "purple_structure": pstruct,
            "purple2": p2,
            "base_quality": base_quality,
        }
    if not p2:
        return {"qualified": False, "reason": "no_purple2", "purple_structure": pstruct, "base_quality": base_quality}

    ref = _f(p2.get("ha_price"))
    trigger_idx = None
    cross_idx = None
    for idx in range(yellow_start, len(points)):
        if points[idx].get("color") != "yellow":
            break
        bp = _f(points[idx].get("band_pos"), 0.5)
        if trigger_idx is None and _f(points[idx].get("close")) >= ref:
            trigger_idx = idx
        if cross_idx is None and bp >= 0.5:
            cross_idx = idx

    if trigger_idx is None or cross_idx is None:
        return {
            "qualified": False,
            "reason": "yellow_run_has_not_completed_p2_and_midline_cross",
            "purple_structure": pstruct,
            "purple2": p2,
            "base_quality": base_quality,
            "trigger_index": trigger_idx,
            "cross_index": cross_idx,
        }

    prefix_for_mid = points[:trigger_idx + 1]
    origin_mid = _midline_regime(prefix_for_mid) if len(prefix_for_mid) >= 5 else _midline_regime(points)
    origin_state = "S0.5" if (
        origin_mid.get("state") in {"rising", "flat", "flattening"}
        or base_quality.get("qualified")
    ) else "S0"
    return {
        "qualified": True,
        "trigger_index": trigger_idx,
        "cross_index": cross_idx,
        "origin_state": origin_state,
        "origin_midline": origin_mid,
        "base_quality": base_quality,
        "purple_structure": pstruct,
        "purple2": p2,
    }


def _p2_with_gap(points: list[dict[str, Any]], p2: dict[str, Any] | None) -> tuple[dict[str, Any] | None, bool, float | None, float | None]:
    if not p2 or not points:
        return p2, False, None, None
    latest = points[-1]
    ref_price = _f(p2.get("ha_price"))
    ref_pct = _f(p2.get("pct_vs_midline"))
    gap_price = None
    if abs(ref_price) > 1e-18:
        gap_price = (_f(latest.get("close")) - ref_price) / abs(ref_price) * 100.0
    gap_rel = _f(latest.get("pct")) - ref_pct
    passed = bool(gap_price is not None and gap_price >= 0)
    enriched = dict(p2)
    enriched.update({
        "current_gap_price_pct": _round(gap_price, 6),
        "current_gap_relative_points": _round(gap_rel, 6),
        "passed_by_actual_ha_price": passed,
        "passed_by_midline_relative_pct": bool(gap_rel >= 0),
    })
    return enriched, passed, gap_price, gap_rel


def build_long_opportunity(r: dict, ladder_history: list[dict] | None = None) -> dict[str, Any]:
    """S0 / S0.5 / S1 / S2 / S3 快速做多狀態掃描（v4.3）。

    核心原則：
    - 不用固定「第幾天」讓訊號過期；用 BB band position 判斷還剩多少空間。
    - S1 / S3 只在中軌→上軌的前段保留，貼近上軌就不追。
    - S2 是持續狀態；失敗的小黃反彈不會把整個 2 浪記憶洗掉。
    - S0 vs S0.5 由「單邊下殺」或「已形成第二隻腳/底部抬高」決定，而不是只看 5 日斜率。
    """
    del ladder_history
    points = _opportunity_points(r)
    if len(points) < 6:
        return {
            "stars": 1, "stars_text": "★☆☆☆☆", "opportunity_label": "其他｜資料不足",
            "market_state_id": "OTHER", "market_state_name": "資料不足", "market_state_order": 99,
            "setup_id": 0, "setup_name": "其他｜資料不足", "structure_state": "30日幾何資料不足",
            "trigger_stage": "T0", "midline": {"state":"unknown","symbol":"?","label":"未知"},
            "purple2_reference": None, "purple_structure": {}, "reasons": ["30日幾何資料不足"],
        }

    latest = points[-1]
    latest_idx = len(points) - 1
    latest_color = str(latest.get("color") or "unknown")
    latest_pos = _f(latest.get("band_pos"), 0.5)
    latest_pct = _f(latest.get("pct"))
    below_now = latest_pos < 0.5
    midline = _midline_regime(points)
    current_start = _run_start(points, latest_idx)
    current_run_length = latest_idx - current_start + 1

    state_id = "OTHER"
    state_name = "其他｜略過"
    state_order = 99
    stars = 1
    setup_id = 0
    structure = "目前不是快速機會"
    reasons: list[str] = []
    purple2 = None
    purple_structure: dict[str, Any] = {}
    trigger_idx = None
    state_path: list[str] = []
    stage = "T0" if latest_color == "purple" else "T1" if latest_color == "yellow" else "T0"
    consumed_wave2_yellow = False

    # ── S3：S2 回踩完成 → 轉黃 → 勝該次 P2。是否仍可進場由 BB 空間決定，不用「第2天」寫死。 ──
    if latest_color == "yellow":
        wave2_finished = _wave2_pullback_context(points, yellow_start=current_start)
        if wave2_finished.get("qualified"):
            local_p2 = wave2_finished.get("purple2")
            local_p2, local_pass, _, _ = _p2_with_gap(points, local_p2)
            if local_p2:
                ref_price = _f(local_p2.get("ha_price"))
                for idx in range(current_start, latest_idx + 1):
                    if points[idx].get("color") == "yellow" and _f(points[idx].get("close")) >= ref_price:
                        trigger_idx = idx
                        break
                if local_pass and latest_pos >= 0.5:
                    consumed_wave2_yellow = True
                    if latest_pos <= S3_ACTIVE_MAX_BANDPOS:
                        state_id, state_name, state_order = "S3", "3浪啟動", 0
                        stars, setup_id = 5, 30
                        structure = "2浪回踩完成｜轉黃勝 Purple-2"
                        reasons.append("2浪回踩已完成，黃階勝 Purple-2；目前仍在中軌→上軌的可交易前段，因此保留 S3")
                        purple2 = local_p2
                        purple_structure = {
                            "engine_rule": PURPLE2_RULE_VERSION,
                            "scope": "wave2_pullback_only",
                            "anchor_side": "S2",
                            "anchor_reason": "finished_wave2_purple_run",
                            "active_purple2": local_p2,
                            "wave2_pullback": wave2_finished,
                        }
                        stage = "T2"
                        state_path = ["S2", "S3"]
                    else:
                        structure = "S3 已發動但已走到上軌側｜不追"
                        reasons.append("黃階雖已勝 S2 Purple-2，但目前在 BB 上半帶的位置已太高；TAO 類不再維持五星 S3")
                        purple2 = local_p2
                        purple_structure = {
                            "engine_rule": PURPLE2_RULE_VERSION,
                            "scope": "wave2_pullback_expired_by_space",
                            "anchor_side": "S2",
                            "active_purple2": local_p2,
                            "wave2_pullback": wave2_finished,
                        }
                        stage = "T2"
                elif not local_pass and latest_pos >= 0.5:
                    consumed_wave2_yellow = True
                    state_id, state_name, state_order = "S2", "2浪回踩", 2
                    stars, setup_id = 3, 20
                    structure = "2浪已轉黃｜等待勝 Purple-2"
                    reasons.append("2浪已轉黃，但尚未吃掉該次 Purple-2；仍是 S2 等待，不提前升 S3")
                    purple2 = local_p2
                    purple_structure = {
                        "engine_rule": PURPLE2_RULE_VERSION,
                        "scope": "wave2_pullback_only",
                        "anchor_side": "S2",
                        "anchor_reason": "wave2_yellow_pending_purple2",
                        "active_purple2": local_p2,
                        "wave2_pullback": wave2_finished,
                    }
                    stage = "T1"
                    state_path = ["S2"]
        # 一階紫隔天立刻轉黃，不算完整 S2；不在這裡硬保留 S2，後面再看是否其實仍是 S1。

    # ── S1：同一段黃 run 從中軌下起跑、勝 P2、穿越中軌；只要還在 BB 前段就持續保留。 ──
    if state_id == "OTHER" and not consumed_wave2_yellow and latest_color == "yellow" and latest_pos >= 0.5:
        origin = _yellow_run_origin_below_midline(points, current_start)
        cross_idx = origin.get("cross_index")
        if origin.get("qualified") and cross_idx is not None:
            if latest_pos <= S1_ACTIVE_MAX_BANDPOS:
                state_id, state_name, state_order = "S1", "1浪突破", 2
                stars, setup_id = 3, 10
                origin_state = str(origin.get("origin_state") or "S0")
                structure = f"{origin_state} → 黃階自然突破中軌"
                reasons.append("同一段黃色已完成中軌下 P2 反轉與中軌突破；仍在中軌→上軌的前段，所以即使連續多天黃也維持 S1")
                purple2, _, _, _ = _p2_with_gap(points, origin.get("purple2"))
                purple_structure = dict(origin.get("purple_structure") or {})
                purple_structure["active_purple2"] = purple2
                purple_structure["scope"] = "state0_origin_for_state1"
                purple_structure["origin_base_quality"] = origin.get("base_quality")
                trigger_idx = origin.get("trigger_index")
                stage = "T2"
                state_path = [origin_state, "S1"]
            else:
                structure = "1浪已離開中軌甜蜜區｜等待2浪"
                reasons.append("這段黃確實是 S1 路徑，但已走到 BB 上方較深位置；不再當新進場，等待轉紫形成 S2")

    # ── S2：第一浪後目前是紫色回踩。允許 S2 中間曾有失敗的小黃反彈，再次轉紫仍保留 S2 記憶。 ──
    if state_id == "OTHER" and latest_color == "purple":
        wave2_live = _wave2_pullback_context(points)
        if wave2_live.get("qualified"):
            state_id, state_name, state_order = "S2", "2浪回踩", 2
            stars, setup_id = 3, 20
            phase = str(wave2_live.get("pullback_phase") or "wave2_pullback")
            structure = "中軌上紫色回踩｜等待轉黃"
            if phase == "early_upper_pullback":
                reasons.append("第一浪後紫色已進入可交易回踩區，判 S2；尚未轉黃前不猜 Purple-2")
            else:
                reasons.append("第一浪後紫色正在中軌附近回踩；即使中間曾有未完成 S3 的小黃反彈，仍維持 S2")
            purple_structure = {
                "engine_rule": PURPLE2_RULE_VERSION,
                "scope": "wave2_live_no_purple2_until_yellow",
                "anchor_side": None,
                "anchor_reason": "purple_run_still_open",
                "active_purple2": None,
                "wave2_pullback": wave2_live,
            }
            stage = "T0"
            state_path = ["S2"]

    # ── S0 / S0.5：中軌下方黃階勝有效 P2。不要用第1/第2天寫死；未穿中軌前都用結構品質判斷。 ──
    if state_id == "OTHER" and latest_color == "yellow" and below_now:
        prefix = points[:current_start]
        pstruct = _dynamic_purple_structure(prefix)
        dp2 = pstruct.get("active_purple2")
        dp2, dp2_pass, _, _ = _p2_with_gap(points, dp2)
        if dp2 and dp2_pass:
            ref_price = _f(dp2.get("ha_price"))
            ref_idx = int(dp2.get("index", 0))
            for idx in range(max(ref_idx + 1, current_start), latest_idx + 1):
                if points[idx].get("color") == "yellow" and _f(points[idx].get("close")) >= ref_price:
                    trigger_idx = idx
                    break
            if trigger_idx is not None:
                purple2 = dp2
                purple_structure = dict(pstruct)
                purple_structure["active_purple2"] = purple2
                purple_structure["scope"] = "below_midline_state0"
                stage = "T2"
                base_quality = _below_midline_base_quality(prefix)
                purple_structure["base_quality"] = base_quality
                if midline.get("state") in {"rising", "flat", "flattening"} or base_quality.get("qualified"):
                    state_id, state_name, state_order = "S0.5", "優質反轉", 1
                    stars, setup_id = 4, 5
                    if base_quality.get("qualified"):
                        structure = "中軌下勝 Purple-2｜底部已有第二隻腳"
                        reasons.append("20根內已看見 Higher-Low / W / Cup / 雙底式第二隻腳，因此即使 5 日中軌仍顯示下斜，也歸 S0.5 而不是單邊 S0")
                    else:
                        structure = "中軌下勝 Purple-2｜中軌平緩/改善"
                        reasons.append("中軌下方黃階勝 Purple-2，且中軌已平緩、上斜或下降明顯鈍化")
                    state_path = ["S0.5"]
                else:
                    state_id, state_name, state_order = "S0", "下殺反彈", 3
                    stars, setup_id = 2, 1
                    structure = "中軌下勝 Purple-2｜單邊紫下殺後反彈"
                    reasons.append("可見結構仍主要是單一路徑連續紫色下殺，尚未形成第二隻腳，因此只列 S0")
                    state_path = ["S0"]

    if state_id == "OTHER":
        if structure.startswith("S3 已發動") or structure.startswith("1浪已離開"):
            pass
        elif latest_color == "purple" and latest_pos < 0.5:
            structure = "中軌下紫階｜等待新的 S0/S0.5"
            reasons.append("目前仍在中軌下方且沒有新的可交易 Trigger")
        elif latest_color == "yellow" and latest_pos > S1_ACTIVE_MAX_BANDPOS:
            structure = "黃階已走到 BB 上方較深位置｜不追"
            reasons.append("用每顆幣自己的 BB 空間判斷已走遠，而不是用固定百分比")
        else:
            reasons.append("目前不屬 S0 / S0.5 / S1 / S2 / S3 快速機會")

    stars_text = "★" * stars + "☆" * (5 - stars)
    label_map = {
        "S3": "S3｜3浪啟動",
        "S0.5": "S0.5｜優質反轉",
        "S1": "S1｜1浪突破",
        "S2": "S2｜2浪回踩",
        "S0": "S0｜下殺反彈",
        "OTHER": "其他｜略過",
    }
    if purple2 is not None:
        purple2, passed, _, _ = _p2_with_gap(points, purple2)
        if purple_structure:
            purple_structure = dict(purple_structure)
            purple_structure["active_purple2"] = purple2
    else:
        passed = False

    trigger_days_ago = latest_idx - int(trigger_idx) if trigger_idx is not None else None
    trigger_date = points[int(trigger_idx)].get("date") if trigger_idx is not None else None
    freshness = "not_triggered" if trigger_days_ago is None else "today" if trigger_days_ago == 0 else "yesterday" if trigger_days_ago == 1 else f"{trigger_days_ago}d_ago"

    return {
        "stars": int(stars),
        "stars_text": stars_text,
        "opportunity_label": label_map[state_id],
        "market_state_id": state_id,
        "market_state_name": state_name,
        "market_state_order": int(state_order),
        "state_path": state_path,
        "setup_id": int(setup_id),
        "setup_name": label_map[state_id],
        "structure_state": structure,
        "trigger_stage": stage,
        "trigger_stage_meaning": {
            "T0": "等待轉黃",
            "T1": "已轉黃，但尚未勝此狀態的 Purple-2",
            "T2": "此狀態的 Purple-2 已被黃階超越",
        }.get(stage, "unknown"),
        "midline": midline,
        "current": {
            "ha_color": latest_color,
            "ha_price": _round(latest.get("close"), 10),
            "ha_vs_midline_pct": _round(latest_pct),
            "ha_band_position": _round(latest_pos),
            "near_midline": bool(_near_midline(latest)),
            "midline_band_distance": _round(abs(latest_pos - 0.5), 6),
            "current_color_run_length": int(current_run_length),
        },
        "purple2_reference": purple2,
        "purple_structure": purple_structure,
        "trigger_freshness": {"status": freshness, "trigger_date": trigger_date, "days_ago": trigger_days_ago},
        "geometry": {
            "state_engine": "S0-S0.5-S1-S2-S3",
            "state_progression": "S0/S0.5 -> S1 -> S2 -> S3",
            "wave2_purple2_is_deferred_until_yellow": True,
            "signals_expire_by_bb_space_not_day_count": True,
            "s1_active_bandpos_max": S1_ACTIVE_MAX_BANDPOS,
            "s2_active_bandpos_max": S2_ACTIVE_MAX_BANDPOS,
            "s3_active_bandpos_max": S3_ACTIVE_MAX_BANDPOS,
            "near_midline_bandpos_range": [_round(0.5 - MIDLINE_NEAR_BANDPOS_DISTANCE, 3), _round(0.5 + MIDLINE_NEAR_BANDPOS_DISTANCE, 3)],
        },
        "maturity": {"mature_bull_expansion": False, "mature_bear_expansion": False},
        "reasons": reasons,
    }


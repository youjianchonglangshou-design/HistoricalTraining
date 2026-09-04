from __future__ import annotations

import math
from typing import Any


def _bin_bandpos(value: float) -> str:
    if value < 0.25:
        return "LT_025"
    if value < 0.50:
        return "025_050"
    if value < 0.60:
        return "050_060"
    if value < 0.75:
        return "060_075"
    return "GE_075"


def _bin_age(value: int) -> str:
    if value <= 1:
        return "1"
    if value <= 3:
        return "2_3"
    if value <= 6:
        return "4_6"
    return "7_PLUS"


def _bin_run(value: int) -> str:
    if value <= 1:
        return "1"
    if value == 2:
        return "2"
    return "3_PLUS"


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _aligned_float_series(values: list[Any]) -> list[float | None]:
    return [_safe_float(value) for value in values]


def _valid_series(values: list[Any]) -> list[float]:
    return [value for value in (_safe_float(x) for x in values) if value is not None]


def _slope(values: list[Any], lookback: int) -> float | None:
    series = _valid_series(values)
    if len(series) < lookback + 1:
        return None
    return (series[-1] - series[-1 - lookback]) / float(lookback)


def _pct_slope(values: list[Any], lookback: int, end_offset: int = 0) -> float | None:
    series = _aligned_float_series(values)
    end = len(series) - 1 - max(0, int(end_offset))
    start = end - max(1, int(lookback))
    if start < 0 or end < 0:
        return None
    a = series[start]
    b = series[end]
    if a is None or b is None or abs(a) <= 1e-18:
        return None
    return ((b - a) / abs(a) * 100.0) / float(max(1, lookback))


def _bandwidth_trend(record: dict[str, Any]) -> tuple[str, float]:
    upper = list(record.get("_bb_upper_series") or [])
    lower = list(record.get("_bb_lower_series") or [])
    mid = list(record.get("_bb_basis_series") or [])
    if len(upper) < 4 or len(lower) < 4 or len(mid) < 4:
        return "UNKNOWN", 0.0
    widths = []
    for u, l, m in zip(upper[-4:], lower[-4:], mid[-4:]):
        uf, lf, mf = _safe_float(u), _safe_float(l), _safe_float(m)
        if uf is None or lf is None or mf is None:
            return "UNKNOWN", 0.0
        widths.append(((uf - lf) / abs(mf) * 100.0) if abs(mf) > 1e-18 else 0.0)
    delta = widths[-1] - widths[0]
    if delta > 0.20:
        return "EXPANDING", delta
    if delta < -0.20:
        return "CONTRACTING", delta
    return "FLAT", delta


def _cci_zone(value: float | None) -> str:
    if value is None:
        return "UNKNOWN"
    if value < -150.0:
        return "LT_NEG150"
    if value < -120.0:
        return "NEG150_NEG120"
    if value <= -80.0:
        return "NEG120_NEG80"
    if value < 0.0:
        return "NEG80_0"
    if value < 100.0:
        return "0_100"
    if value < 150.0:
        return "100_150"
    return "GE_150"


def _relation(cci: float | None, smoothing: float | None) -> str:
    if cci is None or smoothing is None:
        return "UNKNOWN"
    if cci > smoothing:
        return "ABOVE"
    if cci < smoothing:
        return "BELOW"
    return "TIE"


def _relation_series(cci_values: list[Any], smoothing_values: list[Any]) -> list[str]:
    return [_relation(_safe_float(c), _safe_float(s)) for c, s in zip(cci_values, smoothing_values)]


def _relation_age(relations: list[str]) -> int:
    if not relations:
        return 0
    index = len(relations) - 1
    while index >= 0 and relations[index] == "UNKNOWN":
        index -= 1
    if index < 0:
        return 0
    current = relations[index]
    age = 1
    index -= 1
    while index >= 0:
        if relations[index] == "UNKNOWN":
            index -= 1
            continue
        if relations[index] != current:
            break
        age += 1
        index -= 1
    return age


def _cross_events(
    cci_values: list[Any],
    smoothing_values: list[Any],
    color_values: list[Any],
) -> list[dict[str, Any]]:
    cci = _aligned_float_series(cci_values)
    smoothing = _aligned_float_series(smoothing_values)
    relations = _relation_series(cci_values, smoothing_values)
    colors = [_normalize_smoothing_color(x) for x in color_values]
    output: list[dict[str, Any]] = []
    for index in range(1, min(len(relations), len(cci), len(smoothing))):
        previous, current = relations[index - 1], relations[index]
        event = None
        if previous in {"BELOW", "TIE"} and current == "ABOVE":
            event = "UP"
        elif previous in {"ABOVE", "TIE"} and current == "BELOW":
            event = "DOWN"
        if event is None:
            continue
        value = cci[index]
        output.append({
            "index": index,
            "type": event,
            "cci": value,
            "sma": smoothing[index],
            "zone": _cci_zone(value),
            "sma_direction": colors[index] if index < len(colors) else "UNKNOWN",
        })
    return output


def _cross_event(relations: list[str]) -> str:
    if len(relations) < 2:
        return "UNKNOWN"
    previous, current = relations[-2], relations[-1]
    if previous in {"BELOW", "TIE"} and current == "ABOVE":
        return "CCI_CROSS_UP"
    if previous in {"ABOVE", "TIE"} and current == "BELOW":
        return "CCI_CROSS_DOWN"
    if previous == current and current != "UNKNOWN":
        return "NO_NEW_CROSS"
    return "OTHER_CROSS"


def _normalize_smoothing_color(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == "yellow":
        return "YELLOW"
    if text == "purple":
        return "PURPLE"
    if text == "gray":
        return "GRAY"
    return "UNKNOWN"


def _smoothing_age(colors: list[Any]) -> int:
    normalized = [_normalize_smoothing_color(x) for x in colors]
    if not normalized:
        return 0
    index = len(normalized) - 1
    while index >= 0 and normalized[index] == "UNKNOWN":
        index -= 1
    if index < 0:
        return 0
    current = normalized[index]
    age = 1
    index -= 1
    while index >= 0:
        if normalized[index] == "UNKNOWN":
            index -= 1
            continue
        if normalized[index] != current:
            break
        age += 1
        index -= 1
    return age


def _smoothing_turn(colors: list[Any]) -> str:
    normalized = [_normalize_smoothing_color(x) for x in colors]
    if len(normalized) < 2:
        return "UNKNOWN"
    previous, current = normalized[-2], normalized[-1]
    if previous == "PURPLE" and current == "YELLOW":
        return "PURPLE_TO_YELLOW"
    if previous == "YELLOW" and current == "PURPLE":
        return "YELLOW_TO_PURPLE"
    if previous == current:
        return "NONE"
    if current == "GRAY" or previous == "GRAY":
        return "GRAY_TRANSITION"
    return "OTHER_TURN"


def _midline_phase_at(midlines: list[Any], end_index: int | None = None) -> tuple[str, float | None, float | None]:
    values = _aligned_float_series(midlines)
    if not values:
        return "UNKNOWN", None, None
    end = len(values) - 1 if end_index is None else int(end_index)
    if end < 3:
        return "UNKNOWN", None, None

    def slope_at(offset_end: int, lookback: int = 3) -> float | None:
        start = offset_end - lookback
        if start < 0:
            return None
        a, b = values[start], values[offset_end]
        if a is None or b is None or abs(a) <= 1e-18:
            return None
        return ((b - a) / abs(a) * 100.0) / float(lookback)

    current = slope_at(end, 3)
    previous = slope_at(end - 3, 3) if end >= 6 else None
    if current is None:
        return "UNKNOWN", current, None
    change = current - previous if previous is not None else 0.0
    # This threshold only defines visual "flat" geometry; outcome direction remains learned.
    flat = 0.03
    if abs(current) <= flat:
        phase = "FLAT"
    elif current > 0:
        phase = "RISING_ACCEL" if change > 0 else "RISING_DECEL"
    else:
        phase = "FALLING_IMPROVE" if change > 0 else "FALLING_WORSEN"
    return phase, current, change


def _gap_motion(gaps: list[float | None], relation: str) -> tuple[str, float | None, float | None]:
    if len(gaps) < 2 or gaps[-1] is None or gaps[-2] is None:
        return "UNKNOWN", None, None
    velocity = float(gaps[-1]) - float(gaps[-2])
    acceleration = None
    if len(gaps) >= 3 and gaps[-3] is not None:
        previous_velocity = float(gaps[-2]) - float(gaps[-3])
        acceleration = velocity - previous_velocity
    if relation == "BELOW":
        state = "BELOW_APPROACHING" if velocity > 0 else "BELOW_SEPARATING"
    elif relation == "ABOVE":
        state = "ABOVE_EXPANDING" if velocity >= 0 else "ABOVE_PULLBACK"
    else:
        state = "TIE_OR_UNKNOWN"
    return state, velocity, acceleration


def _retest_state(relations: list[str], gaps: list[float | None], smoothing_direction: str) -> str:
    if not relations or not gaps or gaps[-1] is None:
        return "UNKNOWN"
    current_relation = relations[-1]
    recent_relations = relations[-4:]
    if smoothing_direction == "YELLOW":
        if len(recent_relations) >= 3 and recent_relations[-3:] == ["ABOVE", "BELOW", "ABOVE"]:
            return "YELLOW_RECLAIM_AFTER_BREAK"
        if current_relation == "BELOW":
            return "YELLOW_BREAK_BELOW"
        positive = [float(x) for x in gaps[-6:] if x is not None and float(x) > 0]
        if current_relation == "ABOVE" and positive:
            peak = max(positive)
            current = float(gaps[-1])
            if peak > 0 and current < peak * 0.50:
                return "YELLOW_RETEST_NEAR_SMA"
            return "YELLOW_ABOVE"
    if smoothing_direction == "PURPLE":
        if len(recent_relations) >= 3 and recent_relations[-3:] == ["BELOW", "ABOVE", "BELOW"]:
            return "PURPLE_REJECT_AFTER_BREAK"
        if current_relation == "ABOVE":
            return "PURPLE_BREAK_ABOVE"
        negative = [abs(float(x)) for x in gaps[-6:] if x is not None and float(x) < 0]
        if current_relation == "BELOW" and negative:
            peak = max(negative)
            current = abs(float(gaps[-1]))
            if peak > 0 and current < peak * 0.50:
                return "PURPLE_RETEST_NEAR_SMA"
            return "PURPLE_BELOW"
    return f"{smoothing_direction}_{current_relation}"


def _divergence_features(record: dict[str, Any], cci_values: list[Any]) -> dict[str, Any]:
    highs = _aligned_float_series(list(record.get("_raw_highs_last30") or []))
    lows = _aligned_float_series(list(record.get("_raw_lows_last30") or []))
    cci = _aligned_float_series(cci_values)
    if len(highs) < 10 or len(lows) < 10 or len(cci) < 10:
        return {
            "cci_divergence": "UNKNOWN",
            "price_high_delta_pct": None,
            "cci_high_delta": None,
            "price_low_delta_pct": None,
            "cci_low_delta": None,
        }

    def finite_window(values: list[float | None], start: int, end: int) -> list[float]:
        return [float(x) for x in values[start:end] if x is not None]

    prior_highs, recent_highs = finite_window(highs, -10, -5), finite_window(highs, -5, None)
    prior_lows, recent_lows = finite_window(lows, -10, -5), finite_window(lows, -5, None)
    prior_cci, recent_cci = finite_window(cci, -10, -5), finite_window(cci, -5, None)
    if not all((prior_highs, recent_highs, prior_lows, recent_lows, prior_cci, recent_cci)):
        return {
            "cci_divergence": "UNKNOWN",
            "price_high_delta_pct": None,
            "cci_high_delta": None,
            "price_low_delta_pct": None,
            "cci_low_delta": None,
        }

    prior_price_high, recent_price_high = max(prior_highs), max(recent_highs)
    prior_price_low, recent_price_low = min(prior_lows), min(recent_lows)
    prior_cci_high, recent_cci_high = max(prior_cci), max(recent_cci)
    prior_cci_low, recent_cci_low = min(prior_cci), min(recent_cci)

    high_pct = ((recent_price_high - prior_price_high) / abs(prior_price_high) * 100.0) if abs(prior_price_high) > 1e-18 else 0.0
    low_pct = ((recent_price_low - prior_price_low) / abs(prior_price_low) * 100.0) if abs(prior_price_low) > 1e-18 else 0.0
    high_cci_delta = recent_cci_high - prior_cci_high
    low_cci_delta = recent_cci_low - prior_cci_low

    if high_pct > 0.20 and high_cci_delta < -5.0:
        divergence = "BEARISH_PRICE_HH_CCI_LH"
    elif low_pct < -0.20 and low_cci_delta > 5.0:
        divergence = "BULLISH_PRICE_LL_CCI_HL"
    else:
        divergence = "NONE"

    return {
        "cci_divergence": divergence,
        "price_high_delta_pct": round(high_pct, 8),
        "cci_high_delta": round(high_cci_delta, 8),
        "price_low_delta_pct": round(low_pct, 8),
        "cci_low_delta": round(low_cci_delta, 8),
    }


def _cci_path_features(record: dict[str, Any]) -> dict[str, Any]:
    cci_series = list(record.get("_cci_last30") or [])
    smoothing_series = list(record.get("_cci_smoothing_ma_last30") or [])
    color_series = list(record.get("_cci_smoothing_color_last30") or [])
    midline_series = list(record.get("_bb_basis_series") or [])

    cci_values = _aligned_float_series(cci_series)
    smoothing_values = _aligned_float_series(smoothing_series)
    cci = cci_values[-1] if cci_values else None
    smoothing = smoothing_values[-1] if smoothing_values else None
    relations = _relation_series(cci_series, smoothing_series)
    relation = relations[-1] if relations else "UNKNOWN"
    cross_event = _cross_event(relations)
    smoothing_direction = _normalize_smoothing_color(color_series[-1]) if color_series else "UNKNOWN"
    relation_age = _relation_age(relations)
    smoothing_age = _smoothing_age(color_series)
    events = _cross_events(cci_series, smoothing_series, color_series)

    gaps: list[float | None] = []
    for c, s in zip(cci_values, smoothing_values):
        gaps.append((c - s) if c is not None and s is not None else None)
    gap = gaps[-1] if gaps else None
    gap_motion, gap_velocity, gap_acceleration = _gap_motion(gaps, relation)

    last_event = events[-1] if events else None
    days_since_last_cross = (len(cci_series) - 1 - int(last_event["index"])) if last_event else None
    recent_21 = [e for e in events if len(cci_series) - 1 - int(e["index"]) <= 20]
    up_events = [e for e in recent_21 if e["type"] == "UP"]
    down_events = [e for e in recent_21 if e["type"] == "DOWN"]

    if last_event:
        if days_since_last_cross == 0:
            count = len(up_events) if last_event["type"] == "UP" else len(down_events)
            cross_cycle = f"{last_event['type']}_{'SECOND_PLUS' if count >= 2 else 'FIRST'}_21D"
        elif days_since_last_cross is not None and days_since_last_cross <= 3:
            cross_cycle = f"POST_{last_event['type']}_1_3D"
        else:
            cross_cycle = f"POST_{last_event['type']}_4PLUS"
    else:
        cross_cycle = "NO_CROSS_30D"

    previous_same = None
    if last_event:
        same = [e for e in events[:-1] if e["type"] == last_event["type"]]
        previous_same = same[-1] if same else None

    midline_phase, midline_slope_3d, midline_slope_change_3d = _midline_phase_at(midline_series)
    last_cross_midline_phase = "UNKNOWN"
    if last_event and midline_series:
        # CCI and BB last-30 series are aligned to the same daily points.
        last_cross_midline_phase = _midline_phase_at(midline_series, int(last_event["index"]))[0]

    retest_state = _retest_state(relations, gaps, smoothing_direction)
    divergence = _divergence_features(record, cci_series)

    cci_slope_1d = _slope(cci_series, 1)
    cci_slope_2d = _slope(cci_series, 2)
    cci_slope_3d = _slope(cci_series, 3)
    smoothing_slope_1d = _slope(smoothing_series, 1)
    smoothing_slope_3d = _slope(smoothing_series, 3)
    midline_slope_1d = _pct_slope(midline_series, 1)
    if midline_slope_3d is None:
        midline_slope_3d = _pct_slope(midline_series, 3)

    cci_acceleration = None
    if cci_slope_1d is not None and len(cci_series) >= 3:
        previous = None
        a, b = _safe_float(cci_series[-3]), _safe_float(cci_series[-2])
        if a is not None and b is not None:
            previous = b - a
        if previous is not None:
            cci_acceleration = cci_slope_1d - previous

    return {
        "cci": round(cci, 8) if cci is not None else None,
        "cci_zone": _cci_zone(cci),
        "cci_distance_to_neg100": round(abs(cci + 100.0), 8) if cci is not None else None,
        "cci_distance_to_zero": round(abs(cci), 8) if cci is not None else None,
        "cci_smoothing_ma": round(smoothing, 8) if smoothing is not None else None,
        "cci_sma_gap": round(gap, 8) if gap is not None else None,
        "cci_sma_relation": relation,
        "cci_relation_age_days": int(relation_age),
        "cci_relation_age_bin": _bin_age(max(1, relation_age)) if relation_age else "UNKNOWN",
        "cci_cross_event": cross_event,
        "cci_cross_cycle": cross_cycle,
        "cci_days_since_last_cross": int(days_since_last_cross) if days_since_last_cross is not None else None,
        "cci_last_cross_type": str(last_event["type"]) if last_event else "NONE",
        "cci_last_cross_zone": str(last_event["zone"]) if last_event else "UNKNOWN",
        "cci_last_cross_value": round(float(last_event["cci"]), 8) if last_event and last_event.get("cci") is not None else None,
        "cci_last_cross_sma_direction": str(last_event["sma_direction"]) if last_event else "UNKNOWN",
        "cci_last_cross_midline_phase": last_cross_midline_phase,
        "cci_previous_same_cross_zone": str(previous_same["zone"]) if previous_same else "NONE",
        "cci_previous_same_cross_value": round(float(previous_same["cci"]), 8) if previous_same and previous_same.get("cci") is not None else None,
        "cci_up_cross_count_21d": len(up_events),
        "cci_down_cross_count_21d": len(down_events),
        "cci_up_cross_count_bin": "0" if len(up_events) == 0 else "1" if len(up_events) == 1 else "2_PLUS",
        "cci_down_cross_count_bin": "0" if len(down_events) == 0 else "1" if len(down_events) == 1 else "2_PLUS",
        "cci_gap_motion": gap_motion,
        "cci_gap_velocity_1d": round(gap_velocity, 8) if gap_velocity is not None else None,
        "cci_gap_acceleration": round(gap_acceleration, 8) if gap_acceleration is not None else None,
        "cci_retest_state": retest_state,
        "cci_slope_1d": round(cci_slope_1d, 8) if cci_slope_1d is not None else None,
        "cci_slope_2d": round(cci_slope_2d, 8) if cci_slope_2d is not None else None,
        "cci_slope_3d": round(cci_slope_3d, 8) if cci_slope_3d is not None else None,
        "cci_acceleration": round(cci_acceleration, 8) if cci_acceleration is not None else None,
        "cci_smoothing_slope_1d": round(smoothing_slope_1d, 8) if smoothing_slope_1d is not None else None,
        "cci_smoothing_slope_3d": round(smoothing_slope_3d, 8) if smoothing_slope_3d is not None else None,
        "cci_smoothing_direction": smoothing_direction,
        "cci_smoothing_age_days": int(smoothing_age),
        "cci_smoothing_age_bin": _bin_age(max(1, smoothing_age)) if smoothing_age else "UNKNOWN",
        "cci_smoothing_turn_event": _smoothing_turn(color_series),
        "cci_cross_on_yellow": (
            "CROSS_UP_YELLOW" if cross_event == "CCI_CROSS_UP" and smoothing_direction == "YELLOW"
            else "CROSS_UP_OTHER" if cross_event == "CCI_CROSS_UP" else "NO_CROSS_UP"
        ),
        "cci_regime": f"{relation}_{smoothing_direction}" if relation != "UNKNOWN" and smoothing_direction != "UNKNOWN" else "UNKNOWN",
        "midline_path_phase": midline_phase,
        "midline_slope_1d": round(midline_slope_1d, 8) if midline_slope_1d is not None else None,
        "midline_slope_3d": round(midline_slope_3d, 8) if midline_slope_3d is not None else None,
        "midline_slope_change_3d": round(midline_slope_change_3d, 8) if midline_slope_change_3d is not None else None,
        **divergence,
    }


def extract_features(
    record: dict[str, Any],
    opportunity: dict[str, Any],
    previous_state: str | None,
    state_age_bars: int,
) -> dict[str, Any]:
    current = opportunity.get("current") or {}
    midline = opportunity.get("midline") or {}
    purple = opportunity.get("purple_structure") or {}
    base_quality = purple.get("base_quality") or {}
    bandpos = float(current.get("ha_band_position", 0.5) or 0.5)
    bandwidth_state, bandwidth_delta = _bandwidth_trend(record)
    features = {
        "state": str(opportunity.get("market_state_id") or "OTHER"),
        "trigger_stage": str(opportunity.get("trigger_stage") or "T0"),
        "midline_state": str(midline.get("state") or "unknown"),
        "midline_slope_5d": float(midline.get("recent_5d_slope_pct_per_day") or 0.0),
        "midline_improvement": float(midline.get("slope_improvement_pct_per_day") or 0.0),
        "bandpos": bandpos,
        "bandpos_bin": _bin_bandpos(bandpos),
        "ha_color": str(current.get("ha_color") or "unknown"),
        "current_run_length": int(current.get("current_color_run_length") or 1),
        "current_run_bin": _bin_run(int(current.get("current_color_run_length") or 1)),
        "previous_state": str(previous_state or "NONE"),
        "state_age_bars": int(state_age_bars),
        "state_age_bin": _bin_age(int(state_age_bars)),
        "bandwidth_trend": bandwidth_state,
        "bandwidth_delta_3d": round(float(bandwidth_delta), 8),
        "higher_low_base": bool(base_quality.get("qualified", False)),
        "purple2_passed": str(opportunity.get("trigger_stage") or "T0") == "T2",
    }
    features.update(_cci_path_features(record))
    return features

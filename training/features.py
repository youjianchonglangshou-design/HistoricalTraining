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


def _valid_series(values: list[Any]) -> list[float]:
    output: list[float] = []
    for value in values:
        number = _safe_float(value)
        if number is not None:
            output.append(number)
    return output


def _slope_last3(values: list[Any]) -> float | None:
    series = _valid_series(values)
    if len(series) < 3:
        return None
    return (series[-1] - series[-3]) / 2.0


def _bandwidth_trend(record: dict[str, Any]) -> tuple[str, float]:
    upper = list(record.get("_bb_upper_series") or [])
    lower = list(record.get("_bb_lower_series") or [])
    mid = list(record.get("_bb_basis_series") or [])
    if len(upper) < 4 or len(lower) < 4 or len(mid) < 4:
        return "UNKNOWN", 0.0
    widths = []
    for u, l, m in zip(upper[-4:], lower[-4:], mid[-4:]):
        m = float(m)
        widths.append(((float(u) - float(l)) / abs(m) * 100.0) if abs(m) > 1e-18 else 0.0)
    delta = widths[-1] - widths[0]
    if delta > 0.20:
        return "EXPANDING", delta
    if delta < -0.20:
        return "CONTRACTING", delta
    return "FLAT", delta


def _cci_zone(value: float | None) -> str:
    """Keep the visually important CCI regions explicit without assigning direction."""
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
    return "GE_100"


def _relation(cci: float | None, smoothing: float | None) -> str:
    if cci is None or smoothing is None:
        return "UNKNOWN"
    if cci > smoothing:
        return "ABOVE"
    if cci < smoothing:
        return "BELOW"
    return "TIE"


def _relation_series(cci_values: list[Any], smoothing_values: list[Any]) -> list[str]:
    output: list[str] = []
    for cci, sma in zip(cci_values, smoothing_values):
        output.append(_relation(_safe_float(cci), _safe_float(sma)))
    return output


def _relation_age(relations: list[str]) -> int:
    valid = [x for x in relations if x != "UNKNOWN"]
    if not valid:
        return 0
    current = valid[-1]
    age = 1
    for value in reversed(valid[:-1]):
        if value != current:
            break
        age += 1
    return age


def _cross_event(relations: list[str]) -> str:
    valid = [x for x in relations if x != "UNKNOWN"]
    if len(valid) < 2:
        return "UNKNOWN"
    previous, current = valid[-2], valid[-1]
    if previous in {"BELOW", "TIE"} and current == "ABOVE":
        return "CCI_CROSS_UP"
    if previous in {"ABOVE", "TIE"} and current == "BELOW":
        return "CCI_CROSS_DOWN"
    if previous == current:
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
    valid = [x for x in normalized if x != "UNKNOWN"]
    if not valid:
        return 0
    current = valid[-1]
    age = 1
    for value in reversed(valid[:-1]):
        if value != current:
            break
        age += 1
    return age


def _smoothing_turn(colors: list[Any]) -> str:
    normalized = [_normalize_smoothing_color(x) for x in colors]
    valid = [x for x in normalized if x != "UNKNOWN"]
    if len(valid) < 2:
        return "UNKNOWN"
    previous, current = valid[-2], valid[-1]
    if previous == "PURPLE" and current == "YELLOW":
        return "PURPLE_TO_YELLOW"
    if previous == "YELLOW" and current == "PURPLE":
        return "YELLOW_TO_PURPLE"
    if previous == current:
        return "NONE"
    if current == "GRAY" or previous == "GRAY":
        return "GRAY_TRANSITION"
    return "OTHER_TURN"


def _cci_features(record: dict[str, Any]) -> dict[str, Any]:
    cci_series = list(record.get("_cci_last30") or [])
    smoothing_series = list(record.get("_cci_smoothing_ma_last30") or [])
    color_series = list(record.get("_cci_smoothing_color_last30") or [])

    cci = _safe_float(cci_series[-1]) if cci_series else None
    smoothing = _safe_float(smoothing_series[-1]) if smoothing_series else None
    relations = _relation_series(cci_series, smoothing_series)
    relation = next((x for x in reversed(relations) if x != "UNKNOWN"), "UNKNOWN")
    cross_event = _cross_event(relations)
    smoothing_direction = (
        _normalize_smoothing_color(color_series[-1]) if color_series else "UNKNOWN"
    )
    relation_age = _relation_age(relations)
    smoothing_age = _smoothing_age(color_series)

    gap = (cci - smoothing) if cci is not None and smoothing is not None else None
    cci_slope = _slope_last3(cci_series)
    smoothing_slope = _slope_last3(smoothing_series)
    zone = _cci_zone(cci)
    cross_on_yellow = (
        "CROSS_UP_YELLOW"
        if cross_event == "CCI_CROSS_UP" and smoothing_direction == "YELLOW"
        else "CROSS_UP_OTHER"
        if cross_event == "CCI_CROSS_UP"
        else "NO_CROSS_UP"
    )

    return {
        "cci": round(cci, 8) if cci is not None else None,
        "cci_zone": zone,
        "cci_distance_to_neg100": round(abs(cci + 100.0), 8) if cci is not None else None,
        "cci_smoothing_ma": round(smoothing, 8) if smoothing is not None else None,
        "cci_sma_gap": round(gap, 8) if gap is not None else None,
        "cci_sma_relation": relation,
        "cci_relation_age_days": int(relation_age),
        "cci_relation_age_bin": _bin_age(max(1, relation_age)) if relation_age else "UNKNOWN",
        "cci_cross_event": cross_event,
        "cci_slope_3d": round(cci_slope, 8) if cci_slope is not None else None,
        "cci_smoothing_slope_3d": round(smoothing_slope, 8) if smoothing_slope is not None else None,
        "cci_smoothing_direction": smoothing_direction,
        "cci_smoothing_age_days": int(smoothing_age),
        "cci_smoothing_age_bin": _bin_age(max(1, smoothing_age)) if smoothing_age else "UNKNOWN",
        "cci_smoothing_turn_event": _smoothing_turn(color_series),
        "cci_cross_on_yellow": cross_on_yellow,
        "cci_regime": (
            f"{relation}_{smoothing_direction}"
            if relation != "UNKNOWN" and smoothing_direction != "UNKNOWN"
            else "UNKNOWN"
        ),
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
    features.update(_cci_features(record))
    return features

from __future__ import annotations

import math
from typing import Any

DMI_AXIS = 20.0


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
    # Daily DMI chart slope in indicator-points per day, using the same current
    # partial daily candle that historical replay can see at this 4H cutoff.
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


def dmi_relation_from_record(record: dict[str, Any]) -> str:
    plus_series = list(record.get("_di_plus_last30") or [])
    minus_series = list(record.get("_di_minus_last30") or [])
    plus = _safe_float(plus_series[-1]) if plus_series else None
    minus = _safe_float(minus_series[-1]) if minus_series else None
    if plus is None or minus is None:
        return "UNKNOWN"
    if plus > minus:
        return "PLUS"
    if minus > plus:
        return "MINUS"
    return "TIE"


def _dmi_axis_zone(di_plus: float | None, di_minus: float | None) -> str:
    if di_plus is None or di_minus is None:
        return "UNKNOWN"
    plus_above = di_plus > DMI_AXIS
    minus_above = di_minus > DMI_AXIS
    plus_below = di_plus < DMI_AXIS
    minus_below = di_minus < DMI_AXIS
    if plus_above and minus_above:
        return "BOTH_ABOVE_20"
    if plus_below and minus_below:
        return "BOTH_BELOW_20"
    if plus_above and not minus_above:
        return "PLUS_ONLY_ABOVE_20"
    if minus_above and not plus_above:
        return "MINUS_ONLY_ABOVE_20"
    return "TOUCHING_20"


def _cross_event(previous_relation: str | None, current_relation: str) -> str:
    previous = str(previous_relation or "UNKNOWN")
    current = str(current_relation or "UNKNOWN")
    if previous == "MINUS" and current == "PLUS":
        return "PLUS_CROSS_UP"
    if previous == "PLUS" and current == "MINUS":
        return "MINUS_CROSS_UP"
    if previous == "TIE" and current == "PLUS":
        return "PLUS_TAKES_LEAD"
    if previous == "TIE" and current == "MINUS":
        return "MINUS_TAKES_LEAD"
    if current == previous and current in {"PLUS", "MINUS", "TIE"}:
        return "NO_NEW_CROSS"
    return "UNKNOWN"


def _dmi_features(
    record: dict[str, Any],
    previous_dmi_relation: str | None,
    dmi_relation_age_bars: int,
) -> dict[str, Any]:
    plus_series = list(record.get("_di_plus_last30") or [])
    minus_series = list(record.get("_di_minus_last30") or [])
    adx_series = list(record.get("_adx_last30") or [])

    di_plus = _safe_float(plus_series[-1]) if plus_series else None
    di_minus = _safe_float(minus_series[-1]) if minus_series else None
    adx = _safe_float(adx_series[-1]) if adx_series else None
    relation = dmi_relation_from_record(record)

    di_gap = (di_plus - di_minus) if di_plus is not None and di_minus is not None else None
    di_abs_gap = abs(di_gap) if di_gap is not None else None
    di_axis_distance = (
        (abs(di_plus - DMI_AXIS) + abs(di_minus - DMI_AXIS)) / 2.0
        if di_plus is not None and di_minus is not None
        else None
    )

    plus_slope = _slope_last3(plus_series)
    minus_slope = _slope_last3(minus_series)
    gap_series = [
        float(p) - float(m)
        for p, m in zip(plus_series, minus_series)
        if _safe_float(p) is not None and _safe_float(m) is not None
    ]
    gap_slope = _slope_last3(gap_series)
    adx_slope = _slope_last3(adx_series)

    return {
        # Raw values are kept in every historical case so later research can
        # inspect exact DI+/DI- values rather than only categorical rules.
        "di_plus": round(di_plus, 8) if di_plus is not None else None,
        "di_minus": round(di_minus, 8) if di_minus is not None else None,
        "di_gap": round(di_gap, 8) if di_gap is not None else None,
        "di_abs_gap": round(di_abs_gap, 8) if di_abs_gap is not None else None,
        "di_axis_distance": round(di_axis_distance, 8) if di_axis_distance is not None else None,
        "di_plus_slope_3d": round(plus_slope, 8) if plus_slope is not None else None,
        "di_minus_slope_3d": round(minus_slope, 8) if minus_slope is not None else None,
        "di_gap_slope_3d": round(gap_slope, 8) if gap_slope is not None else None,
        "adx": round(adx, 8) if adx is not None else None,
        "adx_slope_3d": round(adx_slope, 8) if adx_slope is not None else None,
        "dmi_relation": relation,
        "dmi_axis_zone": _dmi_axis_zone(di_plus, di_minus),
        "dmi_cross_event": _cross_event(previous_dmi_relation, relation),
        "dmi_cross_age_bars": int(max(1, dmi_relation_age_bars)),
        "dmi_cross_age_bin": _bin_age(int(max(1, dmi_relation_age_bars))),
    }


def extract_features(
    record: dict[str, Any],
    opportunity: dict[str, Any],
    previous_state: str | None,
    state_age_bars: int,
    previous_dmi_relation: str | None = None,
    dmi_relation_age_bars: int = 1,
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
    features.update(_dmi_features(record, previous_dmi_relation, dmi_relation_age_bars))
    return features

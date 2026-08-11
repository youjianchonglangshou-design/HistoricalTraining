from __future__ import annotations

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
    return {
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

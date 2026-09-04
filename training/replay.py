from __future__ import annotations

from typing import Any

from engine.runtime_core import build_record_from_daily_and_4h, iso_tw, utc_day_start_ms
from engine.scoring_rules import build_long_opportunity
from .features import extract_features
from .outcomes import build_confirmed_close_label, confirmed_close_target_hit

TARGET_STATES = {"S0.5", "S1", "S2", "S3"}
DEFAULT_HORIZONS = (3, 6, 12, 18)  # 12H observation only / 24H / 48H / 72H scored
LATE_SUCCESS_END_DAY = 7
FOUR_HOUR_MS = 4 * 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000


def target_name(state: str) -> str:
    if state == "S0.5":
        return "S1_OR_HIGHER"
    if state == "S2":
        return "S3"
    if state in {"S1", "S3"}:
        return "BANDPOS_GT_075"
    return "UNKNOWN"


def _new_daily(row: dict[str, Any]) -> dict[str, float]:
    return {
        "time": utc_day_start_ms(int(row["time"])),
        "open": float(row["open"]),
        "high": float(row["high"]),
        "low": float(row["low"]),
        "close": float(row["close"]),
        "volume": float(row.get("volume", 0.0)),
    }


def _update_daily(current: dict[str, float], row: dict[str, Any]) -> None:
    current["high"] = max(float(current["high"]), float(row["high"]))
    current["low"] = min(float(current["low"]), float(row["low"]))
    current["close"] = float(row["close"])
    current["volume"] = float(current.get("volume", 0.0)) + float(row.get("volume", 0.0))


def _timeline_features(features: dict[str, Any], market_type: str) -> dict[str, Any]:
    keys = [
        "midline_state", "midline_slope_5d", "midline_improvement",
        "midline_path_phase", "midline_slope_1d", "midline_slope_3d", "midline_slope_change_3d",
        "bandpos", "bandpos_bin", "trigger_stage", "bandwidth_trend", "bandwidth_delta_3d",
        "state_age_bars", "state_age_bin", "ha_color", "current_run_length", "current_run_bin",
        "cci", "cci_zone", "cci_distance_to_neg100", "cci_distance_to_zero",
        "cci_smoothing_ma", "cci_sma_gap", "cci_sma_relation",
        "cci_relation_age_days", "cci_relation_age_bin", "cci_cross_event", "cci_cross_cycle",
        "cci_days_since_last_cross", "cci_last_cross_type", "cci_last_cross_zone",
        "cci_last_cross_value", "cci_last_cross_sma_direction", "cci_last_cross_midline_phase",
        "cci_previous_same_cross_zone", "cci_previous_same_cross_value",
        "cci_up_cross_count_21d", "cci_down_cross_count_21d",
        "cci_up_cross_count_bin", "cci_down_cross_count_bin",
        "cci_gap_motion", "cci_gap_velocity_1d", "cci_gap_acceleration", "cci_retest_state",
        "cci_slope_1d", "cci_slope_2d", "cci_slope_3d", "cci_acceleration",
        "cci_smoothing_slope_1d", "cci_smoothing_slope_3d",
        "cci_smoothing_direction", "cci_smoothing_age_days", "cci_smoothing_age_bin",
        "cci_smoothing_turn_event", "cci_cross_on_yellow", "cci_regime",
        "cci_divergence", "price_high_delta_pct", "cci_high_delta", "price_low_delta_pct", "cci_low_delta",
    ]
    out = {key: features.get(key) for key in keys}
    out["market_type"] = market_type
    return out


def replay_symbol(
    symbol: str,
    rows_4h: list[dict[str, Any]],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    step_bars: int = 1,
    daily_timeline: list[dict[str, Any]] | None = None,
    allow_partial_horizons: bool = False,
    market_type: str = "CRYPTO",
) -> list[dict[str, Any]]:
    """Replay the S-state engine, but score only completed daily closes.

    v3.7 contract:
    - The engine may still calculate every 4H internally so CCI/SMA14 and
      S-state-age inputs match the live Terminal.
    - A training decision case is created only from the final completed 4H bar
      of each UTC day (Taiwan 08:00 post-close state).
    - Intraday partial-daily S-state flips never count as SUCCESS.
    - 12H is observation-only and is not a model training label.
    - 24H / 48H / 72H are judged only at the next 1 / 2 / 3 completed daily closes.
    """
    if not rows_4h:
        return []

    market_type = str(market_type or "CRYPTO").upper()
    rows = sorted(rows_4h, key=lambda x: int(x["time"]))
    daily_points: list[dict[str, Any]] = []

    completed_days: list[dict[str, float]] = []
    current_daily: dict[str, float] | None = None
    current_day_key: int | None = None
    previous_state = "NONE"
    state_age = 0

    for idx, row in enumerate(rows):
        day_key = utc_day_start_ms(int(row["time"]))
        if current_daily is None or day_key != current_day_key:
            if current_daily is not None:
                completed_days.append(current_daily)
            current_daily = _new_daily(row)
            current_day_key = day_key
        else:
            _update_daily(current_daily, row)

        daily_window = (completed_days + [current_daily])[-150:]
        if len(daily_window) < 49 or idx < 149:
            continue
        four_h_window = rows[max(0, idx - 149): idx + 1]
        record = build_record_from_daily_and_4h(symbol, daily_window, four_h_window)
        if record is None:
            continue

        opportunity = build_long_opportunity(record, None)
        state = str(opportunity.get("market_state_id") or "OTHER")
        state_age = state_age + 1 if state == previous_state else 1

        next_day_key = utc_day_start_ms(int(rows[idx + 1]["time"])) if idx + 1 < len(rows) else None
        if next_day_key != day_key:
            # Expensive path features are only needed for the formal completed-daily
            # decision point. State age still updates every 4H above, preserving live parity.
            features = extract_features(
                record,
                opportunity,
                previous_state,
                state_age,
            )
            features["market_type"] = market_type
            bandpos = float((opportunity.get("current") or {}).get("ha_band_position", 0.5) or 0.5)
            # The row timestamp is the OPEN of the last 4H candle. Once its OHLC
            # is present, the completed daily close is the next UTC midnight,
            # which is Taiwan 08:00.
            close_time = int(day_key + DAY_MS)
            structure_state = str(opportunity.get("structure_state") or "")
            purple_scope = str((opportunity.get("purple_structure") or {}).get("scope") or "")
            point = {
                "day_time": int(day_key),
                "cutoff_time": close_time,
                "state": state,
                "price": float(record["_price"]),
                "bandpos": bandpos,
                "ha_color": str(features.get("ha_color") or "unknown"),
                "trigger_stage": str(features.get("trigger_stage") or "T0"),
                "structure_state": structure_state,
                "s1_expanded": structure_state.startswith("1浪已離開"),
                "s3_expanded": structure_state.startswith("S3 已發動") or purple_scope == "wave2_pullback_expired_by_space",
                "features": _timeline_features(features, market_type),
                "source_index": idx,
            }
            daily_points.append(point)
            if daily_timeline is not None:
                daily_timeline.append({k: v for k, v in point.items() if k != "source_index"})

        previous_state = state

    if not daily_points:
        return []

    # Existing model schema keeps 6/12/18 bar keys for 24/48/72H compatibility.
    # 3 bars / 12H is intentionally absent because it is an observation-only
    # intraday window under the new contract.
    horizon_days = {6: 1, 12: 2, 18: 3}
    requested = [h for h in horizons if h in horizon_days]
    step_days = max(1, int(step_bars))
    cases: list[dict[str, Any]] = []

    for pos, point in enumerate(daily_points):
        if pos % step_days != 0:
            continue
        state = str(point.get("state") or "OTHER")
        if state not in TARGET_STATES:
            continue

        labels: dict[str, Any] = {}
        for horizon in requested:
            days = horizon_days[horizon]
            if pos + days >= len(daily_points):
                if allow_partial_horizons:
                    continue
                labels = {}
                break
            future_points = daily_points[pos + 1: pos + days + 1]
            future_snaps = [
                {
                    "state": x["state"],
                    "bandpos": x["bandpos"],
                    "price": x["price"],
                    "ha_color": x.get("ha_color"),
                    "trigger_stage": x.get("trigger_stage"),
                    "structure_state": x.get("structure_state"),
                    "s1_expanded": bool(x.get("s1_expanded")),
                    "s3_expanded": bool(x.get("s3_expanded")),
                }
                for x in future_points
            ]
            label = build_confirmed_close_label(
                state,
                future_snaps,
                entry_price=float(point.get("price", 0.0) or 0.0),
            )
            label["settlement_basis"] = "POST_CLOSE_DAILY_ROUTE_V2"
            label["confirmed_close_count"] = len(future_points)
            label["confirmed_dates_utc"] = [int(x["cutoff_time"]) for x in future_points]

            if horizon == 18 and not label.get("hit"):
                if pos + LATE_SUCCESS_END_DAY < len(daily_points):
                    late_hit = None
                    for day_no, future in enumerate(daily_points[pos + 4: pos + LATE_SUCCESS_END_DAY + 1], start=4):
                        if confirmed_close_target_hit(state, future):
                            late_hit = day_no
                            break
                    label["late_success_4_7d"] = late_hit is not None
                    label["late_bars_to_hit"] = (late_hit * 6) if late_hit is not None else None
                else:
                    label["late_success_4_7d"] = None
                    label["late_bars_to_hit"] = None
            labels[str(horizon)] = label

        if not labels:
            continue
        if not allow_partial_horizons and "18" not in labels:
            continue

        cases.append({
            "symbol": symbol,
            "market_type": market_type,
            "time": int(point["cutoff_time"]),
            "time_tw": iso_tw(int(point["cutoff_time"])),
            "state": state,
            "target": target_name(state),
            "entry_price": float(point.get("price", 0.0) or 0.0),
            "features": point["features"],
            "labels": labels,
            "decision_contract": "POST_CLOSE_DAILY_ROUTE_V2",
        })

    return cases

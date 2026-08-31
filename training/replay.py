from __future__ import annotations

from typing import Any

from engine.runtime_core import build_record_from_daily_and_4h, iso_tw, utc_day_start_ms
from engine.scoring_rules import build_long_opportunity
from .features import dmi_relation_from_record, extract_features
from .outcomes import classify_outcome

TARGET_STATES = {"S0.5", "S1", "S2", "S3"}
DEFAULT_HORIZONS = (3, 6, 12, 18)  # 12H / 24H / 48H / 72H
LATE_SUCCESS_END_BAR = 42  # optional diagnostic: day 4-7 after the 72H capital-efficiency window


def target_name(state: str) -> str:
    if state == "S0.5":
        return "S1_OR_HIGHER"
    if state == "S2":
        return "S3"
    if state in {"S1", "S3"}:
        return "BANDPOS_GT_075"
    return "UNKNOWN"


def _target_hit(source_state: str, future_state: str, future_bandpos: float) -> bool:
    if source_state == "S0.5":
        # With 4H sampling, a fast move can skip the exact S1 print. S2/S3 or >0.75
        # are accepted as evidence that the S0.5 setup progressed beyond S1 territory.
        return future_state in {"S1", "S2", "S3"} or future_bandpos > 0.75
    if source_state == "S2":
        return future_state == "S3"
    if source_state in {"S1", "S3"}:
        return future_bandpos > 0.75
    return False


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


def replay_symbol(
    symbol: str,
    rows_4h: list[dict[str, Any]],
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    step_bars: int = 1,
    daily_timeline: list[dict[str, Any]] | None = None,
    allow_partial_horizons: bool = False,
    market_type: str = "CRYPTO",
) -> list[dict[str, Any]]:
    """Replay the real S-state engine at each historical 4H cutoff without look-ahead.

    State/features are computed only from information available at that cutoff.
    Future bars are touched only later by the settlement loop.
    """
    if not rows_4h:
        return []
    market_type = str(market_type or "CRYPTO").upper()
    rows = sorted(rows_4h, key=lambda x: int(x["time"]))
    max_h = max(horizons)
    snapshots: list[dict[str, Any] | None] = [None] * len(rows)

    completed_days: list[dict[str, float]] = []
    current_daily: dict[str, float] | None = None
    current_day_key: int | None = None
    previous_state = "NONE"
    state_age = 0
    previous_dmi_relation = "UNKNOWN"
    dmi_relation_age = 0

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
        four_h_window = rows[max(0, idx - 149) : idx + 1]
        record = build_record_from_daily_and_4h(symbol, daily_window, four_h_window)
        if record is None:
            continue
        opportunity = build_long_opportunity(record, None)
        state = str(opportunity.get("market_state_id") or "OTHER")
        if state == previous_state:
            state_age += 1
        else:
            state_age = 1

        current_dmi_relation = dmi_relation_from_record(record)
        if current_dmi_relation == previous_dmi_relation and current_dmi_relation != "UNKNOWN":
            dmi_relation_age += 1
        else:
            dmi_relation_age = 1

        features = extract_features(
            record,
            opportunity,
            previous_state,
            state_age,
            previous_dmi_relation=previous_dmi_relation,
            dmi_relation_age_bars=dmi_relation_age,
        )
        features["market_type"] = market_type
        bandpos = float((opportunity.get("current") or {}).get("ha_band_position", 0.5) or 0.5)
        snapshots[idx] = {
            "state": state,
            "features": features,
            "bandpos": bandpos,
            "price": float(record["_price"]),
        }

        # Quiz timeline: capture the last available 4H engine snapshot of each
        # UTC day.  This is produced inside the same replay pass, so the quiz
        # sees the exact S-state/features (including 4H state age) that the
        # probability model was trained against without running a second engine.
        if daily_timeline is not None:
            next_day_key = (
                utc_day_start_ms(int(rows[idx + 1]["time"]))
                if idx + 1 < len(rows)
                else None
            )
            if next_day_key != day_key:
                daily_timeline.append(
                    {
                        "day_time": int(day_key),
                        "cutoff_time": int(row["time"]),
                        "state": state,
                        "price": float(record["_price"]),
                        "bandpos": bandpos,
                        "features": {
                            "market_type": market_type,
                            "midline_state": features.get("midline_state"),
                            "bandpos": features.get("bandpos"),
                            "bandpos_bin": features.get("bandpos_bin"),
                            "trigger_stage": features.get("trigger_stage"),
                            "bandwidth_trend": features.get("bandwidth_trend"),
                            "bandwidth_delta_3d": features.get("bandwidth_delta_3d"),
                            "state_age_bars": features.get("state_age_bars"),
                            "state_age_bin": features.get("state_age_bin"),
                            "di_plus": features.get("di_plus"),
                            "di_minus": features.get("di_minus"),
                            "di_gap": features.get("di_gap"),
                            "dmi_relation": features.get("dmi_relation"),
                            "dmi_axis_zone": features.get("dmi_axis_zone"),
                            "dmi_cross_event": features.get("dmi_cross_event"),
                            "dmi_cross_age_bars": features.get("dmi_cross_age_bars"),
                            "dmi_cross_age_bin": features.get("dmi_cross_age_bin"),
                            "di_plus_slope_3d": features.get("di_plus_slope_3d"),
                            "di_minus_slope_3d": features.get("di_minus_slope_3d"),
                            "di_gap_slope_3d": features.get("di_gap_slope_3d"),
                            "adx": features.get("adx"),
                            "adx_slope_3d": features.get("adx_slope_3d"),
                            "adx_axis_zone": features.get("adx_axis_zone"),
                            "adx_step_direction": features.get("adx_step_direction"),
                            "adx_step_age_days": features.get("adx_step_age_days"),
                            "adx_step_age_bin": features.get("adx_step_age_bin"),
                            "adx_turn_event": features.get("adx_turn_event"),
                            "adx_step_delta": features.get("adx_step_delta"),
                            "dmi_adx_regime": features.get("dmi_adx_regime"),
                            "adx_step_direction_legacy": features.get("adx_step_direction_legacy"),
                            "adx_step_age_days_legacy": features.get("adx_step_age_days_legacy"),
                            "adx_step_age_bin_legacy": features.get("adx_step_age_bin_legacy"),
                            "adx_turn_event_legacy": features.get("adx_turn_event_legacy"),
                            "dmi_adx_regime_legacy": features.get("dmi_adx_regime_legacy"),
                        },
                    }
                )

        previous_state = state
        previous_dmi_relation = current_dmi_relation

    cases: list[dict[str, Any]] = []
    step_bars = max(1, int(step_bars))
    for idx, snapshot in enumerate(snapshots):
        if snapshot is None or idx % step_bars != 0:
            continue
        state = str(snapshot["state"])
        if state not in TARGET_STATES:
            continue
        available_horizons = tuple(h for h in horizons if idx + h < len(rows)) if allow_partial_horizons else tuple(horizons)
        if not allow_partial_horizons and idx + max_h >= len(rows):
            continue
        if not available_horizons:
            continue

        labels: dict[str, Any] = {}
        for horizon in available_horizons:
            hit_bar = None
            max_bandpos = float(snapshot["bandpos"])
            max_return = 0.0
            min_return = 0.0
            entry_price = float(snapshot["price"])
            future_slice: list[dict[str, Any] | None] = []
            state_path = [state]
            for future_idx in range(idx + 1, idx + horizon + 1):
                future = snapshots[future_idx]
                future_slice.append(future)
                if future is None:
                    continue
                future_state = str(future["state"])
                future_bandpos = float(future["bandpos"])
                future_price = float(future["price"])
                if future_state and future_state != state_path[-1]:
                    state_path.append(future_state)
                max_bandpos = max(max_bandpos, future_bandpos)
                ret = (future_price / entry_price - 1.0) if entry_price else 0.0
                max_return = max(max_return, ret)
                min_return = min(min_return, ret)
                if hit_bar is None and _target_hit(state, future_state, future_bandpos):
                    hit_bar = future_idx - idx

            outcome_info = classify_outcome(
                state,
                future_slice,
                target_hit=hit_bar is not None,
            )
            label = {
                "hit": hit_bar is not None,
                "bars_to_hit": hit_bar,
                "max_bandpos": round(max_bandpos, 8),
                "max_return": round(max_return, 8),
                "max_drawdown": round(min_return, 8),
                "state_path": state_path,
                **outcome_info,
            }

            # Optional audit metric: if the 72H capital-efficiency target was
            # missed, did the exact same target arrive on day 4-7?  This does
            # not change the 4-way outcome at 72H; it only explains "slow" paths.
            if horizon == max_h and hit_bar is None:
                if idx + LATE_SUCCESS_END_BAR < len(rows):
                    late_hit_bar = None
                    for late_idx in range(idx + horizon + 1, idx + LATE_SUCCESS_END_BAR + 1):
                        future = snapshots[late_idx]
                        if future is None:
                            continue
                        if _target_hit(state, str(future["state"]), float(future["bandpos"])):
                            late_hit_bar = late_idx - idx
                            break
                    label["late_success_4_7d"] = late_hit_bar is not None
                    label["late_bars_to_hit"] = late_hit_bar
                else:
                    label["late_success_4_7d"] = None
                    label["late_bars_to_hit"] = None
            labels[str(horizon)] = label

        cases.append(
            {
                "symbol": symbol,
                "market_type": market_type,
                "time": int(rows[idx]["time"]),
                "time_tw": iso_tw(int(rows[idx]["time"])),
                "state": state,
                "target": target_name(state),
                "entry_price": float(snapshot["price"]),
                "features": snapshot["features"],
                "labels": labels,
            }
        )
    return cases

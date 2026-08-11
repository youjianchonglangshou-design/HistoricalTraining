from __future__ import annotations

from typing import Any

from engine.runtime_core import build_record_from_daily_and_4h, iso_tw, utc_day_start_ms
from engine.scoring_rules import build_long_opportunity
from .features import extract_features

TARGET_STATES = {"S0.5", "S1", "S2", "S3"}
DEFAULT_HORIZONS = (3, 6, 12, 18)  # 12H / 24H / 48H / 72H


def _target_name(state: str) -> str:
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
) -> list[dict[str, Any]]:
    """Replay the real S-state engine at each historical 4H cutoff without look-ahead.

    State/features are computed only from information available at that cutoff.
    Future bars are touched only later by the settlement loop.
    """
    if not rows_4h:
        return []
    rows = sorted(rows_4h, key=lambda x: int(x["time"]))
    max_h = max(horizons)
    snapshots: list[dict[str, Any] | None] = [None] * len(rows)

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
        features = extract_features(record, opportunity, previous_state, state_age)
        bandpos = float((opportunity.get("current") or {}).get("ha_band_position", 0.5) or 0.5)
        snapshots[idx] = {
            "state": state,
            "features": features,
            "bandpos": bandpos,
            "price": float(record["_price"]),
        }
        previous_state = state

    cases: list[dict[str, Any]] = []
    step_bars = max(1, int(step_bars))
    for idx, snapshot in enumerate(snapshots):
        if snapshot is None or idx % step_bars != 0:
            continue
        state = str(snapshot["state"])
        if state not in TARGET_STATES or idx + max_h >= len(rows):
            continue

        labels: dict[str, Any] = {}
        for horizon in horizons:
            hit_bar = None
            max_bandpos = float(snapshot["bandpos"])
            max_return = 0.0
            min_return = 0.0
            entry_price = float(snapshot["price"])
            for future_idx in range(idx + 1, idx + horizon + 1):
                future = snapshots[future_idx]
                if future is None:
                    continue
                future_state = str(future["state"])
                future_bandpos = float(future["bandpos"])
                future_price = float(future["price"])
                max_bandpos = max(max_bandpos, future_bandpos)
                ret = (future_price / entry_price - 1.0) if entry_price else 0.0
                max_return = max(max_return, ret)
                min_return = min(min_return, ret)
                if hit_bar is None and _target_hit(state, future_state, future_bandpos):
                    hit_bar = future_idx - idx
            labels[str(horizon)] = {
                "hit": hit_bar is not None,
                "bars_to_hit": hit_bar,
                "max_bandpos": round(max_bandpos, 8),
                "max_return": round(max_return, 8),
                "max_drawdown": round(min_return, 8),
            }

        cases.append(
            {
                "symbol": symbol,
                "time": int(rows[idx]["time"]),
                "time_tw": iso_tw(int(rows[idx]["time"])),
                "state": state,
                "target": _target_name(state),
                "entry_price": float(snapshot["price"]),
                "features": snapshot["features"],
                "labels": labels,
            }
        )
    return cases

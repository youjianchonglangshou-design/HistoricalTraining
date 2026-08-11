from __future__ import annotations

"""Headless market calculations extracted from the original Streamlit main.py.

The S-state rules themselves remain in engine/scoring_rules.py unchanged.
This module only builds the same input record shape that build_long_opportunity()
expects, so historical replay and live inference can share one engine.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Iterable

import numpy as np

from .ha_threshold import compute_threshold_from_daily_data

TW_TZ = timezone(timedelta(hours=8))
STRUCTURE_WINDOW_DAYS = 30
BB_PERIOD = 20
LIVE_DAILY_FETCH_BARS = 150
LIVE_4H_FETCH_BARS = 150
MIN_DAILY_BARS = STRUCTURE_WINDOW_DAYS + BB_PERIOD - 1
FOUR_H_MS = 4 * 60 * 60 * 1000
DAY_MS = 24 * 60 * 60 * 1000


def calculate_heikin_ashi(klines: list[dict[str, Any]]) -> list[dict[str, float]]:
    if not klines:
        return []
    output: list[dict[str, float]] = []
    previous_open = None
    previous_close = None
    for index, candle in enumerate(klines):
        open_price = float(candle["open"])
        high_price = float(candle["high"])
        low_price = float(candle["low"])
        close_price = float(candle["close"])
        ha_close = (open_price + high_price + low_price + close_price) / 4.0
        ha_open = (
            (open_price + close_price) / 2.0
            if index == 0
            else (float(previous_open) + float(previous_close)) / 2.0
        )
        output.append(
            {
                "time": int(candle["time"]),
                "open": ha_open,
                "high": max(high_price, ha_open, ha_close),
                "low": min(low_price, ha_open, ha_close),
                "close": ha_close,
            }
        )
        previous_open = ha_open
        previous_close = ha_close
    return output


def get_ha_color(candle: dict[str, Any]) -> str:
    if float(candle["close"]) > float(candle["open"]):
        return "🟢"
    if float(candle["close"]) < float(candle["open"]):
        return "🔴"
    return "⚫"


def calculate_bollinger_bands(
    klines: list[dict[str, Any]], period: int = 20, std_multiplier: float = 2.0
) -> tuple[float | None, float | None, float | None]:
    if len(klines) < period:
        return None, None, None
    closes = np.asarray([float(item["close"]) for item in klines[-period:]], dtype=float)
    basis = float(np.mean(closes))
    std = float(np.std(closes, ddof=0))
    return basis, basis + std_multiplier * std, basis - std_multiplier * std


def utc_day_start_ms(timestamp_ms: int) -> int:
    return (int(timestamp_ms) // DAY_MS) * DAY_MS


def aggregate_4h_to_daily(klines_4h: Iterable[dict[str, Any]]) -> list[dict[str, float]]:
    """Aggregate 4H candles to Pionex-style UTC daily candles."""
    rows = sorted(klines_4h, key=lambda x: int(x["time"]))
    days: list[dict[str, float]] = []
    current: dict[str, float] | None = None
    current_day = None
    for row in rows:
        t = int(row["time"])
        day = utc_day_start_ms(t)
        if current is None or day != current_day:
            if current is not None:
                days.append(current)
            current_day = day
            current = {
                "time": day,
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
            }
        else:
            current["high"] = max(float(current["high"]), float(row["high"]))
            current["low"] = min(float(current["low"]), float(row["low"]))
            current["close"] = float(row["close"])
            current["volume"] = float(current.get("volume", 0.0)) + float(row.get("volume", 0.0))
    if current is not None:
        days.append(current)
    return days


def _rolling_bb_series(raw_daily: list[dict[str, Any]], start_index: int) -> tuple[list[float], list[float], list[float]]:
    bases: list[float] = []
    uppers: list[float] = []
    lowers: list[float] = []
    closes = [float(x["close"]) for x in raw_daily]
    for idx in range(start_index, len(raw_daily)):
        window = closes[idx - BB_PERIOD + 1 : idx + 1]
        arr = np.asarray(window, dtype=float)
        basis = float(np.mean(arr))
        std = float(np.std(arr, ddof=0))
        bases.append(basis)
        uppers.append(basis + 2.0 * std)
        lowers.append(basis - 2.0 * std)
    return bases, uppers, lowers


def build_record_from_daily_and_4h(
    symbol: str,
    daily_raw_utc: list[dict[str, Any]],
    four_h_raw_utc: list[dict[str, Any]],
    api_symbol: str | None = None,
) -> dict[str, Any] | None:
    """Build the engine record from already prepared UTC daily/4H windows."""
    if len(four_h_raw_utc) < 6 or len(daily_raw_utc) < MIN_DAILY_BARS:
        return None

    daily_raw_utc = sorted(daily_raw_utc[-LIVE_DAILY_FETCH_BARS:], key=lambda x: int(x["time"]))
    four_h_raw_utc = sorted(four_h_raw_utc[-LIVE_4H_FETCH_BARS:], key=lambda x: int(x["time"]))

    # Original main.py adds +8h to Pionex timestamps before the engine sees them.
    daily_raw = [dict(x, time=int(x["time"]) + 8 * 3600 * 1000) for x in daily_raw_utc]
    four_h_raw_display = [dict(x, time=int(x["time"]) + 8 * 3600 * 1000) for x in four_h_raw_utc]

    daily_ha = calculate_heikin_ashi(daily_raw)
    four_h_ha = calculate_heikin_ashi(four_h_raw_display)
    basis, upper_band, lower_band = calculate_bollinger_bands(daily_raw, period=20, std_multiplier=2.0)
    if basis is None or upper_band is None or lower_band is None:
        return None

    price = float(four_h_raw_display[-1]["close"])
    four_h_colors = [get_ha_color(item) for item in four_h_ha[-6:]]

    last_30 = daily_ha[-STRUCTURE_WINDOW_DAYS:]
    raw_last_30 = daily_raw[-STRUCTURE_WINDOW_DAYS:]
    start_index = len(daily_raw) - len(last_30)
    band_basis_series, band_upper_series, band_lower_series = _rolling_bb_series(daily_raw, start_index)
    percentages = [
        ((float(candle["close"]) - float(sma)) / float(sma) * 100.0) if float(sma) else 0.0
        for candle, sma in zip(last_30, band_basis_series)
    ]

    bb_pct = ((price - basis) / basis * 100.0) if basis else 0.0
    threshold = compute_threshold_from_daily_data(
        daily_raw_candle=daily_raw[-1],
        daily_ha_open=daily_ha[-1]["open"],
        ordinary_close=price,
        precision=8,
    )

    current_four_h = four_h_colors[-1]
    previous_four_h = four_h_colors[-2]
    previous_four_h_1 = four_h_colors[-3] if len(four_h_colors) >= 3 else "⚫"
    previous_four_h_2 = four_h_colors[-4] if len(four_h_colors) >= 4 else "⚫"
    previous_four_h_3 = four_h_colors[-5] if len(four_h_colors) >= 5 else "⚫"

    return {
        "幣種": symbol,
        "_api_symbol": api_symbol or symbol,
        "4H前'''": previous_four_h_3,
        "4H前''": previous_four_h_2,
        "4H前'": previous_four_h_1,
        "4H前": previous_four_h,
        "4H當": current_four_h,
        "_price": price,
        "_bb1d": basis,
        "_bb_upper_1d": upper_band,
        "_bb_lower_1d": lower_band,
        "_bb_pct": bb_pct,
        "_abs_dev": abs(bb_pct),
        "_ha_pct_series": percentages,
        "_ha_curr_pct": percentages[-1],
        "_bb_basis_series": band_basis_series,
        "_bb_upper_series": band_upper_series,
        "_bb_lower_series": band_lower_series,
        "_ha_opens_last30": [float(item["open"]) for item in last_30],
        "_ha_closes_last30": [float(item["close"]) for item in last_30],
        "_ha_times_last30": [int(item["time"]) for item in last_30],
        "_raw_opens_last30": [float(item["open"]) for item in raw_last_30],
        "_raw_highs_last30": [float(item["high"]) for item in raw_last_30],
        "_raw_lows_last30": [float(item["low"]) for item in raw_last_30],
        "_raw_closes_last30": [float(item["close"]) for item in raw_last_30],
        "_ha4h_color_series": four_h_colors,
        "_ha_threshold": threshold,
    }


def build_live_compatible_record(
    symbol: str,
    four_h_history: list[dict[str, Any]],
    api_symbol: str | None = None,
) -> dict[str, Any] | None:
    """Convenience wrapper for tests/small runs; replay uses the faster prepared-window API."""
    if len(four_h_history) < 6:
        return None
    rows = sorted(four_h_history, key=lambda x: int(x["time"]))
    daily_raw_utc = aggregate_4h_to_daily(rows)[-LIVE_DAILY_FETCH_BARS:]
    four_h_raw_utc = rows[-LIVE_4H_FETCH_BARS:]
    return build_record_from_daily_and_4h(symbol, daily_raw_utc, four_h_raw_utc, api_symbol=api_symbol)


def band_position_from_record(record: dict[str, Any]) -> float:
    lower = float(record.get("_bb_lower_series", [0])[-1])
    upper = float(record.get("_bb_upper_series", [0])[-1])
    close = float(record.get("_ha_closes_last30", [0])[-1])
    width = upper - lower
    if abs(width) <= 1e-18:
        return 0.5
    return (close - lower) / width


def iso_tw(timestamp_ms: int) -> str:
    dt = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc).astimezone(TW_TZ)
    return dt.isoformat()

from __future__ import annotations

import csv
import time
from pathlib import Path
from typing import Any

import requests

from engine.symbols_config import resolve_api_symbol

API_URL = "https://api.pionex.com/api/v1/market/klines"
PAGE_LIMIT = 500
MAX_RECORDS_API = 10_000
FOUR_H_MS = 4 * 60 * 60 * 1000


def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        output.append(
            {
                "time": int(row["time"]),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row.get("volume", 0.0)),
            }
        )
    output.sort(key=lambda x: x["time"])
    return output


def fetch_4h_history(
    symbol: str,
    max_records: int = 5_000,
    min_interval_seconds: float = 0.30,
    session: requests.Session | None = None,
) -> list[dict[str, Any]]:
    """Page backward with endTime. Pionex caps each response at 500 and documents
    a maximum of 10,000 kline records.
    """
    max_records = max(1, min(int(max_records), MAX_RECORDS_API))
    http = session or requests.Session()
    api_symbol = resolve_api_symbol(symbol)
    collected: dict[int, dict[str, Any]] = {}
    end_time: int | None = None
    last_error: Exception | None = None

    while len(collected) < max_records:
        request_limit = min(PAGE_LIMIT, max_records - len(collected))
        params: dict[str, Any] = {"symbol": api_symbol, "interval": "4H", "limit": request_limit}
        if end_time is not None:
            params["endTime"] = end_time

        response = None
        for attempt in range(1, 5):
            try:
                response = http.get(API_URL, params=params, timeout=(7, 30))
                if response.status_code == 429:
                    retry_after = response.headers.get("Retry-After")
                    cooldown = max(65.0, float(retry_after) if retry_after else 0.0)
                    time.sleep(cooldown)
                    continue
                response.raise_for_status()
                payload = response.json()
                rows = payload.get("data", {}).get("klines", [])
                break
            except (requests.RequestException, ValueError) as exc:
                last_error = exc
                if attempt == 4:
                    raise
                time.sleep(1.5 * attempt)
        else:
            rows = []

        normalized = _normalize_rows(rows)
        if not normalized:
            break

        before_count = len(collected)
        for row in normalized:
            collected[int(row["time"])] = row
        added = len(collected) - before_count

        oldest = min(int(row["time"]) for row in normalized)
        next_end = oldest - 1
        if end_time is not None and next_end >= end_time:
            break
        end_time = next_end

        if len(normalized) < request_limit or added == 0:
            break
        time.sleep(max(0.0, min_interval_seconds))

    if not collected and last_error:
        raise last_error
    rows = sorted(collected.values(), key=lambda x: x["time"])
    return rows[-max_records:]


def load_csv(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(
                {
                    "time": int(row["time"]),
                    "open": float(row["open"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "close": float(row["close"]),
                    "volume": float(row.get("volume", 0.0)),
                }
            )
    rows.sort(key=lambda x: x["time"])
    return rows


def save_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=["time", "open", "high", "low", "close", "volume"])
        writer.writeheader()
        for row in sorted(rows, key=lambda x: int(x["time"])):
            writer.writerow(row)


def merge_rows(old: list[dict[str, Any]], new: list[dict[str, Any]], max_records: int) -> list[dict[str, Any]]:
    merged = {int(x["time"]): x for x in old}
    for row in new:
        merged[int(row["time"])] = row
    out = sorted(merged.values(), key=lambda x: x["time"])
    return out[-max_records:]


def update_symbol_cache(symbol: str, cache_dir: Path, max_records: int, full_refresh: bool = False) -> list[dict[str, Any]]:
    """Maintain a local history that may grow beyond Pionex's initial 10k backfill cap.

    On first/full refresh we can only backfill up to MAX_RECORDS_API. On later runs
    the newest 500 bars are merged into the local CSV, so the repository can keep
    accumulating future observations beyond the original API backfill window.
    """
    path = cache_dir / f"{symbol}.csv"
    existing = [] if full_refresh else load_csv(path)
    if full_refresh or not existing:
        fetched = fetch_4h_history(symbol, max_records=min(max_records, MAX_RECORDS_API))
    else:
        # Latest 500 is enough for routine daily continuation; merge/dedupe by timestamp.
        fetched = fetch_4h_history(symbol, max_records=PAGE_LIMIT)
    merged = merge_rows(existing, fetched, max_records=max_records)
    save_csv(path, merged)
    return merged

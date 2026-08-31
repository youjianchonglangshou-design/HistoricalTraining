from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from engine.symbols_config import EXAM_SYMBOLS
from training.champion_learning import (
    apply_case_settlement,
    build_evolution_review,
    build_performance,
    ensure_generation,
    load_json,
    load_ledger,
    make_frozen_record,
    save_json,
    save_ledger,
)
from training.model_builder import lookup_probability
from training.pionex_history import load_csv, update_symbol_cache
from training.replay import DEFAULT_HORIZONS, replay_symbol, target_name

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache" / "4h"
CHAMPION_DIR = ROOT / "data" / "champion"
GENERATION_PATH = CHAMPION_DIR / "generation.json"
GENERATIONS_PATH = CHAMPION_DIR / "generations.json"
LEDGER_PATH = CHAMPION_DIR / "ledger.jsonl"
PERFORMANCE_PATH = CHAMPION_DIR / "performance.json"
EVOLUTION_REVIEW_PATH = ROOT / "reports" / "evolution_review.json"
TARGET_STATES = {"S0.5", "S1", "S2", "S3"}


def parse_symbols(text: str) -> list[str]:
    if not text or text.upper() == "ALL":
        return list(EXAM_SYMBOLS)
    requested = [x.strip().upper() for x in text.split(",") if x.strip()]
    unknown = [x for x in requested if x not in EXAM_SYMBOLS]
    if unknown:
        raise SystemExit(f"Unknown symbols: {', '.join(unknown)}")
    return requested


def main() -> int:
    ap = argparse.ArgumentParser(description="Freeze current Champion predictions and settle previous frozen paths")
    ap.add_argument("--active-model", required=True, help="Downloaded R2 Active model JSON")
    ap.add_argument("--symbols", default="ALL")
    ap.add_argument("--max-records", type=int, default=20000)
    ap.add_argument("--cache-only", action="store_true", help="Use existing local 4H cache; do not call Pionex")
    ap.add_argument("--replay-bars", type=int, default=1500, help="Recent 4H bars used for live Champion snapshot/settlement replay")
    args = ap.parse_args()

    active_model = json.loads(Path(args.active_model).read_text(encoding="utf-8"))
    active_model_id = str(active_model.get("model_id") or "").strip()
    if not active_model_id:
        raise SystemExit("Active model has no model_id")

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    manifest = load_json(GENERATION_PATH, {"schema_version": 1, "generation": 1, "champion_model_id": "", "evolution_min_settled_72h": 200})
    history = load_json(GENERATIONS_PATH, [])
    manifest, history, _ = ensure_generation(manifest, history, active_model_id, now_iso)
    ledger = load_ledger(LEDGER_PATH)
    by_snapshot_id = {str(r.get("snapshot_id")): r for r in ledger}
    by_symbol_time: dict[tuple[str, int], dict[str, Any]] = {
        (str(r.get("symbol") or ""), int(r.get("decision_time", 0))): r for r in ledger
    }

    symbols = parse_symbols(args.symbols)
    max_records = max(500, min(50000, int(args.max_records)))
    replay_bars = max(500, min(max_records, int(args.replay_bars)))
    new_snapshots = 0
    settled_updates = 0

    for pos, symbol in enumerate(symbols, start=1):
        print(f"[{pos}/{len(symbols)}] {symbol}: update cache + replay", flush=True)
        rows = load_csv(CACHE_DIR / f"{symbol}.csv")[-max_records:] if args.cache_only else update_symbol_cache(symbol, CACHE_DIR, max_records=max_records, full_refresh=False)
        review_rows = rows[-replay_bars:]
        timeline: list[dict[str, Any]] = []
        cases = replay_symbol(
            symbol,
            review_rows,
            horizons=DEFAULT_HORIZONS,
            step_bars=1,
            daily_timeline=timeline,
            allow_partial_horizons=True,
        )

        case_index = {int(c.get("time", 0)): c for c in cases}
        for (row_symbol, decision_time), frozen in list(by_symbol_time.items()):
            if row_symbol != symbol:
                continue
            case = case_index.get(decision_time)
            if case and apply_case_settlement(frozen, case):
                settled_updates += 1

        if not timeline:
            continue
        latest = timeline[-1]
        state = str(latest.get("state") or "")
        if state not in TARGET_STATES:
            continue
        prediction = lookup_probability(active_model, state, 18, latest.get("features") or {})
        if not prediction.get("available"):
            continue
        snapshot_id = f"{active_model_id}:{symbol}:{int(latest['cutoff_time'])}"
        if snapshot_id in by_snapshot_id:
            continue
        frozen = make_frozen_record(
            symbol=symbol,
            model=active_model,
            timeline_row=latest,
            prediction=prediction,
            target=target_name(state),
            frozen_at_iso=now_iso,
            generation=int(manifest.get("generation") or 1),
        )
        ledger.append(frozen)
        by_snapshot_id[snapshot_id] = frozen
        by_symbol_time[(symbol, int(latest["cutoff_time"]))] = frozen
        new_snapshots += 1

    performance = build_performance(ledger, manifest, history, now_ms=now_ms)
    evolution_review = build_evolution_review(ledger, manifest)

    save_json(GENERATION_PATH, manifest)
    save_json(GENERATIONS_PATH, history)
    save_ledger(LEDGER_PATH, ledger)
    save_json(PERFORMANCE_PATH, performance)
    save_json(EVOLUTION_REVIEW_PATH, evolution_review)

    print(f"Champion={active_model_id}")
    print(f"Generation={manifest.get('generation')}")
    print(f"Frozen new snapshots={new_snapshots}")
    print(f"Settlement updates={settled_updates}")
    print(f"Settled 72H={evolution_review.get('settled_72h')}")
    print(f"Evolution due={evolution_review.get('evolution_due')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

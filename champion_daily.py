from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from engine.symbols_config import EXAM_SYMBOLS, get_unlocked_rwa_symbols, is_rwa_symbol
from training.champion_learning import (
    apply_case_settlement,
    build_evolution_policy,
    build_evolution_review,
    build_performance,
    ensure_generation,
    load_json,
    load_ledger,
    make_frozen_record,
    prune_rolling_ledger,
    save_json,
    save_ledger,
    save_ledger_shards,
)
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
EVOLUTION_POLICY_PATH = ROOT / "reports" / "evolution_policy.json"
TARGET_STATES = {"S0.5", "S1", "S2", "S3"}
FOUR_HOUR_MS = 4 * 60 * 60 * 1000
TW = timezone(timedelta(hours=8))


def champion_symbols() -> list[str]:
    return list(dict.fromkeys([*EXAM_SYMBOLS, *get_unlocked_rwa_symbols()]))


def parse_symbols(text: str) -> list[str]:
    key = str(text or "ALL").strip().upper()
    if key == "ALL":
        return champion_symbols()
    if key in {"CRYPTO", "CRYPTO_ONLY"}:
        return list(EXAM_SYMBOLS)
    if key in {"US_STOCK", "US-STOCK", "RWA"}:
        return list(get_unlocked_rwa_symbols())
    allowed = set(champion_symbols())
    requested = [x.strip().upper() for x in text.split(",") if x.strip()]
    unknown = [x for x in requested if x not in allowed]
    if unknown:
        raise SystemExit(f"Unknown symbols: {', '.join(unknown)}")
    return requested


def _parse_checkpoint_time(value: Any) -> datetime:
    text = str(value or "").strip()
    if not text:
        raise ValueError("checkpoint batch.generated_at_taiwan missing")
    normalized = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=TW)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=TW)
    return parsed


def checkpoint_cutoff_ms(payload: dict[str, Any]) -> int:
    generated = _parse_checkpoint_time((payload.get("batch") or {}).get("generated_at_taiwan"))
    utc_ms = int(generated.astimezone(timezone.utc).timestamp() * 1000)
    return (utc_ms // FOUR_HOUR_MS) * FOUR_HOUR_MS


def load_checkpoint(path: str | None, market_type: str) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.exists() or p.stat().st_size == 0:
        print(f"[checkpoint] {market_type}: file missing; settlement continues without new freeze")
        return None
    payload = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(payload.get("records"), list):
        raise ValueError(f"{market_type} checkpoint records missing")
    generated = _parse_checkpoint_time((payload.get("batch") or {}).get("generated_at_taiwan"))
    payload["_checkpoint_market_type"] = market_type
    payload["_checkpoint_cutoff_ms"] = checkpoint_cutoff_ms(payload)
    payload["_checkpoint_generated_at"] = generated.isoformat()
    return payload


def checkpoint_model_id(payload: dict[str, Any] | None) -> str:
    if not payload:
        return ""
    batch_model = (((payload.get("batch") or {}).get("probability_model") or {}).get("model_id"))
    if batch_model:
        return str(batch_model)
    for row in payload.get("records") or []:
        model_id = ((row.get("historical_probability") or {}).get("model_id"))
        if model_id:
            return str(model_id)
    return ""


def checkpoint_records_by_symbol(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not payload:
        return {}
    result: dict[str, dict[str, Any]] = {}
    for row in payload.get("records") or []:
        symbol = str(row.get("symbol") or "").strip().upper()
        if symbol:
            result[symbol] = row
    return result


def frozen_from_terminal_checkpoint(
    *,
    row: dict[str, Any],
    payload: dict[str, Any],
    market_type: str,
    generation: int,
    active_model_id: str,
    frozen_at_iso: str,
) -> dict[str, Any] | None:
    probability = dict(row.get("historical_probability") or {})
    opportunity = dict(row.get("opportunity_long") or {})
    state = str(probability.get("state") or opportunity.get("market_state_id") or "")
    if state not in TARGET_STATES or not probability.get("available"):
        return None

    model_id = str(probability.get("model_id") or checkpoint_model_id(payload) or "")
    if model_id != active_model_id:
        # Do not mis-attribute a 04:01 prediction to another generation.
        print(
            f"[checkpoint] SKIP {market_type}/{row.get('symbol')}: "
            f"04:01 model={model_id or '?'} != active Champion={active_model_id}"
        )
        return None

    p72 = dict(probability.get("72h") or {})
    if not p72.get("available"):
        return None

    cutoff_ms = int(payload["_checkpoint_cutoff_ms"])
    current = dict(opportunity.get("current") or {})
    features = dict(probability.get("features") or {})
    features["market_type"] = market_type

    timeline_row = {
        "cutoff_time": cutoff_ms,
        "state": state,
        "price": float(row.get("price", 0.0) or 0.0),
        "bandpos": float(current.get("ha_band_position", features.get("bandpos", 0.0)) or 0.0),
        "features": features,
    }
    prediction = {
        "available": True,
        "probability": float(p72.get("success_probability", 0.0) or 0.0),
        "alive_slow_probability": float(p72.get("alive_slow_probability", 0.0) or 0.0),
        "structural_survival_probability": float(p72.get("structural_survival_probability", 0.0) or 0.0),
        "true_fail_probability": float(p72.get("true_fail_probability", 0.0) or 0.0),
        "other_probability": float(p72.get("other_probability", 0.0) or 0.0),
        "samples": int(p72.get("matched_samples", probability.get("matched_samples", 0)) or 0),
        "level": int(p72.get("level", probability.get("model_level", 0)) or 0),
        "signature": p72.get("signature"),
        "dmi_expert": p72.get("dmi_expert") or probability.get("dmi_expert") or {},
    }
    frozen = make_frozen_record(
        symbol=str(row.get("symbol") or "").strip().upper(),
        model={"model_id": model_id},
        timeline_row=timeline_row,
        prediction=prediction,
        target=str(probability.get("target") or target_name(state)),
        frozen_at_iso=frozen_at_iso,
        generation=generation,
        market_type=market_type,
    )
    frozen["frozen_source"] = "TERMINAL_0401_CHECKPOINT"
    frozen["checkpoint_time_tw"] = str(payload.get("_checkpoint_generated_at") or "")
    frozen["checkpoint_snapshot_hash"] = (payload.get("batch") or {}).get("snapshot_hash")
    frozen["checkpoint_engine_version"] = (payload.get("batch") or {}).get("engine_version")
    frozen["checkpoint_probability_model_id"] = model_id
    return frozen


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Settle previous Champion paths and freeze the real Terminal 04:01 Champion checkpoint"
    )
    ap.add_argument("--active-model", required=True, help="Downloaded R2 Active model JSON")
    ap.add_argument("--checkpoint-crypto", default="", help="Terminal 04:01 Crypto checkpoint JSON")
    ap.add_argument("--checkpoint-us-stock", default="", help="Terminal 04:01 US-stock checkpoint JSON")
    ap.add_argument("--symbols", default="ALL")
    ap.add_argument("--max-records", type=int, default=20000)
    ap.add_argument("--cache-only", action="store_true", help="Use existing local 4H cache; do not call Pionex")
    ap.add_argument("--replay-bars", type=int, default=1500, help="Recent 4H bars used only for path settlement replay")
    ap.add_argument("--ledger-cache", default=str(LEDGER_PATH), help="Recent ledger cache loaded from R2 export; not the long-term source of truth")
    ap.add_argument("--ledger-cache-days", type=int, default=3650, help="Temporary rolling ledger retention; workflow cache lives in /tmp, long-term truth is R2 shards")
    ap.add_argument("--r2-shard-dir", default=str(ROOT / "data" / "champion" / "r2_shards"), help="Output directory for Generation/date R2 ledger shards")
    args = ap.parse_args()

    active_model = json.loads(Path(args.active_model).read_text(encoding="utf-8"))
    active_model_id = str(active_model.get("model_id") or "").strip()
    if not active_model_id:
        raise SystemExit("Active model has no model_id")

    checkpoints = {
        "CRYPTO": load_checkpoint(args.checkpoint_crypto, "CRYPTO"),
        "US_STOCK": load_checkpoint(args.checkpoint_us_stock, "US_STOCK"),
    }
    for market_type, payload in checkpoints.items():
        if not payload:
            continue
        cid = checkpoint_model_id(payload)
        print(
            f"[checkpoint] {market_type}: generated={payload['_checkpoint_generated_at']} "
            f"cutoff={payload['_checkpoint_cutoff_ms']} model={cid or '?'} "
            f"records={len(payload.get('records') or [])}"
        )

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    now_ms = int(now.timestamp() * 1000)

    manifest = load_json(
        GENERATION_PATH,
        {
            "schema_version": 1,
            "generation": 1,
            "champion_model_id": "",
            "evolution_min_settled_72h": 120,
        },
    )
    history = load_json(GENERATIONS_PATH, [])
    manifest, history, _ = ensure_generation(manifest, history, active_model_id, now_iso)

    ledger_path = Path(args.ledger_cache)
    shard_dir = Path(args.r2_shard_dir)
    ledger = load_ledger(ledger_path)
    by_snapshot_id = {str(r.get("snapshot_id")): r for r in ledger}
    by_symbol_time: dict[tuple[str, str, int], dict[str, Any]] = {
        (
            str(r.get("market_type") or "CRYPTO"),
            str(r.get("symbol") or ""),
            int(r.get("decision_time", 0)),
        ): r
        for r in ledger
    }

    checkpoint_rows = {
        market_type: checkpoint_records_by_symbol(payload)
        for market_type, payload in checkpoints.items()
    }

    symbols = parse_symbols(args.symbols)
    max_records = max(500, min(50000, int(args.max_records)))
    replay_bars = max(500, min(max_records, int(args.replay_bars)))
    new_snapshots = 0
    settled_updates = 0

    for pos, symbol in enumerate(symbols, start=1):
        market_type = "US_STOCK" if is_rwa_symbol(symbol) else "CRYPTO"
        print(f"[{pos}/{len(symbols)}] {market_type}/{symbol}: update cache + settle replay", flush=True)

        # 08:25 still refreshes market data, but ONLY for settlement of previously
        # frozen 04:01 predictions. It never creates a new prediction from this
        # 08:25 partial Daily candle.
        symbol_max_records = min(max_records, replay_bars) if market_type == "US_STOCK" else max_records
        rows = (
            load_csv(CACHE_DIR / f"{symbol}.csv")[-symbol_max_records:]
            if args.cache_only
            else update_symbol_cache(
                symbol,
                CACHE_DIR,
                max_records=symbol_max_records,
                full_refresh=False,
            )
        )
        review_rows = rows[-replay_bars:]
        cases = replay_symbol(
            symbol,
            review_rows,
            horizons=DEFAULT_HORIZONS,
            step_bars=1,
            daily_timeline=None,
            allow_partial_horizons=True,
            market_type=market_type,
        )
        case_index = {int(c.get("time", 0)): c for c in cases}

        for (row_market, row_symbol, decision_time), frozen in list(by_symbol_time.items()):
            if row_market != market_type or row_symbol != symbol:
                continue
            case = case_index.get(decision_time)
            if case and apply_case_settlement(frozen, case):
                settled_updates += 1

        payload = checkpoints.get(market_type)
        checkpoint_row = checkpoint_rows.get(market_type, {}).get(symbol)
        if not payload or not checkpoint_row:
            continue

        frozen = frozen_from_terminal_checkpoint(
            row=checkpoint_row,
            payload=payload,
            market_type=market_type,
            generation=int(manifest.get("generation") or 1),
            active_model_id=active_model_id,
            frozen_at_iso=now_iso,
        )
        if not frozen:
            continue
        snapshot_id = str(frozen.get("snapshot_id") or "")
        if not snapshot_id or snapshot_id in by_snapshot_id:
            continue

        ledger.append(frozen)
        by_snapshot_id[snapshot_id] = frozen
        by_symbol_time[
            (market_type, symbol, int(frozen["decision_time"]))
        ] = frozen
        new_snapshots += 1

    performance = build_performance(ledger, manifest, history, now_ms=now_ms)
    evolution_review = build_evolution_review(ledger, manifest)
    evolution_policy = build_evolution_policy(evolution_review, ledger, manifest)

    # R2 Generation/date shards are the authoritative long-term ledger.
    # The local ledger is now only a bounded recent cache so Git history can
    # never grow without limit.
    rolling_ledger = prune_rolling_ledger(
        ledger,
        now_ms=now_ms,
        keep_days=max(7, min(3650, int(args.ledger_cache_days))),
    )
    shard_manifest = save_ledger_shards(shard_dir, rolling_ledger)

    save_json(GENERATION_PATH, manifest)
    save_json(GENERATIONS_PATH, history)
    save_ledger(ledger_path, rolling_ledger)
    save_json(PERFORMANCE_PATH, performance)
    save_json(EVOLUTION_REVIEW_PATH, evolution_review)
    save_json(EVOLUTION_POLICY_PATH, evolution_policy)

    print(f"Champion={active_model_id}")
    print(f"Generation={manifest.get('generation')}")
    print(f"Frozen new 04:01 snapshots={new_snapshots}")
    print(f"Settlement updates={settled_updates}")
    print(f"Settled 72H={evolution_review.get('settled_72h')}")
    print(f"Evolution due={evolution_review.get('evolution_due')}")
    print(f"Evolution policy={evolution_policy.get('policy_id')} active={evolution_policy.get('active_for_next_training')}")
    print(f"R2 ledger shards prepared={len(shard_manifest)} in {shard_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from engine.symbols_config import EXAM_SYMBOLS, get_unlocked_rwa_symbols, is_rwa_symbol
from training.champion_learning import (
    apply_confirmed_daily_settlements,
    is_official_daily_record,
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
from training.replay import target_name

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


def _daily_exam_key(row: dict[str, Any]) -> tuple[int, str, str, str, str] | None:
    date_tw = str(row.get("decision_date_tw") or "").strip()[:10]
    symbol = str(row.get("symbol") or "").strip().upper()
    if not date_tw or not symbol:
        return None
    return (
        int(row.get("generation") or 0),
        str(row.get("champion_model_id") or ""),
        str(row.get("market_type") or "CRYPTO").upper(),
        symbol,
        date_tw,
    )


def _collapse_same_day_official_duplicates(ledger: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    """Keep one exam per symbol/date once a formal 08:25 row exists.

    Legacy rows on dates without a formal 08:25 exam remain untouched. When a
    formal row exists, it becomes the canonical daily exam and same-day legacy
    copies are folded into its audit metadata instead of remaining as duplicate
    visible exams.
    """
    groups: dict[tuple[int, str, str, str, str], list[dict[str, Any]]] = {}
    unkeyed: list[dict[str, Any]] = []
    for row in ledger:
        key = _daily_exam_key(row)
        if key is None:
            unkeyed.append(row)
            continue
        groups.setdefault(key, []).append(row)

    output: list[dict[str, Any]] = list(unkeyed)
    removed = 0
    for rows in groups.values():
        official = [r for r in rows if is_official_daily_record(r)]
        if not official:
            output.extend(rows)
            continue
        official.sort(key=lambda r: int(r.get("decision_time", 0) or 0), reverse=True)
        canonical = official[0]
        duplicate_ids = [
            str(r.get("snapshot_id") or "")
            for r in rows
            if r is not canonical and str(r.get("snapshot_id") or "")
        ]
        if duplicate_ids:
            prior = list(canonical.get("merged_same_day_snapshot_ids") or [])
            canonical["merged_same_day_snapshot_ids"] = list(dict.fromkeys([*prior, *duplicate_ids]))
        output.append(canonical)
        removed += len(rows) - 1

    output.sort(key=lambda r: (int(r.get("decision_time", 0) or 0), str(r.get("symbol") or "")))
    return output, removed


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
    batch = payload.get("batch") or {}
    formal = batch.get("champion_daily_checkpoint") or {}
    cutoff_text = str(formal.get("confirmed_close_cutoff_utc") or "").strip()
    if cutoff_text:
        parsed = datetime.fromisoformat(cutoff_text.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return int(parsed.astimezone(timezone.utc).timestamp() * 1000)
    generated = _parse_checkpoint_time(batch.get("generated_at_taiwan"))
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
    batch = payload.get("batch") or {}
    formal = batch.get("champion_daily_checkpoint") or {}
    if str(formal.get("contract") or "") != "TAIWAN_0825_USING_COMPLETED_0800_DAILY_CLOSE":
        raise ValueError(f"{market_type} checkpoint is not v3.6 daily-confirmed 08:25 contract")
    if formal.get("partial_daily_excluded") is not True or formal.get("partial_4h_after_close_excluded") is not True:
        raise ValueError(f"{market_type} checkpoint did not exclude post-08:00 partial candles")
    generated = _parse_checkpoint_time(batch.get("generated_at_taiwan"))
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



def confirmed_snapshot_from_row(row: dict[str, Any]) -> dict[str, Any]:
    opportunity = dict(row.get("opportunity_long") or {})
    current = dict(opportunity.get("current") or {})
    probability = dict(row.get("historical_probability") or {})
    state = str(opportunity.get("market_state_id") or probability.get("state") or "OTHER")
    structure_state = str(opportunity.get("structure_state") or "")
    purple_scope = str((opportunity.get("purple_structure") or {}).get("scope") or "")
    return {
        "state": state,
        "price": float(row.get("price", 0.0) or 0.0),
        "bandpos": float(current.get("ha_band_position", 0.5) or 0.5),
        "ha_color": str(current.get("ha_color") or "unknown"),
        "trigger_stage": str(opportunity.get("trigger_stage") or "T0"),
        "structure_state": structure_state,
        "s1_expanded": structure_state.startswith("1浪已離開"),
        "s3_expanded": structure_state.startswith("S3 已發動") or purple_scope == "wave2_pullback_expired_by_space",
    }


def load_checkpoint_history_dir(path: str | None) -> dict[str, dict[str, dict[str, dict[str, Any]]]]:
    """Return market -> date_tw -> symbol -> completed daily snapshot."""
    output: dict[str, dict[str, dict[str, dict[str, Any]]]] = {"CRYPTO": {}, "US_STOCK": {}}
    if not path:
        return output
    root = Path(path)
    if not root.exists():
        return output
    for fp in sorted(root.glob("*.json")):
        name = fp.stem
        if name.endswith("_crypto"):
            market_type = "CRYPTO"
            date_tw = name[:-7]
        elif name.endswith("_us-stock"):
            market_type = "US_STOCK"
            date_tw = name[:-9]
        else:
            continue
        try:
            payload = load_checkpoint(str(fp), market_type)
        except Exception as exc:
            print(f"[checkpoint-history] skip {fp.name}: {exc}")
            continue
        if not payload:
            continue
        records = checkpoint_records_by_symbol(payload)
        output[market_type][date_tw] = {
            symbol: confirmed_snapshot_from_row(row)
            for symbol, row in records.items()
        }
    return output

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
        # Do not mis-attribute an 08:25 daily-confirmed prediction to another generation.
        print(
            f"[checkpoint] SKIP {market_type}/{row.get('symbol')}: "
            f"08:25 model={model_id or '?'} != active Champion={active_model_id}"
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
    frozen["frozen_source"] = "TERMINAL_0825_DAILY_CHECKPOINT"
    frozen["checkpoint_time_tw"] = str(payload.get("_checkpoint_generated_at") or "")
    frozen["checkpoint_snapshot_hash"] = (payload.get("batch") or {}).get("snapshot_hash")
    frozen["checkpoint_engine_version"] = (payload.get("batch") or {}).get("engine_version")
    frozen["checkpoint_probability_model_id"] = model_id
    return frozen


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Settle Champion paths from completed daily closes and freeze the Terminal 08:25 daily-confirmed checkpoint"
    )
    ap.add_argument("--active-model", required=True, help="Downloaded R2 Active model JSON")
    ap.add_argument("--checkpoint-crypto", default="", help="Terminal 08:25 daily-confirmed Crypto checkpoint JSON")
    ap.add_argument("--checkpoint-us-stock", default="", help="Terminal 08:25 daily-confirmed US-stock checkpoint JSON")
    ap.add_argument("--symbols", default="ALL")
    ap.add_argument("--max-records", type=int, default=20000)
    ap.add_argument("--cache-only", action="store_true", help="Use existing local 4H cache; do not call Pionex")
    ap.add_argument("--ledger-cache", default=str(LEDGER_PATH), help="Recent ledger cache loaded from R2 export; not the long-term source of truth")
    ap.add_argument("--ledger-cache-days", type=int, default=3650, help="Temporary rolling ledger retention; workflow cache lives in /tmp, long-term truth is R2 shards")
    ap.add_argument("--r2-shard-dir", default=str(ROOT / "data" / "champion" / "r2_shards"), help="Output directory for Generation/date R2 ledger shards")
    ap.add_argument("--checkpoint-history-dir", default="", help="Directory containing exact daily 08:25 checkpoints used to regrade 24H/48H/72H")
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
    legacy_excluded = 0
    for row in ledger:
        if str(row.get("frozen_source") or "") != "TERMINAL_0825_DAILY_CHECKPOINT":
            row["official_scoring"] = False
            row["legacy_exclusion_reason"] = "PRE_0825_OR_INTRADAY_CONTRACT_NOT_COMPARABLE"
            legacy_excluded += 1
        else:
            row["official_scoring"] = True
    ledger, same_day_duplicates_collapsed = _collapse_same_day_official_duplicates(ledger)
    by_snapshot_id = {str(r.get("snapshot_id")): r for r in ledger}
    by_daily_exam = {
        key: row for row in ledger if (key := _daily_exam_key(row)) is not None
    }
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
    new_snapshots = 0
    replaced_same_day_legacy_snapshots = 0
    settled_updates = 0

    checkpoint_history = load_checkpoint_history_dir(args.checkpoint_history_dir)
    # Always expose today's checkpoint to the settlement map even when the
    # workflow only supplied it through --checkpoint-crypto / --checkpoint-us-stock.
    for market_type, payload in checkpoints.items():
        if not payload:
            continue
        date_tw = _parse_checkpoint_time((payload.get("batch") or {}).get("generated_at_taiwan")).astimezone(TW).date().isoformat()
        checkpoint_history.setdefault(market_type, {})[date_tw] = {
            symbol: confirmed_snapshot_from_row(row)
            for symbol, row in checkpoint_records_by_symbol(payload).items()
        }

    for pos, symbol in enumerate(symbols, start=1):
        market_type = "US_STOCK" if is_rwa_symbol(symbol) else "CRYPTO"
        print(f"[{pos}/{len(symbols)}] {market_type}/{symbol}: update cache + daily-confirmed settlement", flush=True)

        # Keep the 4H cache fresh for future model evolution, but NEVER use an
        # intraday partial-daily state to score a Frozen Champion prediction.
        symbol_max_records = min(max_records, 1500) if market_type == "US_STOCK" else max_records
        if args.cache_only:
            load_csv(CACHE_DIR / f"{symbol}.csv")[-symbol_max_records:]
        else:
            update_symbol_cache(
                symbol,
                CACHE_DIR,
                max_records=symbol_max_records,
                full_refresh=False,
            )

        confirmed_by_date = {
            date_tw: symbols_map[symbol]
            for date_tw, symbols_map in (checkpoint_history.get(market_type) or {}).items()
            if symbol in symbols_map
        }
        for (row_market, row_symbol, _decision_time), frozen in list(by_symbol_time.items()):
            if row_market != market_type or row_symbol != symbol:
                continue
            # Regrade ALL historical Frozen exams from completed daily closes.
            # official_scoring controls only whether the row contributes to the
            # 120-case Champion statistics/evolution. It must never hide or
            # freeze an incorrect old settlement.
            if apply_confirmed_daily_settlements(frozen, confirmed_by_date):
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
        frozen["official_scoring"] = True
        # New daily exams start with 12H observation semantics immediately, so
        # a just-created row can never display 12H as "PENDING".
        apply_confirmed_daily_settlements(frozen, confirmed_by_date)

        snapshot_id = str(frozen.get("snapshot_id") or "")
        if not snapshot_id:
            continue
        daily_key = _daily_exam_key(frozen)
        existing = by_daily_exam.get(daily_key) if daily_key is not None else None
        if existing is not None:
            # A formal 08:25 row already owns this symbol/date. Never append a
            # second exam during repair/re-run. If the existing row is legacy,
            # replace that same-day slot with the formal row instead of adding
            # another visible record.
            if is_official_daily_record(existing):
                continue
            try:
                idx = ledger.index(existing)
            except ValueError:
                idx = -1
            merged_ids = [str(existing.get("snapshot_id") or "")]
            frozen["merged_same_day_snapshot_ids"] = [x for x in merged_ids if x]
            if idx >= 0:
                ledger[idx] = frozen
            else:
                ledger.append(frozen)
            by_daily_exam[daily_key] = frozen
            by_snapshot_id[snapshot_id] = frozen
            by_symbol_time[(market_type, symbol, int(frozen["decision_time"]))] = frozen
            replaced_same_day_legacy_snapshots += 1
            continue

        if snapshot_id in by_snapshot_id:
            continue
        ledger.append(frozen)
        by_snapshot_id[snapshot_id] = frozen
        if daily_key is not None:
            by_daily_exam[daily_key] = frozen
        by_symbol_time[(market_type, symbol, int(frozen["decision_time"]))] = frozen
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
    print(f"Frozen new 08:25 daily-confirmed snapshots={new_snapshots}")
    print(f"Same-day duplicate exams collapsed={same_day_duplicates_collapsed}")
    print(f"Replaced same-day legacy pre-08:25 snapshots={replaced_same_day_legacy_snapshots}")
    print(f"Legacy pre-08:25 records excluded from official scoring={legacy_excluded}")
    print(f"Settlement updates={settled_updates}")
    print(f"Settled 72H={evolution_review.get('settled_72h')}")
    print(f"Evolution due={evolution_review.get('evolution_due')}")
    print(f"Evolution policy={evolution_policy.get('policy_id')} active={evolution_policy.get('active_for_next_training')}")
    print(f"R2 ledger shards prepared={len(shard_manifest)} in {shard_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

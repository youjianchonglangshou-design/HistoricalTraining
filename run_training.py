from __future__ import annotations

import argparse
import json
import sys
import traceback
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

from engine.scoring_rules import ENGINE_API_VERSION, OPPORTUNITY_ENGINE_VERSION, PURPLE2_RULE_VERSION
from engine.symbols_config import EXAM_SYMBOLS, get_unlocked_rwa_symbols, is_rwa_symbol
from training.io_utils import write_jsonl_gz
from training.champion_learning import (
    adaptive_reinforcement_weight,
    current_generation_frozen_cases,
    load_json as load_champion_json,
    load_ledger,
)
from training.model_builder import build_model, lookup_probability, save_json, summarize_path_tree
from training.outcomes import OUTCOME_KEYS, OUTCOME_SUCCESS
from training.pionex_history import load_csv, update_symbol_cache
from training.replay import DEFAULT_HORIZONS, replay_symbol

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache" / "4h"
CASES_PATH = ROOT / "data" / "cases" / "history_cases.jsonl.gz"
MODEL_PATH = ROOT / "models" / "probability_model.json"
REPORT_PATH = ROOT / "reports" / "training_report.json"
META_PATH = ROOT / "data" / "learning_meta.json"
QUIZ_TIMELINE_DIR = ROOT / "quiz" / "model_timeline"
CHAMPION_LEDGER_PATH = ROOT / "data" / "champion" / "ledger.jsonl"
EVOLUTION_POLICY_PATH = ROOT / "reports" / "evolution_policy.json"
CHAMPION_GENERATION_PATH = ROOT / "data" / "champion" / "generation.json"
PRIMARY_HORIZON = 18


def all_training_symbols() -> list[str]:
    return list(dict.fromkeys([*EXAM_SYMBOLS, *get_unlocked_rwa_symbols()]))


def parse_symbols(text: str) -> list[str]:
    key = str(text or "ALL").strip().upper()
    if key == "ALL":
        return all_training_symbols()
    if key in {"CRYPTO", "CRYPTO_ONLY"}:
        return list(EXAM_SYMBOLS)
    if key in {"US_STOCK", "US-STOCK", "RWA"}:
        return list(get_unlocked_rwa_symbols())
    allowed = set(all_training_symbols())
    requested = [x.strip().upper() for x in text.split(",") if x.strip()]
    unknown = [x for x in requested if x not in allowed]
    if unknown:
        raise SystemExit(f"Unknown symbols: {', '.join(unknown)}")
    return requested


def _outcome(case: dict, horizon: int = PRIMARY_HORIZON) -> str:
    return str(((case.get("labels") or {}).get(str(horizon)) or {}).get("outcome") or "")


def _split_by_time(cases: list[dict]) -> tuple[list[dict], list[dict], list[dict], dict]:
    usable = [c for c in cases if str(PRIMARY_HORIZON) in (c.get("labels") or {})]
    times = sorted({int(c.get("time") or 0) for c in usable})
    if len(times) < 10:
        return usable, [], [], {"train_end_ms": None, "validation_end_ms": None}
    train_end = times[min(len(times) - 1, max(0, int(len(times) * 0.70) - 1))]
    validation_end = times[min(len(times) - 1, max(0, int(len(times) * 0.85) - 1))]
    train = [c for c in usable if int(c.get("time") or 0) <= train_end]
    validation = [c for c in usable if train_end < int(c.get("time") or 0) <= validation_end]
    holdout = [c for c in usable if int(c.get("time") or 0) > validation_end]
    return train, validation, holdout, {
        "train_end_ms": train_end,
        "validation_end_ms": validation_end,
    }


def _evaluate_cases(model: dict, cases: list[dict], horizon: int = PRIMARY_HORIZON) -> dict:
    if not cases:
        return {"samples": 0}
    brier = 0.0
    baseline_brier = 0.0
    multiclass_brier = 0.0
    by_state = defaultdict(lambda: {"n": 0, "brier": 0.0, "baseline_brier": 0.0})
    buckets = defaultdict(lambda: {"n": 0, "success": 0, "pred_sum": 0.0})
    used = 0
    for case in cases:
        state = str(case.get("state") or "")
        label = (case.get("labels") or {}).get(str(horizon)) or {}
        actual = str(label.get("outcome") or "")
        if actual not in OUTCOME_KEYS:
            continue
        pred = lookup_probability(model, state, horizon, case.get("features") or {})
        if not pred.get("available"):
            continue
        p = float(pred.get("success_probability", pred.get("probability", 0.0)) or 0.0)
        y = 1.0 if actual == OUTCOME_SUCCESS else 0.0
        state_base = float(((((model.get("states") or {}).get(state) or {}).get("horizons") or {}).get(str(horizon), {}).get("baseline", {}).get("probability", 0.0)) or 0.0)
        brier += (p - y) ** 2
        baseline_brier += (state_base - y) ** 2
        outcomes = pred.get("outcomes") or {}
        for key in OUTCOME_KEYS:
            pk = float((outcomes.get(key) or {}).get("probability", 0.0) or 0.0)
            yk = 1.0 if actual == key else 0.0
            multiclass_brier += (pk - yk) ** 2
        row = by_state[state]
        row["n"] += 1
        row["brier"] += (p - y) ** 2
        row["baseline_brier"] += (state_base - y) ** 2
        bucket_low = min(90, int(max(0.0, min(0.999999, p)) * 10) * 10)
        bucket = buckets[f"{bucket_low:02d}-{bucket_low+10:02d}"]
        bucket["n"] += 1
        bucket["success"] += int(y)
        bucket["pred_sum"] += p
        used += 1
    if used <= 0:
        return {"samples": 0}
    return {
        "samples": used,
        "success_brier": round(brier / used, 8),
        "state_baseline_brier": round(baseline_brier / used, 8),
        "brier_improvement": round((baseline_brier - brier) / used, 8),
        "multiclass_brier": round(multiclass_brier / used, 8),
        "by_state": {
            state: {
                "samples": row["n"],
                "success_brier": round(row["brier"] / row["n"], 8) if row["n"] else None,
                "state_baseline_brier": round(row["baseline_brier"] / row["n"], 8) if row["n"] else None,
                "brier_improvement": round((row["baseline_brier"] - row["brier"]) / row["n"], 8) if row["n"] else None,
            }
            for state, row in sorted(by_state.items())
        },
        "calibration": {
            key: {
                "samples": row["n"],
                "mean_predicted": round(row["pred_sum"] / row["n"], 6) if row["n"] else None,
                "actual_success_rate": round(row["success"] / row["n"], 6) if row["n"] else None,
            }
            for key, row in sorted(buckets.items()) if row["n"]
        },
    }


def _walk_forward_report(cases: list[dict], min_samples: int) -> dict:
    train, validation, holdout, cuts = _split_by_time(cases)
    if len(train) < 500:
        return {"available": False, "reason": "insufficient_train_cases", **cuts}
    diagnostic = build_model(train, DEFAULT_HORIZONS, min_samples=min_samples)
    return {
        "available": True,
        **cuts,
        "train_samples": len(train),
        "validation": _evaluate_cases(diagnostic, validation),
        "holdout": _evaluate_cases(diagnostic, holdout),
        "note": "Chronological 70/15/15 diagnostic only. Production Champion is rebuilt on all available training cases after this audit.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Post-close daily S-state replay + CCI PRIMARY path-tree + 4-way outcome JSON builder")
    parser.add_argument("--symbols", default="ALL", help="ALL / CRYPTO / US_STOCK or comma-separated symbols")
    parser.add_argument("--max-records", type=int, default=20000, help="Local 4H history capacity per symbol")
    parser.add_argument("--full-refresh", action="store_true", help="Refetch full configured history instead of latest-page merge")
    parser.add_argument("--step-bars", type=int, default=1, help="Replay every N completed daily checkpoints; production default 1")
    parser.add_argument("--min-samples", type=int, default=50, help="Minimum cases per learned path-tree branch")
    parser.add_argument("--cache-only", action="store_true", help="Use existing local 4H cache only; do not call Pionex API")
    parser.add_argument("--frozen-reinforcement", type=int, default=10, help="Base training weight for each settled Frozen Champion case")
    parser.add_argument("--ledger-cache", default=str(CHAMPION_LEDGER_PATH))
    parser.add_argument("--evolution-policy", default=str(EVOLUTION_POLICY_PATH))
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols)
    max_records = max(500, min(50_000, int(args.max_records)))
    min_samples = max(10, int(args.min_samples))
    all_cases: list[dict] = []
    symbol_reports: list[dict] = []

    print(f"ENGINE={ENGINE_API_VERSION} / {OPPORTUNITY_ENGINE_VERSION} / {PURPLE2_RULE_VERSION}")
    print(f"symbols={len(symbols)} max_records={max_records} post_close_step_days={args.step_bars}")

    for pos, symbol in enumerate(symbols, start=1):
        market_type = "US_STOCK" if is_rwa_symbol(symbol) else "CRYPTO"
        print(f"[{pos}/{len(symbols)}] {symbol} ({market_type}): update Pionex 4H cache ...", flush=True)
        try:
            cache_path = CACHE_DIR / f"{symbol}.csv"
            if args.cache_only:
                rows = load_csv(cache_path)[-max_records:]
            else:
                try:
                    rows = update_symbol_cache(
                        symbol, CACHE_DIR, max_records=max_records, full_refresh=args.full_refresh
                    )
                except Exception as fetch_exc:
                    # Full rebuild should not throw away a valid repository cache
                    # because one Pionex continuation request is temporarily unavailable.
                    cached = load_csv(cache_path)[-max_records:]
                    if not cached or args.full_refresh:
                        raise
                    print(
                        f"[{pos}/{len(symbols)}] {symbol}: Pionex update failed "
                        f"({type(fetch_exc).__name__}); replay existing cache={len(cached)}",
                        flush=True,
                    )
                    rows = cached
            print(f"[{pos}/{len(symbols)}] {symbol}: {len(rows)} bars; replay ...", flush=True)
            quiz_timeline: list[dict] = []
            cases = replay_symbol(
                symbol,
                rows,
                horizons=DEFAULT_HORIZONS,
                step_bars=max(1, args.step_bars),
                daily_timeline=quiz_timeline,
                market_type=market_type,
            )
            save_json(
                QUIZ_TIMELINE_DIR / f"{symbol}.json",
                {
                    "schema_version": 2,
                    "symbol": symbol,
                    "market_type": market_type,
                    "source": "same S-state replay; completed UTC daily close only (Taiwan 08:00); CCI PRIMARY path features",
                    "rows": quiz_timeline,
                },
            )
            all_cases.extend(cases)
            state_counts: dict[str, int] = {}
            for case in cases:
                state_counts[case["state"]] = state_counts.get(case["state"], 0) + 1
            symbol_reports.append({
                "symbol": symbol,
                "market_type": market_type,
                "bars": len(rows),
                "cases": len(cases),
                "states": state_counts,
                "ok": True,
            })
            print(f"[{pos}/{len(symbols)}] {symbol}: {len(cases)} settled cases {state_counts}")
        except Exception as exc:
            traceback.print_exc()
            symbol_reports.append({"symbol": symbol, "market_type": market_type, "ok": False, "error": f"{type(exc).__name__}: {exc}"})

    if not all_cases:
        print("No training cases were produced.", file=sys.stderr)
        return 2

    base_replay_cases = list(all_cases)
    generation_manifest = load_champion_json(CHAMPION_GENERATION_PATH, {})
    frozen_live_cases = current_generation_frozen_cases(load_ledger(Path(args.ledger_cache)), generation_manifest)
    reinforcement = max(1, min(50, int(args.frozen_reinforcement)))
    evolution_policy = load_champion_json(Path(args.evolution_policy), {})
    policy_active = bool(evolution_policy.get("active_for_next_training"))

    weighted_live_cases: list[dict] = []
    live_weight_audit = []
    for case in frozen_live_cases:
        weight = adaptive_reinforcement_weight(case, evolution_policy, reinforcement)
        weighted_live_cases.extend([case] * weight)
        live_weight_audit.append({
            "symbol": case.get("symbol"),
            "market_type": case.get("market_type"),
            "state": case.get("state"),
            "time": case.get("time"),
            "weight": weight,
            "actual_72h_outcome": (case.get("live_feedback") or {}).get("actual_72h_outcome"),
            "predicted_success_probability": (case.get("live_feedback") or {}).get("predicted_success_probability"),
        })

    audit_cases = base_replay_cases + frozen_live_cases
    training_cases = base_replay_cases + weighted_live_cases
    audit_cases.sort(key=lambda x: (int(x["time"]), str(x.get("market_type", "")), x["symbol"]))
    effective_live = len(weighted_live_cases)
    avg_live_weight = (effective_live / len(frozen_live_cases)) if frozen_live_cases else 0.0
    print(f"write {len(audit_cases)} unique/audit cases -> {CASES_PATH}")
    print(f"Frozen live feedback: unique={len(frozen_live_cases)} base_weight={reinforcement} policy_active={policy_active} effective={effective_live} avg_weight={avg_live_weight:.2f}")
    write_jsonl_gz(CASES_PATH, audit_cases)

    try:
        meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
    except Exception:
        meta = {}
    if meta.get("live_since_ms") is None and args.full_refresh:
        cutoff_ms = max(int(c["time"]) for c in audit_cases)
        cutoff_case = max(audit_cases, key=lambda c: int(c["time"]))
        meta = {
            "schema_version": 1,
            "live_since_ms": cutoff_ms,
            "live_since_tw": cutoff_case.get("time_tw"),
            "note": "Cases after this timestamp are live/out-of-sample continuation observations.",
        }
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    live_since_ms = meta.get("live_since_ms")
    historical_cases = [c for c in audit_cases if live_since_ms is None or int(c["time"]) <= int(live_since_ms)]
    live_cases = [c for c in audit_cases if live_since_ms is not None and int(c["time"]) > int(live_since_ms)]

    walk_forward = _walk_forward_report(base_replay_cases, min_samples)
    model = build_model(training_cases, DEFAULT_HORIZONS, min_samples=min_samples)
    model["training"] = {
        "case_count": len(training_cases),
        "audit_case_count": len(audit_cases),
        "base_replay_case_count": len(base_replay_cases),
        "frozen_live_unique_case_count": len(frozen_live_cases),
        "frozen_live_base_reinforcement_weight": reinforcement,
        "frozen_live_effective_case_count": effective_live,
        "frozen_live_average_reinforcement_weight": round(avg_live_weight, 4),
        "evolution_policy_id": evolution_policy.get("policy_id"),
        "evolution_policy_active": policy_active,
        "evolution_policy_group_rule_count": len(evolution_policy.get("group_rules") or []),
        "frozen_live_market_counts": {
            "CRYPTO": sum(1 for c in frozen_live_cases if str(c.get("market_type") or "CRYPTO") == "CRYPTO"),
            "US_STOCK": sum(1 for c in frozen_live_cases if str(c.get("market_type") or "CRYPTO") == "US_STOCK"),
        },
        "symbols_requested": symbols,
        "symbol_count": len(symbols),
        "crypto_symbol_count": sum(1 for x in symbols if not is_rwa_symbol(x)),
        "us_stock_symbol_count": sum(1 for x in symbols if is_rwa_symbol(x)),
        "max_records_per_symbol": max_records,
        "step_bars": max(1, args.step_bars),
        "engine_api_version": ENGINE_API_VERSION,
        "opportunity_engine_version": OPPORTUNITY_ENGINE_VERSION,
        "purple2_rule_version": PURPLE2_RULE_VERSION,
        "live_since_ms": live_since_ms,
        "historical_case_count": len(historical_cases),
        "live_case_count": len(live_cases),
    }
    save_json(MODEL_PATH, model)

    primary_horizon = str(PRIMARY_HORIZON)
    successful_symbol_count = sum(1 for row in symbol_reports if row.get("ok"))
    successful_us_stock_symbol_count = sum(1 for row in symbol_reports if row.get("ok") and row.get("market_type") == "US_STOCK")
    successful_crypto_symbol_count = sum(1 for row in symbol_reports if row.get("ok") and row.get("market_type") == "CRYPTO")
    us_stock_case_count = sum(int(row.get("cases", 0) or 0) for row in symbol_reports if row.get("ok") and row.get("market_type") == "US_STOCK")
    crypto_case_count = sum(int(row.get("cases", 0) or 0) for row in symbol_reports if row.get("ok") and row.get("market_type") == "CRYPTO")
    failed_symbol_count = len(symbol_reports) - successful_symbol_count
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model.get("model_id"),
        "schema_version": model.get("schema_version"),
        "total_cases": len(training_cases),
        "audit_case_count": len(audit_cases),
        "base_replay_case_count": len(base_replay_cases),
        "symbol_count": len(symbols),
        "crypto_symbol_count": sum(1 for x in symbols if not is_rwa_symbol(x)),
        "us_stock_symbol_count": sum(1 for x in symbols if is_rwa_symbol(x)),
        "successful_symbol_count": successful_symbol_count,
        "successful_crypto_symbol_count": successful_crypto_symbol_count,
        "successful_us_stock_symbol_count": successful_us_stock_symbol_count,
        "failed_symbol_count": failed_symbol_count,
        "crypto_case_count": crypto_case_count,
        "us_stock_case_count": us_stock_case_count,
        "frozen_live_unique_case_count": len(frozen_live_cases),
        "frozen_live_effective_case_count": effective_live,
        "historical_case_count": len(historical_cases),
        "live_case_count": len(live_cases),
        "live_since_ms": live_since_ms,
        "live_since_tw": meta.get("live_since_tw"),
        "engine_api_version": ENGINE_API_VERSION,
        "symbols": symbol_reports,
        "state_horizon_baselines": {
            state: {h: node["baseline"] for h, node in state_node.get("horizons", {}).items()}
            for state, state_node in model.get("states", {}).items()
        },
        "primary_72h_outcomes": {
            state: (state_node.get("horizons", {}).get(primary_horizon, {}).get("baseline", {}).get("outcomes") or {})
            for state, state_node in model.get("states", {}).items()
        },
        "primary_72h_structural_survival": {
            state: state_node.get("horizons", {}).get(primary_horizon, {}).get("baseline", {}).get("structural_survival_probability")
            for state, state_node in model.get("states", {}).items()
        },
        "outcome_note": "72H main view: success + alive_slow + true_fail + other = 100%. CCI PRIMARY path leaf directly supplies these probabilities.",
        "cci_primary_contract": model.get("cci_primary_contract") or {},
        "cci_primary_72h": summarize_path_tree(model, primary_horizon, top_n=12),
        "walk_forward": walk_forward,
        "evolution_policy": {
            "policy_id": evolution_policy.get("policy_id"),
            "active": policy_active,
            "group_rule_count": len(evolution_policy.get("group_rules") or []),
            "effective_live_case_count": effective_live,
            "average_live_case_weight": round(avg_live_weight, 4),
            "highest_weight_cases": sorted(live_weight_audit, key=lambda x: int(x.get("weight", 0)), reverse=True)[:50],
        },
    }
    save_json(REPORT_PATH, report)
    print(f"MODEL={MODEL_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print(f"model_id={model.get('model_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

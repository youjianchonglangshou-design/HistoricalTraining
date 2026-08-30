from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path

from engine.scoring_rules import ENGINE_API_VERSION, OPPORTUNITY_ENGINE_VERSION, PURPLE2_RULE_VERSION
from engine.symbols_config import EXAM_SYMBOLS
from training.io_utils import write_jsonl_gz
from training.model_builder import build_model, save_json
from training.pionex_history import update_symbol_cache
from training.replay import DEFAULT_HORIZONS, replay_symbol

ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / "data" / "cache" / "4h"
CASES_PATH = ROOT / "data" / "cases" / "history_cases.jsonl.gz"
MODEL_PATH = ROOT / "models" / "probability_model.json"
REPORT_PATH = ROOT / "reports" / "training_report.json"
META_PATH = ROOT / "data" / "learning_meta.json"
QUIZ_TIMELINE_DIR = ROOT / "quiz" / "model_timeline"




def build_dmi_expert_report(model: dict, horizon: str = "18", top_n: int = 6) -> dict:
    """Compact audit view of what the DMI expert learned at the primary horizon."""
    output = {}
    for state, state_node in (model.get("states") or {}).items():
        hnode = (state_node.get("horizons") or {}).get(str(horizon)) or {}
        baseline = hnode.get("baseline") or {}
        baseline_success = float(baseline.get("probability", 0.0) or 0.0)
        baseline_fail = float(baseline.get("true_fail_probability", 0.0) or 0.0)
        facets_out = []
        for facet in ((hnode.get("dmi_expert") or {}).get("facets") or []):
            rows = []
            for rule in facet.get("rules") or []:
                if not rule.get("eligible"):
                    continue
                success = float(rule.get("probability", 0.0) or 0.0)
                fail = float(rule.get("true_fail_probability", 0.0) or 0.0)
                survival = float(rule.get("structural_survival_probability", success) or success)
                score = (success - baseline_success) - (fail - baseline_fail)
                rows.append({
                    "signature": rule.get("signature"),
                    "samples": int(rule.get("samples", 0)),
                    "success_probability": round(success, 6),
                    "structural_survival_probability": round(survival, 6),
                    "true_fail_probability": round(fail, 6),
                    "success_delta_vs_state": round(success - baseline_success, 6),
                    "true_fail_delta_vs_state": round(fail - baseline_fail, 6),
                    "direction_score": round(score, 6),
                })
            strongest = sorted(rows, key=lambda x: (-x["direction_score"], -x["samples"]))[:top_n]
            weakest = sorted(rows, key=lambda x: (x["direction_score"], -x["samples"]))[:top_n]
            facets_out.append({
                "name": facet.get("name"),
                "fields": facet.get("fields") or [],
                "eligible_rule_count": len(rows),
                "strongest_positive": strongest,
                "strongest_negative": weakest,
            })
        output[state] = {
            "baseline_samples": int(baseline.get("samples", 0)),
            "baseline_success_probability": round(baseline_success, 6),
            "baseline_structural_survival_probability": round(float(baseline.get("structural_survival_probability", baseline_success) or baseline_success), 6),
            "baseline_true_fail_probability": round(baseline_fail, 6),
            "dmi_binning": state_node.get("dmi_binning") or {},
            "facets": facets_out,
        }
    return output

ADX_STEP_FACET_NAMES = {"adx_step_regime", "adx_step_persistence", "adx_turn_handover"}


def build_adx_step_report(model: dict, horizon: str = "18", top_n: int = 6) -> dict:
    """Focused audit for S-state x DI-controller x red/green ADX stepline evidence."""
    full = build_dmi_expert_report(model, horizon=horizon, top_n=top_n)
    output = {}
    for state, node in full.items():
        output[state] = {
            key: value
            for key, value in node.items()
            if key != "facets"
        }
        output[state]["facets"] = [
            facet for facet in (node.get("facets") or [])
            if facet.get("name") in ADX_STEP_FACET_NAMES
        ]
    return output


def parse_symbols(text: str) -> list[str]:
    if not text or text.upper() == "ALL":
        return list(EXAM_SYMBOLS)
    requested = [x.strip().upper() for x in text.split(",") if x.strip()]
    unknown = [x for x in requested if x not in EXAM_SYMBOLS]
    if unknown:
        raise SystemExit(f"Unknown symbols: {', '.join(unknown)}")
    return requested


def main() -> int:
    parser = argparse.ArgumentParser(description="Historical S-state replay + 4-way outcome probability JSON builder")
    parser.add_argument("--symbols", default="ALL", help="ALL or comma-separated symbols, e.g. BTC,ETH,LINK")
    parser.add_argument("--max-records", type=int, default=5000, help="Local 4H history capacity per symbol; first backfill is capped by Pionex at 10000")
    parser.add_argument("--full-refresh", action="store_true", help="Refetch full configured history instead of latest-page merge")
    parser.add_argument("--step-bars", type=int, default=1, help="Replay every N 4H bars; production default 1")
    parser.add_argument("--min-samples", type=int, default=50, help="Minimum cases for a conditional probability rule")
    args = parser.parse_args()

    symbols = parse_symbols(args.symbols)
    max_records = max(500, min(50_000, int(args.max_records)))
    all_cases = []
    symbol_reports = []

    print(f"ENGINE={ENGINE_API_VERSION} / {OPPORTUNITY_ENGINE_VERSION} / {PURPLE2_RULE_VERSION}")
    print(f"symbols={len(symbols)} max_records={max_records} step_bars={args.step_bars}")

    for pos, symbol in enumerate(symbols, start=1):
        print(f"[{pos}/{len(symbols)}] {symbol}: update Pionex 4H cache ...", flush=True)
        try:
            rows = update_symbol_cache(symbol, CACHE_DIR, max_records=max_records, full_refresh=args.full_refresh)
            print(f"[{pos}/{len(symbols)}] {symbol}: {len(rows)} bars; replay ...", flush=True)
            quiz_timeline: list[dict] = []
            cases = replay_symbol(
                symbol,
                rows,
                horizons=DEFAULT_HORIZONS,
                step_bars=max(1, args.step_bars),
                daily_timeline=quiz_timeline,
            )
            save_json(
                QUIZ_TIMELINE_DIR / f"{symbol}.json",
                {
                    "schema_version": 1,
                    "symbol": symbol,
                    "source": "same S-state replay; last 4H snapshot of each UTC day",
                    "rows": quiz_timeline,
                },
            )
            all_cases.extend(cases)
            state_counts = {}
            for case in cases:
                state_counts[case["state"]] = state_counts.get(case["state"], 0) + 1
            symbol_reports.append({"symbol": symbol, "bars": len(rows), "cases": len(cases), "states": state_counts, "ok": True})
            print(f"[{pos}/{len(symbols)}] {symbol}: {len(cases)} settled cases {state_counts}")
        except Exception as exc:
            traceback.print_exc()
            symbol_reports.append({"symbol": symbol, "ok": False, "error": f"{type(exc).__name__}: {exc}"})

    if not all_cases:
        print("No training cases were produced.", file=sys.stderr)
        return 2

    all_cases.sort(key=lambda x: (int(x["time"]), x["symbol"]))
    print(f"write {len(all_cases)} cases -> {CASES_PATH}")
    write_jsonl_gz(CASES_PATH, all_cases)

    # Freeze the first historical/live boundary once. It is not reset by later retraining.
    try:
        meta = json.loads(META_PATH.read_text(encoding="utf-8")) if META_PATH.exists() else {}
    except Exception:
        meta = {}
    if meta.get("live_since_ms") is None and args.full_refresh:
        cutoff_ms = max(int(c["time"]) for c in all_cases)
        cutoff_case = max(all_cases, key=lambda c: int(c["time"]))
        meta = {
            "schema_version": 1,
            "live_since_ms": cutoff_ms,
            "live_since_tw": cutoff_case.get("time_tw"),
            "note": "Cases after this timestamp are live/out-of-sample continuation observations.",
        }
        META_PATH.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    live_since_ms = meta.get("live_since_ms")
    historical_cases = [c for c in all_cases if live_since_ms is None or int(c["time"]) <= int(live_since_ms)]
    live_cases = [c for c in all_cases if live_since_ms is not None and int(c["time"]) > int(live_since_ms)]

    model = build_model(all_cases, DEFAULT_HORIZONS, min_samples=max(10, args.min_samples))
    model["training"] = {
        "case_count": len(all_cases),
        "symbols_requested": symbols,
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

    primary_horizon = "18"
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_id": model.get("model_id"),
        "schema_version": model.get("schema_version"),
        "total_cases": len(all_cases),
        "historical_case_count": len(historical_cases),
        "live_case_count": len(live_cases),
        "live_since_ms": live_since_ms,
        "live_since_tw": meta.get("live_since_tw"),
        "engine_api_version": ENGINE_API_VERSION,
        "symbols": symbol_reports,
        "state_horizon_baselines": {
            state: {
                h: node["baseline"]
                for h, node in state_node.get("horizons", {}).items()
            }
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
        "outcome_note": "72H main view: success + alive_slow + true_fail + other = 100%. Existing probability remains success-within-horizon for UI compatibility.",
        "dmi_expert_contract": model.get("dmi_expert_contract") or {},
        "dmi_expert_72h": build_dmi_expert_report(model, primary_horizon),
        "adx_step_regime_72h": build_adx_step_report(model, primary_horizon),
    }
    save_json(REPORT_PATH, report)
    print(f"MODEL={MODEL_PATH}")
    print(f"REPORT={REPORT_PATH}")
    print(f"model_id={model.get('model_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

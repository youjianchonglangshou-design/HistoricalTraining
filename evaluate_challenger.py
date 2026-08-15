from __future__ import annotations

import argparse
import gzip
import json
import math
import random
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from training.model_builder import lookup_probability
from training.outcomes import OUTCOME_KEYS, OUTCOME_SUCCESS, OUTCOME_FAIL

PRIMARY_HORIZON_BARS = 18
PRIMARY_HORIZON_HOURS = 72


def _parse_iso_ms(value: str | None) -> int:
    if not value:
        return 0
    text = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def _load_json(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _load_cases(path: str | Path) -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    return cases


def _one_per_symbol_utc_day(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Reduce serial correlation: keep one settled decision per symbol per UTC day."""
    chosen: dict[tuple[str, str], dict[str, Any]] = {}
    for case in sorted(cases, key=lambda c: (int(c.get("time", 0)), str(c.get("symbol", "")))):
        ts = int(case.get("time", 0)) / 1000.0
        day = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
        key = (str(case.get("symbol", "")), day)
        chosen.setdefault(key, case)
    return sorted(chosen.values(), key=lambda c: (int(c.get("time", 0)), str(c.get("symbol", ""))))


def _prediction_vector(model: dict[str, Any], case: dict[str, Any]) -> dict[str, float] | None:
    state = str(case.get("state") or "")
    result = lookup_probability(model, state, PRIMARY_HORIZON_BARS, case.get("features") or {})
    if not result.get("available"):
        return None
    outcomes = result.get("outcomes") or {}
    probs: dict[str, float] = {}
    for key in OUTCOME_KEYS:
        node = outcomes.get(key) or {}
        probs[key] = max(1e-12, float(node.get("probability", 0.0) or 0.0))
    total = sum(probs.values())
    if total <= 0:
        return None
    return {k: v / total for k, v in probs.items()}


def _actual_outcome(case: dict[str, Any]) -> str | None:
    label = (case.get("labels") or {}).get(str(PRIMARY_HORIZON_BARS)) or {}
    outcome = str(label.get("outcome") or "")
    return outcome if outcome in OUTCOME_KEYS else None


def _brier(probs: dict[str, float], actual: str) -> float:
    return sum((probs[k] - (1.0 if k == actual else 0.0)) ** 2 for k in OUTCOME_KEYS)


def _binary_brier(prob: float, actual: bool) -> float:
    return (prob - (1.0 if actual else 0.0)) ** 2


def _ece(rows: list[tuple[float, int]], bins: int = 10) -> float:
    if not rows:
        return 1.0
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in rows:
        idx = min(bins - 1, max(0, int(p * bins)))
        buckets[idx].append((p, y))
    n = len(rows)
    total = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        avg_p = sum(p for p, _ in bucket) / len(bucket)
        avg_y = sum(y for _, y in bucket) / len(bucket)
        total += len(bucket) / n * abs(avg_p - avg_y)
    return total


def score_model(model: dict[str, Any], cases: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    scored: list[dict[str, Any]] = []
    by_state: dict[str, list[float]] = defaultdict(list)
    success_cal: list[tuple[float, int]] = []
    fail_cal: list[tuple[float, int]] = []
    briers: list[float] = []
    loglosses: list[float] = []
    success_briers: list[float] = []
    fail_briers: list[float] = []

    for case in cases:
        actual = _actual_outcome(case)
        if not actual:
            continue
        probs = _prediction_vector(model, case)
        if not probs:
            continue
        b = _brier(probs, actual)
        ll = -math.log(max(1e-12, probs[actual]))
        sb = _binary_brier(probs[OUTCOME_SUCCESS], actual == OUTCOME_SUCCESS)
        fb = _binary_brier(probs[OUTCOME_FAIL], actual == OUTCOME_FAIL)
        state = str(case.get("state") or "")
        briers.append(b)
        loglosses.append(ll)
        success_briers.append(sb)
        fail_briers.append(fb)
        by_state[state].append(b)
        success_cal.append((probs[OUTCOME_SUCCESS], int(actual == OUTCOME_SUCCESS)))
        fail_cal.append((probs[OUTCOME_FAIL], int(actual == OUTCOME_FAIL)))
        scored.append({
            "symbol": str(case.get("symbol") or ""),
            "time": int(case.get("time", 0)),
            "state": state,
            "actual": actual,
            "brier": b,
            "logloss": ll,
            "success_brier": sb,
            "fail_brier": fb,
        })

    def avg(values: list[float]) -> float | None:
        return (sum(values) / len(values)) if values else None

    metrics = {
        "model_id": model.get("model_id"),
        "cases": len(scored),
        "symbols": len({r["symbol"] for r in scored}),
        "multiclass_brier": avg(briers),
        "log_loss": avg(loglosses),
        "success_brier": avg(success_briers),
        "true_fail_brier": avg(fail_briers),
        "success_ece": _ece(success_cal),
        "true_fail_ece": _ece(fail_cal),
        "state_brier": {
            state: {"cases": len(vals), "brier": avg(vals)}
            for state, vals in sorted(by_state.items())
        },
    }
    return metrics, scored


def _cluster_bootstrap_probability(active_rows: list[dict[str, Any]], challenger_rows: list[dict[str, Any]], iterations: int = 1000) -> float | None:
    amap = {(r["symbol"], r["time"]): r for r in active_rows}
    cmap = {(r["symbol"], r["time"]): r for r in challenger_rows}
    keys = sorted(set(amap) & set(cmap))
    by_symbol: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for key in keys:
        a, c = amap[key], cmap[key]
        by_symbol[key[0]].append((a["brier"], c["brier"]))
    symbols = sorted(by_symbol)
    if len(symbols) < 2:
        # No meaningful OOS evidence yet.  Do not invent a neutral 50% confidence.
        return None
    rng = random.Random(260812)
    score = 0.0
    for _ in range(iterations):
        picked = [rng.choice(symbols) for _ in symbols]
        a_vals: list[float] = []
        c_vals: list[float] = []
        for symbol in picked:
            for a, c in by_symbol[symbol]:
                a_vals.append(a)
                c_vals.append(c)
        if a_vals:
            c_mean = sum(c_vals) / len(c_vals)
            a_mean = sum(a_vals) / len(a_vals)
            if c_mean < a_mean - 1e-15:
                score += 1.0
            elif abs(c_mean - a_mean) <= 1e-15:
                score += 0.5
    return score / iterations


def promotion_decision(
    active: dict[str, Any],
    challenger: dict[str, Any],
    *,
    candidate_age_hours: float,
    p_brier_better: float | None,
    min_cases: int = 180,
    min_symbols: int = 50,
    min_age_hours: float = 72.0,
    max_age_hours: float = 168.0,
) -> tuple[str, list[str], dict[str, Any]]:
    reasons: list[str] = []
    n = int(challenger.get("cases") or 0)
    symbols = int(challenger.get("symbols") or 0)
    if candidate_age_hours < min_age_hours:
        reasons.append(f"candidate_age_hours {candidate_age_hours:.1f} < {min_age_hours:.0f}")
    if n < min_cases:
        reasons.append(f"settled_cases {n} < {min_cases}")
    if symbols < min_symbols:
        reasons.append(f"symbols {symbols} < {min_symbols}")
    if reasons:
        # Timeout must win over WAITING_EVIDENCE. Otherwise a Challenger that never
        # accumulates 180 cases / 50 symbols can remain WAITING forever.
        if candidate_age_hours >= max_age_hours:
            reasons.append("challenger reached max shadow age without sufficient OOS evidence")
            return "REJECT", reasons, {
                "timeout": True,
                "evidence": {"cases": n, "symbols": symbols},
            }
        return "WAITING_EVIDENCE", reasons, {}

    # At this point evidence is sufficient, so bootstrap confidence must be real.
    # Defensive fallback only; with >= min_symbols paired symbols this should not be None.
    p_brier_better_value = float(p_brier_better) if p_brier_better is not None else 0.0

    ab = float(active["multiclass_brier"])
    cb = float(challenger["multiclass_brier"])
    allog = float(active["log_loss"])
    clog = float(challenger["log_loss"])
    afb = float(active["true_fail_brier"])
    cfb = float(challenger["true_fail_brier"])
    as_ece = float(active["success_ece"])
    cs_ece = float(challenger["success_ece"])

    brier_delta = ab - cb
    logloss_delta = allog - clog
    fail_brier_delta = afb - cfb
    success_ece_delta = as_ece - cs_ece

    state_guardrail_ok = True
    state_details: dict[str, Any] = {}
    for state, cnode in (challenger.get("state_brier") or {}).items():
        anode = (active.get("state_brier") or {}).get(state) or {}
        count = int(cnode.get("cases") or 0)
        if count < 25 or anode.get("brier") is None or cnode.get("brier") is None:
            continue
        delta = float(anode["brier"]) - float(cnode["brier"])
        state_details[state] = {"cases": count, "active_minus_challenger_brier": delta}
        if delta < -0.02:
            state_guardrail_ok = False

    gates = {
        "brier_improvement": brier_delta >= 0.002,
        "logloss_not_worse": logloss_delta >= 0.0,
        "bootstrap_confidence": p_brier_better_value >= 0.70,
        "true_fail_not_worse": fail_brier_delta >= -0.01,
        "success_calibration_not_worse": success_ece_delta >= -0.02,
        "state_guardrail": state_guardrail_ok,
    }

    if all(gates.values()):
        return "PROMOTE", ["all promotion gates passed"], {
            "gates": gates,
            "deltas": {
                "multiclass_brier": brier_delta,
                "log_loss": logloss_delta,
                "true_fail_brier": fail_brier_delta,
                "success_ece": success_ece_delta,
            },
            "state_details": state_details,
        }

    clearly_worse = brier_delta <= -0.003 and p_brier_better_value <= 0.30
    too_old = candidate_age_hours >= max_age_hours
    if clearly_worse or too_old:
        if clearly_worse:
            reasons.append("challenger is clearly worse on OOS Brier")
        if too_old:
            reasons.append("challenger reached max shadow age without promotion")
        return "REJECT", reasons, {"gates": gates, "state_details": state_details}

    reasons.append("evidence is sufficient but promotion gates are not decisive yet")
    return "HOLD", reasons, {"gates": gates, "state_details": state_details}


def main() -> int:
    ap = argparse.ArgumentParser(description="Evaluate active Champion vs current Challenger on future settled OOS cases")
    ap.add_argument("--cases", required=True)
    ap.add_argument("--active", required=True)
    ap.add_argument("--challenger", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-cases", type=int, default=180)
    ap.add_argument("--min-symbols", type=int, default=50)
    args = ap.parse_args()

    cases = _load_cases(args.cases)
    active_model = _load_json(args.active)
    challenger_model = _load_json(args.challenger)
    manifest = _load_json(args.manifest)

    generated_at = manifest.get("generated_at") or challenger_model.get("generated_at")
    generated_ms = _parse_iso_ms(generated_at)
    now = datetime.now(timezone.utc)
    age_hours = max(0.0, (now.timestamp() * 1000 - generated_ms) / 3_600_000) if generated_ms else 0.0

    future_cases = [c for c in cases if int(c.get("time", 0)) > generated_ms]
    eval_cases = _one_per_symbol_utc_day(future_cases)

    active_metrics, active_rows = score_model(active_model, eval_cases)
    challenger_metrics, challenger_rows = score_model(challenger_model, eval_cases)

    # Keep only exact paired rows if one model could not predict a case.
    pair_keys = {(r["symbol"], r["time"]) for r in active_rows} & {(r["symbol"], r["time"]) for r in challenger_rows}
    if len(pair_keys) != len(active_rows) or len(pair_keys) != len(challenger_rows):
        paired_cases = [c for c in eval_cases if (str(c.get("symbol") or ""), int(c.get("time", 0))) in pair_keys]
        active_metrics, active_rows = score_model(active_model, paired_cases)
        challenger_metrics, challenger_rows = score_model(challenger_model, paired_cases)

    p_better = _cluster_bootstrap_probability(active_rows, challenger_rows)
    decision, reasons, detail = promotion_decision(
        active_metrics,
        challenger_metrics,
        candidate_age_hours=age_hours,
        p_brier_better=p_better,
        min_cases=args.min_cases,
        min_symbols=args.min_symbols,
    )

    payload = {
        "schema_version": 1,
        "evaluated_at": now.isoformat(),
        "contract": "Champion and Challenger are compared only on settled cases whose decision time is after Challenger generated_at. One case per symbol per UTC day is kept to reduce serial correlation.",
        "primary_horizon_hours": PRIMARY_HORIZON_HOURS,
        "active_model_id": active_model.get("model_id"),
        "challenger_model_id": challenger_model.get("model_id"),
        "challenger_generated_at": generated_at,
        "challenger_age_hours": round(age_hours, 3),
        "eligible_future_cases_before_thinning": len(future_cases),
        "paired_oos_cases": int(challenger_metrics.get("cases") or 0),
        "paired_oos_symbols": int(challenger_metrics.get("symbols") or 0),
        "active": active_metrics,
        "challenger": challenger_metrics,
        "bootstrap_probability_challenger_brier_better": round(p_better, 6) if p_better is not None else None,
        "decision": decision,
        "reasons": reasons,
        "decision_detail": detail,
        "promotion_policy": {
            "min_candidate_age_hours": 72,
            "min_paired_oos_cases": args.min_cases,
            "min_paired_symbols": args.min_symbols,
            "brier_improvement_required": 0.002,
            "bootstrap_probability_required": 0.70,
            "log_loss_must_not_worsen": True,
            "true_fail_brier_max_worsening": 0.01,
            "success_ece_max_worsening": 0.02,
            "state_brier_max_worsening": 0.02,
            "max_shadow_age_hours_before_reject": 168,
        },
    }

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "decision": decision,
        "active_model_id": payload["active_model_id"],
        "challenger_model_id": payload["challenger_model_id"],
        "age_hours": payload["challenger_age_hours"],
        "cases": payload["paired_oos_cases"],
        "symbols": payload["paired_oos_symbols"],
        "p_better": payload["bootstrap_probability_challenger_brier_better"],
        "reasons": reasons,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

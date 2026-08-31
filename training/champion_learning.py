from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

OUTCOME_SUCCESS = "SUCCESS_WITHIN_HORIZON"
OUTCOME_ALIVE = "ALIVE_SLOW"
OUTCOME_FAIL = "TRUE_FAIL"
OUTCOME_OTHER = "OTHER"
OUTCOME_KEYS = (OUTCOME_SUCCESS, OUTCOME_ALIVE, OUTCOME_FAIL, OUTCOME_OTHER)
TW_TZ = timezone(timedelta(hours=8))
HORIZON_BARS_TO_HOURS = {3: 12, 6: 24, 12: 48, 18: 72}


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_ledger(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def save_ledger(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = sorted(rows, key=lambda r: (int(r.get("decision_time", 0)), str(r.get("symbol", ""))))
    text = "\n".join(json.dumps(r, ensure_ascii=False, separators=(",", ":")) for r in ordered)
    path.write_text((text + "\n") if text else "", encoding="utf-8")


def _iso_tw_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone(TW_TZ).isoformat()


def _date_tw_from_ms(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).astimezone(TW_TZ).date().isoformat()


def ensure_generation(
    manifest: dict[str, Any],
    history: list[dict[str, Any]],
    active_model_id: str,
    now_iso: str,
) -> tuple[dict[str, Any], list[dict[str, Any]], bool]:
    active_model_id = str(active_model_id or "").strip()
    if not active_model_id:
        raise ValueError("active_model_id is required")
    changed = False
    current_id = str(manifest.get("champion_model_id") or "").strip()
    if not current_id:
        manifest = {
            "schema_version": 1,
            "generation": 1,
            "champion_model_id": active_model_id,
            "started_at": now_iso,
            "evolution_min_settled_72h": int(manifest.get("evolution_min_settled_72h") or 120),
            "frozen_live_reinforcement_weight": int(manifest.get("frozen_live_reinforcement_weight") or 10),
        }
        changed = True
    elif current_id != active_model_id:
        closed = dict(manifest)
        closed["ended_at"] = now_iso
        closed["end_reason"] = "active_champion_changed"
        history = list(history) + [closed]
        manifest = {
            "schema_version": 1,
            "generation": int(manifest.get("generation") or 1) + 1,
            "champion_model_id": active_model_id,
            "started_at": now_iso,
            "evolution_min_settled_72h": int(manifest.get("evolution_min_settled_72h") or 120),
            "frozen_live_reinforcement_weight": int(manifest.get("frozen_live_reinforcement_weight") or 10),
        }
        changed = True
    elif not manifest.get("started_at"):
        manifest = dict(manifest)
        manifest["started_at"] = now_iso
        changed = True
    return manifest, history, changed


def _outcome_probability(prediction: dict[str, Any], key: str) -> float:
    node = (prediction.get("outcomes") or {}).get(key) or {}
    try:
        return float(node.get("probability", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def make_frozen_record(
    *,
    symbol: str,
    model: dict[str, Any],
    timeline_row: dict[str, Any],
    prediction: dict[str, Any],
    target: str,
    frozen_at_iso: str,
    generation: int,
    market_type: str = "CRYPTO",
) -> dict[str, Any]:
    cutoff = int(timeline_row["cutoff_time"])
    market_type = str(market_type or "CRYPTO").upper()
    success = float(prediction.get("probability", 0.0) or 0.0)
    survival = float(prediction.get("structural_survival_probability", success) or success)
    fail = float(prediction.get("true_fail_probability", 0.0) or 0.0)
    other = float(prediction.get("other_probability", 0.0) or 0.0)
    alive = _outcome_probability(prediction, OUTCOME_ALIVE)
    if alive <= 0.0:
        alive = max(0.0, survival - success)
    return {
        "schema_version": 1,
        "snapshot_id": f"{model.get('model_id')}:{market_type}:{symbol}:{cutoff}",
        "generation": int(generation),
        "market_type": market_type,
        "champion_model_id": str(model.get("model_id") or ""),
        "frozen_at": frozen_at_iso,
        "symbol": symbol,
        "decision_time": cutoff,
        "decision_time_tw": _iso_tw_from_ms(cutoff),
        "decision_date_tw": _date_tw_from_ms(cutoff),
        "state": str(timeline_row.get("state") or ""),
        "target": target,
        "entry_price": float(timeline_row.get("price", 0.0) or 0.0),
        "bandpos": float(timeline_row.get("bandpos", 0.0) or 0.0),
        "prediction": {
            "success_probability": round(success, 8),
            "alive_slow_probability": round(alive, 8),
            "structural_survival_probability": round(survival, 8),
            "true_fail_probability": round(fail, 8),
            "other_probability": round(other, 8),
            "samples": int(prediction.get("samples", 0) or 0),
            "level": int(prediction.get("level", 0) or 0),
            "signature": prediction.get("signature"),
            "dmi_expert": prediction.get("dmi_expert") or {},
        },
        "features": dict(timeline_row.get("features") or {}),
        "settlements": {
            "12H": {"status": "PENDING"},
            "24H": {"status": "PENDING"},
            "48H": {"status": "PENDING"},
            "72H": {"status": "PENDING"},
        },
        "final_outcome": None,
    }


def apply_case_settlement(record: dict[str, Any], case: dict[str, Any]) -> bool:
    labels = case.get("labels") or {}
    changed = False
    settlements = record.setdefault("settlements", {})
    for bars, hours in HORIZON_BARS_TO_HOURS.items():
        label = labels.get(str(bars))
        if not isinstance(label, dict):
            continue
        key = f"{hours}H"
        previous = settlements.get(key) or {}
        if previous.get("status") == "SETTLED":
            continue
        payload = {
            "status": "SETTLED",
            "outcome": label.get("outcome"),
            "hit": bool(label.get("hit")),
            "bars_to_hit": label.get("bars_to_hit"),
            "max_return": label.get("max_return"),
            "max_drawdown": label.get("max_drawdown"),
            "max_bandpos": label.get("max_bandpos"),
            "hard_invalidated": bool(label.get("hard_invalidated", False)),
            "end_state": label.get("end_state"),
            "end_bandpos": label.get("end_bandpos"),
            "state_path": label.get("state_path") or [],
            "reason": label.get("reason"),
        }
        settlements[key] = payload
        changed = True
        if hours == 72:
            record["final_outcome"] = label.get("outcome")
            record["final_settled"] = True
            record["final_path"] = label.get("state_path") or []
    return changed


def _blank_counts() -> Counter[str]:
    return Counter({k: 0 for k in OUTCOME_KEYS})


def _summary_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = [r for r in rows if ((r.get("settlements") or {}).get("72H") or {}).get("status") == "SETTLED"]
    counts = _blank_counts()
    for row in settled:
        outcome = ((row.get("settlements") or {}).get("72H") or {}).get("outcome")
        if outcome in OUTCOME_KEYS:
            counts[outcome] += 1
    n = len(settled)
    success = counts[OUTCOME_SUCCESS]
    alive = counts[OUTCOME_ALIVE]
    fail = counts[OUTCOME_FAIL]
    other = counts[OUTCOME_OTHER]
    return {
        "snapshots": len(rows),
        "settled_72h": n,
        "pending_72h": len(rows) - n,
        "success": success,
        "alive_slow": alive,
        "true_fail": fail,
        "other": other,
        "success_rate": round(success / n, 6) if n else None,
        "alive_slow_rate": round(alive / n, 6) if n else None,
        "structural_survival_rate": round((success + alive) / n, 6) if n else None,
        "true_fail_rate": round(fail / n, 6) if n else None,
        "other_rate": round(other / n, 6) if n else None,
    }


def build_performance(
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
    generation_history: list[dict[str, Any]],
    *,
    now_ms: int,
) -> dict[str, Any]:
    model_id = str(manifest.get("champion_model_id") or "")
    generation = int(manifest.get("generation") or 1)
    current = [r for r in rows if str(r.get("champion_model_id") or "") == model_id and int(r.get("generation") or 0) == generation]

    windows: dict[str, Any] = {}
    for days in (7, 14, 30, 90):
        cutoff = now_ms - days * 24 * 60 * 60 * 1000
        windows[str(days)] = _summary_from_rows([r for r in current if int(r.get("decision_time", 0)) >= cutoff])
    windows["all"] = _summary_from_rows(current)

    by_state: dict[str, Any] = {}
    for state in ("S0.5", "S1", "S2", "S3"):
        by_state[state] = _summary_from_rows([r for r in current if r.get("state") == state])

    by_market: dict[str, Any] = {}
    for market_type in ("CRYPTO", "US_STOCK"):
        market_rows = [r for r in current if str(r.get("market_type") or "CRYPTO") == market_type]
        by_market[market_type] = {
            "all": _summary_from_rows(market_rows),
            "by_state": {state: _summary_from_rows([r for r in market_rows if r.get("state") == state]) for state in ("S0.5", "S1", "S2", "S3")},
        }

    thresholds: dict[str, Any] = {}
    settled = [r for r in current if ((r.get("settlements") or {}).get("72H") or {}).get("status") == "SETTLED"]
    for threshold in (0.60, 0.65, 0.70):
        eligible = [r for r in settled if float((r.get("prediction") or {}).get("success_probability", 0.0) or 0.0) >= threshold]
        wins = sum(1 for r in eligible if r.get("final_outcome") == OUTCOME_SUCCESS)
        avg_pred = sum(float((r.get("prediction") or {}).get("success_probability", 0.0) or 0.0) for r in eligible) / len(eligible) if eligible else None
        actual = wins / len(eligible) if eligible else None
        thresholds[f"gte_{int(threshold*100)}"] = {
            "threshold": threshold,
            "samples": len(eligible),
            "success": wins,
            "actual_success_rate": round(actual, 6) if actual is not None else None,
            "average_predicted_success": round(avg_pred, 6) if avg_pred is not None else None,
            "calibration_gap": round(actual - avg_pred, 6) if actual is not None and avg_pred is not None else None,
        }

    by_day: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in settled:
        by_day[str(r.get("decision_date_tw") or "")].append(r)
    daily = []
    for day in sorted(by_day, reverse=True):
        node = _summary_from_rows(by_day[day])
        node["date"] = day
        daily.append(node)

    recent = []
    for r in sorted(current, key=lambda x: int(x.get("decision_time", 0)), reverse=True)[:300]:
        s72 = ((r.get("settlements") or {}).get("72H") or {})
        recent.append({
            "snapshot_id": r.get("snapshot_id"),
            "decision_time_tw": r.get("decision_time_tw"),
            "symbol": r.get("symbol"),
            "market_type": str(r.get("market_type") or "CRYPTO"),
            "state": r.get("state"),
            "target": r.get("target"),
            "success_probability": (r.get("prediction") or {}).get("success_probability"),
            "structural_survival_probability": (r.get("prediction") or {}).get("structural_survival_probability"),
            "true_fail_probability": (r.get("prediction") or {}).get("true_fail_probability"),
            "status_72h": s72.get("status"),
            "outcome_72h": s72.get("outcome"),
            "state_path_72h": s72.get("state_path") or [],
            "max_return_72h": s72.get("max_return"),
            "max_drawdown_72h": s72.get("max_drawdown"),
        })

    return {
        "schema_version": 1,
        "generated_at": datetime.fromtimestamp(now_ms / 1000.0, tz=timezone.utc).isoformat(),
        "contract": "Frozen Champion predictions only. Historical replay may change; frozen live predictions never change after creation. Settlement is appended later from actual future 4H path.",
        "champion": {
            "generation": generation,
            "model_id": model_id,
            "started_at": manifest.get("started_at"),
            "evolution_min_settled_72h": int(manifest.get("evolution_min_settled_72h") or 120),
        },
        "windows": windows,
        "by_state": by_state,
        "by_market": by_market,
        "probability_validation": thresholds,
        "daily": daily,
        "recent_records": recent,
        "previous_generations": generation_history,
    }



def frozen_record_to_case(record: dict[str, Any]) -> dict[str, Any] | None:
    """Convert one settled Frozen Champion snapshot into a training case.

    This is the live feedback loop. The original frozen prediction is never
    rewritten; only its observed settlements are converted into labels for the
    next generation training pass.
    """
    if not isinstance(record, dict) or not record.get("final_settled"):
        return None
    settlements = record.get("settlements") or {}
    labels: dict[str, Any] = {}
    for bars, hours in HORIZON_BARS_TO_HOURS.items():
        node = settlements.get(f"{hours}H") or {}
        if node.get("status") != "SETTLED":
            continue
        labels[str(bars)] = {
            "outcome": node.get("outcome"),
            "hit": bool(node.get("hit")),
            "bars_to_hit": node.get("bars_to_hit"),
            "max_return": node.get("max_return"),
            "max_drawdown": node.get("max_drawdown"),
            "max_bandpos": node.get("max_bandpos"),
            "hard_invalidated": bool(node.get("hard_invalidated", False)),
            "end_state": node.get("end_state"),
            "end_bandpos": node.get("end_bandpos"),
            "state_path": node.get("state_path") or [],
            "reason": node.get("reason"),
        }
    if "18" not in labels:
        return None
    market_type = str(record.get("market_type") or "CRYPTO").upper()
    features = dict(record.get("features") or {})
    features["market_type"] = market_type
    return {
        "symbol": str(record.get("symbol") or ""),
        "market_type": market_type,
        "time": int(record.get("decision_time", 0) or 0),
        "time_tw": record.get("decision_time_tw"),
        "state": str(record.get("state") or ""),
        "target": str(record.get("target") or ""),
        "entry_price": float(record.get("entry_price", 0.0) or 0.0),
        "features": features,
        "labels": labels,
        "source": "champion_frozen_live",
        "generation": int(record.get("generation", 0) or 0),
        "champion_model_id": str(record.get("champion_model_id") or ""),
    }


def current_generation_frozen_cases(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> list[dict[str, Any]]:
    model_id = str(manifest.get("champion_model_id") or "")
    generation = int(manifest.get("generation") or 1)
    output: list[dict[str, Any]] = []
    for row in rows:
        if str(row.get("champion_model_id") or "") != model_id or int(row.get("generation") or 0) != generation:
            continue
        case = frozen_record_to_case(row)
        if case is not None:
            output.append(case)
    output.sort(key=lambda c: (int(c.get("time", 0)), str(c.get("market_type", "")), str(c.get("symbol", ""))))
    return output

def build_evolution_review(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    model_id = str(manifest.get("champion_model_id") or "")
    generation = int(manifest.get("generation") or 1)
    threshold = int(manifest.get("evolution_min_settled_72h") or 120)
    current = [r for r in rows if str(r.get("champion_model_id") or "") == model_id and int(r.get("generation") or 0) == generation]
    settled = [r for r in current if r.get("final_outcome") in OUTCOME_KEYS]
    due = len(settled) >= threshold

    state_stats = {state: _summary_from_rows([r for r in current if r.get("state") == state]) for state in ("S0.5", "S1", "S2", "S3")}
    market_stats = {
        market_type: _summary_from_rows([r for r in current if str(r.get("market_type") or "CRYPTO") == market_type])
        for market_type in ("CRYPTO", "US_STOCK")
    }
    regime_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in settled:
        regime = str((r.get("features") or {}).get("dmi_adx_regime") or "UNKNOWN")
        regime_groups[regime].append(r)
    regime_stats = {name: _summary_from_rows(group) for name, group in sorted(regime_groups.items())}

    overconfident_failures = []
    for r in settled:
        p = float((r.get("prediction") or {}).get("success_probability", 0.0) or 0.0)
        if p >= 0.65 and r.get("final_outcome") != OUTCOME_SUCCESS:
            overconfident_failures.append({
                "symbol": r.get("symbol"),
                "decision_time_tw": r.get("decision_time_tw"),
                "state": r.get("state"),
                "predicted_success": p,
                "actual": r.get("final_outcome"),
                "adx_regime": (r.get("features") or {}).get("dmi_adx_regime"),
                "adx": (r.get("features") or {}).get("adx"),
                "di_plus": (r.get("features") or {}).get("di_plus"),
                "di_minus": (r.get("features") or {}).get("di_minus"),
            })
    overconfident_failures.sort(key=lambda x: x["predicted_success"], reverse=True)

    return {
        "schema_version": 1,
        "champion_model_id": model_id,
        "generation": generation,
        "settled_72h": len(settled),
        "minimum_settled_72h": threshold,
        "evolution_due": due,
        "state_review": state_stats,
        "market_review": market_stats,
        "adx_regime_review": regime_stats,
        "overconfident_failures": overconfident_failures[:50],
        "next_action": "retrain_and_publish_next_champion" if due else "keep_collecting_frozen_settlements",
    }

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .outcomes import build_confirmed_close_label

OUTCOME_SUCCESS = "SUCCESS_WITHIN_HORIZON"
OUTCOME_ALIVE = "ALIVE_SLOW"
OUTCOME_FAIL = "TRUE_FAIL"
OUTCOME_OTHER = "OTHER"
OUTCOME_KEYS = (OUTCOME_SUCCESS, OUTCOME_ALIVE, OUTCOME_FAIL, OUTCOME_OTHER)
TW_TZ = timezone(timedelta(hours=8))
HORIZON_BARS_TO_HOURS = {3: 12, 6: 24, 12: 48, 18: 72}
ROLLING_LEDGER_CACHE_DAYS = 90
EVOLUTION_POLICY_VERSION = "EVOLUTION-POLICY-v1"
OFFICIAL_FROZEN_SOURCE = "TERMINAL_0825_DAILY_CHECKPOINT"


def is_official_daily_record(row: dict[str, Any]) -> bool:
    """Only 08:25 exams built from the completed 08:00 daily close are scored."""
    return (
        str(row.get("frozen_source") or "") == OFFICIAL_FROZEN_SOURCE
        and row.get("official_scoring", True) is not False
    )


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
            "cci_expert": prediction.get("cci_expert") or {},
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
            "route_invalidated": bool(label.get("route_invalidated", False)),
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




def _parse_tw_date(value: Any) -> datetime.date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def apply_confirmed_daily_settlements(
    record: dict[str, Any],
    confirmed_by_date: dict[str, dict[str, Any]],
) -> bool:
    """Regrade one Frozen prediction only from completed daily checkpoints.

    ``confirmed_by_date`` is keyed by Taiwan date and contains exactly one
    post-close state snapshot per date for this symbol. The 12H window is
    intentionally observation-only. Old intraday-settled results are replaced
    once the corresponding post-close checkpoint exists; otherwise they are
    reset to PENDING so a false intraday SUCCESS can never survive migration.
    """
    changed = False
    settlements = record.setdefault("settlements", {})

    observation = {
        "status": "OBSERVATION_ONLY",
        "outcome": None,
        "hit": False,
        "settlement_basis": "INTRADAY_NOT_SCORED",
        "reason": "12H partial-daily movement is observation-only; official scoring waits for completed daily close",
    }
    if settlements.get("12H") != observation:
        settlements["12H"] = observation
        changed = True

    decision_date = _parse_tw_date(record.get("decision_date_tw"))
    if decision_date is None:
        return changed

    source_state = str(record.get("state") or "")
    entry_price = float(record.get("entry_price", 0.0) or 0.0)
    basis = "POST_CLOSE_DAILY_ROUTE_V2"

    for hours, day_count in ((24, 1), (48, 2), (72, 3)):
        key = f"{hours}H"
        expected_dates = [
            (decision_date + timedelta(days=i)).isoformat()
            for i in range(1, day_count + 1)
        ]
        future = [confirmed_by_date.get(day) for day in expected_dates]
        complete = all(isinstance(x, dict) for x in future)
        previous = settlements.get(key) or {}

        if not complete:
            # Any old 4H/intraday result is invalid under v3.6. Clear it now so
            # the UI does not keep showing a false green SUCCESS while waiting
            # for the exact post-close date(s) needed for regrading.
            if previous.get("status") == "SETTLED" and previous.get("settlement_basis") != basis:
                settlements[key] = {
                    "status": "PENDING",
                    "settlement_basis": basis,
                    "reason": "awaiting_exact_post_close_checkpoint_for_regrade",
                    "expected_checkpoint_dates_tw": expected_dates,
                }
                changed = True
            continue

        label = build_confirmed_close_label(
            source_state,
            future,
            entry_price=entry_price,
        )
        payload = {
            "status": "SETTLED",
            "outcome": label.get("outcome"),
            "hit": bool(label.get("hit")),
            "days_to_hit": label.get("days_to_hit"),
            "bars_to_hit": label.get("bars_to_hit"),
            "max_return": label.get("max_return"),
            "max_drawdown": label.get("max_drawdown"),
            "max_bandpos": label.get("max_bandpos"),
            "hard_invalidated": bool(label.get("hard_invalidated", False)),
            "end_state": label.get("end_state"),
            "end_bandpos": label.get("end_bandpos"),
            "state_path": label.get("state_path") or [],
            "reason": label.get("reason"),
            "settlement_basis": basis,
            "confirmed_checkpoint_dates_tw": expected_dates,
        }
        if previous != payload:
            settlements[key] = payload
            changed = True

        if hours == 72:
            if record.get("final_outcome") != label.get("outcome") or not record.get("final_settled"):
                record["final_outcome"] = label.get("outcome")
                record["final_settled"] = True
                record["final_path"] = label.get("state_path") or []
                record["final_settlement_basis"] = basis
                changed = True

    # If 72H was previously settled by the obsolete intraday contract but the
    # exact 3 daily checkpoints are not available yet, revoke final_settled.
    s72 = settlements.get("72H") or {}
    if s72.get("status") != "SETTLED" or s72.get("settlement_basis") != basis:
        if record.get("final_settled") or record.get("final_outcome") is not None:
            record["final_settled"] = False
            record["final_outcome"] = None
            record["final_path"] = []
            record.pop("final_settlement_basis", None)
            changed = True

    record["settlement_contract"] = "POST_CLOSE_DAILY_ROUTE_V2"
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
    generation_rows = [r for r in rows if str(r.get("champion_model_id") or "") == model_id and int(r.get("generation") or 0) == generation]
    current = [r for r in generation_rows if is_official_daily_record(r)]
    legacy_excluded = len(generation_rows) - len(current)

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
            "checkpoint_time_tw": r.get("checkpoint_time_tw"),
            "frozen_source": r.get("frozen_source"),
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
        "contract": "Official Champion records only: Taiwan 08:25 exam using the completed 08:00 daily close. Intraday 4H/partial-daily states cannot score SUCCESS; 12H is observation-only; 24H/48H/72H use confirmed daily checkpoints.",
        "legacy_excluded": legacy_excluded,
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
    if not is_official_daily_record(record):
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
            "route_invalidated": bool(node.get("route_invalidated", False)),
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
        "live_feedback": {
            "predicted_success_probability": float((record.get("prediction") or {}).get("success_probability", 0.0) or 0.0),
            "predicted_structural_survival_probability": float((record.get("prediction") or {}).get("structural_survival_probability", 0.0) or 0.0),
            "predicted_true_fail_probability": float((record.get("prediction") or {}).get("true_fail_probability", 0.0) or 0.0),
            "actual_72h_outcome": ((record.get("settlements") or {}).get("72H") or {}).get("outcome"),
        },
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


def prune_rolling_ledger(
    rows: list[dict[str, Any]],
    *,
    now_ms: int,
    keep_days: int = ROLLING_LEDGER_CACHE_DAYS,
) -> list[dict[str, Any]]:
    """Keep only a bounded compatibility cache in Git/local workspace.

    R2 date shards are the authoritative ledger. Pending rows are always kept
    even if their timestamp somehow falls outside the normal retention window.
    """
    days = max(7, min(3650, int(keep_days)))
    cutoff = int(now_ms) - days * 24 * 60 * 60 * 1000
    kept = [
        row for row in rows
        if int(row.get("decision_time", 0) or 0) >= cutoff or not bool(row.get("final_settled"))
    ]
    kept.sort(key=lambda r: (int(r.get("decision_time", 0)), str(r.get("market_type", "")), str(r.get("symbol", ""))))
    return kept


def save_ledger_shards(base_dir: Path, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Write R2-ready Generation/date shards.

    Existing remote shards are never deleted here. Rewriting the same date key
    is intentional because 12H/24H/48H/72H settlements are appended later.
    """
    if base_dir.exists():
        for child in sorted(base_dir.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                try:
                    child.rmdir()
                except OSError:
                    pass
    base_dir.mkdir(parents=True, exist_ok=True)

    grouped: dict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        generation = int(row.get("generation", 0) or 0)
        date_tw = str(row.get("decision_date_tw") or "")
        if generation <= 0 or not date_tw:
            continue
        grouped[(generation, date_tw)].append(row)

    manifest: list[dict[str, Any]] = []
    for (generation, date_tw), bucket in sorted(grouped.items()):
        gen_name = f"GEN{generation:03d}"
        rel = Path(gen_name) / f"{date_tw}.json"
        path = base_dir / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "generation": generation,
            "date_tw": date_tw,
            "champion_model_id": str(bucket[0].get("champion_model_id") or ""),
            "records": sorted(bucket, key=lambda r: (int(r.get("decision_time", 0)), str(r.get("market_type", "")), str(r.get("symbol", "")))),
        }
        save_json(path, payload)
        manifest.append({
            "generation": generation,
            "date_tw": date_tw,
            "file": str(path),
            "relative_file": rel.as_posix(),
            "r2_key": f"champion/ledger/{gen_name}/{date_tw}.json",
            "records": len(bucket),
        })
    save_json(base_dir / "_upload_manifest.json", {"schema_version": 1, "shards": manifest})
    return manifest


def _calibration_stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    settled = [r for r in rows if r.get("final_outcome") in OUTCOME_KEYS]
    n = len(settled)
    if not n:
        return {
            "samples": 0,
            "average_predicted_success": None,
            "actual_success_rate": None,
            "calibration_gap": None,
            "overconfident_misses": 0,
            "underconfident_successes": 0,
            "true_fail": 0,
        }
    preds = [float((r.get("prediction") or {}).get("success_probability", 0.0) or 0.0) for r in settled]
    actual = [1.0 if r.get("final_outcome") == OUTCOME_SUCCESS else 0.0 for r in settled]
    avg_pred = sum(preds) / n
    actual_rate = sum(actual) / n
    return {
        "samples": n,
        "average_predicted_success": round(avg_pred, 6),
        "actual_success_rate": round(actual_rate, 6),
        "calibration_gap": round(actual_rate - avg_pred, 6),
        "overconfident_misses": sum(1 for r, p in zip(settled, preds) if p >= 0.65 and r.get("final_outcome") != OUTCOME_SUCCESS),
        "underconfident_successes": sum(1 for r, p in zip(settled, preds) if p <= 0.45 and r.get("final_outcome") == OUTCOME_SUCCESS),
        "true_fail": sum(1 for r in settled if r.get("final_outcome") == OUTCOME_FAIL),
    }


def _group_calibration(
    rows: list[dict[str, Any]],
    key_fn,
) -> dict[str, Any]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if row.get("final_outcome") not in OUTCOME_KEYS:
            continue
        key = str(key_fn(row) or "").strip()
        if key and "UNKNOWN" not in key:
            groups[key].append(row)
    return {key: _calibration_stats(group) for key, group in sorted(groups.items())}


def build_evolution_review(rows: list[dict[str, Any]], manifest: dict[str, Any]) -> dict[str, Any]:
    model_id = str(manifest.get("champion_model_id") or "")
    generation = int(manifest.get("generation") or 1)
    threshold = int(manifest.get("evolution_min_settled_72h") or 120)
    generation_rows = [r for r in rows if str(r.get("champion_model_id") or "") == model_id and int(r.get("generation") or 0) == generation]
    current = [r for r in generation_rows if is_official_daily_record(r)]
    settled = [r for r in current if r.get("final_outcome") in OUTCOME_KEYS]
    due = len(settled) >= threshold

    state_stats = {state: _summary_from_rows([r for r in current if r.get("state") == state]) for state in ("S0.5", "S1", "S2", "S3")}
    market_stats = {
        market_type: _summary_from_rows([r for r in current if str(r.get("market_type") or "CRYPTO") == market_type])
        for market_type in ("CRYPTO", "US_STOCK")
    }
    regime_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in settled:
        regime = str((r.get("features") or {}).get("cci_regime") or "UNKNOWN")
        regime_groups[regime].append(r)
    regime_stats = {name: _summary_from_rows(group) for name, group in sorted(regime_groups.items())}

    overconfident_failures = []
    for r in settled:
        p = float((r.get("prediction") or {}).get("success_probability", 0.0) or 0.0)
        if p >= 0.65 and r.get("final_outcome") != OUTCOME_SUCCESS:
            overconfident_failures.append({
                "symbol": r.get("symbol"),
                "decision_time_tw": r.get("decision_time_tw"),
                "market_type": r.get("market_type"),
                "state": r.get("state"),
                "predicted_success": p,
                "actual": r.get("final_outcome"),
                "cci_regime": (r.get("features") or {}).get("cci_regime"),
                "cci_smoothing_turn_event": (r.get("features") or {}).get("cci_smoothing_turn_event"),
                "cci": (r.get("features") or {}).get("cci"),
                "cci_zone": (r.get("features") or {}).get("cci_zone"),
                "cci_cross_event": (r.get("features") or {}).get("cci_cross_event"),
                "cci_smoothing_direction": (r.get("features") or {}).get("cci_smoothing_direction"),
            })
    overconfident_failures.sort(key=lambda x: x["predicted_success"], reverse=True)

    error_groups = {
        "state": _group_calibration(settled, lambda r: r.get("state")),
        "market": _group_calibration(settled, lambda r: str(r.get("market_type") or "CRYPTO")),
        "state_regime": _group_calibration(
            settled,
            lambda r: f"{r.get('state')}|{(r.get('features') or {}).get('cci_regime')}",
        ),
        "state_turn": _group_calibration(
            settled,
            lambda r: f"{r.get('state')}|{(r.get('features') or {}).get('cci_smoothing_turn_event')}",
        ),
    }

    return {
        "schema_version": 2,
        "champion_model_id": model_id,
        "generation": generation,
        "settled_72h": len(settled),
        "legacy_excluded": len(generation_rows) - len(current),
        "minimum_settled_72h": threshold,
        "evolution_due": due,
        "overall_calibration": _calibration_stats(settled),
        "state_review": state_stats,
        "market_review": market_stats,
        "cci_regime_review": regime_stats,
        "error_groups": error_groups,
        "overconfident_failures": overconfident_failures[:50],
        "next_action": "build_error_driven_policy_then_retrain_next_champion" if due else "keep_collecting_frozen_settlements",
    }


def build_evolution_policy(
    review: dict[str, Any],
    rows: list[dict[str, Any]],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    """Turn the review into machine-actionable next-generation weighting rules.

    This does not invent new indicators or rewrite S-state definitions. It
    changes how strongly the next model learns from the exact live conditions
    where the current Champion was over/under-confident.
    """
    due = bool(review.get("evolution_due"))
    minimum_group_samples = 5
    group_rules: list[dict[str, Any]] = []
    groups = review.get("error_groups") or {}

    for group_type in ("state", "market", "state_regime", "state_turn"):
        for key, stats in (groups.get(group_type) or {}).items():
            n = int(stats.get("samples", 0) or 0)
            gap = stats.get("calibration_gap")
            if n < minimum_group_samples or gap is None:
                continue
            gap = float(gap)
            abs_gap = abs(gap)
            direction = "HOLD"
            if gap <= -0.05:
                direction = "LOWER_CONFIDENCE"
            elif gap >= 0.05:
                direction = "RAISE_CONFIDENCE"
            # Larger live calibration errors receive more representation in the
            # next training set. Actual outcomes still decide the direction.
            multiplier = min(2.0, 1.0 + abs_gap * 5.0)
            group_rules.append({
                "group_type": group_type,
                "key": key,
                "samples": n,
                "average_predicted_success": stats.get("average_predicted_success"),
                "actual_success_rate": stats.get("actual_success_rate"),
                "calibration_gap": round(gap, 6),
                "direction": direction,
                "live_weight_multiplier": round(multiplier, 4),
                "overconfident_misses": int(stats.get("overconfident_misses", 0) or 0),
                "underconfident_successes": int(stats.get("underconfident_successes", 0) or 0),
            })

    group_rules.sort(
        key=lambda x: (abs(float(x.get("calibration_gap", 0.0))), int(x.get("samples", 0))),
        reverse=True,
    )
    policy_seed = {
        "champion_model_id": str(review.get("champion_model_id") or ""),
        "generation": int(review.get("generation") or manifest.get("generation") or 1),
        "settled_72h": int(review.get("settled_72h", 0) or 0),
        "group_rules": group_rules,
    }
    policy_id = f"{EVOLUTION_POLICY_VERSION}-GEN{policy_seed['generation']:03d}-{policy_seed['settled_72h']}"
    return {
        "schema_version": 1,
        "policy_version": EVOLUTION_POLICY_VERSION,
        "policy_id": policy_id,
        "active_for_next_training": due,
        "source_review": {
            "champion_model_id": policy_seed["champion_model_id"],
            "generation": policy_seed["generation"],
            "settled_72h": policy_seed["settled_72h"],
            "minimum_settled_72h": int(review.get("minimum_settled_72h", 120) or 120),
        },
        "objective": "Use this generation's real Frozen mistakes to change live-case reinforcement in the next model; reduce repeated high-confidence errors without rewriting fixed S-state rules.",
        "minimum_group_samples": minimum_group_samples,
        "case_error_multipliers": {
            "overconfident_non_success_p65": 2.5,
            "true_fail_p55": 2.0,
            "underconfident_success_p45": 2.0,
            "ordinary_non_success_p50": 1.4,
            "default": 1.0,
        },
        "group_rules": group_rules,
        "max_effective_case_weight": 50,
        "overconfident_failures": list(review.get("overconfident_failures") or [])[:50],
    }


def _case_group_keys(case: dict[str, Any]) -> dict[str, str]:
    features = case.get("features") or {}
    state = str(case.get("state") or "")
    market = str(case.get("market_type") or features.get("market_type") or "CRYPTO")
    regime = str(features.get("cci_regime") or "UNKNOWN")
    turn = str(features.get("cci_smoothing_turn_event") or "UNKNOWN")
    return {
        "state": state,
        "market": market,
        "state_regime": f"{state}|{regime}",
        "state_turn": f"{state}|{turn}",
    }


def adaptive_reinforcement_weight(
    case: dict[str, Any],
    policy: dict[str, Any] | None,
    base_weight: int,
) -> int:
    """Weight one settled live case according to the Champion's actual mistake.

    The policy is generated from evolution_review.json. The output is bounded
    so a handful of unusual observations can never dominate the historical base.
    """
    base = max(1, min(50, int(base_weight)))
    if not policy or not policy.get("active_for_next_training"):
        return base

    feedback = case.get("live_feedback") or {}
    p = float(feedback.get("predicted_success_probability", 0.0) or 0.0)
    outcome = str(feedback.get("actual_72h_outcome") or "")
    success = outcome == OUTCOME_SUCCESS

    error_mult = 1.0
    cfg = policy.get("case_error_multipliers") or {}
    if not success and p >= 0.65:
        error_mult = float(cfg.get("overconfident_non_success_p65", 2.5) or 2.5)
    elif outcome == OUTCOME_FAIL and p >= 0.55:
        error_mult = float(cfg.get("true_fail_p55", 2.0) or 2.0)
    elif success and p <= 0.45:
        error_mult = float(cfg.get("underconfident_success_p45", 2.0) or 2.0)
    elif not success and p >= 0.50:
        error_mult = float(cfg.get("ordinary_non_success_p50", 1.4) or 1.4)

    keys = _case_group_keys(case)
    group_mult = 1.0
    for rule in policy.get("group_rules") or []:
        gtype = str(rule.get("group_type") or "")
        if keys.get(gtype) == str(rule.get("key") or ""):
            group_mult = max(group_mult, float(rule.get("live_weight_multiplier", 1.0) or 1.0))

    cap = max(base, min(50, int(policy.get("max_effective_case_weight", 50) or 50)))
    weight = int(round(base * error_mult * group_mult))
    return max(1, min(cap, weight))

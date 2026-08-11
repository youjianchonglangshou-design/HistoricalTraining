from __future__ import annotations

import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .outcomes import (
    OUTCOME_ALIVE,
    OUTCOME_FAIL,
    OUTCOME_KEYS,
    OUTCOME_LABELS_ZH,
    OUTCOME_OTHER,
    OUTCOME_SUCCESS,
)

FEATURE_LEVELS = [
    [],
    ["midline_state"],
    ["midline_state", "bandpos_bin"],
    ["midline_state", "bandpos_bin", "trigger_stage"],
    ["midline_state", "bandpos_bin", "trigger_stage", "bandwidth_trend"],
    ["midline_state", "bandpos_bin", "trigger_stage", "bandwidth_trend", "state_age_bin"],
]


def _wilson(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    p = wins / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _signature(features: dict[str, Any], fields: list[str]) -> str:
    if not fields:
        return "BASELINE"
    return "|".join(f"{field}={features.get(field)}" for field in fields)


def _outcome_for(case: dict[str, Any], horizon: int) -> str:
    label = (case.get("labels") or {}).get(str(horizon)) or {}
    outcome = str(label.get("outcome") or "")
    if outcome in OUTCOME_KEYS:
        return outcome
    # Backward compatibility for an old cached cases artifact if someone feeds
    # it into the v2 builder manually.
    return OUTCOME_SUCCESS if bool(label.get("hit")) else OUTCOME_OTHER


def _counts(group: list[dict[str, Any]], horizon: int) -> Counter[str]:
    counts = Counter({key: 0 for key in OUTCOME_KEYS})
    for case in group:
        counts[_outcome_for(case, horizon)] += 1
    return counts


def _late_success_stats(group: list[dict[str, Any]], horizon: int) -> dict[str, Any] | None:
    eligible = 0
    late = 0
    for case in group:
        label = (case.get("labels") or {}).get(str(horizon)) or {}
        value = label.get("late_success_4_7d")
        if value is None:
            continue
        eligible += 1
        if bool(value):
            late += 1
    if eligible <= 0:
        return None
    return {
        "eligible_samples": eligible,
        "count": late,
        "probability": round(late / eligible, 6),
        "meaning": "Among cases that missed the primary horizon and had enough future data, target hit on day 4-7.",
    }


def _distribution_payload(
    counts: Counter[str],
    total: int,
    *,
    baseline_probs: dict[str, float] | None = None,
    prior_strength: float = 0.0,
) -> tuple[dict[str, Any], dict[str, float]]:
    raw_probs = {key: (counts[key] / total if total else 0.0) for key in OUTCOME_KEYS}
    if baseline_probs is None or prior_strength <= 0:
        probs = dict(raw_probs)
    else:
        probs = {
            key: ((counts[key] + baseline_probs.get(key, 0.0) * prior_strength) / (total + prior_strength))
            if total > 0
            else baseline_probs.get(key, 0.0)
            for key in OUTCOME_KEYS
        }

    payload = {
        key: {
            "label_zh": OUTCOME_LABELS_ZH[key],
            "count": int(counts[key]),
            "raw_probability": round(raw_probs[key], 6),
            "probability": round(probs[key], 6),
        }
        for key in OUTCOME_KEYS
    }
    return payload, probs


def _stats_node(
    group: list[dict[str, Any]],
    horizon: int,
    *,
    baseline_probs: dict[str, float] | None = None,
    prior_strength: float = 0.0,
) -> dict[str, Any]:
    n = len(group)
    counts = _counts(group, horizon)
    outcomes, probs = _distribution_payload(
        counts,
        n,
        baseline_probs=baseline_probs,
        prior_strength=prior_strength,
    )
    wins = int(counts[OUTCOME_SUCCESS])
    raw_success = wins / n if n else 0.0
    success_prob = probs[OUTCOME_SUCCESS]
    low, high = _wilson(wins, n)
    raw_survival = raw_success + (counts[OUTCOME_ALIVE] / n if n else 0.0)
    survival_prob = probs[OUTCOME_SUCCESS] + probs[OUTCOME_ALIVE]
    node: dict[str, Any] = {
        "samples": n,
        # Backward-compatible binary fields used by the current Streamlit reader.
        "wins": wins,
        "raw_probability": round(raw_success, 6),
        "probability": round(success_prob, 6),
        "wilson95": [round(low, 6), round(high, 6)],
        # v2 outcome decomposition.
        "outcomes": outcomes,
        "raw_structural_survival_probability": round(raw_survival, 6),
        "structural_survival_probability": round(survival_prob, 6),
        "true_fail_probability": round(probs[OUTCOME_FAIL], 6),
        "other_probability": round(probs[OUTCOME_OTHER], 6),
    }
    late = _late_success_stats(group, horizon)
    if late is not None:
        node["late_success_4_7d"] = late
    return node


def build_model(
    cases: list[dict[str, Any]],
    horizons: tuple[int, ...],
    min_samples: int = 50,
    prior_strength: float = 20.0,
) -> dict[str, Any]:
    by_state_h: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        state = str(case["state"])
        for h in horizons:
            if str(h) in case.get("labels", {}):
                by_state_h[(state, h)].append(case)

    model: dict[str, Any] = {
        "schema_version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_contract": "S-state rules fixed; probability/outcome parameters evolve in JSON",
        "settlement_contract": "Each horizon is decomposed into SUCCESS_WITHIN_HORIZON + ALIVE_SLOW + TRUE_FAIL + OTHER = 100%.",
        "outcome_keys": list(OUTCOME_KEYS),
        "outcome_labels_zh": OUTCOME_LABELS_ZH,
        "default_min_samples": int(min_samples),
        "prior_strength": float(prior_strength),
        "horizons_bars": list(horizons),
        "horizon_hours": {str(h): int(h * 4) for h in horizons},
        "primary_swing_horizon_bars": 18,
        "primary_swing_horizon_hours": 72,
        "states": {},
    }

    for (state, h), group in sorted(by_state_h.items()):
        baseline_node = _stats_node(group, h)
        baseline_probs = {
            key: float((baseline_node["outcomes"].get(key) or {}).get("probability", 0.0))
            for key in OUTCOME_KEYS
        }
        state_node = model["states"].setdefault(state, {"target": group[0]["target"], "horizons": {}})
        horizon_node: dict[str, Any] = {
            "baseline": baseline_node,
            "levels": [],
        }

        for level_idx, fields in enumerate(FEATURE_LEVELS[1:], start=1):
            buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for case in group:
                buckets[_signature(case["features"], fields)].append(case)
            rules = []
            for sig, bucket in buckets.items():
                node = _stats_node(
                    bucket,
                    h,
                    baseline_probs=baseline_probs,
                    prior_strength=prior_strength,
                )
                node.update(
                    {
                        "signature": sig,
                        "eligible": int(node["samples"]) >= min_samples,
                    }
                )
                rules.append(node)
            rules.sort(key=lambda r: (-int(r["samples"]), r["signature"]))
            horizon_node["levels"].append({"level": level_idx, "fields": fields, "rules": rules})
        state_node["horizons"][str(h)] = horizon_node

    digest_src = json.dumps(model["states"], ensure_ascii=False, sort_keys=True).encode("utf-8")
    model["model_id"] = hashlib.sha256(digest_src).hexdigest()[:16]
    return model


def lookup_probability(model: dict[str, Any], state: str, horizon: int, features: dict[str, Any]) -> dict[str, Any]:
    state_node = model.get("states", {}).get(state)
    if not state_node:
        return {"available": False, "reason": "state_missing"}
    hnode = state_node.get("horizons", {}).get(str(horizon))
    if not hnode:
        return {"available": False, "reason": "horizon_missing"}

    min_samples = int(model.get("default_min_samples", 50))
    # Most specific eligible level first.
    for level in reversed(hnode.get("levels", [])):
        sig = _signature(features, list(level.get("fields") or []))
        for rule in level.get("rules", []):
            if rule.get("signature") == sig and int(rule.get("samples", 0)) >= min_samples:
                return {
                    "available": True,
                    "probability": float(rule["probability"]),
                    "raw_probability": float(rule["raw_probability"]),
                    "samples": int(rule["samples"]),
                    "wins": int(rule["wins"]),
                    "level": int(level["level"]),
                    "fields": list(level["fields"]),
                    "signature": sig,
                    "wilson95": rule.get("wilson95"),
                    "outcomes": rule.get("outcomes") or {},
                    "structural_survival_probability": float(rule.get("structural_survival_probability", rule["probability"])),
                    "true_fail_probability": float(rule.get("true_fail_probability", 0.0)),
                    "other_probability": float(rule.get("other_probability", 0.0)),
                    "late_success_4_7d": rule.get("late_success_4_7d"),
                }
    base = hnode["baseline"]
    return {
        "available": True,
        "probability": float(base["probability"]),
        "raw_probability": float(base["raw_probability"]),
        "samples": int(base["samples"]),
        "wins": int(base["wins"]),
        "level": 0,
        "fields": [],
        "signature": "BASELINE",
        "wilson95": base.get("wilson95"),
        "outcomes": base.get("outcomes") or {},
        "structural_survival_probability": float(base.get("structural_survival_probability", base["probability"])),
        "true_fail_probability": float(base.get("true_fail_probability", 0.0)),
        "other_probability": float(base.get("other_probability", 0.0)),
        "late_success_4_7d": base.get("late_success_4_7d"),
    }


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

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

CCI_PRIMARY_VERSION = "CCI-PRIMARY-v2-PATH-TREE-HLC3-20-SMA14"

# Continuous path variables are cut into state-specific quartiles learned from
# the historical distribution. The model never hard-codes which quartile is
# bullish/bearish; the tree chooses useful branches from outcomes.
PATH_QUANTILE_FIELDS = {
    "cci_sma_gap": "cci_sma_gap_q",
    "cci_gap_velocity_1d": "cci_gap_velocity_q",
    "cci_gap_acceleration": "cci_gap_acceleration_q",
    "cci_slope_1d": "cci_slope_1d_q",
    "cci_slope_3d": "cci_slope_3d_q",
    "cci_acceleration": "cci_acceleration_q",
    "cci_smoothing_slope_1d": "cci_smoothing_slope_1d_q",
    "cci_smoothing_slope_3d": "cci_smoothing_slope_3d_q",
    "cci_distance_to_neg100": "cci_distance_to_neg100_q",
    "cci_distance_to_zero": "cci_distance_to_zero_q",
    "midline_slope_1d": "midline_slope_1d_q",
    "midline_slope_3d": "midline_slope_3d_q",
    "midline_slope_change_3d": "midline_slope_change_q",
    "price_high_delta_pct": "price_high_delta_q",
    "cci_high_delta": "cci_high_delta_q",
    "price_low_delta_pct": "price_low_delta_q",
    "cci_low_delta": "cci_low_delta_q",
}

# S-state only defines the question/target. These pools define what the learner
# is allowed to inspect while answering. The split order itself is learned.
COMMON_PATH_FIELDS = [
    "market_type",
    "midline_path_phase",
    "cci_zone",
    "cci_cross_cycle",
    "cci_last_cross_type",
    "cci_last_cross_zone",
    "cci_last_cross_sma_direction",
    "cci_last_cross_midline_phase",
    "cci_previous_same_cross_zone",
    "cci_up_cross_count_bin",
    "cci_down_cross_count_bin",
    "cci_gap_motion",
    "cci_retest_state",
    "cci_divergence",
    "cci_sma_relation",
    "cci_relation_age_bin",
    "cci_smoothing_direction",
    "cci_smoothing_age_bin",
    "cci_smoothing_turn_event",
    "ha_color",
    "current_run_bin",
    "cci_sma_gap_q",
    "cci_gap_velocity_q",
    "cci_gap_acceleration_q",
    "cci_slope_1d_q",
    "cci_slope_3d_q",
    "cci_acceleration_q",
    "cci_smoothing_slope_1d_q",
    "cci_smoothing_slope_3d_q",
    "cci_distance_to_neg100_q",
    "cci_distance_to_zero_q",
    "midline_slope_1d_q",
    "midline_slope_3d_q",
    "midline_slope_change_q",
]

STATE_PATH_FIELDS = {
    "S0.5": COMMON_PATH_FIELDS,
    "S1": [
        "market_type", "midline_path_phase", "cci_zone", "cci_cross_cycle",
        "cci_gap_motion", "cci_retest_state", "cci_sma_relation",
        "cci_smoothing_direction", "cci_smoothing_turn_event", "ha_color",
        "current_run_bin", "cci_slope_1d_q", "cci_slope_3d_q",
        "cci_smoothing_slope_1d_q", "cci_sma_gap_q", "midline_slope_3d_q",
        "midline_slope_change_q", "cci_divergence",
    ],
    "S2": COMMON_PATH_FIELDS + [
        "price_high_delta_q", "cci_high_delta_q", "price_low_delta_q", "cci_low_delta_q",
    ],
    "S3": [
        "market_type", "midline_path_phase", "cci_zone", "cci_cross_cycle",
        "cci_gap_motion", "cci_retest_state", "cci_divergence",
        "cci_sma_relation", "cci_smoothing_direction", "cci_smoothing_turn_event",
        "ha_color", "current_run_bin", "cci_sma_gap_q", "cci_gap_velocity_q",
        "cci_slope_1d_q", "cci_slope_3d_q", "cci_smoothing_slope_1d_q",
        "midline_slope_3d_q", "midline_slope_change_q", "price_high_delta_q",
        "cci_high_delta_q",
    ],
}

STATE_MAX_DEPTH = {"S0.5": 6, "S1": 5, "S2": 6, "S3": 5}


def _wilson(wins: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return 0.0, 1.0
    p = wins / total
    denom = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denom
    margin = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denom
    return max(0.0, center - margin), min(1.0, center + margin)


def _outcome_for(case: dict[str, Any], horizon: int) -> str:
    label = (case.get("labels") or {}).get(str(horizon)) or {}
    outcome = str(label.get("outcome") or "")
    if outcome in OUTCOME_KEYS:
        return outcome
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
            if total > 0 else baseline_probs.get(key, 0.0)
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
        counts, n, baseline_probs=baseline_probs, prior_strength=prior_strength
    )
    wins = int(counts[OUTCOME_SUCCESS])
    raw_success = wins / n if n else 0.0
    low, high = _wilson(wins, n)
    survival = probs[OUTCOME_SUCCESS] + probs[OUTCOME_ALIVE]
    node: dict[str, Any] = {
        "samples": n,
        "wins": wins,
        "raw_probability": round(raw_success, 6),
        "probability": round(probs[OUTCOME_SUCCESS], 6),
        "wilson95": [round(low, 6), round(high, 6)],
        "outcomes": outcomes,
        "raw_structural_survival_probability": round(
            raw_success + (counts[OUTCOME_ALIVE] / n if n else 0.0), 6
        ),
        "structural_survival_probability": round(survival, 6),
        "true_fail_probability": round(probs[OUTCOME_FAIL], 6),
        "other_probability": round(probs[OUTCOME_OTHER], 6),
    }
    late = _late_success_stats(group, horizon)
    if late is not None:
        node["late_success_4_7d"] = late
    return node


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _quantile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = (len(ordered) - 1) * max(0.0, min(1.0, q))
    low = int(math.floor(position))
    high = int(math.ceil(position))
    if low == high:
        return ordered[low]
    weight = position - low
    return ordered[low] * (1.0 - weight) + ordered[high] * weight


def _build_path_binning(group: list[dict[str, Any]]) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for raw_field, q_field in PATH_QUANTILE_FIELDS.items():
        values = [
            value for value in (
                _safe_float((case.get("features") or {}).get(raw_field)) for case in group
            ) if value is not None
        ]
        output[raw_field] = {
            "derived_field": q_field,
            "q25": round(_quantile(values, 0.25), 8),
            "q50": round(_quantile(values, 0.50), 8),
            "q75": round(_quantile(values, 0.75), 8),
            "samples": len(values),
        }
    return output


def _apply_path_binning(features: dict[str, Any], binning: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(features or {})
    for raw_field, q_field in PATH_QUANTILE_FIELDS.items():
        value = _safe_float(features.get(raw_field))
        node = binning.get(raw_field) or {}
        q25 = _safe_float(node.get("q25"))
        q50 = _safe_float(node.get("q50"))
        q75 = _safe_float(node.get("q75"))
        if value is None or q25 is None or q50 is None or q75 is None:
            enriched[q_field] = "UNKNOWN"
        elif value <= q25:
            enriched[q_field] = "Q1"
        elif value <= q50:
            enriched[q_field] = "Q2"
        elif value <= q75:
            enriched[q_field] = "Q3"
        else:
            enriched[q_field] = "Q4"
    return enriched


def _gini(counts: Counter[str]) -> float:
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    return 1.0 - sum((counts[key] / total) ** 2 for key in OUTCOME_KEYS)


def _feature_value(case: dict[str, Any], field: str, binning: dict[str, Any]) -> str:
    features = _apply_path_binning(case.get("features") or {}, binning)
    value = features.get(field)
    if value is None or value == "":
        return "UNKNOWN"
    return str(value)


def _best_split(
    group: list[dict[str, Any]],
    horizon: int,
    fields: list[str],
    binning: dict[str, Any],
    min_leaf: int,
) -> tuple[str | None, float, dict[str, list[dict[str, Any]]]]:
    if len(group) < min_leaf * 2:
        return None, 0.0, {}
    parent_counts = _counts(group, horizon)
    parent_impurity = _gini(parent_counts)
    if parent_impurity <= 1e-12:
        return None, 0.0, {}

    best_field: str | None = None
    best_gain = 0.0
    best_children: dict[str, list[dict[str, Any]]] = {}
    n_total = len(group)

    for field in fields:
        buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for case in group:
            buckets[_feature_value(case, field, binning)].append(case)
        eligible = {key: rows for key, rows in buckets.items() if len(rows) >= min_leaf}
        if len(eligible) < 2:
            continue
        modeled = sum(len(rows) for rows in eligible.values())
        rare = n_total - modeled
        weighted = 0.0
        for rows in eligible.values():
            weighted += (len(rows) / n_total) * _gini(_counts(rows, horizon))
        # Rare/unseen values fall back to the parent at inference, so they earn
        # no artificial gain during training either.
        if rare > 0:
            weighted += (rare / n_total) * parent_impurity
        gain = parent_impurity - weighted
        if gain > best_gain + 1e-12:
            best_field = field
            best_gain = gain
            best_children = eligible

    return best_field, best_gain, best_children


def _build_tree(
    group: list[dict[str, Any]],
    horizon: int,
    *,
    fields: list[str],
    binning: dict[str, Any],
    baseline_probs: dict[str, float],
    min_leaf: int,
    prior_strength: float,
    max_depth: int,
    min_gain: float,
    depth: int = 0,
    used_fields: tuple[str, ...] = (),
) -> dict[str, Any]:
    node = _stats_node(
        group, horizon, baseline_probs=baseline_probs, prior_strength=prior_strength
    )
    node.update({"depth": depth})
    if depth >= max_depth or len(group) < min_leaf * 2:
        node["leaf"] = True
        return node

    remaining = [field for field in fields if field not in used_fields]
    split_field, gain, children = _best_split(group, horizon, remaining, binning, min_leaf)
    if split_field is None or gain < min_gain:
        node["leaf"] = True
        return node

    node.update({
        "leaf": False,
        "split_field": split_field,
        "gain": round(gain, 8),
        "children": {},
    })
    for value, rows in sorted(children.items(), key=lambda item: (-len(item[1]), item[0])):
        node["children"][value] = _build_tree(
            rows,
            horizon,
            fields=fields,
            binning=binning,
            baseline_probs=baseline_probs,
            min_leaf=min_leaf,
            prior_strength=prior_strength,
            max_depth=max_depth,
            min_gain=min_gain,
            depth=depth + 1,
            used_fields=used_fields + (split_field,),
        )
    return node


def _node_outcome_payload(node: dict[str, Any]) -> dict[str, Any]:
    outcomes = node.get("outcomes") or {}
    success = float((outcomes.get(OUTCOME_SUCCESS) or {}).get("probability", node.get("probability", 0.0)) or 0.0)
    alive = float((outcomes.get(OUTCOME_ALIVE) or {}).get("probability", 0.0) or 0.0)
    fail = float((outcomes.get(OUTCOME_FAIL) or {}).get("probability", node.get("true_fail_probability", 0.0)) or 0.0)
    other = float((outcomes.get(OUTCOME_OTHER) or {}).get("probability", node.get("other_probability", 0.0)) or 0.0)
    return {
        "outcomes": outcomes,
        "success_probability": success,
        "alive_slow_probability": alive,
        "true_fail_probability": fail,
        "other_probability": other,
        "structural_survival_probability": success + alive,
        "late_success_4_7d": node.get("late_success_4_7d"),
    }


def _walk_tree(tree: dict[str, Any], features: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    node = tree
    path: list[dict[str, str]] = []
    while isinstance(node, dict) and not bool(node.get("leaf", True)):
        field = str(node.get("split_field") or "")
        if not field:
            break
        value = str(features.get(field) if features.get(field) is not None else "UNKNOWN")
        child = (node.get("children") or {}).get(value)
        if not isinstance(child, dict):
            break
        path.append({"field": field, "value": value})
        node = child
    return node, path


def build_model(
    cases: list[dict[str, Any]],
    horizons: tuple[int, ...],
    min_samples: int = 50,
    prior_strength: float = 20.0,
    min_gain: float = 0.002,
) -> dict[str, Any]:
    by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_state_h: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        state = str(case["state"])
        by_state[state].append(case)
        for h in horizons:
            if str(h) in case.get("labels", {}):
                by_state_h[(state, h)].append(case)

    path_binning_by_state = {
        state: _build_path_binning(group) for state, group in by_state.items()
    }

    model: dict[str, Any] = {
        "schema_version": 5,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_contract": "S-state defines only the target/question; CCI/BB-midline/HA path tree directly estimates the 4-way outcome.",
        "settlement_contract": "POST_CLOSE_DAILY_ROUTE_V2: 12H observation-only; 24H/48H/72H score only completed UTC daily closes (Taiwan 08:00).",
        "outcome_keys": list(OUTCOME_KEYS),
        "outcome_labels_zh": OUTCOME_LABELS_ZH,
        "default_min_samples": int(min_samples),
        "prior_strength": float(prior_strength),
        "path_min_gain": float(min_gain),
        "horizons_bars": list(horizons),
        "horizon_hours": {str(h): int(h * 4) for h in horizons},
        "primary_swing_horizon_bars": 18,
        "primary_swing_horizon_hours": 72,
        "cci_primary_contract": {
            "version": CCI_PRIMARY_VERSION,
            "role": "PRIMARY probability model. S0.5/S1/S2/S3 only select the target; legacy BB/HA Level 1-5 probability no longer sets the base probability.",
            "source_formula": "TradingView parity: src=hlc3; CCI20=(src-SMA20(src))/(0.015*mean absolute deviation20); smoothingMA=SMA14(CCI).",
            "path_memory": "30 daily points: first/second cross cycle, days since cross, cross location, SMA color at cross, BB midline phase at cross, gap approach/retest/reclaim, divergence, CCI/SMA slopes and acceleration.",
            "tree": "Per-state/per-horizon categorical decision tree using multiclass Gini gain; state-specific quartile cuts are learned from history; unseen/rare branches fall back to the nearest parent node.",
            "min_leaf_samples": int(min_samples),
            "min_gain": float(min_gain),
            "state_max_depth": STATE_MAX_DEPTH,
            "state_candidate_fields": STATE_PATH_FIELDS,
            "quantile_fields": PATH_QUANTILE_FIELDS,
        },
        "states": {},
    }

    for (state, h), group in sorted(by_state_h.items()):
        baseline_node = _stats_node(group, h)
        baseline_probs = {
            key: float((baseline_node.get("outcomes", {}).get(key) or {}).get("probability", 0.0) or 0.0)
            for key in OUTCOME_KEYS
        }
        state_node = model["states"].setdefault(
            state,
            {
                "target": group[0]["target"],
                "path_binning": path_binning_by_state.get(state) or {},
                "horizons": {},
            },
        )
        fields = list(STATE_PATH_FIELDS.get(state) or COMMON_PATH_FIELDS)
        tree = _build_tree(
            group,
            h,
            fields=fields,
            binning=state_node.get("path_binning") or {},
            baseline_probs=baseline_probs,
            min_leaf=max(10, int(min_samples)),
            prior_strength=max(0.0, float(prior_strength)),
            max_depth=int(STATE_MAX_DEPTH.get(state, 5)),
            min_gain=max(0.0, float(min_gain)),
        )
        state_node["horizons"][str(h)] = {
            "baseline": baseline_node,
            "path_tree": tree,
        }

    digest_src = json.dumps(model["states"], ensure_ascii=False, sort_keys=True).encode("utf-8")
    model["model_id"] = hashlib.sha256(digest_src).hexdigest()[:16]
    return model


def lookup_probability(model: dict[str, Any], state: str, horizon: int, features: dict[str, Any]) -> dict[str, Any]:
    state_node = (model.get("states") or {}).get(state)
    if not state_node:
        return {"available": False, "reason": "state_missing"}
    hnode = (state_node.get("horizons") or {}).get(str(horizon))
    if not hnode:
        return {"available": False, "reason": "horizon_missing"}

    enriched = _apply_path_binning(features or {}, state_node.get("path_binning") or {})
    tree = hnode.get("path_tree") or hnode.get("baseline") or {}
    node, path = _walk_tree(tree, enriched)
    payload = _node_outcome_payload(node)
    depth = int(node.get("depth", len(path)) or len(path))
    fields = [item["field"] for item in path]
    signature = "|".join(f"{item['field']}={item['value']}" for item in path) or "STATE_BASELINE"
    primary_meta = {
        "available": bool(path) or bool(tree),
        "version": (model.get("cci_primary_contract") or {}).get("version"),
        "depth": depth,
        "matched_path": path,
        "matched_path_count": len(path),
        "bins": {q_field: enriched.get(q_field) for q_field in PATH_QUANTILE_FIELDS.values()},
        "path_features": {
            key: enriched.get(key)
            for key in (
                "market_type", "midline_path_phase", "cci_zone", "cci_cross_cycle",
                "cci_last_cross_zone", "cci_last_cross_midline_phase", "cci_gap_motion",
                "cci_retest_state", "cci_divergence", "cci_smoothing_direction",
                "cci_smoothing_turn_event", "ha_color",
            )
        },
    }
    # cci_expert is retained only as a compatibility alias for existing Frozen
    # ledger code; it now identifies PRIMARY_PATH instead of a correction layer.
    compatibility = {
        "available": True,
        "version": primary_meta["version"],
        "mode": "PRIMARY_PATH",
        "matched_facets": [],
        "matched_facet_count": 0,
        "blend_strength": 1.0,
        "bins": primary_meta["bins"],
        "matched_path": path,
    }
    return {
        "available": True,
        "probability": float(payload["success_probability"]),
        "raw_probability": float(node.get("raw_probability", payload["success_probability"]) or 0.0),
        "samples": int(node.get("samples", 0) or 0),
        "wins": int(node.get("wins", 0) or 0),
        "level": depth,
        "fields": fields,
        "signature": signature,
        "wilson95": node.get("wilson95"),
        "fallback": len(path) == 0,
        **payload,
        "cci_primary": primary_meta,
        "cci_expert": compatibility,
    }


def _collect_tree_paths(
    node: dict[str, Any],
    path: list[dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    current_path = list(path or [])
    children = node.get("children") or {}
    split_field = node.get("split_field")
    if not children or not split_field:
        return [{
            "path": current_path,
            "depth": int(node.get("depth", len(current_path)) or len(current_path)),
            "samples": int(node.get("samples", 0) or 0),
            "success_probability": float(node.get("probability", 0.0) or 0.0),
            "structural_survival_probability": float(node.get("structural_survival_probability", 0.0) or 0.0),
            "true_fail_probability": float(node.get("true_fail_probability", 0.0) or 0.0),
        }]
    output: list[dict[str, Any]] = []
    for value, child in children.items():
        output.extend(_collect_tree_paths(child, current_path + [{"field": str(split_field), "value": str(value)}]))
    return output


def summarize_path_tree(model: dict[str, Any], horizon: str = "18", top_n: int = 10) -> dict[str, Any]:
    output: dict[str, Any] = {}
    for state, state_node in (model.get("states") or {}).items():
        hnode = (state_node.get("horizons") or {}).get(str(horizon)) or {}
        baseline = hnode.get("baseline") or {}
        baseline_success = float(baseline.get("probability", 0.0) or 0.0)
        baseline_fail = float(baseline.get("true_fail_probability", 0.0) or 0.0)
        tree = hnode.get("path_tree") or {}
        paths = _collect_tree_paths(tree)
        for row in paths:
            row["success_delta_vs_state"] = round(row["success_probability"] - baseline_success, 6)
            row["true_fail_delta_vs_state"] = round(row["true_fail_probability"] - baseline_fail, 6)
            row["direction_score"] = round(
                row["success_delta_vs_state"] - row["true_fail_delta_vs_state"], 6
            )
        output[state] = {
            "baseline_samples": int(baseline.get("samples", 0) or 0),
            "baseline_success_probability": round(baseline_success, 6),
            "baseline_structural_survival_probability": round(float(baseline.get("structural_survival_probability", baseline_success) or baseline_success), 6),
            "baseline_true_fail_probability": round(baseline_fail, 6),
            "root_split_field": tree.get("split_field"),
            "root_gain": tree.get("gain"),
            "leaf_count": len(paths),
            "strongest_positive": sorted(paths, key=lambda x: (-x["direction_score"], -x["samples"]))[:top_n],
            "strongest_negative": sorted(paths, key=lambda x: (x["direction_score"], -x["samples"]))[:top_n],
            "path_binning": state_node.get("path_binning") or {},
        }
    return output


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

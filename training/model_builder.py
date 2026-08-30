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

# Existing BB / HA / S-state hierarchy remains untouched for backward compatibility.
FEATURE_LEVELS = [
    [],
    ["midline_state"],
    ["midline_state", "bandpos_bin"],
    ["midline_state", "bandpos_bin", "trigger_stage"],
    ["midline_state", "bandpos_bin", "trigger_stage", "bandwidth_trend"],
    ["midline_state", "bandpos_bin", "trigger_stage", "bandwidth_trend", "state_age_bin"],
]

DMI_EXPERT_VERSION = "DMI-EXPERT-v2-ADX-STEP"
DMI_QUANTILE_FIELDS = {
    "di_abs_gap": "di_abs_gap_q",
    "di_axis_distance": "di_axis_distance_q",
    "di_plus_slope_3d": "di_plus_slope_q",
    "di_minus_slope_3d": "di_minus_slope_q",
    "di_gap_slope_3d": "di_gap_slope_q",
    "adx": "adx_q",
    "adx_slope_3d": "adx_slope_q",
}

# DMI is deliberately a separate correction layer instead of Level 6/7/8...
# This keeps sample sizes healthy and lets the learner discover several kinds of
# DMI evidence independently: who leads/where relative to 20, recent crossover
# motion, line convergence/divergence, and ADX trend strength.
DMI_EXPERT_FACETS = [
    {
        "name": "lead_axis",
        "fields": ["dmi_relation", "dmi_axis_zone", "di_axis_distance_q"],
    },
    {
        "name": "cross_momentum",
        "fields": ["dmi_relation", "dmi_cross_age_bin", "di_gap_slope_q"],
    },
    {
        "name": "line_motion",
        "fields": ["dmi_relation", "di_plus_slope_q", "di_minus_slope_q"],
    },
    {
        "name": "trend_strength",
        "fields": ["dmi_relation", "di_abs_gap_q", "adx_q", "adx_slope_q"],
    },
    # v2 ADX Step Regime: model the exact red/green stepline language used in
    # SStateMarketTerminal. These remain independent facets so S0.5/S1/S2/S3
    # can learn different meanings without exploding the Level 1-5 hierarchy.
    {
        "name": "adx_step_regime",
        "fields": ["dmi_adx_regime", "adx_axis_zone"],
    },
    {
        "name": "adx_step_persistence",
        "fields": ["dmi_adx_regime", "adx_step_age_bin"],
    },
    {
        "name": "adx_turn_handover",
        "fields": ["dmi_relation", "dmi_cross_age_bin", "adx_turn_event"],
    },
]

ADX_STEP_FACET_NAMES = {"adx_step_regime", "adx_step_persistence", "adx_turn_handover"}


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
    # it into the newer builder manually.
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
        # Backward-compatible binary fields used by the current live reader.
        "wins": wins,
        "raw_probability": round(raw_success, 6),
        "probability": round(success_prob, 6),
        "wilson95": [round(low, 6), round(high, 6)],
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


def _build_dmi_binning(group: list[dict[str, Any]]) -> dict[str, Any]:
    """Learn state-specific tercile cuts from raw DMI values.

    No bullish/bearish threshold is hard-coded here.  The only fixed reference
    is the indicator's own 20 axis, already represented by dmi_axis_zone.
    Magnitude/slope/ADX buckets are learned from the historical distribution.
    """
    output: dict[str, Any] = {}
    for raw_field, q_field in DMI_QUANTILE_FIELDS.items():
        values = []
        for case in group:
            value = _safe_float((case.get("features") or {}).get(raw_field))
            if value is not None:
                values.append(value)
        q33 = _quantile(values, 1.0 / 3.0)
        q67 = _quantile(values, 2.0 / 3.0)
        output[raw_field] = {
            "derived_field": q_field,
            "q33": round(q33, 8),
            "q67": round(q67, 8),
            "samples": len(values),
        }
    return output


def _apply_dmi_binning(features: dict[str, Any], binning: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(features)
    for raw_field, q_field in DMI_QUANTILE_FIELDS.items():
        value = _safe_float(features.get(raw_field))
        node = binning.get(raw_field) or {}
        q33 = _safe_float(node.get("q33"))
        q67 = _safe_float(node.get("q67"))
        if value is None or q33 is None or q67 is None:
            enriched[q_field] = "UNKNOWN"
        elif value <= q33:
            enriched[q_field] = "LOW"
        elif value <= q67:
            enriched[q_field] = "MID"
        else:
            enriched[q_field] = "HIGH"
    return enriched


def _outcome_probs(node: dict[str, Any], *, raw: bool = False) -> dict[str, float]:
    outcomes = node.get("outcomes") or {}
    field = "raw_probability" if raw else "probability"
    values: dict[str, float] = {}
    for key in OUTCOME_KEYS:
        item = outcomes.get(key) or {}
        value = _safe_float(item.get(field))
        if value is None and raw:
            value = _safe_float(item.get("probability"))
        values[key] = max(0.0, float(value or 0.0))
    total = sum(values.values())
    if total <= 0:
        # Old binary model fallback.
        success = max(0.0, min(1.0, float(node.get("probability", 0.0) or 0.0)))
        return {
            OUTCOME_SUCCESS: success,
            OUTCOME_ALIVE: 0.0,
            OUTCOME_FAIL: 0.0,
            OUTCOME_OTHER: 1.0 - success,
        }
    return {key: value / total for key, value in values.items()}


def _find_rule(rules: list[dict[str, Any]], signature: str, min_samples: int) -> dict[str, Any] | None:
    for rule in rules:
        if rule.get("signature") == signature and int(rule.get("samples", 0)) >= min_samples:
            return rule
    return None


def _lookup_base_rule(
    hnode: dict[str, Any],
    features: dict[str, Any],
    min_samples: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    for level in reversed(hnode.get("levels", [])):
        fields = list(level.get("fields") or [])
        sig = _signature(features, fields)
        rule = _find_rule(list(level.get("rules") or []), sig, min_samples)
        if rule is not None:
            return rule, {
                "level": int(level.get("level", 0)),
                "fields": fields,
                "signature": sig,
                "fallback": False,
            }
    return hnode["baseline"], {
        "level": 0,
        "fields": [],
        "signature": "BASELINE",
        "fallback": True,
    }


def _lookup_dmi_facets(
    state_node: dict[str, Any],
    hnode: dict[str, Any],
    features: dict[str, Any],
    min_samples: int,
) -> list[dict[str, Any]]:
    expert = hnode.get("dmi_expert") or {}
    if not expert:
        return []
    enriched = _apply_dmi_binning(features, state_node.get("dmi_binning") or {})
    matches: list[dict[str, Any]] = []
    for facet in expert.get("facets") or []:
        fields = list(facet.get("fields") or [])
        sig = _signature(enriched, fields)
        rule = _find_rule(list(facet.get("rules") or []), sig, min_samples)
        if rule is None:
            continue
        matches.append({
            "name": str(facet.get("name") or "facet"),
            "fields": fields,
            "signature": sig,
            "rule": rule,
        })
    return matches


def _combine_with_dmi(
    base_node: dict[str, Any],
    baseline_node: dict[str, Any],
    dmi_matches: list[dict[str, Any]],
    *,
    prior_strength: float,
    raw: bool = False,
) -> tuple[dict[str, float], float, list[dict[str, Any]]]:
    base_probs = _outcome_probs(base_node, raw=raw)
    if not dmi_matches:
        return base_probs, 0.0, []

    baseline_probs = _outcome_probs(baseline_node, raw=raw)
    eps = 1e-9
    weighted_logs = {key: 0.0 for key in OUTCOME_KEYS}
    weights: list[float] = []
    audit: list[dict[str, Any]] = []

    for match in dmi_matches:
        rule = match["rule"]
        n = int(rule.get("samples", 0))
        reliability = n / (n + max(1.0, float(prior_strength)))
        weights.append(reliability)
        facet_probs = _outcome_probs(rule, raw=raw)
        for key in OUTCOME_KEYS:
            ratio = max(eps, facet_probs[key]) / max(eps, baseline_probs[key])
            weighted_logs[key] += reliability * math.log(ratio)
        audit.append({
            "name": match["name"],
            "fields": match["fields"],
            "signature": match["signature"],
            "samples": n,
            "reliability": round(reliability, 6),
            "success_probability": round(facet_probs[OUTCOME_SUCCESS], 6),
            "structural_survival_probability": round(facet_probs[OUTCOME_SUCCESS] + facet_probs[OUTCOME_ALIVE], 6),
            "true_fail_probability": round(facet_probs[OUTCOME_FAIL], 6),
        })

    weight_sum = sum(weights)
    if weight_sum <= 0:
        return base_probs, 0.0, audit

    # Facets overlap, so do not multiply all likelihood ratios at full strength.
    # Use their reliability-weighted geometric mean, then let the average
    # reliability control how strongly DMI can move the original BB/HA model.
    blend_strength = min(1.0, weight_sum / len(weights))
    logs: dict[str, float] = {}
    for key in OUTCOME_KEYS:
        avg_log_ratio = weighted_logs[key] / weight_sum
        logs[key] = math.log(max(eps, base_probs[key])) + blend_strength * avg_log_ratio

    peak = max(logs.values())
    exp_values = {key: math.exp(value - peak) for key, value in logs.items()}
    total = sum(exp_values.values())
    combined = {key: exp_values[key] / total for key in OUTCOME_KEYS}
    return combined, blend_strength, audit


def _prediction_payload(
    base_node: dict[str, Any],
    base_meta: dict[str, Any],
    baseline_node: dict[str, Any],
    dmi_matches: list[dict[str, Any]],
    *,
    prior_strength: float,
) -> dict[str, Any]:
    combined, blend_strength, audit = _combine_with_dmi(
        base_node,
        baseline_node,
        dmi_matches,
        prior_strength=prior_strength,
        raw=False,
    )
    raw_combined, _, _ = _combine_with_dmi(
        base_node,
        baseline_node,
        dmi_matches,
        prior_strength=prior_strength,
        raw=True,
    )

    outcome_payload = {
        key: {
            "label_zh": OUTCOME_LABELS_ZH[key],
            "probability": round(combined[key], 6),
            "raw_probability": round(raw_combined[key], 6),
        }
        for key in OUTCOME_KEYS
    }
    success = combined[OUTCOME_SUCCESS]
    survival = combined[OUTCOME_SUCCESS] + combined[OUTCOME_ALIVE]

    return {
        "available": True,
        "probability": float(success),
        "raw_probability": float(raw_combined[OUTCOME_SUCCESS]),
        "samples": int(base_node.get("samples", 0)),
        "wins": int(base_node.get("wins", 0)),
        "level": int(base_meta["level"]),
        "fields": list(base_meta["fields"]),
        "signature": str(base_meta["signature"]),
        "wilson95": base_node.get("wilson95"),
        "fallback": bool(base_meta.get("fallback", False)),
        "outcomes": outcome_payload,
        "structural_survival_probability": float(survival),
        "true_fail_probability": float(combined[OUTCOME_FAIL]),
        "other_probability": float(combined[OUTCOME_OTHER]),
        "late_success_4_7d": base_node.get("late_success_4_7d"),
        "dmi_expert": {
            "available": bool(dmi_matches),
            "version": DMI_EXPERT_VERSION,
            "matched_facets": audit,
            "matched_facet_count": len(audit),
            "blend_strength": round(blend_strength, 6),
        },
    }


def build_model(
    cases: list[dict[str, Any]],
    horizons: tuple[int, ...],
    min_samples: int = 50,
    prior_strength: float = 20.0,
) -> dict[str, Any]:
    by_state: dict[str, list[dict[str, Any]]] = defaultdict(list)
    by_state_h: dict[tuple[str, int], list[dict[str, Any]]] = defaultdict(list)
    for case in cases:
        state = str(case["state"])
        by_state[state].append(case)
        for h in horizons:
            if str(h) in case.get("labels", {}):
                by_state_h[(state, h)].append(case)

    dmi_binning_by_state = {
        state: _build_dmi_binning(group)
        for state, group in by_state.items()
    }

    model: dict[str, Any] = {
        "schema_version": 3,
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
        "dmi_expert_contract": {
            "version": DMI_EXPERT_VERSION,
            "role": "Independent DMI evidence corrects the existing BB/HA/S-state probability; it never changes the S-state itself.",
            "source_formula": "Pine-equivalent period14 recursive TR/DM smoothing; DI+/DI-; DX; ADX=SMA14(DX)",
            "axis": 20,
            "binning": "Per-state terciles learned from historical raw DMI values; no fixed bullish/bearish magnitude threshold.",
            "adx_step_definition": "Terminal parity: ADX > previous daily ADX = RISING/green; ADX < previous daily ADX = FALLING/red; equal = FLAT. The current daily candle may be partial at a 4H replay cutoff, never future-complete.",
            "adx_step_semantics": "DI controller and ADX step direction are learned jointly per S-state. Green/red is not hard-coded bullish/bearish; PLUS_RISING, PLUS_FALLING, MINUS_RISING and MINUS_FALLING may have different outcomes in S0.5/S1/S2/S3.",
            "facets": DMI_EXPERT_FACETS,
            "adx_step_facets": sorted(ADX_STEP_FACET_NAMES),
            "combiner": "Reliability-weighted geometric mean of facet likelihood ratios relative to the state baseline, applied as a conservative correction to the legacy BB/HA rule.",
        },
        "states": {},
    }

    for (state, h), group in sorted(by_state_h.items()):
        baseline_node = _stats_node(group, h)
        baseline_probs = {
            key: float((baseline_node["outcomes"].get(key) or {}).get("probability", 0.0))
            for key in OUTCOME_KEYS
        }
        state_node = model["states"].setdefault(
            state,
            {
                "target": group[0]["target"],
                "dmi_binning": dmi_binning_by_state.get(state) or {},
                "horizons": {},
            },
        )
        horizon_node: dict[str, Any] = {
            "baseline": baseline_node,
            "levels": [],
            "dmi_expert": {
                "version": DMI_EXPERT_VERSION,
                "facets": [],
            },
        }

        # Existing structural hierarchy: unchanged Level 1-5 behavior.
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
                node.update({
                    "signature": sig,
                    "eligible": int(node["samples"]) >= min_samples,
                })
                rules.append(node)
            rules.sort(key=lambda r: (-int(r["samples"]), r["signature"]))
            horizon_node["levels"].append({"level": level_idx, "fields": fields, "rules": rules})

        # DMI expert facets are intentionally independent, not cumulative levels.
        binning = state_node.get("dmi_binning") or {}
        for facet in DMI_EXPERT_FACETS:
            fields = list(facet["fields"])
            buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for case in group:
                enriched = _apply_dmi_binning(case.get("features") or {}, binning)
                buckets[_signature(enriched, fields)].append(case)
            rules = []
            for sig, bucket in buckets.items():
                node = _stats_node(
                    bucket,
                    h,
                    baseline_probs=baseline_probs,
                    prior_strength=prior_strength,
                )
                node.update({
                    "signature": sig,
                    "eligible": int(node["samples"]) >= min_samples,
                })
                rules.append(node)
            rules.sort(key=lambda r: (-int(r["samples"]), r["signature"]))
            horizon_node["dmi_expert"]["facets"].append({
                "name": facet["name"],
                "fields": fields,
                "rules": rules,
            })

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
    base_node, base_meta = _lookup_base_rule(hnode, features, min_samples)

    # Schema v1/v2 and any model without DMI remain exactly backward-compatible.
    dmi_matches = _lookup_dmi_facets(state_node, hnode, features, min_samples)
    if not dmi_matches:
        return {
            "available": True,
            "probability": float(base_node["probability"]),
            "raw_probability": float(base_node["raw_probability"]),
            "samples": int(base_node["samples"]),
            "wins": int(base_node["wins"]),
            "level": int(base_meta["level"]),
            "fields": list(base_meta["fields"]),
            "signature": str(base_meta["signature"]),
            "wilson95": base_node.get("wilson95"),
            "fallback": bool(base_meta.get("fallback", False)),
            "outcomes": base_node.get("outcomes") or {},
            "structural_survival_probability": float(base_node.get("structural_survival_probability", base_node["probability"])),
            "true_fail_probability": float(base_node.get("true_fail_probability", 0.0)),
            "other_probability": float(base_node.get("other_probability", 0.0)),
            "late_success_4_7d": base_node.get("late_success_4_7d"),
            "dmi_expert": {
                "available": False,
                "version": (model.get("dmi_expert_contract") or {}).get("version"),
                "matched_facets": [],
                "matched_facet_count": 0,
                "blend_strength": 0.0,
            },
        }

    return _prediction_payload(
        base_node,
        base_meta,
        hnode["baseline"],
        dmi_matches,
        prior_strength=float(model.get("prior_strength", 20.0)),
    )


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

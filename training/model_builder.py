from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine_contract": "S-state rules fixed; probability parameters evolve in JSON",
        "default_min_samples": int(min_samples),
        "prior_strength": float(prior_strength),
        "horizons_bars": list(horizons),
        "horizon_hours": {str(h): int(h * 4) for h in horizons},
        "states": {},
    }

    for (state, h), group in sorted(by_state_h.items()):
        wins = sum(1 for c in group if bool(c["labels"][str(h)]["hit"]))
        n = len(group)
        baseline = wins / n if n else 0.0
        low, high = _wilson(wins, n)
        state_node = model["states"].setdefault(state, {"target": group[0]["target"], "horizons": {}})
        horizon_node: dict[str, Any] = {
            "baseline": {
                "samples": n,
                "wins": wins,
                "raw_probability": round(baseline, 6),
                "probability": round(baseline, 6),
                "wilson95": [round(low, 6), round(high, 6)],
            },
            "levels": [],
        }

        for level_idx, fields in enumerate(FEATURE_LEVELS[1:], start=1):
            buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for case in group:
                buckets[_signature(case["features"], fields)].append(case)
            rules = []
            for sig, bucket in buckets.items():
                bn = len(bucket)
                bw = sum(1 for c in bucket if bool(c["labels"][str(h)]["hit"]))
                raw = bw / bn if bn else 0.0
                # Empirical-Bayes shrinkage toward the state baseline.
                prob = (bw + baseline * prior_strength) / (bn + prior_strength) if bn else baseline
                lo, hi = _wilson(bw, bn)
                rules.append(
                    {
                        "signature": sig,
                        "samples": bn,
                        "wins": bw,
                        "raw_probability": round(raw, 6),
                        "probability": round(prob, 6),
                        "wilson95": [round(lo, 6), round(hi, 6)],
                        "eligible": bn >= min_samples,
                    }
                )
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
    }


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

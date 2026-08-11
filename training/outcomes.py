from __future__ import annotations

"""Settlement outcome classifier for the historical S-state learner.

Important contract:
- scoring_rules.py remains the source of truth for S-state generation.
- This module does *not* alter an S-state. It only classifies what happened
  after a historical decision point.
- SUCCESS has priority: if the requested target was reached inside the horizon,
  the case is a success even if price later pulled back.
- TRUE_FAIL is intentionally conservative and uses the existing engine's hard
  structural invalidation floors rather than inventing new % stop rules.
"""

from typing import Any, Iterable

from engine.scoring_rules import BREAKOUT_INVALIDATE_BANDPOS, S2_ACTIVE_MAX_BANDPOS, S2_BREAKDOWN_FLOOR_BANDPOS

OUTCOME_SUCCESS = "SUCCESS_WITHIN_HORIZON"
OUTCOME_ALIVE = "ALIVE_SLOW"
OUTCOME_FAIL = "TRUE_FAIL"
OUTCOME_OTHER = "OTHER"
OUTCOME_KEYS = (OUTCOME_SUCCESS, OUTCOME_ALIVE, OUTCOME_FAIL, OUTCOME_OTHER)

OUTCOME_LABELS_ZH = {
    OUTCOME_SUCCESS: "期限內成功",
    OUTCOME_ALIVE: "還活著只是慢",
    OUTCOME_FAIL: "真失敗",
    OUTCOME_OTHER: "其他",
}


def hard_failure_floor(source_state: str) -> float:
    """Return the engine-native structural invalidation floor for this family."""
    if source_state in {"S2", "S3"}:
        return float(S2_BREAKDOWN_FLOOR_BANDPOS)
    if source_state in {"S0.5", "S1"}:
        return float(BREAKOUT_INVALIDATE_BANDPOS)
    return 0.0


def _valid_snapshots(items: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [x for x in items if isinstance(x, dict)]


def classify_outcome(
    source_state: str,
    future_snapshots: Iterable[dict[str, Any] | None],
    *,
    target_hit: bool,
) -> dict[str, Any]:
    """Classify one horizon into SUCCESS / ALIVE_SLOW / TRUE_FAIL / OTHER.

    ALIVE_SLOW means the target was not reached, but the source structure has
    not hit the engine's hard invalidation floor and the end of the horizon is
    still in a recoverable geometry for that S-state family.

    OTHER is deliberately retained for ambiguous/regressed paths that are not
    hard-invalidated but can no longer be called the same living setup with
    confidence. This prevents "not failed" from being mislabeled as "alive".
    """
    future = _valid_snapshots(future_snapshots)
    if target_hit:
        return {
            "outcome": OUTCOME_SUCCESS,
            "hard_invalidated": False,
            "failure_floor": hard_failure_floor(source_state),
        }
    if not future:
        return {
            "outcome": OUTCOME_OTHER,
            "hard_invalidated": False,
            "failure_floor": hard_failure_floor(source_state),
            "reason": "no_future_snapshot",
        }

    floor = hard_failure_floor(source_state)
    bandposes = [float(x.get("bandpos", 0.5) or 0.5) for x in future]
    min_bandpos = min(bandposes)
    end = future[-1]
    end_state = str(end.get("state") or "OTHER")
    end_bandpos = float(end.get("bandpos", 0.5) or 0.5)

    hard_invalidated = bool(min_bandpos < floor)
    if hard_invalidated:
        return {
            "outcome": OUTCOME_FAIL,
            "hard_invalidated": True,
            "failure_floor": floor,
            "min_bandpos": round(min_bandpos, 8),
            "end_state": end_state,
            "end_bandpos": round(end_bandpos, 8),
            "reason": "engine_hard_invalidation_floor_broken",
        }

    alive = False
    if source_state == "S0.5":
        # Still below/around the midline without breaking the breakout-cycle
        # invalidation floor. S0 is allowed: the base can remain alive but slow.
        alive = end_state in {"S0", "S0.5"} or (end_state == "OTHER" and floor <= end_bandpos < 0.5)
    elif source_state == "S1":
        # Still on the above-midline first-wave side. A mature OTHER print can be
        # recoverable as long as it has not broken back below the midline.
        alive = end_state in {"S1", "S2", "S3"} or (end_state == "OTHER" and end_bandpos >= 0.5)
    elif source_state in {"S2", "S3"}:
        # S3 -> S2 is a normal regression/retest, not automatically a true fail.
        # OTHER is allowed only while the original wave generation remains above
        # the engine's 0.38 hard breakdown floor.
        alive = end_state in {"S2", "S3"} or (end_state == "OTHER" and floor <= end_bandpos <= float(S2_ACTIVE_MAX_BANDPOS))

    if alive:
        return {
            "outcome": OUTCOME_ALIVE,
            "hard_invalidated": False,
            "failure_floor": floor,
            "min_bandpos": round(min_bandpos, 8),
            "end_state": end_state,
            "end_bandpos": round(end_bandpos, 8),
            "reason": "target_not_hit_but_structure_still_recoverable",
        }

    return {
        "outcome": OUTCOME_OTHER,
        "hard_invalidated": False,
        "failure_floor": floor,
        "min_bandpos": round(min_bandpos, 8),
        "end_state": end_state,
        "end_bandpos": round(end_bandpos, 8),
        "reason": "left_expected_path_without_hard_invalidation",
    }

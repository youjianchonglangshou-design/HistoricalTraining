from __future__ import annotations

"""Settlement outcome classifier for the S-state learner.

Two contracts exist:
1. ``classify_outcome`` is the generic structural classifier.
2. ``build_confirmed_close_label`` is the production Champion contract from
   v3.6 onward: only completed Taiwan 08:00 / UTC 00:00 daily checkpoints can
   confirm a target. Intraday 4H partial-daily states are never allowed to turn
   a Frozen prediction into SUCCESS.
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
    if source_state in {"S2", "S3"}:
        return float(S2_BREAKDOWN_FLOOR_BANDPOS)
    if source_state in {"S0.5", "S1"}:
        return float(BREAKOUT_INVALIDATE_BANDPOS)
    return 0.0


def _valid_snapshots(items: Iterable[dict[str, Any] | None]) -> list[dict[str, Any]]:
    return [x for x in items if isinstance(x, dict)]


def confirmed_close_target_hit(source_state: str, future_state: str, future_bandpos: float) -> bool:
    """Return whether one *completed daily close* confirms the original target."""
    if source_state == "S0.5":
        return future_state in {"S1", "S2", "S3"}
    if source_state == "S2":
        return future_state == "S3"
    if source_state == "S1":
        return future_bandpos > 0.75
    if source_state == "S3":
        # A partial intraday yellow print is never enough. S3 continuation must
        # still be S3 at the completed daily checkpoint and have expanded past
        # the existing BANDPOS_GT_075 target.
        return future_state == "S3" and future_bandpos > 0.75
    return False


def classify_outcome(
    source_state: str,
    future_snapshots: Iterable[dict[str, Any] | None],
    *,
    target_hit: bool,
) -> dict[str, Any]:
    """Generic SUCCESS / ALIVE_SLOW / TRUE_FAIL / OTHER structural classifier."""
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
        alive = end_state in {"S0", "S0.5"} or (end_state == "OTHER" and floor <= end_bandpos < 0.5)
    elif source_state == "S1":
        alive = end_state in {"S1", "S2", "S3"} or (end_state == "OTHER" and end_bandpos >= 0.5)
    elif source_state in {"S2", "S3"}:
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


def build_confirmed_close_label(
    source_state: str,
    future_snapshots: Iterable[dict[str, Any] | None],
    *,
    entry_price: float = 0.0,
) -> dict[str, Any]:
    """Build one horizon label using only completed daily checkpoints.

    ``future_snapshots`` must be chronological, one item per completed daily
    close. This function deliberately ignores all 4H states between closes.
    """
    future = _valid_snapshots(future_snapshots)
    state_path = [source_state]
    max_bandpos = None
    max_return = 0.0
    min_return = 0.0
    hit_day = None
    hit_index = None

    for idx, snap in enumerate(future, start=1):
        state = str(snap.get("state") or "OTHER")
        bandpos = float(snap.get("bandpos", 0.5) or 0.5)
        price = float(snap.get("price", 0.0) or 0.0)
        if state and state != state_path[-1]:
            state_path.append(state)
        max_bandpos = bandpos if max_bandpos is None else max(max_bandpos, bandpos)
        if entry_price and price:
            ret = price / float(entry_price) - 1.0
            max_return = max(max_return, ret)
            min_return = min(min_return, ret)
        if hit_day is None and confirmed_close_target_hit(source_state, state, bandpos):
            hit_day = idx
            hit_index = idx - 1

    # S3 is a continuation setup. If the first completed daily close that
    # matters has already regressed from S3 before any confirmed target hit,
    # the original continuation call failed. This is intentionally stricter
    # than the generic structural classifier.
    if source_state == "S3" and future:
        regression_index = next((i for i, snap in enumerate(future) if str(snap.get("state") or "OTHER") != "S3"), None)
        if regression_index is not None and (hit_index is None or regression_index <= hit_index):
            end = future[-1]
            return {
                "outcome": OUTCOME_FAIL,
                "hit": False,
                "days_to_hit": None,
                "bars_to_hit": None,
                "max_bandpos": round(max_bandpos if max_bandpos is not None else 0.0, 8),
                "max_return": round(max_return, 8),
                "max_drawdown": round(min_return, 8),
                "state_path": state_path,
                "hard_invalidated": True,
                "failure_floor": hard_failure_floor(source_state),
                "end_state": str(end.get("state") or "OTHER"),
                "end_bandpos": round(float(end.get("bandpos", 0.5) or 0.5), 8),
                "reason": "s3_lost_on_confirmed_daily_close",
            }

    outcome = classify_outcome(source_state, future, target_hit=hit_day is not None)
    end = future[-1] if future else {}
    return {
        "hit": hit_day is not None,
        "days_to_hit": hit_day,
        "bars_to_hit": (hit_day * 6) if hit_day is not None else None,
        "max_bandpos": round(max_bandpos if max_bandpos is not None else 0.0, 8),
        "max_return": round(max_return, 8),
        "max_drawdown": round(min_return, 8),
        "state_path": state_path,
        "end_state": str(end.get("state") or "OTHER") if future else None,
        "end_bandpos": round(float(end.get("bandpos", 0.5) or 0.5), 8) if future else None,
        **outcome,
    }

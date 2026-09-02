from __future__ import annotations

"""Settlement outcome classifier for the S-state learner.

Production contract (v3.6.3):
- Only completed Taiwan 08:00 / UTC 00:00 daily checkpoints can score a Frozen exam.
- The Terminal S-state is an *entry-opportunity scanner*, not a monotonic trend-state enum.
  S1 and S3 intentionally disappear to OTHER after price expands too far to chase.
- Therefore settlement must judge the structural route, not blindly treat ``state != source``
  as failure.
"""

from typing import Any, Iterable

from engine.scoring_rules import (
    BREAKOUT_INVALIDATE_BANDPOS,
    S1_ACTIVE_MAX_BANDPOS,
    S2_ACTIVE_MAX_BANDPOS,
    S2_BREAKDOWN_FLOOR_BANDPOS,
    S3_ACTIVE_MAX_BANDPOS,
)

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


def _snapshot(value: dict[str, Any] | str, bandpos: float | None = None) -> dict[str, Any]:
    """Normalize the old (state, bandpos) call shape and the route-aware dict shape."""
    if isinstance(value, dict):
        return value
    return {"state": str(value or "OTHER"), "bandpos": 0.5 if bandpos is None else float(bandpos)}


def _state(snap: dict[str, Any]) -> str:
    return str(snap.get("state") or "OTHER")


def _bandpos(snap: dict[str, Any]) -> float:
    try:
        return float(snap.get("bandpos", 0.5) or 0.5)
    except (TypeError, ValueError):
        return 0.5


def _route_flag(snap: dict[str, Any], key: str) -> bool:
    return bool(snap.get(key, False))


def confirmed_close_target_hit(
    source_state: str,
    future_snapshot: dict[str, Any] | str,
    future_bandpos: float | None = None,
) -> bool:
    """Whether one *completed daily close* confirms the original target.

    Important: S1/S3 are entry-window labels. Once an up-move becomes mature, the
    Terminal deliberately emits OTHER rather than S1/S3. That upward expiry is a
    success for settlement, not a failure.
    """
    snap = _snapshot(future_snapshot, future_bandpos)
    state = _state(snap)
    bandpos = _bandpos(snap)
    ha_color = str(snap.get("ha_color") or "").lower()
    trigger_stage = str(snap.get("trigger_stage") or "")
    s1_expanded = _route_flag(snap, "s1_expanded")
    s3_expanded = _route_flag(snap, "s3_expanded")

    if source_state == "S0.5":
        # Goal = enter S1 or a later upward stage. If S1 already ran beyond the
        # active entry window, Terminal may report OTHER; that still counts.
        return (
            state in {"S1", "S2", "S3"}
            or s1_expanded
            or s3_expanded
            or (ha_color == "yellow" and bandpos > float(S1_ACTIVE_MAX_BANDPOS))
        )

    if source_state == "S1":
        # Existing model target remains BANDPOS_GT_075. State label is irrelevant
        # once price has expanded beyond the S1 entry window.
        return bandpos > 0.75 or s1_expanded or s3_expanded

    if source_state == "S2":
        # Goal = S3. A strong third-wave launch may immediately expire to OTHER
        # because S3 itself is only displayed while bandpos <= 0.75.
        return (
            state == "S3"
            or s3_expanded
            or (
                state == "OTHER"
                and ha_color == "yellow"
                and trigger_stage == "T2"
                and bandpos > float(S3_ACTIVE_MAX_BANDPOS)
            )
        )

    if source_state == "S3":
        # Existing target = BANDPOS_GT_075. By engine design S3 disappears when
        # bandpos > 0.75, so requiring future_state == S3 here would make SUCCESS
        # logically impossible. S2 regression is explicitly not a success.
        if state == "S2":
            return False
        return bandpos > 0.75 or s3_expanded

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
    bandposes = [_bandpos(x) for x in future]
    min_bandpos = min(bandposes)
    end = future[-1]
    end_state = _state(end)
    end_bandpos = _bandpos(end)

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

    if source_state == "S3" and end_state == "S2":
        return {
            "outcome": OUTCOME_FAIL,
            "hard_invalidated": False,
            "route_invalidated": True,
            "failure_floor": floor,
            "min_bandpos": round(min_bandpos, 8),
            "end_state": end_state,
            "end_bandpos": round(end_bandpos, 8),
            "reason": "s3_regressed_to_s2_on_confirmed_daily_close",
        }

    alive = False
    if source_state == "S0.5":
        alive = end_state in {"S0", "S0.5"} or (end_state == "OTHER" and floor <= end_bandpos < 0.5)
    elif source_state == "S1":
        alive = end_state in {"S1", "S2", "S3"} or (end_state == "OTHER" and end_bandpos >= 0.5)
    elif source_state == "S2":
        alive = end_state in {"S2", "S3"} or (
            end_state == "OTHER" and floor <= end_bandpos <= float(S2_ACTIVE_MAX_BANDPOS)
        )
    elif source_state == "S3":
        # User contract: S3 -> S2 is a failed continuation. Remaining S3 is alive;
        # upward OTHER is already caught as SUCCESS above.
        alive = end_state == "S3"

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
    """Build one horizon label using only completed daily checkpoints."""
    future = _valid_snapshots(future_snapshots)
    state_path = [source_state]
    max_bandpos = None
    max_return = 0.0
    min_return = 0.0
    hit_day = None
    hit_index = None

    for idx, snap in enumerate(future, start=1):
        state = _state(snap)
        bandpos = _bandpos(snap)
        price = float(snap.get("price", 0.0) or 0.0)
        if state and state != state_path[-1]:
            state_path.append(state)
        max_bandpos = bandpos if max_bandpos is None else max(max_bandpos, bandpos)
        if entry_price and price:
            ret = price / float(entry_price) - 1.0
            max_return = max(max_return, ret)
            min_return = min(min_return, ret)
        if hit_day is None and confirmed_close_target_hit(source_state, snap):
            hit_day = idx
            hit_index = idx - 1

    # Explicit continuation contract requested by the user:
    # S3 -> S2 on a confirmed daily close means the S3 continuation call failed.
    # Crucially, OTHER is NOT an automatic failure because a strong upward S3
    # intentionally becomes OTHER once it has moved too far to chase.
    if source_state == "S3" and future:
        regression_index = next(
            (i for i, snap in enumerate(future) if _state(snap) == "S2"),
            None,
        )
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
                "hard_invalidated": False,
                "route_invalidated": True,
                "failure_floor": hard_failure_floor(source_state),
                "end_state": _state(end),
                "end_bandpos": round(_bandpos(end), 8),
                "reason": "s3_regressed_to_s2_on_confirmed_daily_close",
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
        "end_state": _state(end) if future else None,
        "end_bandpos": round(_bandpos(end), 8) if future else None,
        **outcome,
    }

from __future__ import annotations

"""Integration example for Crypto Monitor / future HTML.

The existing `probability` field remains the success-within-horizon probability.
Schema v2 additionally returns the 4-way outcome distribution and structural
survival probability.
"""

import json
from pathlib import Path
from typing import Any

from training.model_builder import lookup_probability


def load_model(path: str | Path = "models/probability_model.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def predict_probability(
    model: dict[str, Any],
    state: str,
    features: dict[str, Any],
    horizon_bars: int = 18,
) -> dict[str, Any]:
    """Return success probability + v2 outcome decomposition when available."""
    return lookup_probability(model, state=state, horizon=horizon_bars, features=features)

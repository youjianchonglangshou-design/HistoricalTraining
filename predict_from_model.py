from __future__ import annotations

"""Small integration example for the future crypto-monitor repo.

The live monitor should keep scoring_rules.py as the source of truth for S-state,
extract the same features, then ask this JSON model for probability.
"""

import json
from pathlib import Path
from typing import Any

from training.model_builder import lookup_probability


def load_model(path: str | Path = "models/probability_model.json") -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def predict_probability(model: dict[str, Any], state: str, features: dict[str, Any], horizon_bars: int = 6) -> dict[str, Any]:
    return lookup_probability(model, state=state, horizon=horizon_bars, features=features)

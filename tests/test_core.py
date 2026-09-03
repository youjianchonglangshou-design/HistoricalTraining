import math
import unittest

from engine.runtime_core import (
    aggregate_4h_to_daily,
    build_live_compatible_record,
    calculate_cci_sma,
)
from engine.scoring_rules import build_long_opportunity
from training.features import extract_features
from training.model_builder import build_model, lookup_probability
from training.outcomes import (
    OUTCOME_ALIVE,
    OUTCOME_FAIL,
    OUTCOME_KEYS,
    OUTCOME_OTHER,
    OUTCOME_SUCCESS,
    build_confirmed_close_label,
    classify_outcome,
    confirmed_close_target_hit,
)
from training.replay import DEFAULT_HORIZONS, replay_symbol


class CoreTests(unittest.TestCase):
    def synthetic_rows(self, count=900):
        rows = []
        base = 1704067200000
        price = 100.0
        for i in range(count):
            drift = 0.0012 if (i // 60) % 2 == 0 else -0.0007
            wiggle = ((i % 9) - 4) * 0.00035
            o = price
            c = max(1.0, o * (1 + drift + wiggle))
            h = max(o, c) * 1.003
            l = min(o, c) * 0.997
            rows.append({
                "time": base + i * 4 * 3600 * 1000,
                "open": o, "high": h, "low": l, "close": c, "volume": 1000 + i,
            })
            price = c
        return rows

    def test_daily_aggregation(self):
        rows = self.synthetic_rows(12)
        daily = aggregate_4h_to_daily(rows)
        self.assertEqual(len(daily), 2)
        self.assertEqual(daily[0]["open"], rows[0]["open"])
        self.assertEqual(daily[0]["close"], rows[5]["close"])

    def test_four_way_outcome_classifier(self):
        self.assertEqual(
            classify_outcome("S3", [{"state": "S3", "bandpos": 0.60}], target_hit=True)["outcome"],
            OUTCOME_SUCCESS,
        )
        self.assertEqual(
            classify_outcome("S3", [{"state": "S2", "bandpos": 0.49}], target_hit=False)["outcome"],
            OUTCOME_FAIL,
        )
        self.assertEqual(
            classify_outcome("S3", [{"state": "S0.5", "bandpos": 0.45}], target_hit=False)["outcome"],
            OUTCOME_OTHER,
        )

    def test_route_contract_matrix(self):
        self.assertEqual(
            build_confirmed_close_label("S0.5", [{"state":"S1","bandpos":0.58,"price":103.0}])["outcome"],
            OUTCOME_SUCCESS,
        )
        self.assertEqual(
            build_confirmed_close_label("S0.5", [{"state":"S0.5","bandpos":0.42,"price":99.0}])["outcome"],
            OUTCOME_ALIVE,
        )
        self.assertEqual(
            build_confirmed_close_label("S3", [{"state":"S2","bandpos":0.60,"price":95.0}])["outcome"],
            OUTCOME_FAIL,
        )
        self.assertTrue(confirmed_close_target_hit("S3", {"state":"OTHER","bandpos":0.80,"s3_expanded":True}))

    def test_cci_matches_pine_reference(self):
        daily = []
        base = 1704067200000
        close = 100.0
        for i in range(70):
            o = close
            c = o * (1.0 + (0.006 if i % 7 in {0, 1, 2} else -0.0035))
            h = max(o, c) * (1.004 + (i % 3) * 0.0005)
            l = min(o, c) * (0.996 - (i % 2) * 0.0004)
            daily.append({"time": base + i * 86400000, "open": o, "high": h, "low": l, "close": c})
            close = c

        actual = calculate_cci_sma(daily, length=20, smoothing_length=14)
        typical = [(x["high"] + x["low"] + x["close"]) / 3.0 for x in daily]
        cci = [None] * len(daily)
        for i in range(19, len(daily)):
            window = typical[i-19:i+1]
            mean = sum(window) / 20.0
            dev = sum(abs(v - mean) for v in window) / 20.0
            cci[i] = (typical[i] - mean) / (0.015 * dev) if dev > 1e-18 else 0.0

        smoothing = [None] * len(daily)
        valid = []
        for i, value in enumerate(cci):
            if value is None:
                continue
            valid.append(value)
            if len(valid) >= 14:
                smoothing[i] = sum(valid[-14:]) / 14.0

        for i in range(len(daily)):
            if cci[i] is None:
                self.assertIsNone(actual[i]["cci"])
            else:
                self.assertAlmostEqual(actual[i]["cci"], cci[i], places=10)
            if smoothing[i] is None:
                self.assertIsNone(actual[i]["smoothing_ma"])
            else:
                self.assertAlmostEqual(actual[i]["smoothing_ma"], smoothing[i], places=10)

        self.assertIsNotNone(actual[32]["smoothing_ma"])
        for i in range(33, len(actual)):
            prev = actual[i-1]["smoothing_ma"]
            curr = actual[i]["smoothing_ma"]
            if prev is None or curr is None:
                continue
            expected = "yellow" if curr > prev else "purple" if curr < prev else "gray"
            self.assertEqual(actual[i]["smoothing_color"], expected)

    def test_engine_record_and_replay_contains_cci_contract(self):
        rows = self.synthetic_rows()
        record = build_live_compatible_record("TEST", rows)
        self.assertIsNotNone(record)
        self.assertEqual(len(record["_ha_pct_series"]), 30)
        self.assertEqual(len(record["_cci_last30"]), 30)
        self.assertEqual(len(record["_cci_smoothing_ma_last30"]), 30)
        self.assertEqual(len(record["_cci_smoothing_color_last30"]), 30)
        self.assertIsNotNone(record["_cci_last30"][-1])
        self.assertIsNotNone(record["_cci_smoothing_ma_last30"][-1])

        opportunity = build_long_opportunity(record, None)
        features = extract_features(record, opportunity, "NONE", 1)
        for key in (
            "cci", "cci_zone", "cci_smoothing_ma", "cci_sma_gap", "cci_sma_relation",
            "cci_cross_event", "cci_smoothing_direction", "cci_smoothing_turn_event",
            "cci_cross_on_yellow", "cci_regime", "midline_slope_5d", "midline_improvement",
        ):
            self.assertIn(key, features)

        timeline = []
        cases = replay_symbol("TEST", rows, daily_timeline=timeline)
        self.assertGreater(len(cases), 0)
        self.assertGreater(len(timeline), 0)
        self.assertIn("cci", timeline[-1]["features"])
        self.assertIn("cci_smoothing_direction", timeline[-1]["features"])
        self.assertNotIn("3", cases[0]["labels"])
        self.assertIn("6", cases[0]["labels"])
        self.assertEqual(cases[0].get("decision_contract"), "POST_CLOSE_DAILY_ROUTE_V2")

        model = build_model(cases, DEFAULT_HORIZONS, min_samples=10)
        self.assertEqual(model["schema_version"], 4)
        self.assertEqual(
            (model.get("cci_expert_contract") or {}).get("version"),
            "CCI-EXPERT-v1-HLC3-20-SMA14",
        )
        first = cases[0]
        pred = lookup_probability(model, first["state"], 6, first["features"])
        self.assertTrue(pred["available"])
        self.assertIn("cci_expert", pred)
        total = sum(float(v["probability"]) for v in pred["outcomes"].values())
        self.assertAlmostEqual(total, 1.0, places=5)

    def test_cci_expert_learns_patterns_without_redefining_state(self):
        cases = []
        base = {
            "midline_state": "purple",
            "bandpos_bin": "025_050",
            "trigger_stage": "T0",
            "bandwidth_trend": "FLAT",
            "state_age_bin": "2_3",
            "ha_color": "🟢",
            "current_run_bin": "2",
            "midline_slope_5d": -0.10,
            "midline_improvement": 0.08,
        }
        for i in range(160):
            positive = i < 80
            features = {
                **base,
                "cci": -100.0 if positive else -155.0,
                "cci_zone": "NEG120_NEG80" if positive else "LT_NEG150",
                "cci_distance_to_neg100": 0.0 if positive else 55.0,
                "cci_smoothing_ma": -108.0 if positive else -130.0,
                "cci_sma_gap": 8.0 if positive else -25.0,
                "cci_sma_relation": "ABOVE" if positive else "BELOW",
                "cci_relation_age_bin": "1",
                "cci_cross_event": "CCI_CROSS_UP" if positive else "NO_NEW_CROSS",
                "cci_slope_3d": 20.0 if positive else -10.0,
                "cci_smoothing_slope_3d": 4.0 if positive else -5.0,
                "cci_smoothing_direction": "YELLOW" if positive else "PURPLE",
                "cci_smoothing_age_bin": "1",
                "cci_smoothing_turn_event": "PURPLE_TO_YELLOW" if positive else "NONE",
                "cci_cross_on_yellow": "CROSS_UP_YELLOW" if positive else "NO_CROSS_UP",
                "cci_regime": "ABOVE_YELLOW" if positive else "BELOW_PURPLE",
            }
            outcome = OUTCOME_SUCCESS if positive else OUTCOME_FAIL
            cases.append({
                "state": "S0.5",
                "target": "S1_OR_HIGHER",
                "features": features,
                "labels": {"18": {"outcome": outcome, "hit": positive}},
            })

        model = build_model(cases, (18,), min_samples=20)
        facet_names = {f["name"] for f in model["states"]["S0.5"]["horizons"]["18"]["cci_expert"]["facets"]}
        self.assertTrue({"position_cross", "bb_slope_context", "right_side_confirm"}.issubset(facet_names))
        positive_pred = lookup_probability(model, "S0.5", 18, cases[0]["features"])
        negative_pred = lookup_probability(model, "S0.5", 18, cases[-1]["features"])
        self.assertTrue(positive_pred["cci_expert"]["available"])
        self.assertTrue(negative_pred["cci_expert"]["available"])
        self.assertGreater(positive_pred["probability"], negative_pred["probability"])


if __name__ == "__main__":
    unittest.main()

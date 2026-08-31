import unittest

from engine.runtime_core import aggregate_4h_to_daily, build_live_compatible_record, calculate_adx_dmi
from engine.scoring_rules import build_long_opportunity
from training.features import extract_features
from training.model_builder import _features_for_model_version, build_model, lookup_probability
from training.features import _adx_step_features, _adx_step_features_legacy
from training.outcomes import (
    OUTCOME_ALIVE,
    OUTCOME_FAIL,
    OUTCOME_KEYS,
    OUTCOME_OTHER,
    OUTCOME_SUCCESS,
    classify_outcome,
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
            rows.append({"time": base + i * 4 * 3600 * 1000, "open": o, "high": h, "low": l, "close": c, "volume": 1000 + i})
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
            OUTCOME_ALIVE,
        )
        self.assertEqual(
            classify_outcome("S3", [{"state": "OTHER", "bandpos": 0.31}], target_hit=False)["outcome"],
            OUTCOME_FAIL,
        )
        self.assertEqual(
            classify_outcome("S3", [{"state": "S0.5", "bandpos": 0.45}], target_hit=False)["outcome"],
            OUTCOME_OTHER,
        )

    def test_engine_record_and_replay(self):
        rows = self.synthetic_rows()
        record = build_live_compatible_record("TEST", rows)
        self.assertIsNotNone(record)
        self.assertEqual(len(record["_ha_pct_series"]), 30)
        self.assertEqual(len(record["_di_plus_last30"]), 30)
        self.assertEqual(len(record["_di_minus_last30"]), 30)
        self.assertEqual(len(record["_adx_last30"]), 30)
        self.assertIsNotNone(record["_di_plus_last30"][-1])
        self.assertIsNotNone(record["_di_minus_last30"][-1])
        opportunity = build_long_opportunity(record, None)
        self.assertIn(opportunity["market_state_id"], {"S0", "S0.5", "S1", "S2", "S3", "OTHER"})
        timeline = []
        cases = replay_symbol("TEST", rows, daily_timeline=timeline)
        self.assertGreater(len(cases), 0)
        self.assertGreater(len(timeline), 0)
        self.assertIn("state", timeline[-1])
        self.assertIn("state_age_bin", timeline[-1]["features"])
        self.assertIn("di_plus", timeline[-1]["features"])
        self.assertIn("di_minus", timeline[-1]["features"])
        self.assertIn("dmi_relation", timeline[-1]["features"])
        self.assertIn("dmi_axis_zone", timeline[-1]["features"])
        self.assertIn("adx", timeline[-1]["features"])
        self.assertIn("adx_step_direction", timeline[-1]["features"])
        self.assertIn("adx_step_age_bin", timeline[-1]["features"])
        self.assertIn("adx_turn_event", timeline[-1]["features"])
        self.assertIn("dmi_adx_regime", timeline[-1]["features"])
        primary = cases[0]["labels"]["18"]
        self.assertIn(primary["outcome"], OUTCOME_KEYS)

        model = build_model(cases, DEFAULT_HORIZONS, min_samples=10)
        self.assertEqual(model["schema_version"], 3)
        first = cases[0]
        pred = lookup_probability(model, first["state"], 6, first["features"])
        self.assertTrue(pred["available"])
        self.assertIn("dmi_expert", pred)
        self.assertGreaterEqual(pred["probability"], 0.0)
        self.assertLessEqual(pred["probability"], 1.0)
        self.assertEqual(set(pred["outcomes"].keys()), set(OUTCOME_KEYS))
        total = sum(float(v["probability"]) for v in pred["outcomes"].values())
        self.assertAlmostEqual(total, 1.0, places=5)
        self.assertAlmostEqual(
            pred["structural_survival_probability"],
            float(pred["outcomes"][OUTCOME_SUCCESS]["probability"]) + float(pred["outcomes"][OUTCOME_ALIVE]["probability"]),
            places=5,
        )

    def test_adx_matches_pine_reference(self):
        daily = []
        base = 1704067200000
        close = 100.0
        for i in range(60):
            o = close
            c = o * (1.0 + (0.004 if i % 5 in {0, 1, 2} else -0.0025))
            h = max(o, c) * (1.004 + (i % 3) * 0.0005)
            l = min(o, c) * (0.996 - (i % 2) * 0.0004)
            daily.append({"time": base + i * 86400000, "open": o, "high": h, "low": l, "close": c})
            close = c

        actual = calculate_adx_dmi(daily, period=14)

        sm_tr = sm_plus = sm_minus = 0.0
        dx_window = []
        expected = []
        for i, candle in enumerate(daily):
            prev = daily[i - 1] if i > 0 else None
            pc = float(prev["close"]) if prev else 0.0
            ph = float(prev["high"]) if prev else 0.0
            pl = float(prev["low"]) if prev else 0.0
            high, low = float(candle["high"]), float(candle["low"])
            tr = max(high - low, abs(high - pc), abs(low - pc))
            up = high - ph
            down = pl - low
            dm_plus = max(up, 0.0) if up > down else 0.0
            dm_minus = max(down, 0.0) if down > up else 0.0
            sm_tr = sm_tr - sm_tr / 14 + tr
            sm_plus = sm_plus - sm_plus / 14 + dm_plus
            sm_minus = sm_minus - sm_minus / 14 + dm_minus
            di_plus = sm_plus / sm_tr * 100 if sm_tr > 0 else None
            di_minus = sm_minus / sm_tr * 100 if sm_tr > 0 else None
            denom = (di_plus or 0.0) + (di_minus or 0.0)
            dx = abs(di_plus - di_minus) / denom * 100 if di_plus is not None and di_minus is not None and denom > 0 else None
            if dx is None:
                dx_window.clear()
                adx = None
            else:
                dx_window.append(dx)
                if len(dx_window) > 14:
                    dx_window.pop(0)
                adx = sum(dx_window) / len(dx_window) if len(dx_window) == 14 else None
            expected.append((di_plus, di_minus, dx, adx))

        for row, ref in zip(actual, expected):
            for key, value in zip(("di_plus", "di_minus", "dx", "adx"), ref):
                if value is None:
                    self.assertIsNone(row[key])
                else:
                    self.assertAlmostEqual(float(row[key]), float(value), places=12)

    def test_adx_step_features_match_terminal_red_green_semantics(self):
        record = {
            "_bb_upper_series": [120.0, 120.0, 120.0, 120.0],
            "_bb_lower_series": [80.0, 80.0, 80.0, 80.0],
            "_bb_basis_series": [100.0, 100.0, 100.0, 100.0],
            "_di_plus_last30": [15.0, 16.0, 18.0, 22.0],
            "_di_minus_last30": [27.0, 25.0, 23.0, 20.0],
            "_adx_last30": [26.0, 22.0, 18.0, 19.0],
        }
        opportunity = {
            "market_state_id": "S0.5",
            "trigger_stage": "T1",
            "current": {
                "ha_band_position": 0.48,
                "ha_color": "🟢",
                "current_color_run_length": 1,
            },
            "midline": {
                "state": "flattening",
                "recent_5d_slope_pct_per_day": 0.0,
                "slope_improvement_pct_per_day": 0.0,
            },
            "purple_structure": {"base_quality": {"qualified": True}},
        }
        features = extract_features(
            record, opportunity, "S0", 1, previous_dmi_relation="MINUS", dmi_relation_age_bars=1
        )
        self.assertEqual(features["dmi_relation"], "PLUS")
        self.assertEqual(features["adx_step_direction"], "RISING")
        self.assertEqual(features["adx_step_age_days"], 1)
        self.assertEqual(features["adx_step_age_bin"], "1")
        self.assertEqual(features["adx_turn_event"], "RED_TO_GREEN")
        self.assertEqual(features["adx_axis_zone"], "BELOW_20")
        self.assertEqual(features["dmi_adx_regime"], "PLUS_RISING")

    def test_adx_1dp_sticky_suppresses_micro_flip(self):
        # AMD example: both final displayed values round to 10.5. The old
        # full-precision rule flips red, while v3 keeps the preceding green.
        values = [10.4, 10.496955, 10.454547]
        sticky = _adx_step_features(values)
        legacy = _adx_step_features_legacy(values)
        self.assertEqual(sticky["adx_step_direction"], "RISING")
        self.assertEqual(sticky["adx_step_age_days"], 2)
        self.assertEqual(sticky["adx_turn_event"], "NONE")
        self.assertEqual(legacy["adx_step_direction"], "FALLING")
        self.assertEqual(legacy["adx_turn_event"], "GREEN_TO_RED")

    def test_adx_1dp_sticky_keeps_red_when_equal_after_fall(self):
        values = [10.6, 10.496955, 10.454547]
        sticky = _adx_step_features(values)
        self.assertEqual(sticky["adx_step_direction"], "FALLING")
        self.assertEqual(sticky["adx_step_age_days"], 2)
        self.assertEqual(sticky["adx_turn_event"], "NONE")

    def test_model_version_bridge_keeps_v2_champion_on_legacy_adx_semantics(self):
        features = {
            "adx_step_direction": "RISING",
            "adx_step_age_days": 2,
            "adx_step_age_bin": "2_3",
            "adx_turn_event": "NONE",
            "dmi_adx_regime": "PLUS_RISING",
            "adx_step_direction_legacy": "FALLING",
            "adx_step_age_days_legacy": 1,
            "adx_step_age_bin_legacy": "1",
            "adx_turn_event_legacy": "GREEN_TO_RED",
            "dmi_adx_regime_legacy": "PLUS_FALLING",
        }
        v2 = {"dmi_expert_contract": {"version": "DMI-EXPERT-v2-ADX-STEP"}}
        v3 = {"dmi_expert_contract": {"version": "DMI-EXPERT-v3-ADX-1DP-STICKY"}}
        old = _features_for_model_version(v2, features)
        new = _features_for_model_version(v3, features)
        self.assertEqual(old["adx_step_direction"], "FALLING")
        self.assertEqual(old["dmi_adx_regime"], "PLUS_FALLING")
        self.assertEqual(new["adx_step_direction"], "RISING")
        self.assertEqual(new["dmi_adx_regime"], "PLUS_RISING")

    def test_dmi_expert_v2_learns_adx_step_regime_per_state(self):
        cases = []
        regimes = [
            ("PLUS", "RISING", OUTCOME_SUCCESS),
            ("PLUS", "FALLING", OUTCOME_ALIVE),
            ("MINUS", "RISING", OUTCOME_FAIL),
            ("MINUS", "FALLING", OUTCOME_OTHER),
        ]
        t = 0
        for relation, step_direction, dominant_outcome in regimes:
            for i in range(100):
                t += 1
                outcome = dominant_outcome if i < 85 else OUTCOME_ALIVE
                regime = f"{relation}_{step_direction}"
                features = {
                    "midline_state": "flat",
                    "bandpos_bin": "025_050",
                    "trigger_stage": "T1",
                    "bandwidth_trend": "FLAT",
                    "state_age_bin": "2_3",
                    "dmi_relation": relation,
                    "dmi_axis_zone": "PLUS_ONLY_ABOVE_20" if relation == "PLUS" else "MINUS_ONLY_ABOVE_20",
                    "dmi_cross_age_bin": "1" if i < 50 else "2_3",
                    "di_abs_gap": 6.0,
                    "di_axis_distance": 3.0,
                    "di_plus_slope_3d": 1.0 if relation == "PLUS" else -1.0,
                    "di_minus_slope_3d": -1.0 if relation == "PLUS" else 1.0,
                    "di_gap_slope_3d": 2.0 if relation == "PLUS" else -2.0,
                    "adx": 18.0,
                    "adx_slope_3d": 1.0 if step_direction == "RISING" else -1.0,
                    "adx_axis_zone": "BELOW_20",
                    "adx_step_direction": step_direction,
                    "adx_step_age_days": 1 if i < 50 else 3,
                    "adx_step_age_bin": "1" if i < 50 else "2_3",
                    "adx_turn_event": "RED_TO_GREEN" if step_direction == "RISING" and i < 50 else "GREEN_TO_RED" if step_direction == "FALLING" and i < 50 else "NONE",
                    "adx_step_delta": 1.0 if step_direction == "RISING" else -1.0,
                    "dmi_adx_regime": regime,
                }
                label = {"outcome": outcome, "hit": outcome == OUTCOME_SUCCESS, "late_success_4_7d": None}
                cases.append({
                    "symbol": "TEST",
                    "time": t,
                    "state": "S0.5",
                    "target": "S1_OR_HIGHER",
                    "features": features,
                    "labels": {str(h): dict(label) for h in DEFAULT_HORIZONS},
                })

        model = build_model(cases, DEFAULT_HORIZONS, min_samples=20)
        self.assertEqual(model["schema_version"], 3)
        self.assertEqual((model.get("dmi_expert_contract") or {}).get("version"), "DMI-EXPERT-v3-ADX-1DP-STICKY")
        facet_names = {f["name"] for f in model["states"]["S0.5"]["horizons"]["18"]["dmi_expert"]["facets"]}
        self.assertTrue({"adx_step_regime", "adx_step_persistence", "adx_turn_handover"}.issubset(facet_names))
        plus_rising = lookup_probability(model, "S0.5", 18, cases[0]["features"])
        minus_rising = lookup_probability(model, "S0.5", 18, cases[200]["features"])
        self.assertGreater(plus_rising["probability"], minus_rising["probability"])
        matched_names = {x.get("name") for x in plus_rising["dmi_expert"]["matched_facets"]}
        self.assertIn("adx_step_regime", matched_names)
        self.assertIn("adx_step_persistence", matched_names)
        self.assertIn("adx_turn_handover", matched_names)

    def test_dmi_expert_learns_without_redefining_state(self):
        cases = []
        outcomes = [OUTCOME_SUCCESS, OUTCOME_ALIVE, OUTCOME_FAIL, OUTCOME_OTHER]
        for i in range(240):
            plus_leads = i < 120
            outcome = OUTCOME_SUCCESS if (plus_leads and i % 5 != 0) else OUTCOME_FAIL if not plus_leads and i % 4 != 0 else OUTCOME_OTHER
            features = {
                "midline_state": "flat",
                "bandpos_bin": "025_050",
                "trigger_stage": "T1",
                "bandwidth_trend": "FLAT",
                "state_age_bin": "2_3",
                "dmi_relation": "PLUS" if plus_leads else "MINUS",
                "dmi_axis_zone": "PLUS_ONLY_ABOVE_20" if plus_leads else "MINUS_ONLY_ABOVE_20",
                "dmi_cross_age_bin": "1",
                "di_abs_gap": 8.0 if plus_leads else 7.0,
                "di_axis_distance": 3.0,
                "di_plus_slope_3d": 2.0 if plus_leads else -1.5,
                "di_minus_slope_3d": -1.0 if plus_leads else 2.0,
                "di_gap_slope_3d": 3.0 if plus_leads else -3.0,
                "adx": 26.0,
                "adx_slope_3d": 1.2,
                "adx_axis_zone": "ABOVE_20",
                "adx_step_direction": "RISING",
                "adx_step_age_days": 2,
                "adx_step_age_bin": "2_3",
                "adx_turn_event": "NONE",
                "adx_step_delta": 1.0,
                "dmi_adx_regime": "PLUS_RISING" if plus_leads else "MINUS_RISING",
            }
            label = {
                "outcome": outcome,
                "hit": outcome == OUTCOME_SUCCESS,
                "late_success_4_7d": None,
            }
            cases.append({
                "symbol": "TEST",
                "time": i,
                "state": "S0.5",
                "target": "S1_OR_HIGHER",
                "features": features,
                "labels": {str(h): dict(label) for h in DEFAULT_HORIZONS},
            })

        model = build_model(cases, DEFAULT_HORIZONS, min_samples=20)
        self.assertEqual(model["schema_version"], 3)
        self.assertEqual(model["states"]["S0.5"]["target"], "S1_OR_HIGHER")
        plus = lookup_probability(model, "S0.5", 18, cases[1]["features"])
        minus = lookup_probability(model, "S0.5", 18, cases[-1]["features"])
        self.assertTrue(plus["dmi_expert"]["available"])
        self.assertTrue(minus["dmi_expert"]["available"])
        self.assertGreater(plus["probability"], minus["probability"])
        self.assertLess(plus["true_fail_probability"], minus["true_fail_probability"])
        for result in (plus, minus):
            total = sum(float(v["probability"]) for v in result["outcomes"].values())
            self.assertAlmostEqual(total, 1.0, places=5)


if __name__ == "__main__":
    unittest.main()

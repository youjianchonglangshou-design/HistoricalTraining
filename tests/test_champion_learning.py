from __future__ import annotations

import unittest

from training.champion_learning import (
    OUTCOME_ALIVE,
    OUTCOME_FAIL,
    OUTCOME_SUCCESS,
    adaptive_reinforcement_weight,
    apply_case_settlement,
    apply_confirmed_daily_settlements,
    build_evolution_policy,
    build_evolution_review,
    build_performance,
    ensure_generation,
    frozen_record_to_case,
    prune_rolling_ledger,
    save_ledger_shards,
)


from champion_daily import checkpoint_cutoff_ms, frozen_from_terminal_checkpoint

class ChampionLearningTests(unittest.TestCase):
    def test_generation_changes_only_when_active_model_changes(self):
        manifest = {"generation": 1, "champion_model_id": "A", "started_at": "t0", "evolution_min_settled_72h": 120}
        same, history, changed = ensure_generation(manifest, [], "A", "t1")
        self.assertFalse(changed)
        self.assertEqual(same["generation"], 1)
        nxt, history, changed = ensure_generation(manifest, [], "B", "t1")
        self.assertTrue(changed)
        self.assertEqual(nxt["generation"], 2)
        self.assertEqual(nxt["champion_model_id"], "B")
        self.assertEqual(len(history), 1)

    def test_settlement_appends_12h_and_72h_without_changing_prediction(self):
        record = {
            "prediction": {"success_probability": 0.7},
            "settlements": {"12H": {"status": "PENDING"}, "24H": {"status": "PENDING"}, "48H": {"status": "PENDING"}, "72H": {"status": "PENDING"}},
        }
        case = {"labels": {
            "3": {"outcome": OUTCOME_ALIVE, "hit": False, "state_path": ["S2"]},
            "18": {"outcome": OUTCOME_SUCCESS, "hit": True, "state_path": ["S2", "S3"]},
        }}
        self.assertTrue(apply_case_settlement(record, case))
        self.assertEqual(record["prediction"]["success_probability"], 0.7)
        self.assertEqual(record["settlements"]["12H"]["outcome"], OUTCOME_ALIVE)
        self.assertEqual(record["settlements"]["72H"]["outcome"], OUTCOME_SUCCESS)
        self.assertEqual(record["final_outcome"], OUTCOME_SUCCESS)

    def test_performance_shows_success_survival_and_true_fail(self):
        manifest = {"generation": 1, "champion_model_id": "A", "started_at": "t0", "evolution_min_settled_72h": 3}
        outcomes = [OUTCOME_SUCCESS, OUTCOME_ALIVE, OUTCOME_FAIL]
        rows = []
        for i, outcome in enumerate(outcomes):
            rows.append({
                "generation": 1,
                "champion_model_id": "A",
                "frozen_source": "TERMINAL_0825_DAILY_CHECKPOINT",
                "official_scoring": True,
                "decision_time": 1000 + i,
                "decision_date_tw": "2026-08-31",
                "state": "S2",
                "prediction": {"success_probability": 0.70, "structural_survival_probability": 0.80, "true_fail_probability": 0.10},
                "settlements": {"72H": {"status": "SETTLED", "outcome": outcome, "state_path": ["S2", "S3"]}},
                "final_outcome": outcome,
            })
        p = build_performance(rows, manifest, [], now_ms=10_000)
        all_node = p["windows"]["all"]
        self.assertEqual(all_node["settled_72h"], 3)
        self.assertAlmostEqual(all_node["success_rate"], 1/3, places=6)
        self.assertAlmostEqual(all_node["structural_survival_rate"], 2/3, places=6)
        self.assertAlmostEqual(all_node["true_fail_rate"], 1/3, places=6)
        review = build_evolution_review(rows, manifest)
        self.assertTrue(review["evolution_due"])

    def test_frozen_us_stock_case_becomes_live_training_case(self):
        record = {
            "final_settled": True,
            "generation": 1,
            "champion_model_id": "A",
            "frozen_source": "TERMINAL_0825_DAILY_CHECKPOINT",
            "official_scoring": True,
            "market_type": "US_STOCK",
            "symbol": "AMDX",
            "decision_time": 1000,
            "decision_time_tw": "2026-09-01T08:00:00+08:00",
            "state": "S2",
            "target": "S3",
            "entry_price": 100.0,
            "features": {"adx": 18.2},
            "settlements": {
                "12H": {"status": "SETTLED", "outcome": OUTCOME_ALIVE, "hit": False},
                "24H": {"status": "SETTLED", "outcome": OUTCOME_ALIVE, "hit": False},
                "48H": {"status": "SETTLED", "outcome": OUTCOME_SUCCESS, "hit": True},
                "72H": {"status": "SETTLED", "outcome": OUTCOME_SUCCESS, "hit": True, "state_path": ["S2", "S3"]},
            },
        }
        case = frozen_record_to_case(record)
        self.assertIsNotNone(case)
        self.assertEqual(case["market_type"], "US_STOCK")
        self.assertEqual(case["features"]["market_type"], "US_STOCK")
        self.assertEqual(case["labels"]["18"]["outcome"], OUTCOME_SUCCESS)

    def test_performance_separates_crypto_and_us_stock(self):
        manifest = {"generation": 1, "champion_model_id": "A", "started_at": "t0", "evolution_min_settled_72h": 120}
        rows = []
        for market, outcome in [("CRYPTO", OUTCOME_SUCCESS), ("US_STOCK", OUTCOME_FAIL)]:
            rows.append({
                "generation": 1, "champion_model_id": "A", "frozen_source": "TERMINAL_0825_DAILY_CHECKPOINT", "official_scoring": True, "market_type": market,
                "decision_time": 1000, "decision_date_tw": "2026-08-31", "state": "S2",
                "prediction": {"success_probability": 0.70},
                "settlements": {"72H": {"status": "SETTLED", "outcome": outcome}},
                "final_outcome": outcome,
            })
        p = build_performance(rows, manifest, [], now_ms=10_000)
        self.assertEqual(p["by_market"]["CRYPTO"]["all"]["success"], 1)
        self.assertEqual(p["by_market"]["US_STOCK"]["all"]["true_fail"], 1)

    def test_terminal_0825_checkpoint_uses_daily_cutoff_and_exact_frozen_prediction(self):
        payload = {
            "batch": {
                "generated_at_taiwan": "2026-09-01T08:25:08+08:00",
                "snapshot_hash": "abc",
                "champion_daily_checkpoint": {
                    "contract": "TAIWAN_0825_USING_COMPLETED_0800_DAILY_CLOSE",
                    "checkpoint_date_tw": "2026-09-01",
                    "confirmed_close_cutoff_utc": "2026-09-01T00:00:00+00:00",
                    "partial_daily_excluded": True,
                    "partial_4h_after_close_excluded": True,
                },
                "probability_model": {"model_id": "MODEL001"},
            },
            "records": [],
        }
        # 08:25 TW = 00:25 UTC; canonical daily decision key remains UTC 00:00.
        expected_ms = int(__import__("datetime").datetime(2026, 9, 1, 0, 0, tzinfo=__import__("datetime").timezone.utc).timestamp() * 1000)
        self.assertEqual(checkpoint_cutoff_ms(payload), expected_ms)

        payload["_checkpoint_cutoff_ms"] = expected_ms
        payload["_checkpoint_generated_at"] = "2026-09-01T08:25:08+08:00"
        row = {
            "symbol": "BTC",
            "price": 100.0,
            "opportunity_long": {
                "market_state_id": "S2",
                "current": {"ha_band_position": 0.56},
            },
            "historical_probability": {
                "available": True,
                "model_id": "MODEL001",
                "state": "S2",
                "target": "S3",
                "features": {"adx": 18.4, "dmi_relation": "PLUS"},
                "72h": {
                    "available": True,
                    "success_probability": 0.67,
                    "alive_slow_probability": 0.12,
                    "structural_survival_probability": 0.79,
                    "true_fail_probability": 0.14,
                    "other_probability": 0.07,
                    "matched_samples": 321,
                    "level": 5,
                },
            },
        }
        frozen = frozen_from_terminal_checkpoint(
            row=row,
            payload=payload,
            market_type="CRYPTO",
            generation=1,
            active_model_id="MODEL001",
            frozen_at_iso="2026-09-01T00:25:00+00:00",
        )
        self.assertIsNotNone(frozen)
        self.assertEqual(frozen["frozen_source"], "TERMINAL_0825_DAILY_CHECKPOINT")
        self.assertEqual(frozen["decision_time"], expected_ms)
        self.assertEqual(frozen["prediction"]["success_probability"], 0.67)
        self.assertEqual(frozen["prediction"]["true_fail_probability"], 0.14)
        self.assertEqual(frozen["checkpoint_time_tw"], "2026-09-01T08:25:08+08:00")

    def test_checkpoint_from_wrong_model_is_not_misattributed(self):
        payload = {
            "batch": {
                "generated_at_taiwan": "2026-09-01T08:25:00+08:00",
                "champion_daily_checkpoint": {
                    "contract": "TAIWAN_0825_USING_COMPLETED_0800_DAILY_CLOSE",
                    "checkpoint_date_tw": "2026-09-01",
                    "confirmed_close_cutoff_utc": "2026-09-01T00:00:00+00:00",
                    "partial_daily_excluded": True,
                    "partial_4h_after_close_excluded": True,
                },
                "probability_model": {"model_id": "OLDMODEL1"},
            },
            "_checkpoint_cutoff_ms": 1000,
            "_checkpoint_generated_at": "2026-09-01T08:25:00+08:00",
        }
        row = {
            "symbol": "BTC",
            "price": 100,
            "opportunity_long": {"market_state_id": "S2", "current": {"ha_band_position": 0.5}},
            "historical_probability": {
                "available": True,
                "model_id": "OLDMODEL1",
                "state": "S2",
                "target": "S3",
                "features": {},
                "72h": {"available": True, "success_probability": 0.5},
            },
        }
        frozen = frozen_from_terminal_checkpoint(
            row=row, payload=payload, market_type="CRYPTO", generation=2,
            active_model_id="NEWMODEL2", frozen_at_iso="now",
        )
        self.assertIsNone(frozen)


    def test_post_close_s2_does_not_succeed_from_intraday_flash(self):
        record = {
            "state": "S2", "entry_price": 700.0, "decision_date_tw": "2026-09-01",
            "settlements": {
                "12H": {"status": "SETTLED", "outcome": OUTCOME_SUCCESS},
                "24H": {"status": "SETTLED", "outcome": OUTCOME_SUCCESS},
                "48H": {"status": "PENDING"}, "72H": {"status": "PENDING"},
            },
        }
        history = {"2026-09-02": {"state": "S2", "price": 683.39, "bandpos": 0.602187}}
        self.assertTrue(apply_confirmed_daily_settlements(record, history))
        self.assertEqual(record["settlements"]["12H"]["status"], "OBSERVATION_ONLY")
        self.assertEqual(record["settlements"]["24H"]["outcome"], OUTCOME_ALIVE)
        self.assertFalse(record["settlements"]["24H"]["hit"])
        self.assertEqual(record["settlements"]["24H"]["settlement_basis"], "POST_CLOSE_DAILY_CHECKPOINT")

    def test_post_close_s3_back_to_s2_is_true_fail(self):
        record = {
            "state": "S3", "entry_price": 100.0, "decision_date_tw": "2026-09-01",
            "settlements": {"12H": {"status": "PENDING"}, "24H": {"status": "PENDING"}, "48H": {"status": "PENDING"}, "72H": {"status": "PENDING"}},
        }
        history = {"2026-09-02": {"state": "S2", "price": 95.0, "bandpos": 0.60}}
        self.assertTrue(apply_confirmed_daily_settlements(record, history))
        self.assertEqual(record["settlements"]["24H"]["outcome"], OUTCOME_FAIL)
        self.assertEqual(record["settlements"]["24H"]["reason"], "s3_lost_on_confirmed_daily_close")

    def test_evolution_policy_turns_review_into_adaptive_weighting(self):
        manifest = {"generation": 1, "champion_model_id": "A", "evolution_min_settled_72h": 2}
        rows = [
            {
                "generation": 1, "champion_model_id": "A", "frozen_source": "TERMINAL_0825_DAILY_CHECKPOINT", "official_scoring": True, "market_type": "CRYPTO",
                "symbol": "BTC", "decision_time": 1000, "decision_date_tw": "2026-09-01",
                "state": "S0.5", "features": {"dmi_adx_regime": "PLUS_RISING", "adx_turn_event": "RED_TO_GREEN"},
                "prediction": {"success_probability": 0.80},
                "settlements": {"72H": {"status": "SETTLED", "outcome": OUTCOME_FAIL}},
                "final_outcome": OUTCOME_FAIL, "final_settled": True,
            },
            {
                "generation": 1, "champion_model_id": "A", "frozen_source": "TERMINAL_0825_DAILY_CHECKPOINT", "official_scoring": True, "market_type": "CRYPTO",
                "symbol": "ETH", "decision_time": 2000, "decision_date_tw": "2026-09-01",
                "state": "S0.5", "features": {"dmi_adx_regime": "PLUS_RISING", "adx_turn_event": "RED_TO_GREEN"},
                "prediction": {"success_probability": 0.75},
                "settlements": {"72H": {"status": "SETTLED", "outcome": OUTCOME_FAIL}},
                "final_outcome": OUTCOME_FAIL, "final_settled": True,
            },
        ]
        review = build_evolution_review(rows, manifest)
        self.assertTrue(review["evolution_due"])
        policy = build_evolution_policy(review, rows, manifest)
        self.assertTrue(policy["active_for_next_training"])
        case = frozen_record_to_case(rows[0])
        self.assertIsNotNone(case)
        self.assertGreater(adaptive_reinforcement_weight(case, policy, 10), 10)

    def test_legacy_frozen_exam_can_be_regraded_without_becoming_official(self):
        legacy = {
            "generation": 1, "champion_model_id": "A", "market_type": "CRYPTO",
            "frozen_source": "TERMINAL_0401_CHECKPOINT", "official_scoring": False,
            "symbol": "BNB", "decision_time": 1000, "decision_date_tw": "2026-09-01",
            "state": "S2", "entry_price": 700.0,
            "settlements": {
                "12H": {"status": "SETTLED", "outcome": OUTCOME_SUCCESS},
                "24H": {"status": "SETTLED", "outcome": OUTCOME_SUCCESS},
                "48H": {"status": "PENDING"}, "72H": {"status": "PENDING"},
            },
        }
        history = {"2026-09-02": {"state": "S2", "price": 683.39, "bandpos": 0.602187}}
        self.assertTrue(apply_confirmed_daily_settlements(legacy, history))
        self.assertEqual(legacy["settlements"]["12H"]["status"], "OBSERVATION_ONLY")
        self.assertEqual(legacy["settlements"]["24H"]["outcome"], OUTCOME_ALIVE)
        self.assertFalse(legacy["official_scoring"])

    def test_legacy_pre_0825_rows_do_not_count_as_official_performance_or_evolution(self):
        manifest = {"generation": 1, "champion_model_id": "A", "evolution_min_settled_72h": 1}
        legacy = {
            "generation": 1, "champion_model_id": "A", "market_type": "CRYPTO",
            "frozen_source": "TERMINAL_0401_CHECKPOINT", "official_scoring": False,
            "symbol": "BNB", "decision_time": 1000, "decision_date_tw": "2026-09-01",
            "state": "S2", "prediction": {"success_probability": 0.9},
            "settlements": {"72H": {"status": "SETTLED", "outcome": OUTCOME_SUCCESS}},
            "final_outcome": OUTCOME_SUCCESS, "final_settled": True,
        }
        perf = build_performance([legacy], manifest, [], now_ms=10_000)
        self.assertEqual(perf["windows"]["all"]["snapshots"], 0)
        self.assertEqual(perf["legacy_excluded"], 1)
        review = build_evolution_review([legacy], manifest)
        self.assertFalse(review["evolution_due"])
        self.assertEqual(review["settled_72h"], 0)
        self.assertIsNone(frozen_record_to_case(legacy))

    def test_r2_shards_are_generation_and_date_partitioned(self):
        import tempfile
        from pathlib import Path
        rows = [
            {"generation":1,"champion_model_id":"A","decision_time":1000,"decision_date_tw":"2026-09-01","symbol":"BTC"},
            {"generation":1,"champion_model_id":"A","decision_time":2000,"decision_date_tw":"2026-09-02","symbol":"ETH"},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            manifest = save_ledger_shards(Path(tmp), rows)
            self.assertEqual(len(manifest), 2)
            self.assertTrue((Path(tmp)/"GEN001"/"2026-09-01.json").exists())
            self.assertTrue((Path(tmp)/"GEN001"/"2026-09-02.json").exists())

    def test_rolling_ledger_cache_prunes_old_final_rows_but_keeps_pending(self):
        now_ms = 200 * 86400000
        old_ms = 1 * 86400000
        recent_ms = 190 * 86400000
        rows = [
            {"decision_time":old_ms,"symbol":"OLD","final_settled":True},
            {"decision_time":old_ms,"symbol":"PENDING","final_settled":False},
            {"decision_time":recent_ms,"symbol":"NEW","final_settled":True},
        ]
        kept = prune_rolling_ledger(rows, now_ms=now_ms, keep_days=90)
        symbols = {r["symbol"] for r in kept}
        self.assertNotIn("OLD", symbols)
        self.assertIn("PENDING", symbols)
        self.assertIn("NEW", symbols)



if __name__ == "__main__":
    unittest.main()

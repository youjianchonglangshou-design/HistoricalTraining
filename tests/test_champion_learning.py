from __future__ import annotations

import unittest

from training.champion_learning import (
    OUTCOME_ALIVE,
    OUTCOME_FAIL,
    OUTCOME_SUCCESS,
    apply_case_settlement,
    build_evolution_review,
    build_performance,
    ensure_generation,
)


class ChampionLearningTests(unittest.TestCase):
    def test_generation_changes_only_when_active_model_changes(self):
        manifest = {"generation": 1, "champion_model_id": "A", "started_at": "t0", "evolution_min_settled_72h": 200}
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


if __name__ == "__main__":
    unittest.main()

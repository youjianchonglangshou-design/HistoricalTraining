import unittest

from evaluate_challenger import promotion_decision


def metrics(brier, logloss, fail_brier, success_ece, cases=220, symbols=70):
    return {
        "cases": cases,
        "symbols": symbols,
        "multiclass_brier": brier,
        "log_loss": logloss,
        "true_fail_brier": fail_brier,
        "success_ece": success_ece,
        "state_brier": {
            "S0.5": {"cases": 55, "brier": brier},
            "S1": {"cases": 55, "brier": brier},
            "S2": {"cases": 55, "brier": brier},
            "S3": {"cases": 55, "brier": brier},
        },
    }


class ChallengerPolicyTests(unittest.TestCase):
    def test_waits_before_72h(self):
        a = metrics(0.50, 0.90, 0.12, 0.05)
        c = metrics(0.48, 0.88, 0.11, 0.04)
        decision, _, _ = promotion_decision(a, c, candidate_age_hours=48, p_brier_better=0.90)
        self.assertEqual(decision, "WAITING_EVIDENCE")

    def test_promotes_clear_oos_winner(self):
        a = metrics(0.50, 0.90, 0.12, 0.05)
        c = metrics(0.47, 0.84, 0.10, 0.04)
        decision, _, _ = promotion_decision(a, c, candidate_age_hours=96, p_brier_better=0.90)
        self.assertEqual(decision, "PROMOTE")

    def test_rejects_clear_loser(self):
        a = metrics(0.48, 0.85, 0.10, 0.04)
        c = metrics(0.51, 0.91, 0.13, 0.06)
        decision, _, _ = promotion_decision(a, c, candidate_age_hours=96, p_brier_better=0.10)
        self.assertEqual(decision, "REJECT")


if __name__ == "__main__":
    unittest.main()

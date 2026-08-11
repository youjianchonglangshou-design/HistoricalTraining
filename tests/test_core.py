import unittest

from engine.runtime_core import aggregate_4h_to_daily, build_live_compatible_record
from engine.scoring_rules import build_long_opportunity
from training.model_builder import build_model, lookup_probability
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

    def test_engine_record_and_replay(self):
        rows = self.synthetic_rows()
        record = build_live_compatible_record("TEST", rows)
        self.assertIsNotNone(record)
        self.assertEqual(len(record["_ha_pct_series"]), 30)
        opportunity = build_long_opportunity(record, None)
        self.assertIn(opportunity["market_state_id"], {"S0", "S0.5", "S1", "S2", "S3", "OTHER"})
        cases = replay_symbol("TEST", rows)
        self.assertGreater(len(cases), 0)
        model = build_model(cases, DEFAULT_HORIZONS, min_samples=10)
        first = cases[0]
        pred = lookup_probability(model, first["state"], 6, first["features"])
        self.assertTrue(pred["available"])
        self.assertGreaterEqual(pred["probability"], 0.0)
        self.assertLessEqual(pred["probability"], 1.0)


if __name__ == "__main__":
    unittest.main()

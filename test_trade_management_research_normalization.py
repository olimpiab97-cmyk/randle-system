import json
import tempfile
import unittest
from pathlib import Path

import normalize_trade_management_research as normalizer


class TradeManagementResearchNormalizationTests(unittest.TestCase):
    def test_missing_classification_is_recomputed(self):
        row = {
            "trade_id": "T-414722e3",
            "symbol": "NQM6",
            "direction": "short",
            "entry_price": 30351.5,
            "original_stop": 30379.5,
            "original_tp1_price": 30323.5,
            "be_trigger": 30337.5,
            "be_hit_at": "2026-06-04T13:38:29.3400707Z",
            "closed_at": "2026-06-04T13:38:33.4085068Z",
            "actual_exit_price": 30351.5,
            "actual_exit_reason": "stop_hit",
            "actual_result": "flat",
            "post_be_first_seen_at": "2026-06-04T13:38:29.3400707Z",
            "post_be_last_updated_at": "2026-06-04T13:38:33.4085068Z",
            "fixed_8_model_result": "tp1",
            "fixed_8_stop_price": 30353.5,
            "fixed_8_tp1_price": 30349.5,
            "fixed_8_stop_distance_points": 2.0,
            "fixed_8_tp1_would_hit": True,
            "fixed_12_model_result": "tp1",
            "fixed_16_model_result": "tp1",
            "structural_dynamic_model_result": "no_hit",
        }
        state = {
            "trades": {
                "T-414722e3": {
                    "trade_id": "T-414722e3",
                    "atr_value": 27.62336362,
                    "fixed_8_model_first_hit": "tp1",
                    "fixed_8_tp1_first_hit_at": "2026-06-04T13:38:29.3400707Z",
                    "fixed_12_model_first_hit": "tp1",
                    "fixed_12_tp1_first_hit_at": "2026-06-04T13:38:29.3400707Z",
                    "fixed_16_model_first_hit": "tp1",
                    "fixed_16_tp1_first_hit_at": "2026-06-04T13:38:29.3400707Z",
                }
            }
        }

        normalized = normalizer.normalize_row(row, state)

        self.assertEqual(normalized["classification"]["overall"], "HELPED")
        self.assertEqual(normalized["classification"]["by_model"]["fixed_8"], "HELPED")
        self.assertEqual(normalized["classification"]["by_model"]["structural_dynamic"], "SAME")
        self.assertEqual(normalized["atr_value"], 27.62336362)
        self.assertEqual(
            normalized["models"]["fixed_8"]["first_hit_at"],
            "2026-06-04T13:38:29.3400707Z",
        )

    def test_missing_trade_is_backfilled_and_backup_created(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp = Path(tmp_dir)
            research_path = tmp / "research.jsonl"
            state_path = tmp / "state.json"
            research_path.write_text(
                json.dumps({
                    "trade_id": "T-existing",
                    "symbol": "NQM6",
                    "direction": "long",
                    "entry_price": 100.0,
                    "original_stop": 90.0,
                    "actual_result": "flat",
                    "closed_at": "2026-06-01T10:00:00Z",
                    "post_be_first_seen_at": "2026-06-01T10:00:00Z",
                    "fixed_8_model_result": "tp1",
                    "fixed_12_model_result": "no_hit",
                    "fixed_16_model_result": "no_hit",
                    "structural_dynamic_model_result": "no_hit",
                }) + "\n",
                encoding="utf-8",
            )
            state_path.write_text(
                json.dumps({
                    "trades": {
                        "T-ce62f567": {
                            "trade_id": "T-ce62f567",
                            "status": "closed",
                            "moved_to_be": True,
                            "symbol": "NQM6",
                            "direction": "long",
                            "entry_price": 30439.75,
                            "original_stop": 30415.75,
                            "tp1_price": 30463.75,
                            "be_trigger": 30451.75,
                            "be_hit_at": "2026-06-02T13:41:51.3129814Z",
                            "closed_at": "2026-06-02T09:03:12.390174",
                            "exit_price": 30415.75,
                            "exit_reason": "flatten_symbol",
                            "total_profit": 0.0,
                            "atr_value": 23.19618078,
                            "post_be_first_seen_at": "2026-06-02T13:41:51.3129814Z",
                            "post_be_last_updated_at": "2026-06-02T09:03:12.390174",
                            "fixed_8_model_first_hit": "tp1",
                            "fixed_8_tp1_first_hit_at": "2026-06-02T13:41:51.3129814Z",
                            "fixed_8_tp1_would_hit": True,
                            "fixed_8_stop_price": 30437.75,
                            "fixed_8_tp1_price": 30441.75,
                        }
                    }
                }),
                encoding="utf-8",
            )

            summary = normalizer.normalize_file(research_path, state_path, tmp)
            rows = [json.loads(line) for line in research_path.read_text(encoding="utf-8").splitlines()]

            self.assertEqual(summary["old_row_count"], 1)
            self.assertEqual(summary["new_row_count"], 2)
            self.assertEqual(summary["backfilled_trade_ids"], ["T-ce62f567"])
            self.assertTrue(Path(summary["backup_path"]).exists())
            self.assertEqual({row["schema_version"] for row in rows}, {2})
            self.assertIn("T-ce62f567", {row["trade_id"] for row in rows})


if __name__ == "__main__":
    unittest.main()

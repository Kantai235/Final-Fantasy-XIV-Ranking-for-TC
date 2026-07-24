from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fflogs_pipeline import state_store


class StateStoreTest(unittest.TestCase):
    def test_write_migrates_inline_checked_reports_without_losing_records(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "data" / "state.json"
            state = {
                "last_scanned_at": 1780000000000,
                "encounters": {
                    "ultimate_bahamut": {
                        "checked_reports": {
                            "old_report": {"status": "skipped_no_clear", "processed_at": 1780000000000},
                            "saved_report": {"status": "saved", "processed_at": 1780000001000},
                        },
                        "processed_reports": {},
                    },
                },
            }

            state_store.write_state(state_path, state)

            main_state = state_store.read_json(state_path, {})
            shard_path = state_store.checked_reports_shard_path(state_path, "ultimate_bahamut")
            shard = state_store.read_json(shard_path, {})
            restored = state_store.load_state(state_path)

            self.assertNotIn("checked_reports", main_state["encounters"]["ultimate_bahamut"])
            self.assertEqual(
                main_state[state_store.CHECKED_REPORTS_STORAGE_FIELD],
                {"format": state_store.CHECKED_REPORTS_STORAGE_FORMAT, "path": state_store.CHECKED_REPORTS_DIRECTORY},
            )
            self.assertEqual(shard, state["encounters"]["ultimate_bahamut"]["checked_reports"])
            self.assertEqual(
                restored["encounters"]["ultimate_bahamut"]["checked_reports"],
                state["encounters"]["ultimate_bahamut"]["checked_reports"],
            )

    def test_load_merges_interrupted_migration_with_newer_shard_record(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            state_path = Path(directory) / "data" / "state.json"
            shard_path = state_store.checked_reports_shard_path(state_path, "savage_m1s")
            state_path.parent.mkdir(parents=True, exist_ok=True)
            shard_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(
                json.dumps(
                    {
                        "encounters": {
                            "savage_m1s": {
                                "checked_reports": {
                                    "report_a": {
                                        "status": "skipped_no_clear",
                                        "processed_at": 100,
                                        "legacy_reason": "old",
                                    },
                                },
                            },
                        },
                    },
                ),
                encoding="utf-8",
            )
            shard_path.write_text(
                json.dumps(
                    {
                        "report_a": {
                            "status": "saved",
                            "processed_at": 200,
                            "has_clear": True,
                        },
                        "report_b": {"status": "skipped_inaccessible", "processed_at": 150},
                    },
                ),
                encoding="utf-8",
            )

            restored = state_store.load_state(state_path)
            reports = restored["encounters"]["savage_m1s"]["checked_reports"]

            self.assertEqual(reports["report_a"]["status"], "saved")
            self.assertEqual(reports["report_a"]["processed_at"], 200)
            self.assertEqual(reports["report_a"]["legacy_reason"], "old")
            self.assertTrue(reports["report_a"]["has_clear"])
            self.assertEqual(reports["report_b"]["status"], "skipped_inaccessible")

    def test_invalid_encounter_key_cannot_escape_shard_directory(self) -> None:
        with self.assertRaises(RuntimeError):
            state_store.checked_reports_shard_path(Path("data/state.json"), "../outside")


if __name__ == "__main__":
    unittest.main()

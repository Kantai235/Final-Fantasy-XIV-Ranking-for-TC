from __future__ import annotations

import unittest

import compact_state


class CompactStateTest(unittest.TestCase):
    def test_removes_redundant_checkpoint_iso_without_dropping_status(self) -> None:
        state = {
            "encounters": {
                "ultimate_bahamut": {
                    "checked_reports": {
                        "saved_report": {
                            "status": "saved",
                            "processed_at": 1780000000000,
                            "processed_at_iso": "2026-05-28T15:06:40+00:00",
                            "mixed_report_dispatch_revision": "mixed_report_dispatch_2026_06_05",
                        },
                        "legacy_report": {
                            "status": "skipped_no_clear",
                            "processed_at_iso": "2026-05-28T15:06:41+00:00",
                        },
                    },
                    "processed_reports": {
                        "pending_report": {
                            "status": "skipped_no_traditional_chinese_players",
                            "processed_at": 1780000001000,
                            "processed_at_iso": "2026-05-28T15:06:41+00:00",
                        },
                    },
                },
            },
        }

        summary = compact_state.compact_report_checkpoint_timestamps(state)

        checked_reports = state["encounters"]["ultimate_bahamut"]["checked_reports"]
        processed_reports = state["encounters"]["ultimate_bahamut"]["processed_reports"]
        self.assertEqual(summary["removed_redundant_processed_at_iso"], 2)
        self.assertNotIn("processed_at_iso", checked_reports["saved_report"])
        self.assertNotIn("processed_at_iso", processed_reports["pending_report"])
        self.assertEqual(checked_reports["saved_report"]["status"], "saved")
        self.assertEqual(checked_reports["saved_report"]["processed_at"], 1780000000000)
        self.assertIn("processed_at_iso", checked_reports["legacy_report"])

    def test_processed_report_duplicate_can_match_after_timestamp_compaction(self) -> None:
        state = {
            "encounters": {
                "ultimate_bahamut": {
                    "checked_reports": {
                        "same_report": {
                            "status": "skipped_no_clear",
                            "processed_at": 1780000000000,
                        },
                    },
                    "processed_reports": {
                        "same_report": {
                            "status": "skipped_no_clear",
                            "processed_at": 1780000000000,
                            "processed_at_iso": "2026-05-28T15:06:40+00:00",
                        },
                    },
                },
            },
        }

        compact_state.compact_report_checkpoint_timestamps(state)
        summary = compact_state.compact_processed_reports(state)

        encounter_state = state["encounters"]["ultimate_bahamut"]
        self.assertEqual(summary["removed_duplicate_processed_reports"], 1)
        self.assertEqual(encounter_state["processed_reports"], {})


if __name__ == "__main__":
    unittest.main()

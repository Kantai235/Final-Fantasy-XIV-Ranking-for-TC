from __future__ import annotations

import unittest

import backfill_gcd_coverage as local_gcd
import backfill_gcd_coverage_xivanalysis as xiv_gcd


class XivanalysisGcdBackfillTest(unittest.TestCase):
    def test_parse_english_checklist_percent(self) -> None:
        text = """
        Checklist
        Always be casting
        98.3%
        Use your cooldowns
        100.0%
        """

        self.assertEqual(xiv_gcd.parse_xivanalysis_gcd_percent(text), 98.3)

    def test_parse_localized_gcd_coverage_percent(self) -> None:
        self.assertEqual(xiv_gcd.parse_xivanalysis_gcd_percent("GCD覆蓋率: 98.30%"), 98.3)
        self.assertEqual(xiv_gcd.parse_xivanalysis_gcd_percent("GCD覆盖率：99.58%"), 99.58)

    def test_apply_xivanalysis_coverage_uses_current_shared_version(self) -> None:
        candidate = local_gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="ABC",
            report={},
            fight={"fight_id": 1},
            player={"name": "測試玩家", "server": "測試伺服器", "job": "Ninja", "dps": 1, "fflogs_id": 7},
            sort_time=0,
        )

        xiv_gcd.apply_xivanalysis_coverage(
            candidate,
            percent=98.3,
            url="https://xivanalysis.com/fflogs/ABC/1/7",
            checked_at_iso="2026-05-17T00:00:00+00:00",
        )

        coverage = candidate.player["gcd_coverage"]
        status = candidate.player["gcd_coverage_status"]
        self.assertEqual(coverage["percent"], 98.3)
        self.assertEqual(coverage["source"], xiv_gcd.XIVANALYSIS_GCD_SOURCE)
        self.assertEqual(coverage["calculation_version"], local_gcd.GCD_CALCULATION_VERSION)
        self.assertTrue(xiv_gcd.gcd_source_is_current_xivanalysis(candidate.player))
        self.assertEqual(status["source"], xiv_gcd.XIVANALYSIS_GCD_SOURCE)


if __name__ == "__main__":
    unittest.main()

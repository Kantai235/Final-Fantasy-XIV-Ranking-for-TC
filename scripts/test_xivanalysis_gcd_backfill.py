from __future__ import annotations

import unittest

import audit_xivanalysis_gcd_sample as audit_gcd
import backfill_gcd_coverage as local_gcd
import backfill_gcd_coverage_xivanalysis as xiv_gcd


class XivanalysisGcdBackfillTest(unittest.TestCase):
    def make_audit_fight(
        self,
        *,
        encounter_key: str,
        report_code: str,
        fight_id: int,
        jobs: list[str],
        category: str = "極",
    ) -> audit_gcd.FightGroup:
        candidates = [
            local_gcd.GcdCandidate(
                encounter_key=encounter_key,
                encounter={"name": f"測試副本 {encounter_key}", "category": category},
                ranking={},
                report_code=report_code,
                report={},
                fight={"fight_id": fight_id},
                player={
                    "name": f"測試玩家 {index}",
                    "server": "測試伺服器",
                    "job": job,
                    "dps": 1,
                    "fflogs_id": index,
                },
                sort_time=0,
            )
            for index, job in enumerate(jobs, start=1)
        ]
        return audit_gcd.FightGroup(
            encounter_key=encounter_key,
            encounter_name=f"測試副本 {encounter_key}",
            category=category,
            report_code=report_code,
            fight_id=fight_id,
            candidates=candidates,
        )

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

    def test_modules_not_found_page_is_retryable(self) -> None:
        text = "Modules not found. A new version has probably been deployed."

        self.assertTrue(xiv_gcd.is_retryable_xivanalysis_page(text))
        self.assertFalse(xiv_gcd.is_terminal_xivanalysis_error(text))

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

    def test_audit_sampling_uses_sample_size_per_encounter(self) -> None:
        fights = [
            self.make_audit_fight(encounter_key="extreme_fixture_a", report_code=f"A{index}", fight_id=index, jobs=["Paladin"])
            for index in range(1, 6)
        ] + [
            self.make_audit_fight(encounter_key="extreme_fixture_b", report_code=f"B{index}", fight_id=index, jobs=["Warrior"])
            for index in range(1, 6)
        ]

        sample = audit_gcd.sample_fights(
            fights,
            sample_size=2,
            seed="fixture",
            required_jobs=set(),
        )

        self.assertEqual(len(sample.fights), 4)
        self.assertEqual(sample.summaries["extreme_fixture_a"].selected_fights, 2)
        self.assertEqual(sample.summaries["extreme_fixture_b"].selected_fights, 2)

    def test_audit_sampling_adds_fights_for_missing_job_coverage(self) -> None:
        fights = [
            self.make_audit_fight(encounter_key="extreme_fixture", report_code="A", fight_id=1, jobs=["Paladin"]),
            self.make_audit_fight(encounter_key="extreme_fixture", report_code="B", fight_id=2, jobs=["Warrior"]),
            self.make_audit_fight(encounter_key="extreme_fixture", report_code="C", fight_id=3, jobs=["WhiteMage"]),
        ]

        sample = audit_gcd.sample_fights(
            fights,
            sample_size=1,
            seed="fixture",
            required_jobs={"Paladin", "Warrior", "WhiteMage"},
        )
        summary = sample.summaries["extreme_fixture"]

        self.assertEqual(len(sample.fights), 3)
        self.assertEqual(summary.base_selected_fights, 1)
        self.assertEqual(summary.supplemental_fights, 2)
        self.assertEqual(set(summary.covered_jobs), {"Paladin", "Warrior", "WhiteMage"})
        self.assertEqual(summary.missing_jobs, [])

    def test_audit_sampling_reports_unavailable_required_jobs(self) -> None:
        fights = [
            self.make_audit_fight(encounter_key="extreme_fixture", report_code="A", fight_id=1, jobs=["Paladin"]),
            self.make_audit_fight(encounter_key="extreme_fixture", report_code="B", fight_id=2, jobs=["Warrior"]),
        ]

        sample = audit_gcd.sample_fights(
            fights,
            sample_size=2,
            seed="fixture",
            required_jobs={"Paladin", "Warrior", "Pictomancer"},
        )
        summary = sample.summaries["extreme_fixture"]

        self.assertEqual(set(summary.covered_jobs), {"Paladin", "Warrior"})
        self.assertEqual(summary.missing_jobs, ["Pictomancer"])
        self.assertEqual(summary.unavailable_jobs, ["Pictomancer"])


if __name__ == "__main__":
    unittest.main()

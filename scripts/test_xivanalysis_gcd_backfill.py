from __future__ import annotations

import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import audit_xivanalysis_gcd_sample as audit_gcd
import backfill_gcd_coverage as local_gcd
import backfill_gcd_coverage_xivanalysis as xiv_gcd
import recompute_xivanalysis_gcd_audit as recompute_gcd


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

    def test_display_percent_matches_xivanalysis_to_fixed_one_decimal(self) -> None:
        self.assertEqual(audit_gcd.display_percent(98.25), 98.3)
        self.assertEqual(
            audit_gcd.display_percent_from_coverage(
                {"covered_time_ms": 9825, "denominator_ms": 10000},
                None,
            ),
            98.3,
        )

    def test_recompute_preserves_xivanalysis_page_zero(self) -> None:
        row = {
            "current_percent": 0.0,
            "current_source": "xivanalysis_page",
            "stored_percent": 0.0,
            "stored_source": "xivanalysis_page",
            "xivanalysis_url": "https://xivanalysis.com/fflogs/example/1/2",
        }

        self.assertTrue(recompute_gcd.should_preserve_xivanalysis_page_zero(row, 0.0))
        coverage = recompute_gcd.xivanalysis_page_zero_coverage(row)
        self.assertEqual(coverage["source"], "xivanalysis_page")
        self.assertEqual(audit_gcd.display_percent_from_coverage(coverage, None), 0.0)

    def test_recompute_does_not_preserve_nonzero_xivanalysis_page(self) -> None:
        row = {
            "current_percent": 97.5,
            "current_source": "xivanalysis_page",
            "stored_percent": 97.5,
            "stored_source": "xivanalysis_page",
        }

        self.assertFalse(recompute_gcd.should_preserve_xivanalysis_page_zero(row, 97.5))

    def test_recompute_does_not_preserve_local_zero_without_page_source(self) -> None:
        row = {
            "current_percent": 0.0,
            "current_source": "fflogs_raw_events",
            "stored_percent": 0.0,
            "stored_source": "fflogs_raw_events",
        }

        self.assertFalse(recompute_gcd.should_preserve_xivanalysis_page_zero(row, 0.0))

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

    def test_audit_cache_enriches_full_fight_list_without_overwriting_fflogs_metadata(self) -> None:
        candidate = local_gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="ABC",
            report={},
            fight={
                "fight_id": 2,
                "start_time": 1000,
                "end_time": 9000,
                "players": [{"name": "Fixture Player", "fflogs_id": 7}],
            },
            player={"name": "Fixture Player", "server": "Fixture Server", "job": "BlackMage", "dps": 1, "fflogs_id": 7},
            sort_time=0,
        )

        with TemporaryDirectory() as temp_dir:
            cache = xiv_gcd.GcdAuditCache(Path(temp_dir))
            cache.write_report_fight_metadata(candidate, {"id": 2, "combatTime": 7600})

            self.assertEqual(cache.read_report_fight(candidate)["combatTime"], 7600)
            self.assertEqual(cache.find_report_fight_by_id("ABC", 2)["combatTime"], 7600)

            cache.write_fflogs_payload(
                "report_fights",
                candidate,
                {"fights": [{"id": 1, "combatTime": 1000}, {"id": 2, "combatTime": 8000}]},
            )
            cache.write_report_fight_metadata(
                candidate,
                {
                    "id": 2,
                    "combatTime": 7000,
                    "players": [{"name": "Fixture Player", "fflogs_id": 7}],
                },
            )

            enriched = cache.read_report_fight(candidate)
            self.assertEqual(enriched["combatTime"], 8000)
            self.assertEqual(enriched["players"], [{"name": "Fixture Player", "fflogs_id": 7}])
            self.assertEqual(cache.find_report_fight_by_id("ABC", 2)["combatTime"], 8000)

            cache.write_fflogs_payload(
                "report_fights",
                candidate,
                {
                    "data": {
                        "fights": [{"id": 2, "combatTime": 8200}],
                        "friendlies": [],
                        "enemies": [],
                    }
                },
            )

            preserved = cache.read_report_fight(candidate)
            self.assertEqual(preserved["combatTime"], 8200)
            self.assertEqual(preserved["players"], [{"name": "Fixture Player", "fflogs_id": 7}])

            thin_candidate = local_gcd.GcdCandidate(
                encounter_key="fixture",
                encounter={},
                ranking={},
                report_code="ABC",
                report={},
                fight={"fight_id": 2, "start_time": 1000, "end_time": 9000},
                player={
                    "name": "Fixture Player",
                    "server": "Fixture Server",
                    "job": "BlackMage",
                    "dps": 1,
                    "fflogs_id": 7,
                },
                sort_time=0,
            )
            fallback = xiv_gcd.LocalGcdFallback(audit_cache=cache, cache_only=True)

            calculation_fight = fallback._calculation_fight(thin_candidate)

            self.assertEqual(calculation_fight["players"], [{"name": "Fixture Player", "fflogs_id": 7}])

    def test_local_fallback_rejects_empty_graphql_raw_events_and_accepts_proxy_events(self) -> None:
        self.assertIsNone(xiv_gcd.LocalGcdFallback._usable_raw_event_payload([]))
        self.assertIsNone(xiv_gcd.LocalGcdFallback._usable_raw_event_payload(["not an event"]))

        proxy_events = xiv_gcd.LocalGcdFallback._usable_proxy_event_payload(
            {
                "events": [
                    {"type": "cast", "sourceID": 7},
                    "not an event",
                    {"type": "calculateddamage", "sourceID": 7},
                ],
            }
        )

        self.assertEqual(
            proxy_events,
            [
                {"type": "cast", "sourceID": 7},
                {"type": "calculateddamage", "sourceID": 7},
            ],
        )

    def test_audit_cache_round_trips_xivanalysis_answer_by_player_identity(self) -> None:
        candidate = local_gcd.GcdCandidate(
            encounter_key="fixture",
            encounter={},
            ranking={},
            report_code="ABC",
            report={},
            fight={"fight_id": 2, "start_time": 1000, "end_time": 9000},
            player={"name": "Fixture Player", "server": "Fixture Server", "job": "BlackMage", "dps": 1, "fflogs_id": 7},
            sort_time=0,
        )

        with TemporaryDirectory() as temp_dir:
            cache = xiv_gcd.GcdAuditCache(Path(temp_dir))
            cache.write_xivanalysis_result(
                candidate,
                percent=98.345,
                url="https://xivanalysis.com/fflogs/ABC/2/7",
            )

            cached = cache.read_xivanalysis_result(candidate)

        self.assertIsNotNone(cached)
        assert cached is not None
        self.assertEqual(cached["kind"], "xivanalysis_gcd_percent")
        self.assertEqual(cached["percent"], 98.34)
        self.assertEqual(cached["source"], xiv_gcd.XIVANALYSIS_GCD_SOURCE)
        self.assertEqual(cached["identity"]["report_code"], "ABC")
        self.assertEqual(cached["identity"]["fight_id"], 2)
        self.assertEqual(cached["identity"]["fflogs_id"], 7)

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

    def test_audit_filter_fights_by_encounter_keys(self) -> None:
        fights = [
            self.make_audit_fight(encounter_key="savage_fixture_a", report_code="A", fight_id=1, jobs=["Paladin"]),
            self.make_audit_fight(encounter_key="savage_fixture_b", report_code="B", fight_id=2, jobs=["Paladin"]),
        ]

        self.assertIs(audit_gcd.filter_fights_by_encounter_keys(fights, set()), fights)
        filtered = audit_gcd.filter_fights_by_encounter_keys(fights, {"savage_fixture_b"})

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered[0].encounter_key, "savage_fixture_b")

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

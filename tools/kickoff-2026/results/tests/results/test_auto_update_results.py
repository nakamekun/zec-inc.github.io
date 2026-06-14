from __future__ import annotations

import argparse
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "results" / "auto_update_results.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
spec = importlib.util.spec_from_file_location("auto_update_results", SCRIPT_PATH)
auto_update_results = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["auto_update_results"] = auto_update_results
spec.loader.exec_module(auto_update_results)


def match(kickoff="2026-06-12T00:00:00Z"):
    return auto_update_results.MatchCandidate(
        match_id="match-001",
        match_number=1,
        kickoff_utc=auto_update_results.parse_utc(kickoff),
        home_team_id="mexico",
        away_team_id="south-africa",
        home_team_name="Mexico",
        away_team_name="South Africa",
        match_centre_url="https://www.fifa.com/en/match-centre",
    )


class AutoUpdateResultsTests(unittest.TestCase):
    def test_kickoff_before_is_not_target(self):
        targets = auto_update_results.select_targets([match()], {}, {"matches": {}}, auto_update_results.parse_utc("2026-06-11T23:59:00Z"))
        self.assertEqual(targets, [])

    def test_two_hours_nine_minutes_is_not_target(self):
        targets = auto_update_results.select_targets([match()], {}, {"matches": {}}, auto_update_results.parse_utc("2026-06-12T02:09:00Z"))
        self.assertEqual(targets, [])

    def test_two_hours_ten_minutes_is_first_check(self):
        targets = auto_update_results.select_targets([match()], {}, {"matches": {}}, auto_update_results.parse_utc("2026-06-12T02:10:00Z"))
        self.assertEqual(targets[0].check_type, "first-check")

    def test_three_hours_is_final_check(self):
        targets = auto_update_results.select_targets([match()], {}, {"matches": {}}, auto_update_results.parse_utc("2026-06-12T03:00:00Z"))
        self.assertEqual(targets[0].check_type, "final-check")

    def test_finished_is_skipped(self):
        targets = auto_update_results.select_targets(
            [match()],
            {"match-001": {"matchId": "match-001", "status": "fullTime"}},
            {"matches": {}},
            auto_update_results.parse_utc("2026-06-12T03:00:00Z"),
        )
        self.assertEqual(targets, [])

    def test_failed_attempt_is_retryable(self):
        targets = auto_update_results.select_targets(
            [match()],
            {},
            {"matches": {"match-001": {"firstCheckAt": "2026-06-12T02:10:00Z", "lastStatus": "provider_error"}}},
            auto_update_results.parse_utc("2026-06-12T02:20:00Z"),
        )
        self.assertEqual(len(targets), 1)

    def test_final_result_captured_is_skipped(self):
        targets = auto_update_results.select_targets(
            [match()],
            {},
            {"matches": {"match-001": {"finalResultCaptured": True}}},
            auto_update_results.parse_utc("2026-06-12T03:00:00Z"),
        )
        self.assertEqual(targets, [])

    def test_force_rechecks_final_result_captured(self):
        targets = auto_update_results.select_targets(
            [match()],
            {},
            {"matches": {"match-001": {"finalResultCaptured": True}}},
            auto_update_results.parse_utc("2026-06-12T03:00:00Z"),
            force=True,
        )
        self.assertEqual(len(targets), 1)

    def test_dry_run_does_not_modify_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map = root / "match-id-map.json"
            manual = root / "manual-match-results.json"
            state = root / "auto-update-state.json"
            feed = root / "feed.json"
            match_map.write_text(json.dumps({"matches": [{
                "matchId": "match-001",
                "matchNumber": 1,
                "kickoffUTC": "2026-06-12T00:00:00Z",
                "homeTeamId": "mexico",
                "homeTeamName": "Mexico",
                "awayTeamId": "south-africa",
                "awayTeamName": "South Africa",
            }]}), encoding="utf-8")
            manual.write_text('{"matches":[]}\n', encoding="utf-8")
            state.write_text('{"matches":{}}\n', encoding="utf-8")
            feed.write_text(json.dumps({"matches": {"match-001": {"status": "finished", "homeScore": 2, "awayScore": 0}}}), encoding="utf-8")
            before_manual = manual.read_text(encoding="utf-8")
            before_state = state.read_text(encoding="utf-8")
            args = argparse.Namespace(
                match_map=match_map,
                manual_results=manual,
                state=state,
                result_feed=feed,
                now="2026-06-12T03:00:00Z",
                dry_run=True,
                force=False,
                skip_generators=True,
            )
            targets, outcomes, updates = auto_update_results.run_update(args)
            self.assertEqual(len(targets), 1)
            self.assertEqual(outcomes[0][1].status, "found")
            self.assertEqual(outcomes[0][2], "updated")
            self.assertEqual(len(updates), 1)
            self.assertEqual(manual.read_text(encoding="utf-8"), before_manual)
            self.assertEqual(state.read_text(encoding="utf-8"), before_state)

    def test_group_standings_regeneration_runner_is_called(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map = root / "match-id-map.json"
            manual = root / "manual-match-results.json"
            state = root / "auto-update-state.json"
            feed = root / "feed.json"
            match_map.write_text(json.dumps({"matches": [{
                "matchId": "match-001",
                "kickoffUTC": "2026-06-12T00:00:00Z",
                "homeTeamId": "mexico",
                "homeTeamName": "Mexico",
                "awayTeamId": "south-africa",
                "awayTeamName": "South Africa",
            }]}), encoding="utf-8")
            manual.write_text('{"matches":[]}\n', encoding="utf-8")
            state.write_text('{"matches":{}}\n', encoding="utf-8")
            feed.write_text(json.dumps({"matches": {"match-001": {"status": "finished", "homeScore": 2, "awayScore": 0}}}), encoding="utf-8")
            calls = []
            args = argparse.Namespace(
                match_map=match_map,
                manual_results=manual,
                state=state,
                result_feed=feed,
                now="2026-06-12T03:00:00Z",
                dry_run=False,
                force=False,
                skip_generators=False,
            )
            auto_update_results.run_update(args, generator_runner=lambda: calls.append("ran"))
            self.assertEqual(calls, ["ran"])
            payload = json.loads(manual.read_text(encoding="utf-8"))
            self.assertEqual(payload["matches"][0]["source"], "zec-auto")

    def test_provider_not_final_yet_does_not_change_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map, manual, state, feed = write_basic_files(root, {"status": "inProgress", "homeScore": 1, "awayScore": 0})
            args = basic_args(match_map, manual, state, feed)
            auto_update_results.run_update(args)
            self.assertEqual(json.loads(manual.read_text(encoding="utf-8"))["matches"], [])
            state_payload = json.loads(state.read_text(encoding="utf-8"))
            self.assertEqual(state_payload["matches"]["match-001"]["lastProviderStatus"], "not_final_yet")
            self.assertFalse(state_payload["matches"]["match-001"]["finalResultCaptured"])

    def test_low_confidence_does_not_change_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map, manual, state, feed = write_basic_files(root, {"status": "finished", "homeScore": 2, "awayScore": 0, "confidence": 0.5})
            args = basic_args(match_map, manual, state, feed)
            auto_update_results.run_update(args)
            self.assertEqual(json.loads(manual.read_text(encoding="utf-8"))["matches"], [])
            self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["matches"]["match-001"]["lastStatus"], "low_confidence")

    def test_existing_same_result_is_unchanged(self):
        existing = {
            "matchId": "match-001",
            "status": "fullTime",
            "homeScore": 2,
            "awayScore": 0,
            "homePenaltyScore": None,
            "awayPenaltyScore": None,
            "winnerTeamId": "mexico",
            "currentMinute": None,
            "resultUpdatedAt": "2026-06-12T03:00:00Z",
            "source": "zec-curated",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map, manual, state, feed = write_basic_files(root, {"status": "finished", "homeScore": 2, "awayScore": 0})
            manual.write_text(json.dumps({"matches": [existing]}) + "\n", encoding="utf-8")
            args = basic_args(match_map, manual, state, feed)
            args.force = True
            _, outcomes, updates = auto_update_results.run_update(args)
            self.assertEqual(outcomes[0][2], "unchanged")
            self.assertEqual(updates, [])

    def test_existing_conflicting_result_is_not_overwritten(self):
        existing = {
            "matchId": "match-001",
            "status": "fullTime",
            "homeScore": 1,
            "awayScore": 0,
            "homePenaltyScore": None,
            "awayPenaltyScore": None,
            "winnerTeamId": "mexico",
            "currentMinute": None,
            "resultUpdatedAt": "2026-06-12T03:00:00Z",
            "source": "zec-curated",
        }
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map, manual, state, feed = write_basic_files(root, {"status": "finished", "homeScore": 2, "awayScore": 0})
            manual.write_text(json.dumps({"matches": [existing]}) + "\n", encoding="utf-8")
            args = basic_args(match_map, manual, state, feed)
            args.force = True
            _, outcomes, updates = auto_update_results.run_update(args)
            self.assertEqual(outcomes[0][2], "conflict")
            self.assertEqual(updates, [])
            self.assertEqual(json.loads(manual.read_text(encoding="utf-8"))["matches"][0]["homeScore"], 1)

    def test_monitoring_summary_counts_provider_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map, manual, state, feed = write_basic_files(root, {"status": "missing"})
            args = basic_args(match_map, manual, state, feed)
            _, outcomes, updates = auto_update_results.run_update(args)
            summary = auto_update_results.monitoring_summary(
                auto_update_results.load_match_candidates(match_map),
                auto_update_results.manual_results_by_match_id(json.loads(manual.read_text(encoding="utf-8"))),
                json.loads(state.read_text(encoding="utf-8")),
                [outcomes[0][0]],
                outcomes,
                updates,
                auto_update_results.parse_utc("2026-06-12T03:00:00Z"),
            )
            self.assertEqual(summary["providerFailureCount"], 1)
            self.assertEqual(summary["updatedCount"], 0)

    def test_monitoring_summary_flags_schedule_miss_suspected_for_overdue_target(self):
        target_match = match()
        target = auto_update_results.CheckTarget(match=target_match, check_type="final-check", current_result=None)
        summary = auto_update_results.monitoring_summary(
            [target_match],
            {},
            {"matches": {}},
            [target],
            [],
            [],
            auto_update_results.parse_utc("2026-06-12T03:25:00Z"),
        )
        self.assertTrue(summary["scheduleMissSuspected"])
        self.assertEqual(summary["overdueMatches"], ["match-001"])

    def test_summary_json_is_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map, manual, state, feed = write_basic_files(root, {"status": "finished", "homeScore": 2, "awayScore": 0})
            summary_path = root / "summary.json"
            args = basic_args(match_map, manual, state, feed)
            args.summary_json = summary_path
            auto_update_results.run_update(args)
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["targetCount"], 1)
            self.assertEqual(summary["updatedCount"], 1)

    def test_no_targets_does_not_rewrite_state_or_run_generators(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            match_map, manual, state, feed = write_basic_files(root, {"status": "finished", "homeScore": 2, "awayScore": 0})
            before_state = state.read_text(encoding="utf-8")
            calls = []
            args = basic_args(match_map, manual, state, feed)
            args.now = "2026-06-12T02:09:00Z"
            targets, _, updates = auto_update_results.run_update(args, generator_runner=lambda: calls.append("ran"))
            self.assertEqual(targets, [])
            self.assertEqual(updates, [])
            self.assertEqual(calls, [])
            self.assertEqual(state.read_text(encoding="utf-8"), before_state)


if __name__ == "__main__":
    unittest.main()


def write_basic_files(root: Path, feed_result: dict):
    match_map = root / "match-id-map.json"
    manual = root / "manual-match-results.json"
    state = root / "auto-update-state.json"
    feed = root / "feed.json"
    match_map.write_text(json.dumps({"matches": [{
        "matchId": "match-001",
        "matchNumber": 1,
        "kickoffUTC": "2026-06-12T00:00:00Z",
        "homeTeamId": "mexico",
        "homeTeamName": "Mexico",
        "awayTeamId": "south-africa",
        "awayTeamName": "South Africa",
    }]}), encoding="utf-8")
    manual.write_text('{"matches":[]}\n', encoding="utf-8")
    state.write_text('{"matches":{}}\n', encoding="utf-8")
    feed.write_text(json.dumps({"matches": {"match-001": feed_result}}), encoding="utf-8")
    return match_map, manual, state, feed


def basic_args(match_map: Path, manual: Path, state: Path, feed: Path):
    return argparse.Namespace(
        match_map=match_map,
        manual_results=manual,
        state=state,
        result_feed=feed,
        now="2026-06-12T03:00:00Z",
        dry_run=False,
        force=False,
        skip_generators=True,
        summary_json=None,
    )

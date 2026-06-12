from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "results" / "generate_match_results.py"
spec = importlib.util.spec_from_file_location("generate_match_results", SCRIPT_PATH)
generate_match_results = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["generate_match_results"] = generate_match_results
spec.loader.exec_module(generate_match_results)


MATCH_REFS = {
    "match-001": generate_match_results.MatchRef(
        match_id="match-001",
        home_team_id="mexico",
        away_team_id="south-africa",
    ),
    "match-002": generate_match_results.MatchRef(
        match_id="match-002",
        home_team_id="south-korea",
        away_team_id="czech-republic",
    ),
}


def valid_result(**overrides):
    result = {
        "matchId": "match-001",
        "status": "fullTime",
        "homeScore": 2,
        "awayScore": 1,
        "homePenaltyScore": None,
        "awayPenaltyScore": None,
        "winnerTeamId": "mexico",
        "currentMinute": None,
        "resultUpdatedAt": "2026-06-12T05:55:00Z",
        "source": "zec-curated",
    }
    result.update(overrides)
    return result


class GenerateMatchResultsTests(unittest.TestCase):
    def generate(self, matches, generated_at="2026-06-12T06:00:00Z"):
        return generate_match_results.generate_payload(
            {"matches": matches},
            MATCH_REFS,
            generated_at,
        )

    def generate_app(self, matches, generated_at="2026-06-12T06:00:00Z"):
        return generate_match_results.generate_app_payload(
            {"matches": matches},
            MATCH_REFS,
            generated_at,
        )

    def test_valid_full_time_result(self):
        payload = self.generate([valid_result()])
        self.assertEqual(payload["matches"][0]["matchId"], "match-001")
        self.assertEqual(payload["matches"][0]["status"], "fullTime")

    def test_valid_auto_source(self):
        payload = self.generate([valid_result(source="zec-auto")])
        self.assertEqual(payload["matches"][0]["source"], "zec-auto")

    def test_invalid_match_id(self):
        with self.assertRaisesRegex(ValueError, "Unknown matchId"):
            self.generate([valid_result(matchId="match-999")])

    def test_invalid_status(self):
        with self.assertRaisesRegex(ValueError, "invalid status"):
            self.generate([valid_result(status="officialFinal")])

    def test_duplicate_match_id(self):
        with self.assertRaisesRegex(ValueError, "Duplicate matchId"):
            self.generate([valid_result(), valid_result()])

    def test_winner_mismatch(self):
        with self.assertRaisesRegex(ValueError, "winnerTeamId does not match"):
            self.generate([valid_result(winnerTeamId="south-africa")])

    def test_penalty_score_invalid(self):
        with self.assertRaisesRegex(ValueError, "penalty scores are only allowed"):
            self.generate([valid_result(homePenaltyScore=4, awayPenaltyScore=3)])

    def test_generated_at_is_attached(self):
        payload = self.generate([valid_result()], generated_at="2026-06-12T06:30:00Z")
        self.assertEqual(payload["generatedAt"], "2026-06-12T06:30:00Z")

    def test_output_json_schema(self):
        payload = self.generate([valid_result()])
        self.assertEqual(payload["version"], 1)
        self.assertEqual(set(payload), {"version", "generatedAt", "matches"})
        self.assertEqual(
            set(payload["matches"][0]),
            {
                "matchId",
                "status",
                "homeScore",
                "awayScore",
                "homePenaltyScore",
                "awayPenaltyScore",
                "winnerTeamId",
                "currentMinute",
                "resultUpdatedAt",
                "source",
            },
        )

    def test_app_schema_maps_full_time_to_finished(self):
        payload = self.generate_app([valid_result()])
        self.assertEqual(set(payload), {"source", "results"})
        self.assertEqual(payload["source"]["updatedAt"], "2026-06-12T06:00:00Z")
        self.assertEqual(payload["results"][0]["status"], "finished")
        self.assertNotIn("currentMinute", payload["results"][0])

    def test_app_schema_maps_penalties_to_finished(self):
        payload = self.generate_app([
            valid_result(
                status="penalties",
                homeScore=1,
                awayScore=1,
                homePenaltyScore=4,
                awayPenaltyScore=3,
                winnerTeamId="mexico",
            )
        ])
        self.assertEqual(payload["results"][0]["status"], "finished")
        self.assertEqual(payload["results"][0]["homePenaltyScore"], 4)

    def test_app_schema_rejects_in_progress_status(self):
        with self.assertRaisesRegex(ValueError, "cannot be represented"):
            self.generate_app([
                valid_result(
                    status="inProgress",
                    homeScore=1,
                    awayScore=0,
                    winnerTeamId="mexico",
                    currentMinute=55,
                )
            ])


if __name__ == "__main__":
    unittest.main()

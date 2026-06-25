from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "results" / "generate_match_display_overrides.py"
sys.path.insert(0, str(SCRIPT_PATH.parent))
spec = importlib.util.spec_from_file_location("generate_match_display_overrides", SCRIPT_PATH)
generate_match_display_overrides = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["generate_match_display_overrides"] = generate_match_display_overrides
spec.loader.exec_module(generate_match_display_overrides)


MATCH_MAP = {
    "matches": [
        {
            "matchId": "match-073",
            "matchNumber": 73,
            "kickoffUTC": "2026-06-28T19:00:00Z",
            "homeTeamId": "runner-up-group-a",
            "awayTeamId": "runner-up-group-b",
        },
        {
            "matchId": "match-074",
            "matchNumber": 74,
            "kickoffUTC": "2026-06-29T20:30:00Z",
            "homeTeamId": "winner-group-e",
            "awayTeamId": "third-place-group-a-b-c-d-f",
        },
        {
            "matchId": "match-075",
            "matchNumber": 75,
            "kickoffUTC": "2026-06-30T01:00:00Z",
            "homeTeamId": "mexico",
            "homeTeamName": "Mexico",
            "awayTeamId": "canada",
            "awayTeamName": "Canada",
        },
        {
            "matchId": "match-013",
            "matchNumber": 13,
            "kickoffUTC": "2026-06-15T16:00:00Z",
            "homeTeamId": "spain",
            "homeTeamName": "Spain",
            "awayTeamId": "cape-verde",
            "awayTeamName": "Cape Verde",
        },
    ]
}

FIFA_CALENDAR = {
    "Results": [
        {
            "IdCompetition": "17",
            "IdSeason": "285023",
            "MatchNumber": 74,
            "Date": "2026-06-29T20:30:00Z",
            "Home": {"TeamName": [{"Description": "Spain"}], "ShortClubName": "Spain"},
            "Away": {"TeamName": [{"Description": "Canada"}], "ShortClubName": "Canada"},
        },
        {
            "IdCompetition": "17",
            "IdSeason": "285023",
            "MatchNumber": 73,
            "Date": "2026-06-28T19:00:00Z",
            "Home": {"TeamName": [{"Description": "South Africa"}], "ShortClubName": "South Africa"},
            "Away": {"TeamName": [{"Description": "Canada"}], "ShortClubName": "Canada"},
        },
    ]
}

STANDINGS = {
    "source": {
        "updatedAt": "2026-06-25T22:13:07Z",
    },
    "groups": [
        {
            "group": "Group A",
            "teams": [
                {"teamId": "mexico", "rank": 1},
                {"teamId": "south-africa", "rank": 2},
            ],
        },
        {
            "group": "Group B",
            "teams": [
                {"teamId": "switzerland", "rank": 1},
                {"teamId": "canada", "rank": 2},
            ],
        },
        {
            "group": "Group E",
            "teams": [
                {"teamId": "spain", "rank": 1},
                {"teamId": "japan", "rank": 2},
            ],
        },
    ],
}


class GenerateMatchDisplayOverridesTests(unittest.TestCase):
    def generate(self, manual=None):
        return generate_match_display_overrides.generate_payload(
            MATCH_MAP,
            STANDINGS,
            manual or {"matchOverrides": {}},
        )

    def generate_with_fifa(self, manual=None):
        return generate_match_display_overrides.generate_payload(
            MATCH_MAP,
            STANDINGS,
            manual or {"matchOverrides": {}},
            FIFA_CALENDAR,
        )

    def test_resolves_winner_and_runner_up_placeholders(self):
        payload = self.generate()
        match_073 = payload["matchOverrides"]["match-073"]
        self.assertEqual(match_073["homeTeamId"], "south-africa")
        self.assertEqual(match_073["awayTeamId"], "canada")
        self.assertTrue(match_073["isConfirmed"])
        self.assertEqual(match_073["updatedAt"], "2026-06-25T22:13:07Z")

    def test_skips_unresolved_third_place_placeholder_matchups(self):
        payload = self.generate()
        self.assertNotIn("match-074", payload["matchOverrides"])

    def test_fifa_calendar_direct_matchup_wins_over_standings_fallback(self):
        payload = self.generate_with_fifa()
        match_074 = payload["matchOverrides"]["match-074"]
        self.assertEqual(match_074["homeTeamId"], "spain")
        self.assertEqual(match_074["awayTeamId"], "canada")
        self.assertTrue(match_074["isConfirmed"])

    def test_fifa_calendar_can_confirm_runner_up_matchup_directly(self):
        payload = self.generate_with_fifa()
        match_073 = payload["matchOverrides"]["match-073"]
        self.assertEqual(match_073["homeTeamId"], "south-africa")
        self.assertEqual(match_073["awayTeamId"], "canada")

    def test_manual_override_wins(self):
        payload = self.generate({
            "matchOverrides": {
                "match-073": {
                    "homeTeamId": "mexico",
                    "awayTeamId": "canada",
                    "isConfirmed": True,
                    "updatedAt": "2026-06-26T00:00:00Z",
                }
            }
        })
        self.assertEqual(payload["matchOverrides"]["match-073"]["homeTeamId"], "mexico")
        self.assertEqual(payload["matchOverrides"]["match-073"]["updatedAt"], "2026-06-26T00:00:00Z")

    def test_app_schema(self):
        payload = self.generate()
        self.assertEqual(set(payload), {"source", "matchOverrides"})
        self.assertEqual(payload["source"]["updatedAt"], "2026-06-25T22:13:07Z")
        self.assertEqual(payload["source"]["generatedAt"], "2026-06-25T22:13:07Z")


if __name__ == "__main__":
    unittest.main()

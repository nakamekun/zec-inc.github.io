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
            "matchId": "match-081",
            "matchNumber": 81,
            "kickoffUTC": "2026-07-02T00:00:00Z",
            "homeTeamId": "winner-group-d",
            "awayTeamId": "third-place-group-b-e-f-i-j",
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
        {
            "matchId": "match-014",
            "matchNumber": 14,
            "kickoffUTC": "2026-06-15T19:00:00Z",
            "homeTeamId": "usa",
            "homeTeamName": "USA",
            "awayTeamId": "bosnia-and-herzegovina",
            "awayTeamName": "Bosnia and Herzegovina",
        },
        {
            "matchId": "match-015",
            "matchNumber": 15,
            "kickoffUTC": "2026-06-15T22:00:00Z",
            "homeTeamId": "south-africa",
            "homeTeamName": "South Africa",
            "awayTeamId": "canada",
            "awayTeamName": "Canada",
        },
        {
            "matchId": "match-016",
            "matchNumber": 16,
            "kickoffUTC": "2026-06-16T01:00:00Z",
            "homeTeamId": "germany",
            "homeTeamName": "Germany",
            "awayTeamId": "curacao",
            "awayTeamName": "Curaçao",
        },
    ]
}

FIFA_CALENDAR = {
    "Results": [
        {
            "IdCompetition": "17",
            "IdSeason": "285023",
            "MatchNumber": 81,
            "Date": "2026-07-02T00:00:00Z",
            "Home": {"TeamName": [{"Description": "USA"}], "ShortClubName": "USA"},
            "Away": {"TeamName": [{"Description": "Bosnia and Herzegovina"}], "ShortClubName": "Bosnia and Herzegovina"},
        },
        {
            "IdCompetition": "17",
            "IdSeason": "285023",
            "MatchNumber": 73,
            "Date": "2026-06-28T19:00:00Z",
            "Home": {"TeamName": [{"Description": "South Africa"}], "ShortClubName": "South Africa"},
            "Away": {"TeamName": [{"Description": "Canada"}], "ShortClubName": "Canada"},
        },
        {
            "IdCompetition": "17",
            "IdSeason": "285023",
            "MatchNumber": 74,
            "Date": "2026-06-29T20:30:00Z",
            "Home": {"TeamName": [{"Description": "Germany"}], "ShortClubName": "Germany"},
            "Away": None,
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

    def test_standings_do_not_generate_knockout_overrides(self):
        payload = self.generate()
        self.assertEqual(payload["matchOverrides"], {})

    def test_fifa_calendar_partial_matchup_generates_known_side_only(self):
        payload = self.generate_with_fifa()
        match_074 = payload["matchOverrides"]["match-074"]
        self.assertEqual(match_074["homeTeamId"], "germany")
        self.assertNotIn("awayTeamId", match_074)
        self.assertTrue(match_074["isConfirmed"])

    def test_fifa_calendar_direct_matchup_generates_override(self):
        payload = self.generate_with_fifa()
        match_081 = payload["matchOverrides"]["match-081"]
        self.assertEqual(match_081["homeTeamId"], "usa")
        self.assertEqual(match_081["awayTeamId"], "bosnia-and-herzegovina")
        self.assertTrue(match_081["isConfirmed"])

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

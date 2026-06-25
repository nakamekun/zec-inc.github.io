from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "results" / "generate_match_display_overrides.py"
spec = importlib.util.spec_from_file_location("generate_match_display_overrides", SCRIPT_PATH)
generate_match_display_overrides = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["generate_match_display_overrides"] = generate_match_display_overrides
spec.loader.exec_module(generate_match_display_overrides)


MATCH_MAP = {
    "matches": [
        {
            "matchId": "match-073",
            "homeTeamId": "runner-up-group-a",
            "awayTeamId": "runner-up-group-b",
        },
        {
            "matchId": "match-074",
            "homeTeamId": "winner-group-e",
            "awayTeamId": "third-place-group-a-b-c-d-f",
        },
        {
            "matchId": "match-075",
            "homeTeamId": "mexico",
            "awayTeamId": "canada",
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

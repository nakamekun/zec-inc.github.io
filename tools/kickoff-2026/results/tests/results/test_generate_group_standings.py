from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "results" / "generate_group_standings.py"
spec = importlib.util.spec_from_file_location("generate_group_standings", SCRIPT_PATH)
generate_group_standings = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["generate_group_standings"] = generate_group_standings
spec.loader.exec_module(generate_group_standings)


MATCH_REFS = {
    "match-001": generate_group_standings.MatchRef(
        match_id="match-001",
        group="Group A",
        home_team_id="mexico",
        away_team_id="south-africa",
    ),
    "match-002": generate_group_standings.MatchRef(
        match_id="match-002",
        group="Group A",
        home_team_id="south-korea",
        away_team_id="czech-republic",
    ),
    "match-003": generate_group_standings.MatchRef(
        match_id="match-003",
        group="Group A",
        home_team_id="mexico",
        away_team_id="south-korea",
    ),
}

GROUP_TEAMS = {
    "Group A": ["mexico", "south-africa", "south-korea", "czech-republic"],
}


def result(match_id="match-001", home_score=2, away_score=0, status="finished"):
    return {
        "matchId": match_id,
        "status": status,
        "homeScore": home_score,
        "awayScore": away_score,
        "homePenaltyScore": None,
        "awayPenaltyScore": None,
        "winnerTeamId": None,
        "resultUpdatedAt": "2026-06-12T05:55:00Z",
        "source": "zec-curated",
    }


class GenerateGroupStandingsTests(unittest.TestCase):
    def generate(self, results, overrides=None, generated_at="2026-06-12T06:00:00Z"):
        return generate_group_standings.generate_payload(
            {"source": {"name": "test"}, "results": results},
            overrides or {"groups": []},
            MATCH_REFS,
            GROUP_TEAMS,
            generated_at,
        )

    def group_a(self, payload):
        return payload["groups"][0]["teams"]

    def team(self, payload, team_id):
        return next(team for team in self.group_a(payload) if team["teamId"] == team_id)

    def test_no_finished_matches_all_zero(self):
        payload = self.generate([])
        self.assertEqual(sum(team["played"] for team in self.group_a(payload)), 0)
        self.assertEqual(len(self.group_a(payload)), 4)

    def test_one_home_win(self):
        payload = self.generate([result(home_score=2, away_score=0)])
        mexico = self.team(payload, "mexico")
        south_africa = self.team(payload, "south-africa")
        self.assertEqual(mexico["won"], 1)
        self.assertEqual(mexico["points"], 3)
        self.assertEqual(south_africa["lost"], 1)

    def test_one_away_win(self):
        payload = self.generate([result(home_score=0, away_score=1)])
        self.assertEqual(self.team(payload, "south-africa")["won"], 1)
        self.assertEqual(self.team(payload, "mexico")["lost"], 1)

    def test_draw(self):
        payload = self.generate([result(home_score=1, away_score=1)])
        self.assertEqual(self.team(payload, "mexico")["drawn"], 1)
        self.assertEqual(self.team(payload, "south-africa")["points"], 1)

    def test_goal_difference(self):
        payload = self.generate([result(home_score=3, away_score=1)])
        self.assertEqual(self.team(payload, "mexico")["goalDifference"], 2)
        self.assertEqual(self.team(payload, "south-africa")["goalDifference"], -2)

    def test_points_ordering(self):
        payload = self.generate([
            result(match_id="match-001", home_score=1, away_score=0),
            result(match_id="match-002", home_score=0, away_score=1),
        ])
        self.assertEqual(self.team(payload, "mexico")["rank"], 1)
        self.assertEqual(self.team(payload, "czech-republic")["rank"], 2)

    def test_goals_for_tiebreak(self):
        payload = self.generate([
            result(match_id="match-001", home_score=1, away_score=0),
            result(match_id="match-002", home_score=2, away_score=1),
        ])
        self.assertEqual(self.team(payload, "south-korea")["rank"], 1)
        self.assertEqual(self.team(payload, "mexico")["rank"], 2)

    def test_manual_rank_override(self):
        payload = self.generate(
            [result(home_score=2, away_score=0)],
            overrides={
                "groups": [
                    {
                        "group": "Group A",
                        "teams": [
                            {"teamId": "south-africa", "rank": 1},
                            {"teamId": "mexico", "rank": 2},
                            {"teamId": "south-korea", "rank": 3},
                            {"teamId": "czech-republic", "rank": 4},
                        ],
                    }
                ]
            },
        )
        self.assertEqual(self.team(payload, "south-africa")["rank"], 1)

    def test_known_non_group_match_is_ignored(self):
        payload = generate_group_standings.generate_payload(
            {"source": {"name": "test"}, "results": [result(match_id="match-073", home_score=0, away_score=1)]},
            {"groups": []},
            MATCH_REFS,
            GROUP_TEAMS,
            "2026-06-12T06:00:00Z",
            known_match_ids={"match-001", "match-002", "match-003", "match-073"},
        )
        self.assertEqual(sum(team["played"] for team in self.group_a(payload)), 0)

    def test_unknown_match_id_errors(self):
        with self.assertRaisesRegex(ValueError, "Unknown matchId"):
            self.generate([result(match_id="match-999")])

    def test_duplicate_team_validation(self):
        with self.assertRaisesRegex(ValueError, "duplicate teamId"):
            generate_group_standings.generate_payload(
                {"results": []},
                {"groups": []},
                MATCH_REFS,
                {"Group A": ["mexico", "mexico"]},
                "2026-06-12T06:00:00Z",
            )

    def test_generated_at_is_attached(self):
        payload = self.generate([], generated_at="2026-06-12T06:30:00Z")
        self.assertEqual(payload["source"]["generatedAt"], "2026-06-12T06:30:00Z")


if __name__ == "__main__":
    unittest.main()

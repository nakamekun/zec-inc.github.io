from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[2] / "scripts" / "results"
sys.path.insert(0, str(SCRIPT_DIR))

from providers.base import MatchContext  # noqa: E402
from providers.fifa_match_centre_provider import FifaMatchCentreProvider  # noqa: E402


def context() -> MatchContext:
    return MatchContext(
        match_id="match-001",
        match_number=1,
        kickoff_utc=datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc),
        home_team_id="mexico",
        away_team_id="south-africa",
        home_team_name="Mexico",
        away_team_name="South Africa",
        match_centre_url="https://www.fifa.com/en/match-centre",
    )


def page_for(match_payload: dict) -> str:
    payload = {"props": {"pageProps": {"matches": [match_payload]}}}
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(payload)}</script></html>'


def failing_json_loader(_: str):
    raise RuntimeError("fixture intentionally bypasses calendar API")


def calendar_payload(match_payload: dict) -> dict:
    return {"Results": [match_payload]}


def calendar_match(**overrides) -> dict:
    payload = {
        "IdCompetition": "17",
        "IdSeason": "285023",
        "IdMatch": "400021443",
        "MatchNumber": 1,
        "Date": "2026-06-12T00:00:00Z",
        "MatchStatus": 0,
        "ResultType": 1,
        "HomeTeamScore": 2,
        "AwayTeamScore": 0,
        "HomeTeamPenaltyScore": None,
        "AwayTeamPenaltyScore": None,
        "Winner": "43911",
        "Home": {
            "Score": 2,
            "IdCountry": "MEX",
            "TeamName": [{"Locale": "en-GB", "Description": "Mexico"}],
            "ShortClubName": "Mexico",
        },
        "Away": {
            "Score": 0,
            "IdCountry": "RSA",
            "TeamName": [{"Locale": "en-GB", "Description": "South Africa"}],
            "ShortClubName": "South Africa",
        },
    }
    payload.update(overrides)
    return payload


class FifaMatchCentreProviderTests(unittest.TestCase):
    def test_found_result_from_embedded_json(self):
        provider = FifaMatchCentreProvider(page_loader=lambda _: page_for({
            "matchNumber": 1,
            "date": "2026-06-12T00:00:00Z",
            "status": "finished",
            "homeTeam": {"name": "Mexico"},
            "awayTeam": {"name": "South Africa"},
            "homeScore": 2,
            "awayScore": 0,
        }), json_loader=failing_json_loader)
        outcome = provider.fetch_result(context())
        self.assertEqual(outcome.status, "found")
        self.assertGreaterEqual(outcome.confidence, 0.90)
        self.assertEqual(outcome.home_score, 2)
        self.assertEqual(outcome.winner_team_id, "mexico")

    def test_score_without_final_state_is_low_confidence(self):
        provider = FifaMatchCentreProvider(page_loader=lambda _: page_for({
            "matchNumber": 1,
            "date": "2026-06-12T00:00:00Z",
            "status": "live",
            "homeTeam": {"name": "Mexico"},
            "awayTeam": {"name": "South Africa"},
            "homeScore": 2,
            "awayScore": 0,
        }), json_loader=failing_json_loader)
        outcome = provider.fetch_result(context())
        self.assertIn(outcome.status, {"not_final_yet", "low_confidence"})

    def test_wrong_match_is_not_found(self):
        provider = FifaMatchCentreProvider(page_loader=lambda _: page_for({
            "matchNumber": 9,
            "date": "2026-06-14T00:00:00Z",
            "status": "finished",
            "homeTeam": {"name": "Germany"},
            "awayTeam": {"name": "Curacao"},
            "homeScore": 1,
            "awayScore": 0,
        }), json_loader=failing_json_loader)
        outcome = provider.fetch_result(context())
        self.assertEqual(outcome.status, "not_found")

    def test_found_result_from_calendar_api(self):
        provider = FifaMatchCentreProvider(json_loader=lambda _: calendar_payload(calendar_match()))
        outcome = provider.fetch_result(context())
        self.assertEqual(outcome.status, "found")
        self.assertEqual(outcome.raw_source_name, "fifa-calendar-api")
        self.assertGreaterEqual(outcome.confidence, 0.90)
        self.assertEqual(outcome.home_score, 2)
        self.assertEqual(outcome.away_score, 0)
        self.assertEqual(outcome.winner_team_id, "mexico")

    def test_calendar_api_accepts_team_aliases(self):
        korean_context = MatchContext(
            match_id="match-002",
            match_number=2,
            kickoff_utc=datetime(2026, 6, 12, 2, 0, tzinfo=timezone.utc),
            home_team_id="south-korea",
            away_team_id="czech-republic",
            home_team_name="South Korea",
            away_team_name="Czech Republic",
            match_centre_url="https://www.fifa.com/en/match-centre",
        )
        provider = FifaMatchCentreProvider(json_loader=lambda _: calendar_payload(calendar_match(
            MatchNumber=2,
            Date="2026-06-12T02:00:00Z",
            HomeTeamScore=2,
            AwayTeamScore=1,
            Home={"Score": 2, "TeamName": [{"Description": "Korea Republic"}], "ShortClubName": "Korea Republic"},
            Away={"Score": 1, "TeamName": [{"Description": "Czechia"}], "ShortClubName": "Czechia"},
        )))
        outcome = provider.fetch_result(korean_context)
        self.assertEqual(outcome.status, "found")
        self.assertEqual(outcome.home_score, 2)
        self.assertEqual(outcome.away_score, 1)
        self.assertEqual(outcome.winner_team_id, "south-korea")

    def test_calendar_api_scheduled_match_is_not_final_yet(self):
        provider = FifaMatchCentreProvider(json_loader=lambda _: calendar_payload(calendar_match(
            MatchStatus=1,
            HomeTeamScore=None,
            AwayTeamScore=None,
        )))
        outcome = provider.fetch_result(context())
        self.assertEqual(outcome.status, "not_final_yet")

    def test_calendar_api_wrong_world_cup_season_is_not_found(self):
        provider = FifaMatchCentreProvider(json_loader=lambda _: calendar_payload(calendar_match(IdSeason="255711")))
        outcome = provider.fetch_result(context())
        self.assertEqual(outcome.status, "not_found")


if __name__ == "__main__":
    unittest.main()

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
from providers.fifa_match_centre_provider import FifaMatchCentreProvider, calendar_url_for  # noqa: E402


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


def qatar_switzerland_context() -> MatchContext:
    return MatchContext(
        match_id="match-005",
        match_number=5,
        kickoff_utc=datetime(2026, 6, 13, 19, 0, tzinfo=timezone.utc),
        home_team_id="qatar",
        away_team_id="switzerland",
        home_team_name="Qatar",
        away_team_name="Switzerland",
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

    def test_calendar_url_filters_world_cup_competition_and_season(self):
        url = calendar_url_for(context())
        self.assertIn("idCompetition=17", url)
        self.assertIn("idSeason=285023", url)

    def test_calendar_api_accepts_match_number_mismatch_when_team_kickoff_and_final_score_match(self):
        provider = FifaMatchCentreProvider(json_loader=lambda _: calendar_payload(calendar_match(
            MatchNumber=8,
            Date="2026-06-13T19:00:00Z",
            HomeTeamScore=1,
            AwayTeamScore=1,
            Home={"Score": 1, "TeamName": [{"Description": "Qatar"}], "ShortClubName": "Qatar"},
            Away={"Score": 1, "TeamName": [{"Description": "Switzerland"}], "ShortClubName": "Switzerland"},
        )))
        outcome = provider.fetch_result(qatar_switzerland_context())
        self.assertEqual(outcome.status, "found")
        self.assertEqual(outcome.match_id, "match-005")
        self.assertGreaterEqual(outcome.confidence, 0.90)
        self.assertEqual(outcome.home_score, 1)
        self.assertEqual(outcome.away_score, 1)
        self.assertIsNone(outcome.winner_team_id)
        self.assertIn('"appMatchNumber": 5', outcome.notes)
        self.assertIn('"providerMatchNumber": 8', outcome.notes)

    def test_calendar_api_rejects_match_number_only_match_when_team_differs(self):
        provider = FifaMatchCentreProvider(json_loader=lambda _: calendar_payload(calendar_match(
            MatchNumber=5,
            Date="2026-06-13T19:00:00Z",
            HomeTeamScore=1,
            AwayTeamScore=1,
            Home={"Score": 1, "TeamName": [{"Description": "Haiti"}], "ShortClubName": "Haiti"},
            Away={"Score": 1, "TeamName": [{"Description": "Scotland"}], "ShortClubName": "Scotland"},
        )))
        outcome = provider.fetch_result(qatar_switzerland_context())
        self.assertEqual(outcome.status, "not_found")
        self.assertIn("home team mismatch", outcome.notes)

    def test_calendar_api_team_and_kickoff_match_without_final_status_is_not_final_yet(self):
        provider = FifaMatchCentreProvider(json_loader=lambda _: calendar_payload(calendar_match(
            MatchNumber=8,
            Date="2026-06-13T19:00:00Z",
            MatchStatus=1,
            HomeTeamScore=1,
            AwayTeamScore=1,
            Home={"Score": 1, "TeamName": [{"Description": "Qatar"}], "ShortClubName": "Qatar"},
            Away={"Score": 1, "TeamName": [{"Description": "Switzerland"}], "ShortClubName": "Switzerland"},
        )))
        outcome = provider.fetch_result(qatar_switzerland_context())
        self.assertEqual(outcome.status, "not_final_yet")

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

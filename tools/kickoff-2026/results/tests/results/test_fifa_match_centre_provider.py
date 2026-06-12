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
        }))
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
        }))
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
        }))
        outcome = provider.fetch_result(context())
        self.assertEqual(outcome.status, "not_found")


if __name__ == "__main__":
    unittest.main()

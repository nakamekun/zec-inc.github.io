#!/usr/bin/env python3
"""Print a manual Match Centre checking queue.

This helper does not scrape FIFA pages. It lists Kickoff Bell match IDs and
facts already bundled in the app so an operator can open the relevant Match
Centre page in a browser, verify factual scores, and update
data/results/manual-match-results.json.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_TOURNAMENT_PATH = APP_DIR / "Kickoff2026" / "Resources" / "tournament_2026.json"
DEFAULT_MATCH_CENTRE_URL = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def build_rows(tournament: dict[str, Any], match_centre_url: str, include_future: bool) -> list[dict[str, Any]]:
    teams = {team["id"]: team for team in tournament.get("teams", [])}
    venues = {venue["id"]: venue for venue in tournament.get("venues", [])}
    now = datetime.now(timezone.utc)
    rows: list[dict[str, Any]] = []
    for match in sorted(tournament.get("matches", []), key=lambda item: item.get("matchNumber") or 999):
        kickoff = parse_utc(match["kickoffUTC"])
        if not include_future and kickoff > now:
            continue
        home = teams.get(match["homeTeamId"], {})
        away = teams.get(match["awayTeamId"], {})
        venue = venues.get(match["venueId"], {})
        rows.append({
            "matchId": match["id"],
            "matchNumber": match.get("matchNumber"),
            "kickoffUTC": match["kickoffUTC"],
            "homeTeamId": match["homeTeamId"],
            "homeTeamName": home.get("name", match["homeTeamId"]),
            "awayTeamId": match["awayTeamId"],
            "awayTeamName": away.get("name", match["awayTeamId"]),
            "venueId": match["venueId"],
            "venueName": venue.get("name", match["venueId"]),
            "venueCity": venue.get("city"),
            "matchCentreUrl": match_centre_url,
        })
    return rows


def print_text(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("No matches to check for the selected filters.")
        return
    for row in rows:
        print(
            f"{row['matchId']} #{row['matchNumber']}: "
            f"{row['homeTeamName']} ({row['homeTeamId']}) vs "
            f"{row['awayTeamName']} ({row['awayTeamId']}) | "
            f"{row['kickoffUTC']} | {row['venueName']} | {row['matchCentreUrl']}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="List matches for manual Match Centre checking.")
    parser.add_argument("--tournament", type=Path, default=DEFAULT_TOURNAMENT_PATH)
    parser.add_argument("--match-centre-url", default=DEFAULT_MATCH_CENTRE_URL)
    parser.add_argument("--include-future", action="store_true", help="Include matches that have not kicked off yet.")
    parser.add_argument("--format", choices=["text", "json"], default="text")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    rows = build_rows(read_json(args.tournament), args.match_centre_url, args.include_future)
    if args.format == "json":
        print(json.dumps({"matches": rows}, ensure_ascii=False, indent=2))
    else:
        print_text(rows)


if __name__ == "__main__":
    main()

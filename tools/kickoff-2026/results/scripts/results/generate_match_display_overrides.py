#!/usr/bin/env python3
"""Generate Kickoff Bell match display overrides from official fixtures.

The iOS app bundles the base schedule. This generator resolves knockout
placeholders only when the official FIFA calendar payload contains both teams
for the matching fixture, then emits the remote JSON used by the app and widget.
"""

from __future__ import annotations

import argparse
import json
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from providers.fifa_match_centre_provider import normalize_team_name, parse_fifa_datetime, team_name


APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MATCH_MAP_PATH = APP_DIR / "data" / "results" / "match-id-map.json"
DEFAULT_GROUP_STANDINGS_PATH = APP_DIR / "data" / "generated" / "groupStandings.json"
DEFAULT_MANUAL_OVERRIDES_PATH = APP_DIR / "data" / "results" / "manual-match-display-overrides.json"
DEFAULT_OUTPUT_PATH = APP_DIR / "data" / "generated" / "matchDisplayOverrides.json"
REFERENCE_URL = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"
FIFA_CALENDAR_API_URL = "https://api.fifa.com/api/v3/calendar/matches"
FIFA_WORLD_CUP_COMPETITION_ID = "17"
FIFA_WORLD_CUP_2026_SEASON_ID = "285023"
TIME_MATCH_TOLERANCE = timedelta(hours=2)


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is not None and not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def load_json_url(url: str, timeout: int = 20) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "ZEC Kickoff Bell matchup updater; contact: https://zec-inc.jp/support/"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise RuntimeError(f"HTTP {status}")
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    if not isinstance(payload, dict):
        raise ValueError("FIFA calendar API response must be an object")
    return payload


def calendar_url_for_match_map(match_map: dict[str, Any]) -> str:
    dates = [
        parse_match_utc(require_string(match, "kickoffUTC", require_string(match, "matchId", "match map")))
        for match in match_map.get("matches", [])
    ]
    if not dates:
        raise ValueError("match map must contain matches")
    start = (min(dates) - timedelta(days=1)).date().isoformat()
    end = (max(dates) + timedelta(days=1)).date().isoformat()
    query = urlencode({
        "language": "en",
        "from": start,
        "to": end,
        "idCompetition": FIFA_WORLD_CUP_COMPETITION_ID,
        "idSeason": FIFA_WORLD_CUP_2026_SEASON_ID,
        "count": 200,
    })
    return f"{FIFA_CALENDAR_API_URL}?{query}"


def parse_match_utc(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def team_id_lookup(match_map: dict[str, Any]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for match in match_map.get("matches", []):
        for id_key, name_key in [("homeTeamId", "homeTeamName"), ("awayTeamId", "awayTeamName")]:
            team_id = require_string(match, id_key, "match map")
            if is_placeholder(team_id):
                continue
            team_name_value = require_string(match, name_key, team_id)
            lookup.setdefault(normalize_team_name(team_name_value), team_id)
            lookup.setdefault(normalize_team_name(team_id), team_id)
    aliases = {
        "united states": "usa",
        "usa": "usa",
        "korea republic": "south-korea",
        "czechia": "czech-republic",
        "cote d ivoire": "ivory-coast",
        "cote divoire": "ivory-coast",
        "cotedivoire": "ivory-coast",
        "turkiye": "turkey",
        "cabo verde": "cape-verde",
        "ir iran": "iran",
        "congo dr": "dr-congo",
        "congo democratic republic": "dr-congo",
        "bosnia and herzegovina": "bosnia-and-herzegovina",
    }
    for alias, team_id in aliases.items():
        if team_id in lookup.values():
            lookup.setdefault(alias, team_id)
    return lookup


def resolve_provider_team_id(raw_team: Any, teams_by_name: dict[str, str]) -> str | None:
    name = team_name(raw_team)
    if not name:
        return None
    return teams_by_name.get(normalize_team_name(name))


def fifa_calendar_overrides(
    match_map: dict[str, Any],
    calendar_payload: dict[str, Any],
    updated_at: str,
) -> dict[str, dict[str, Any]]:
    results = calendar_payload.get("Results")
    if not isinstance(results, list):
        raise ValueError("FIFA calendar API response missing Results array")
    teams_by_name = team_id_lookup(match_map)
    overrides: dict[str, dict[str, Any]] = {}
    for match in match_map.get("matches", []):
        match_id = require_string(match, "matchId", "match map")
        if not (is_placeholder(require_string(match, "homeTeamId", match_id)) or is_placeholder(require_string(match, "awayTeamId", match_id))):
            continue
        candidate = choose_fifa_candidate(match, results)
        if candidate is None:
            continue
        override: dict[str, Any] = {
            "isConfirmed": True,
            "updatedAt": updated_at,
        }
        home_team_id = resolve_provider_team_id(candidate.get("Home"), teams_by_name)
        if home_team_id:
            override["homeTeamId"] = home_team_id
        away_team_id = resolve_provider_team_id(candidate.get("Away"), teams_by_name)
        if away_team_id:
            override["awayTeamId"] = away_team_id
        if "homeTeamId" not in override and "awayTeamId" not in override:
            continue
        overrides[match_id] = override
    return overrides


def choose_fifa_candidate(match: dict[str, Any], candidates: list[Any]) -> dict[str, Any] | None:
    match_number = match.get("matchNumber")
    kickoff = parse_match_utc(require_string(match, "kickoffUTC", require_string(match, "matchId", "match map")))
    scored: list[tuple[float, dict[str, Any]]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("IdCompetition")) != FIFA_WORLD_CUP_COMPETITION_ID:
            continue
        if str(candidate.get("IdSeason")) != FIFA_WORLD_CUP_2026_SEASON_ID:
            continue
        candidate_kickoff = parse_fifa_datetime(candidate.get("Date"))
        if candidate_kickoff is None or abs(candidate_kickoff - kickoff) > TIME_MATCH_TOLERANCE:
            continue
        confidence = 0.70
        if isinstance(match_number, int) and candidate.get("MatchNumber") == match_number:
            confidence += 0.25
        if candidate_kickoff == kickoff:
            confidence += 0.05
        if confidence >= 0.90:
            scored.append((confidence, candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1]


def is_placeholder(team_id: str) -> bool:
    return "-group-" in team_id


def merge_manual_overrides(generated: dict[str, dict[str, Any]], manual_payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    merged = dict(generated)
    manual = manual_payload.get("matchOverrides", {})
    if not isinstance(manual, dict):
        raise ValueError("manual match display overrides must contain matchOverrides object")
    for match_id, override in manual.items():
        if not isinstance(match_id, str) or not match_id:
            raise ValueError("manual override matchId must be a non-empty string")
        if not isinstance(override, dict):
            raise ValueError(f"{match_id}: manual override must be an object")
        merged[match_id] = dict(override)
    return dict(sorted(merged.items()))


def generate_payload(
    match_map: dict[str, Any],
    standings: dict[str, Any],
    manual_payload: dict[str, Any],
    fifa_calendar_payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = standings.get("source", {})
    updated_at = source.get("updatedAt") or source.get("generatedAt")
    if not isinstance(updated_at, str) or not updated_at:
        raise ValueError("group standings source.updatedAt must be a non-empty string")
    overrides: dict[str, dict[str, Any]] = {}
    if fifa_calendar_payload is not None:
        overrides.update(fifa_calendar_overrides(match_map, fifa_calendar_payload, updated_at))
    overrides = merge_manual_overrides(overrides, manual_payload)
    return {
        "source": {
            "name": "Kickoff Bell match display overrides",
            "updatedAt": updated_at,
            "generatedAt": updated_at,
            "url": REFERENCE_URL,
        },
        "matchOverrides": overrides,
    }


def require_string(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Kickoff match display override JSON.")
    parser.add_argument("--match-map", type=Path, default=DEFAULT_MATCH_MAP_PATH)
    parser.add_argument("--group-standings", type=Path, default=DEFAULT_GROUP_STANDINGS_PATH)
    parser.add_argument("--manual-overrides", type=Path, default=DEFAULT_MANUAL_OVERRIDES_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--skip-fifa-calendar", action="store_true")
    parser.add_argument("--fifa-calendar-json", type=Path, help="Use a saved FIFA calendar response instead of network fetch.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    match_map = read_json(args.match_map)
    fifa_calendar_payload = None
    if args.fifa_calendar_json:
        fifa_calendar_payload = read_json(args.fifa_calendar_json)
    elif not args.skip_fifa_calendar:
        fifa_calendar_payload = load_json_url(calendar_url_for_match_map(match_map))
    payload = generate_payload(
        match_map,
        read_json(args.group_standings),
        read_json(args.manual_overrides, {"matchOverrides": {}}),
        fifa_calendar_payload,
    )
    write_json(args.output, payload)


if __name__ == "__main__":
    main()

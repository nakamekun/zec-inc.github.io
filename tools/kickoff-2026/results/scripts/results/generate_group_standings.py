#!/usr/bin/env python3
"""Generate Kickoff Bell group standings from curated match results.

This tool runs outside the iOS app. It reads the ZEC-curated matchResults.json
file, calculates factual table values, and emits the existing app reader schema
for groupStandings.json. It does not call FIFA pages or any third-party API.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MATCH_MAP_PATH = APP_DIR / "data" / "results" / "match-id-map.json"
DEFAULT_MATCH_RESULTS_PATH = APP_DIR / "data" / "generated" / "matchResults.json"
DEFAULT_OVERRIDES_PATH = APP_DIR / "data" / "results" / "manual-standings-overrides.json"
DEFAULT_OUTPUT_PATH = APP_DIR / "data" / "generated" / "groupStandings.json"
REFERENCE_URL = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/standings"

ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
COUNTED_STATUSES = {"finished"}
IGNORED_STATUSES = {"scheduled", "postponed", "cancelled"}
TEAM_OVERRIDE_FIELDS = {"teamId", "rank", "qualificationStatus", "updatedAt"}


@dataclass(frozen=True)
class MatchRef:
    match_id: str
    group: str
    home_team_id: str
    away_team_id: str


@dataclass
class TeamStanding:
    team_id: str
    seed_order: int
    rank: int | None = None
    played: int = 0
    won: int = 0
    drawn: int = 0
    lost: int = 0
    goals_for: int = 0
    goals_against: int = 0
    points: int = 0

    @property
    def goal_difference(self) -> int:
        return self.goals_for - self.goals_against

    def to_app_json(self) -> dict[str, Any]:
        return {
            "teamId": self.team_id,
            "rank": self.rank,
            "played": self.played,
            "won": self.won,
            "drawn": self.drawn,
            "lost": self.lost,
            "goalsFor": self.goals_for,
            "goalsAgainst": self.goals_against,
            "goalDifference": self.goal_difference,
            "points": self.points,
        }


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def load_match_map(path: Path) -> tuple[dict[str, MatchRef], dict[str, list[str]], set[str]]:
    match_map = read_json(path)
    match_refs: dict[str, MatchRef] = {}
    group_teams: dict[str, list[str]] = {}
    known_match_ids: set[str] = set()

    for match in match_map.get("matches", []):
        match_id = require_string(match, "matchId", "match map")
        known_match_ids.add(match_id)
        group = match.get("groupName")
        if not isinstance(group, str) or not group:
            continue
        home_team_id = require_string(match, "homeTeamId", match_id)
        away_team_id = require_string(match, "awayTeamId", match_id)
        match_refs[match_id] = MatchRef(match_id, group, home_team_id, away_team_id)
        group_teams.setdefault(group, [])
        append_unique(group_teams[group], home_team_id)
        append_unique(group_teams[group], away_team_id)

    if not group_teams:
        raise ValueError("match map does not contain group-stage teams")
    return match_refs, dict(sorted(group_teams.items(), key=lambda item: group_sort_key(item[0]))), known_match_ids


def append_unique(values: list[str], value: str) -> None:
    if value not in values:
        values.append(value)


def generate_payload(
    match_results_payload: dict[str, Any],
    overrides_payload: dict[str, Any],
    match_refs: dict[str, MatchRef],
    group_teams: dict[str, list[str]],
    generated_at: str,
    reference_url: str | None = None,
    known_match_ids: set[str] | None = None,
) -> dict[str, Any]:
    validate_iso8601_utc(generated_at, "generatedAt")
    standings = initial_standings(group_teams)
    counted_results = apply_match_results(standings, match_results_payload, match_refs, known_match_ids)
    assign_ranks(standings)
    apply_overrides(standings, overrides_payload)
    payload = {
        "source": {
            "name": "ZEC curated group standings",
            "updatedAt": generated_at,
            "generatedAt": generated_at,
            "url": reference_url,
        },
        "groups": [
            {
                "group": group,
                "teams": [team.to_app_json() for team in sorted(teams.values(), key=lambda item: item.rank or 999)],
            }
            for group, teams in standings.items()
        ],
    }
    validate_payload(payload, counted_results, group_teams, generated_at)
    return payload


def initial_standings(group_teams: dict[str, list[str]]) -> dict[str, dict[str, TeamStanding]]:
    standings: dict[str, dict[str, TeamStanding]] = {}
    for group, team_ids in group_teams.items():
        if len(team_ids) != len(set(team_ids)):
            raise ValueError(f"{group}: duplicate teamId in tournament data")
        standings[group] = {
            team_id: TeamStanding(team_id=team_id, seed_order=index)
            for index, team_id in enumerate(team_ids)
        }
    return standings


def apply_match_results(
    standings: dict[str, dict[str, TeamStanding]],
    match_results_payload: dict[str, Any],
    match_refs: dict[str, MatchRef],
    known_match_ids: set[str] | None = None,
) -> int:
    results = match_results_payload.get("results")
    if not isinstance(results, list):
        raise ValueError("match results input must contain a results array")

    counted = 0
    seen: set[str] = set()
    for index, result in enumerate(results):
        if not isinstance(result, dict):
            raise ValueError(f"results[{index}] must be an object")
        match_id = require_string(result, "matchId", f"results[{index}]")
        if match_id in seen:
            raise ValueError(f"Duplicate matchId: {match_id}")
        seen.add(match_id)
        if match_id not in match_refs:
            if known_match_ids is not None and match_id in known_match_ids:
                continue
            raise ValueError(f"Unknown matchId: {match_id}")

        status = require_string(result, "status", match_id)
        if status in IGNORED_STATUSES:
            continue
        if status not in COUNTED_STATUSES:
            raise ValueError(f"{match_id}: status {status} cannot be counted in group standings")

        match_ref = match_refs[match_id]
        home_score = require_non_negative_int(result.get("homeScore"), f"{match_id}.homeScore")
        away_score = require_non_negative_int(result.get("awayScore"), f"{match_id}.awayScore")
        group = match_ref.group
        if match_ref.home_team_id not in standings[group] or match_ref.away_team_id not in standings[group]:
            raise ValueError(f"{match_id}: match team missing from {group}")
        apply_finished_match(
            standings[group][match_ref.home_team_id],
            standings[group][match_ref.away_team_id],
            home_score,
            away_score,
        )
        counted += 1
    return counted


def apply_finished_match(home: TeamStanding, away: TeamStanding, home_score: int, away_score: int) -> None:
    home.played += 1
    away.played += 1
    home.goals_for += home_score
    home.goals_against += away_score
    away.goals_for += away_score
    away.goals_against += home_score

    if home_score > away_score:
        home.won += 1
        away.lost += 1
        home.points += 3
    elif home_score < away_score:
        away.won += 1
        home.lost += 1
        away.points += 3
    else:
        home.drawn += 1
        away.drawn += 1
        home.points += 1
        away.points += 1


def assign_ranks(standings: dict[str, dict[str, TeamStanding]]) -> None:
    for teams in standings.values():
        ordered = sorted(
            teams.values(),
            key=lambda team: (-team.points, -team.goal_difference, -team.goals_for, team.seed_order),
        )
        for rank, team in enumerate(ordered, start=1):
            team.rank = rank


def apply_overrides(standings: dict[str, dict[str, TeamStanding]], overrides_payload: dict[str, Any]) -> None:
    groups = overrides_payload.get("groups", [])
    if not isinstance(groups, list):
        raise ValueError("standings overrides must contain a groups array")

    for group_index, group_override in enumerate(groups):
        if not isinstance(group_override, dict):
            raise ValueError(f"overrides.groups[{group_index}] must be an object")
        group = require_string(group_override, "group", f"overrides.groups[{group_index}]")
        if group not in standings:
            raise ValueError(f"Unknown override group: {group}")
        teams = group_override.get("teams", [])
        if not isinstance(teams, list):
            raise ValueError(f"{group}: override teams must be an array")
        for team_index, team_override in enumerate(teams):
            if not isinstance(team_override, dict):
                raise ValueError(f"{group}.teams[{team_index}] must be an object")
            unknown = set(team_override) - TEAM_OVERRIDE_FIELDS
            if unknown:
                raise ValueError(f"{group}.teams[{team_index}] has unsupported fields: {sorted(unknown)}")
            team_id = require_string(team_override, "teamId", f"{group}.teams[{team_index}]")
            if team_id not in standings[group]:
                raise ValueError(f"{group}: unknown override teamId {team_id}")
            rank = team_override.get("rank")
            if rank is not None:
                standings[group][team_id].rank = require_positive_int(rank, f"{group}.{team_id}.rank")
            updated_at = team_override.get("updatedAt")
            if updated_at is not None:
                validate_iso8601_utc(updated_at, f"{group}.{team_id}.updatedAt")
            qualification_status = team_override.get("qualificationStatus")
            if qualification_status is not None and (not isinstance(qualification_status, str) or not qualification_status):
                raise ValueError(f"{group}.{team_id}.qualificationStatus must be null or a non-empty string")


def validate_payload(
    payload: dict[str, Any],
    counted_results: int,
    expected_group_teams: dict[str, list[str]],
    generated_at: str,
) -> None:
    validate_iso8601_utc(payload["source"]["updatedAt"], "source.updatedAt")
    validate_iso8601_utc(payload["source"]["generatedAt"], "source.generatedAt")
    if payload["source"]["generatedAt"] != generated_at:
        raise ValueError("source.generatedAt does not match generatedAt")

    total_played_entries = 0
    for group in payload["groups"]:
        group_name = require_string(group, "group", "group")
        teams = group.get("teams")
        if not isinstance(teams, list):
            raise ValueError(f"{group_name}: teams must be an array")
        expected_teams = expected_group_teams[group_name]
        if len(teams) != len(expected_teams):
            raise ValueError(f"{group_name}: expected {len(expected_teams)} teams")
        team_ids = [require_string(team, "teamId", group_name) for team in teams]
        if len(team_ids) != len(set(team_ids)):
            raise ValueError(f"{group_name}: duplicate teamId")
        if set(team_ids) != set(expected_teams):
            raise ValueError(f"{group_name}: teamId set does not match tournament data")

        ranks = [team.get("rank") for team in teams]
        if any(not isinstance(rank, int) or rank <= 0 for rank in ranks):
            raise ValueError(f"{group_name}: all ranks must be positive integers")
        if len(ranks) != len(set(ranks)):
            raise ValueError(f"{group_name}: duplicate rank")

        goals_for = sum(require_non_negative_int(team.get("goalsFor"), f"{group_name}.goalsFor") for team in teams)
        goals_against = sum(require_non_negative_int(team.get("goalsAgainst"), f"{group_name}.goalsAgainst") for team in teams)
        if goals_for != goals_against:
            raise ValueError(f"{group_name}: goalsFor and goalsAgainst totals must match")
        for team in teams:
            won = require_non_negative_int(team.get("won"), f"{group_name}.won")
            drawn = require_non_negative_int(team.get("drawn"), f"{group_name}.drawn")
            lost = require_non_negative_int(team.get("lost"), f"{group_name}.lost")
            played = require_non_negative_int(team.get("played"), f"{group_name}.played")
            points = require_non_negative_int(team.get("points"), f"{group_name}.points")
            goals_for_team = require_non_negative_int(team.get("goalsFor"), f"{group_name}.goalsFor")
            goals_against_team = require_non_negative_int(team.get("goalsAgainst"), f"{group_name}.goalsAgainst")
            goal_difference = require_int(team.get("goalDifference"), f"{group_name}.goalDifference")
            if played != won + drawn + lost:
                raise ValueError(f"{group_name}.{team['teamId']}: played does not match W/D/L")
            if points != won * 3 + drawn:
                raise ValueError(f"{group_name}.{team['teamId']}: points do not match W/D/L")
            if goal_difference != goals_for_team - goals_against_team:
                raise ValueError(f"{group_name}.{team['teamId']}: goalDifference does not match goals")
            total_played_entries += played
    if total_played_entries != counted_results * 2:
        raise ValueError("played totals do not match counted finished match results")


def validate_iso8601_utc(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not ISO_UTC_RE.match(value):
        raise ValueError(f"{field_name} must be ISO-8601 UTC like 2026-06-12T06:00:00Z")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO-8601 UTC timestamp") from error


def group_sort_key(group: str) -> tuple[int, str]:
    parts = group.split()
    if len(parts) == 2 and len(parts[1]) == 1 and parts[1].isalpha():
        return (ord(parts[1].upper()) - ord("A"), group)
    return (999, group)


def require_string(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value


def require_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def require_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def require_positive_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ZEC-curated Kickoff group standings JSON.")
    parser.add_argument("--match-results", type=Path, default=DEFAULT_MATCH_RESULTS_PATH)
    parser.add_argument("--overrides", type=Path, default=DEFAULT_OVERRIDES_PATH)
    parser.add_argument("--match-map", type=Path, default=DEFAULT_MATCH_MAP_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--generated-at", default=utc_now())
    parser.add_argument("--reference-url", default=None)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    match_refs, group_teams, known_match_ids = load_match_map(args.match_map)
    match_results_payload = read_json(args.match_results)
    overrides_payload = read_json(args.overrides)
    payload = generate_payload(
        match_results_payload,
        overrides_payload,
        match_refs,
        group_teams,
        args.generated_at,
        reference_url=args.reference_url,
        known_match_ids=known_match_ids,
    )
    if args.dry_run:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    write_json(args.output, payload)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Generate Kickoff Bell match display overrides from standings.

The iOS app bundles the base schedule. This generator resolves knockout
placeholders that can be inferred from finalized group standings, then emits the
remote JSON used by the app and widget.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MATCH_MAP_PATH = APP_DIR / "data" / "results" / "match-id-map.json"
DEFAULT_GROUP_STANDINGS_PATH = APP_DIR / "data" / "generated" / "groupStandings.json"
DEFAULT_MANUAL_OVERRIDES_PATH = APP_DIR / "data" / "results" / "manual-match-display-overrides.json"
DEFAULT_OUTPUT_PATH = APP_DIR / "data" / "generated" / "matchDisplayOverrides.json"
REFERENCE_URL = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/scores-fixtures"
PLACEHOLDER_RE = re.compile(r"^(winner|runner-up)-group-([a-l])$")


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is not None and not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def group_rank_lookup(group_standings: dict[str, Any]) -> dict[str, dict[int, str]]:
    lookup: dict[str, dict[int, str]] = {}
    for group in group_standings.get("groups", []):
        group_name = require_string(group, "group", "group standings")
        ranks: dict[int, str] = {}
        for team in group.get("teams", []):
            team_id = require_string(team, "teamId", group_name)
            rank = team.get("rank")
            if not isinstance(rank, int):
                raise ValueError(f"{group_name}.{team_id}: rank must be an integer")
            ranks[rank] = team_id
        lookup[group_name.lower()] = ranks
    return lookup


def resolve_placeholder(team_id: str, lookup: dict[str, dict[int, str]]) -> str | None:
    match = PLACEHOLDER_RE.match(team_id)
    if not match:
        return None
    rank = 1 if match.group(1) == "winner" else 2
    group_name = f"group {match.group(2)}"
    return lookup.get(group_name, {}).get(rank)


def is_placeholder(team_id: str) -> bool:
    return "-group-" in team_id


def generated_overrides(match_map: dict[str, Any], standings: dict[str, Any], updated_at: str) -> dict[str, dict[str, Any]]:
    lookup = group_rank_lookup(standings)
    overrides: dict[str, dict[str, Any]] = {}
    for match in match_map.get("matches", []):
        match_id = require_string(match, "matchId", "match map")
        home_team_id = require_string(match, "homeTeamId", match_id)
        away_team_id = require_string(match, "awayTeamId", match_id)
        resolved_home = resolve_placeholder(home_team_id, lookup)
        resolved_away = resolve_placeholder(away_team_id, lookup)
        unresolved_home = is_placeholder(home_team_id) and not resolved_home
        unresolved_away = is_placeholder(away_team_id) and not resolved_away
        if unresolved_home or unresolved_away:
            continue
        if not resolved_home and not resolved_away:
            continue
        override: dict[str, Any] = {
            "isConfirmed": True,
            "updatedAt": updated_at,
        }
        if resolved_home:
            override["homeTeamId"] = resolved_home
        if resolved_away:
            override["awayTeamId"] = resolved_away
        overrides[match_id] = override
    return overrides


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
) -> dict[str, Any]:
    source = standings.get("source", {})
    updated_at = source.get("updatedAt") or source.get("generatedAt")
    if not isinstance(updated_at, str) or not updated_at:
        raise ValueError("group standings source.updatedAt must be a non-empty string")
    overrides = merge_manual_overrides(
        generated_overrides(match_map, standings, updated_at),
        manual_payload,
    )
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = generate_payload(
        read_json(args.match_map),
        read_json(args.group_standings),
        read_json(args.manual_overrides, {"matchOverrides": {}}),
    )
    write_json(args.output, payload)


if __name__ == "__main__":
    main()

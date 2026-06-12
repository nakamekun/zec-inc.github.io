#!/usr/bin/env python3
"""Generate public Kickoff Bell match results JSON from curated input.

This tool runs outside the iOS app. It does not call FIFA pages or any
third-party API. Operators verify factual match results separately, enter only
facts into data/results/manual-match-results.json, then generate the ZEC JSON
that the app can read later.
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
DEFAULT_INPUT_PATH = APP_DIR / "data" / "results" / "manual-match-results.json"
DEFAULT_OUTPUT_PATH = APP_DIR / "data" / "generated" / "matchResults.json"
DEFAULT_V1_OUTPUT_PATH = APP_DIR / "data" / "generated" / "match-results.json"

ALLOWED_STATUSES = {
    "scheduled",
    "inProgress",
    "halfTime",
    "fullTime",
    "penalties",
    "postponed",
    "cancelled",
}
ALLOWED_SOURCES = {"zec-curated", "zec-auto"}
REQUIRED_FIELDS = {
    "matchId",
    "status",
    "homeScore",
    "awayScore",
    "homePenaltyScore",
    "awayPenaltyScore",
    "winnerTeamId",
    "currentMinute",
    "resultUpdatedAt",
    "source",
}
ISO_UTC_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")


@dataclass(frozen=True)
class MatchRef:
    match_id: str
    home_team_id: str
    away_team_id: str


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}")


def load_match_refs(match_map_path: Path) -> dict[str, MatchRef]:
    match_map = read_json(match_map_path)
    refs: dict[str, MatchRef] = {}
    for match in match_map.get("matches", []):
        match_id = require_string(match, "matchId", "match map")
        refs[match_id] = MatchRef(
            match_id=match_id,
            home_team_id=require_string(match, "homeTeamId", match_id),
            away_team_id=require_string(match, "awayTeamId", match_id),
        )
    return refs


def generate_payload(manual_payload: dict[str, Any], match_refs: dict[str, MatchRef], generated_at: str) -> dict[str, Any]:
    validate_iso8601_utc(generated_at, "generatedAt")
    matches = manual_payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("manual input must contain a matches array")

    normalized = [normalize_result(match, index) for index, match in enumerate(matches)]
    validate_results(normalized, match_refs)
    return {
        "version": 1,
        "generatedAt": generated_at,
        "matches": normalized,
    }


def generate_app_payload(manual_payload: dict[str, Any], match_refs: dict[str, MatchRef], generated_at: str) -> dict[str, Any]:
    v1_payload = generate_payload(manual_payload, match_refs, generated_at)
    return convert_v1_to_app_payload(v1_payload, generated_at)


def convert_v1_to_app_payload(v1_payload: dict[str, Any], generated_at: str) -> dict[str, Any]:
    app_results: list[dict[str, Any]] = []
    for result in v1_payload["matches"]:
        app_status = app_status_for(result)
        app_results.append({
            "matchId": result["matchId"],
            "status": app_status,
            "homeScore": result["homeScore"],
            "awayScore": result["awayScore"],
            "homePenaltyScore": result["homePenaltyScore"],
            "awayPenaltyScore": result["awayPenaltyScore"],
            "winnerTeamId": result["winnerTeamId"],
            "resultUpdatedAt": result["resultUpdatedAt"],
            "source": result["source"],
        })
    return {
        "source": {
            "name": "ZEC curated match results",
            "updatedAt": generated_at,
            "generatedAt": generated_at,
            "url": None,
        },
        "results": app_results,
    }


def app_status_for(result: dict[str, Any]) -> str:
    status = result["status"]
    if status in {"fullTime", "penalties"}:
        return "finished"
    if status in {"scheduled", "postponed", "cancelled"}:
        return status
    raise ValueError(f"{result['matchId']}: {status} cannot be represented by the current app reader")


def normalize_result(raw: Any, index: int) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise ValueError(f"matches[{index}] must be an object")
    unknown = set(raw) - REQUIRED_FIELDS
    if unknown:
        raise ValueError(f"matches[{index}] has unsupported fields: {sorted(unknown)}")
    missing = REQUIRED_FIELDS - set(raw)
    if missing:
        raise ValueError(f"matches[{index}] is missing fields: {sorted(missing)}")

    match_id = require_string(raw, "matchId", f"matches[{index}]")
    status = require_string(raw, "status", match_id)
    source = require_string(raw, "source", match_id)
    if source not in ALLOWED_SOURCES:
        raise ValueError(f"{match_id}: source must be one of {sorted(ALLOWED_SOURCES)}")

    return {
        "matchId": match_id,
        "status": status,
        "homeScore": optional_non_negative_int(raw.get("homeScore"), f"{match_id}.homeScore"),
        "awayScore": optional_non_negative_int(raw.get("awayScore"), f"{match_id}.awayScore"),
        "homePenaltyScore": optional_non_negative_int(raw.get("homePenaltyScore"), f"{match_id}.homePenaltyScore"),
        "awayPenaltyScore": optional_non_negative_int(raw.get("awayPenaltyScore"), f"{match_id}.awayPenaltyScore"),
        "winnerTeamId": optional_string(raw.get("winnerTeamId"), f"{match_id}.winnerTeamId"),
        "currentMinute": optional_non_negative_int(raw.get("currentMinute"), f"{match_id}.currentMinute"),
        "resultUpdatedAt": require_string(raw, "resultUpdatedAt", match_id),
        "source": source,
    }


def validate_results(results: list[dict[str, Any]], match_refs: dict[str, MatchRef]) -> None:
    seen: set[str] = set()
    for result in results:
        match_id = result["matchId"]
        if match_id not in match_refs:
            raise ValueError(f"Unknown matchId: {match_id}")
        if match_id in seen:
            raise ValueError(f"Duplicate matchId: {match_id}")
        seen.add(match_id)

        status = result["status"]
        if status not in ALLOWED_STATUSES:
            raise ValueError(f"{match_id}: invalid status {status}")

        validate_iso8601_utc(result["resultUpdatedAt"], f"{match_id}.resultUpdatedAt")
        validate_score_state(result)
        validate_winner(result, match_refs[match_id])


def validate_score_state(result: dict[str, Any]) -> None:
    match_id = result["matchId"]
    status = result["status"]
    has_score = result["homeScore"] is not None or result["awayScore"] is not None
    has_full_score = result["homeScore"] is not None and result["awayScore"] is not None
    has_penalties = result["homePenaltyScore"] is not None or result["awayPenaltyScore"] is not None

    if status == "scheduled":
        if has_score or has_penalties or result["winnerTeamId"] is not None or result["currentMinute"] is not None:
            raise ValueError(f"{match_id}: scheduled matches must not include scores, winner, or minute")
        return

    if status in {"postponed", "cancelled"}:
        if has_score or has_penalties or result["winnerTeamId"] is not None:
            raise ValueError(f"{match_id}: {status} matches must not include scores or winner")
        return

    if status in {"fullTime", "penalties"} and not has_full_score:
        raise ValueError(f"{match_id}: {status} requires homeScore and awayScore")

    if status in {"inProgress", "halfTime"}:
        if not has_full_score:
            raise ValueError(f"{match_id}: {status} requires current score values")
        if result["currentMinute"] is None:
            raise ValueError(f"{match_id}: {status} requires currentMinute")

    if status != "penalties" and has_penalties:
        raise ValueError(f"{match_id}: penalty scores are only allowed when status is penalties")

    if status == "penalties":
        if result["homePenaltyScore"] is None or result["awayPenaltyScore"] is None:
            raise ValueError(f"{match_id}: penalties requires both penalty scores")
        if result["homePenaltyScore"] == result["awayPenaltyScore"]:
            raise ValueError(f"{match_id}: penalty scores cannot be tied")


def validate_winner(result: dict[str, Any], match_ref: MatchRef) -> None:
    match_id = result["matchId"]
    winner = result["winnerTeamId"]
    home_score = result["homeScore"]
    away_score = result["awayScore"]
    home_penalty = result["homePenaltyScore"]
    away_penalty = result["awayPenaltyScore"]
    allowed = {match_ref.home_team_id, match_ref.away_team_id}

    if winner is not None and winner not in allowed:
        raise ValueError(f"{match_id}: winnerTeamId must be home or away team")

    if result["status"] in {"scheduled", "postponed", "cancelled"}:
        return

    if result["status"] == "penalties":
        expected = match_ref.home_team_id if home_penalty > away_penalty else match_ref.away_team_id
    elif home_score is not None and away_score is not None and home_score != away_score:
        expected = match_ref.home_team_id if home_score > away_score else match_ref.away_team_id
    else:
        expected = None

    if winner != expected:
        raise ValueError(f"{match_id}: winnerTeamId does not match score state")


def validate_iso8601_utc(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not ISO_UTC_RE.match(value):
        raise ValueError(f"{field_name} must be ISO-8601 UTC like 2026-06-12T06:00:00Z")
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError as error:
        raise ValueError(f"{field_name} must be a valid ISO-8601 UTC timestamp") from error


def require_string(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value


def optional_string(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field_name} must be null or a non-empty string")
    return value


def optional_non_negative_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be null or a non-negative integer")
    return value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate ZEC-curated Kickoff match results JSON.")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_PATH)
    parser.add_argument("--v1-output", type=Path, default=DEFAULT_V1_OUTPUT_PATH)
    parser.add_argument("--match-map", type=Path, default=DEFAULT_MATCH_MAP_PATH)
    parser.add_argument("--generated-at", default=utc_now())
    parser.add_argument(
        "--schema",
        choices=["app", "v1", "both"],
        default="app",
        help="app writes the existing iOS reader schema; v1 writes the normalized generation schema.",
    )
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    manual_payload = read_json(args.input)
    match_refs = load_match_refs(args.match_map)
    v1_payload = generate_payload(manual_payload, match_refs, args.generated_at)
    app_payload = convert_v1_to_app_payload(v1_payload, args.generated_at)
    if args.dry_run:
        payload = app_payload if args.schema == "app" else v1_payload
        if args.schema == "both":
            payload = {"app": app_payload, "v1": v1_payload}
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return
    if args.schema in {"app", "both"}:
        write_json(args.output, app_payload)
    if args.schema in {"v1", "both"}:
        write_json(args.v1_output, v1_payload)


if __name__ == "__main__":
    main()

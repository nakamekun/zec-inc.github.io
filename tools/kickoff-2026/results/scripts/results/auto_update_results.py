#!/usr/bin/env python3
"""Attempt scheduled Kickoff Bell result updates outside the iOS app."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from providers.base import MatchContext, ResultFetchOutcome, ResultProvider
from providers.fifa_match_centre_provider import FifaMatchCentreProvider
from providers.static_result_feed_provider import StaticResultFeedProvider


APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MATCH_MAP_PATH = APP_DIR / "data" / "results" / "match-id-map.json"
DEFAULT_MANUAL_RESULTS_PATH = APP_DIR / "data" / "results" / "manual-match-results.json"
DEFAULT_STATE_PATH = APP_DIR / "data" / "results" / "auto-update-state.json"
DEFAULT_RESULT_FEED_PATH: Path | None = None
GENERATE_MATCH_RESULTS = APP_DIR / "scripts" / "results" / "generate_match_results.py"
GENERATE_GROUP_STANDINGS = APP_DIR / "scripts" / "results" / "generate_group_standings.py"
MATCH_CENTRE_URL = "https://www.fifa.com/en/match-centre"
FIRST_CHECK_DELAY = timedelta(hours=2, minutes=10)
FINAL_CHECK_DELAY = timedelta(hours=3)
MIN_UPDATE_CONFIDENCE = 0.90
ISO_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
SCHEDULE_MISS_GRACE = timedelta(minutes=20)


@dataclass(frozen=True)
class MatchCandidate:
    match_id: str
    match_number: int | None
    kickoff_utc: datetime
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str
    match_centre_url: str


@dataclass(frozen=True)
class CheckTarget:
    match: MatchCandidate
    check_type: str
    current_result: dict[str, Any] | None


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime(ISO_FORMAT)


def parse_utc(value: str) -> datetime:
    return datetime.strptime(value, ISO_FORMAT).replace(tzinfo=timezone.utc)


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if default is not None and not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_match_candidates(path: Path) -> list[MatchCandidate]:
    payload = read_json(path)
    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("match-id-map.json must contain matches array")
    candidates: list[MatchCandidate] = []
    for raw in matches:
        if not isinstance(raw, dict):
            raise ValueError("match-id-map matches must be objects")
        match_id = require_string(raw, "matchId", "match map")
        kickoff = parse_utc(require_string(raw, "kickoffUTC", match_id))
        candidates.append(
            MatchCandidate(
                match_id=match_id,
                match_number=raw.get("matchNumber") if isinstance(raw.get("matchNumber"), int) else None,
                kickoff_utc=kickoff,
                home_team_id=require_string(raw, "homeTeamId", match_id),
                away_team_id=require_string(raw, "awayTeamId", match_id),
                home_team_name=require_string(raw, "homeTeamName", match_id),
                away_team_name=require_string(raw, "awayTeamName", match_id),
                match_centre_url=raw.get("matchCentreUrl") or MATCH_CENTRE_URL,
            )
        )
    return candidates


def manual_results_by_match_id(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    matches = payload.get("matches")
    if not isinstance(matches, list):
        raise ValueError("manual-match-results.json must contain matches array")
    results: dict[str, dict[str, Any]] = {}
    for result in matches:
        if not isinstance(result, dict):
            raise ValueError("manual match results must be objects")
        match_id = require_string(result, "matchId", "manual result")
        if match_id in results:
            raise ValueError(f"Duplicate manual result: {match_id}")
        results[match_id] = result
    return results


def select_targets(
    matches: list[MatchCandidate],
    manual_results: dict[str, dict[str, Any]],
    state: dict[str, Any],
    now: datetime,
    force: bool = False,
) -> list[CheckTarget]:
    state_matches = state.get("matches", {})
    if not isinstance(state_matches, dict):
        raise ValueError("auto-update-state.json matches must be an object")

    targets: list[CheckTarget] = []
    for match in matches:
        current = manual_results.get(match.match_id)
        match_state = state_matches.get(match.match_id, {})
        if not isinstance(match_state, dict):
            match_state = {}
        if match_state.get("finalResultCaptured") is True and not force:
            continue
        current_status = current.get("status") if current else None
        if current_status in {"fullTime", "penalties"} and not force:
            continue
        if not force and now < match.kickoff_utc + FIRST_CHECK_DELAY:
            continue

        final_due = now >= match.kickoff_utc + FINAL_CHECK_DELAY
        check_type = "final-check" if final_due else "first-check"
        next_retry_after = match_state.get("nextRetryAfter")
        if not force and isinstance(next_retry_after, str) and now < parse_utc(next_retry_after):
            continue
        targets.append(CheckTarget(match=match, check_type=check_type, current_result=current))
    return targets


def monitoring_summary(
    matches: list[MatchCandidate],
    manual_results: dict[str, dict[str, Any]],
    state: dict[str, Any],
    targets: list[CheckTarget],
    outcomes: list[tuple[CheckTarget, ResultFetchOutcome, str, str, dict[str, Any] | None]],
    updates: list[dict[str, Any]],
    now: datetime,
) -> dict[str, Any]:
    state_matches = state.get("matches", {})
    if not isinstance(state_matches, dict):
        state_matches = {}

    skipped_already_finished = 0
    schedule_miss_suspected = False
    overdue_matches: list[str] = []
    for match in matches:
        current = manual_results.get(match.match_id)
        match_state = state_matches.get(match.match_id, {})
        if not isinstance(match_state, dict):
            match_state = {}
        if current and current.get("status") in {"fullTime", "penalties"}:
            skipped_already_finished += 1
            continue
        if match_state.get("finalResultCaptured") is True:
            skipped_already_finished += 1
            continue
        final_due = match.kickoff_utc + FINAL_CHECK_DELAY
        first_due = match.kickoff_utc + FIRST_CHECK_DELAY
        due = final_due if now >= final_due else first_due
        if now >= due + SCHEDULE_MISS_GRACE and any(target.match.match_id == match.match_id for target in targets):
            schedule_miss_suspected = True
            overdue_matches.append(match.match_id)

    provider_failure_statuses = {"not_found", "provider_error", "low_confidence", "conflict"}
    provider_failure_count = sum(1 for _, _, accepted_status, _, _ in outcomes if accepted_status in provider_failure_statuses)
    unchanged_count = sum(1 for _, _, accepted_status, _, _ in outcomes if accepted_status == "unchanged")
    return {
        "targetCount": len(targets),
        "updatedCount": len(updates),
        "skippedAlreadyFinishedCount": skipped_already_finished,
        "providerFailureCount": provider_failure_count,
        "unchangedCount": unchanged_count,
        "dueMatchNoUpdateCount": len(targets) - len(updates) - unchanged_count,
        "scheduleMissSuspected": schedule_miss_suspected,
        "overdueMatches": overdue_matches,
        "generatedAt": format_utc(now),
    }


def build_provider(args: argparse.Namespace) -> ResultProvider:
    if args.result_feed:
        return StaticResultFeedProvider(read_json(args.result_feed))
    return FifaMatchCentreProvider()


def match_context(match: MatchCandidate) -> MatchContext:
    return MatchContext(
        match_id=match.match_id,
        match_number=match.match_number,
        kickoff_utc=match.kickoff_utc,
        home_team_id=match.home_team_id,
        away_team_id=match.away_team_id,
        home_team_name=match.home_team_name,
        away_team_name=match.away_team_name,
        match_centre_url=match.match_centre_url,
    )


def manual_result_from_outcome(outcome: ResultFetchOutcome) -> dict[str, Any]:
    status = "penalties" if outcome.home_penalty_score is not None or outcome.away_penalty_score is not None else "fullTime"
    return {
        "matchId": outcome.match_id,
        "status": status,
        "homeScore": outcome.home_score,
        "awayScore": outcome.away_score,
        "homePenaltyScore": outcome.home_penalty_score,
        "awayPenaltyScore": outcome.away_penalty_score,
        "winnerTeamId": outcome.winner_team_id,
        "currentMinute": None,
        "resultUpdatedAt": outcome.result_updated_at or format_utc(utc_now()),
        "source": "zec-auto",
    }


def accept_outcome(
    target: CheckTarget,
    outcome: ResultFetchOutcome,
) -> tuple[str, str, dict[str, Any] | None]:
    if outcome.status != "found":
        return outcome.status, outcome.notes, None
    if outcome.confidence < MIN_UPDATE_CONFIDENCE:
        return "low_confidence", f"confidence {outcome.confidence:.2f} below {MIN_UPDATE_CONFIDENCE:.2f}", None
    if outcome.home_score is None or outcome.away_score is None:
        return "low_confidence", "score is incomplete", None
    proposed = manual_result_from_outcome(outcome)
    if target.current_result and result_values_conflict(target.current_result, proposed):
        return "conflict", "provider result conflicts with existing final result; keeping existing JSON", None
    if target.current_result and result_values_equal(target.current_result, proposed):
        return "unchanged", "provider result matches existing result", None
    return "updated", outcome.notes or "provider result accepted", proposed


def result_values_equal(existing: dict[str, Any], proposed: dict[str, Any]) -> bool:
    keys = ["status", "homeScore", "awayScore", "homePenaltyScore", "awayPenaltyScore", "winnerTeamId"]
    return all(existing.get(key) == proposed.get(key) for key in keys)


def result_values_conflict(existing: dict[str, Any], proposed: dict[str, Any]) -> bool:
    if existing.get("status") not in {"fullTime", "penalties"}:
        return False
    return not result_values_equal(existing, proposed)


def merge_results(manual_payload: dict[str, Any], updates: list[dict[str, Any]]) -> dict[str, Any]:
    existing = manual_results_by_match_id(manual_payload)
    for update in updates:
        existing[update["matchId"]] = update
    ordered_ids = [item["matchId"] for item in manual_payload.get("matches", []) if item["matchId"] in existing]
    for update in updates:
        if update["matchId"] not in ordered_ids:
            ordered_ids.append(update["matchId"])
    return {"matches": [existing[match_id] for match_id in ordered_ids]}


def update_state(
    state: dict[str, Any],
    target: CheckTarget,
    provider_outcome: ResultFetchOutcome,
    accepted_status: str,
    accepted_message: str,
    now: datetime,
) -> None:
    state.setdefault("matches", {})
    match_state = state["matches"].setdefault(target.match.match_id, {})
    if target.check_type == "first-check":
        match_state["firstCheckAttempted"] = True
        match_state.setdefault("firstCheckAt", format_utc(now))
    if target.check_type == "final-check":
        match_state["finalCheckAttempted"] = True
        match_state.setdefault("finalCheckAt", format_utc(now))
    match_state["lastAttemptAt"] = format_utc(now)
    match_state["lastProviderStatus"] = provider_outcome.status
    match_state["lastStatus"] = accepted_status
    match_state["lastConfidence"] = provider_outcome.confidence
    match_state["attemptCount"] = int(match_state.get("attemptCount", 0)) + 1
    match_state["lastMessage"] = accepted_message
    if accepted_status in {"updated", "unchanged"}:
        match_state["lastSuccessfulUpdateAt"] = format_utc(now)
        match_state["finalResultCaptured"] = True
        match_state.pop("nextRetryAfter", None)
    else:
        match_state["finalResultCaptured"] = False
        match_state["nextRetryAfter"] = format_utc(now + timedelta(minutes=10))


def run_generators() -> None:
    subprocess.run([sys.executable, str(GENERATE_MATCH_RESULTS)], cwd=APP_DIR, check=True)
    subprocess.run([sys.executable, str(GENERATE_GROUP_STANDINGS)], cwd=APP_DIR, check=True)


def print_summary(
    targets: list[CheckTarget],
    outcomes: list[tuple[CheckTarget, ResultFetchOutcome, str, str, dict[str, Any] | None]],
    dry_run: bool,
    summary: dict[str, Any],
) -> None:
    print(f"dryRun: {dry_run}")
    print(f"targetCount: {summary['targetCount']}")
    print(f"updatedCount: {summary['updatedCount']}")
    print(f"skippedAlreadyFinishedCount: {summary['skippedAlreadyFinishedCount']}")
    print(f"providerFailureCount: {summary['providerFailureCount']}")
    print(f"scheduleMissSuspected: {str(summary['scheduleMissSuspected']).lower()}")
    if summary["overdueMatches"]:
        print(f"overdueMatches: {', '.join(summary['overdueMatches'])}")
    for target in targets:
        current = target.current_result.get("status") if target.current_result else "none"
        print(
            f"- {target.match.match_id} {target.check_type} "
            f"{target.match.home_team_name} vs {target.match.away_team_name} "
            f"kickoff={format_utc(target.match.kickoff_utc)} current={current} "
            f"url={target.match.match_centre_url}"
        )
    for target, provider_outcome, accepted_status, accepted_message, update in outcomes:
        print(
            f"  outcome {target.match.match_id}: provider={provider_outcome.status} "
            f"accepted={accepted_status} confidence={provider_outcome.confidence:.2f} - {accepted_message}"
        )
        if update:
            print(
                "    update "
                f"{update['homeScore']}-{update['awayScore']} "
                f"status={update['status']} winner={update['winnerTeamId']}"
            )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scheduled Kickoff result updater.")
    parser.add_argument("--match-map", type=Path, default=DEFAULT_MATCH_MAP_PATH)
    parser.add_argument("--manual-results", type=Path, default=DEFAULT_MANUAL_RESULTS_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--result-feed", type=Path, default=DEFAULT_RESULT_FEED_PATH)
    parser.add_argument("--now", help="Override current UTC time, e.g. 2026-06-12T06:10:00Z")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--skip-generators", action="store_true")
    parser.add_argument("--summary-json", type=Path, help="Write machine-readable monitoring summary.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    run_update(args)


def run_update(
    args: argparse.Namespace,
    generator_runner=run_generators,
    provider: ResultProvider | None = None,
) -> tuple[list[CheckTarget], list[tuple[CheckTarget, ResultFetchOutcome, str, str, dict[str, Any] | None]], list[dict[str, Any]]]:
    now = parse_utc(args.now) if args.now else utc_now()
    matches = load_match_candidates(args.match_map)
    manual_payload = read_json(args.manual_results, {"matches": []})
    manual_results = manual_results_by_match_id(manual_payload)
    state = read_json(args.state, {"matches": {}})
    provider = provider or build_provider(args)
    targets = select_targets(matches, manual_results, state, now, force=args.force)

    updates: list[dict[str, Any]] = []
    outcomes: list[tuple[CheckTarget, ResultFetchOutcome, str, str, dict[str, Any] | None]] = []
    for target in targets:
        provider_outcome = provider.fetch_result(match_context(target.match))
        accepted_status, accepted_message, update = accept_outcome(target, provider_outcome)
        outcomes.append((target, provider_outcome, accepted_status, accepted_message, update))
        if update:
            updates.append(update)
        if not args.dry_run:
            update_state(state, target, provider_outcome, accepted_status, accepted_message, now)

    summary = monitoring_summary(matches, manual_results, state, targets, outcomes, updates, now)
    print_summary(targets, outcomes, args.dry_run, summary)
    summary_json = getattr(args, "summary_json", None)
    if summary_json:
        write_json(summary_json, summary)

    if args.dry_run:
        return targets, outcomes, updates
    if not targets:
        return targets, outcomes, updates
    if updates:
        write_json(args.manual_results, merge_results(manual_payload, updates))
    write_json(args.state, state)
    if updates and not args.skip_generators:
        generator_runner()
    return targets, outcomes, updates


def require_string(payload: dict[str, Any], key: str, context: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{context}: {key} must be a non-empty string")
    return value


def require_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def optional_non_negative_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return require_non_negative_int(value, field_name)


if __name__ == "__main__":
    main()

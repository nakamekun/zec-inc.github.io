from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .base import MatchContext, ResultFetchOutcome, ResultProvider


class StaticResultFeedProvider(ResultProvider):
    """Trusted local result feed provider for tests and operator-controlled jobs."""

    def __init__(self, payload: dict[str, Any]) -> None:
        matches = payload.get("matches", {})
        if isinstance(matches, list):
            matches = {item.get("matchId"): item for item in matches if isinstance(item, dict)}
        if not isinstance(matches, dict):
            raise ValueError("result feed must contain matches object or array")
        self.matches = matches

    def fetch_result(self, match_context: MatchContext) -> ResultFetchOutcome:
        raw = self.matches.get(match_context.match_id)
        if raw is None:
            return ResultFetchOutcome(
                status="not_found",
                match_id=match_context.match_id,
                raw_source_name="static-result-feed",
                notes="no result in feed",
            )
        if not isinstance(raw, dict):
            return ResultFetchOutcome(
                status="provider_error",
                match_id=match_context.match_id,
                raw_source_name="static-result-feed",
                notes="feed result is not an object",
            )
        status = raw.get("status")
        if status in {"inProgress", "halfTime", "scheduled"}:
            return ResultFetchOutcome(
                status="not_final_yet",
                match_id=match_context.match_id,
                raw_source_name="static-result-feed",
                notes=f"feed status is {status}",
            )
        if status not in {"finished", "fullTime", "penalties"}:
            return ResultFetchOutcome(
                status="not_found",
                match_id=match_context.match_id,
                raw_source_name="static-result-feed",
                notes=f"unsupported feed status {status}",
            )
        try:
            home_score = require_non_negative_int(raw.get("homeScore"), "homeScore")
            away_score = require_non_negative_int(raw.get("awayScore"), "awayScore")
            home_penalty = optional_non_negative_int(raw.get("homePenaltyScore"), "homePenaltyScore")
            away_penalty = optional_non_negative_int(raw.get("awayPenaltyScore"), "awayPenaltyScore")
            if status == "penalties" and (home_penalty is None or away_penalty is None):
                return ResultFetchOutcome(
                    status="low_confidence",
                    match_id=match_context.match_id,
                    raw_source_name="static-result-feed",
                    notes="penalties result is missing penalty scores",
                    confidence=0.5,
                )
            if status != "penalties":
                home_penalty = None
                away_penalty = None
        except ValueError as error:
            return ResultFetchOutcome(
                status="provider_error",
                match_id=match_context.match_id,
                raw_source_name="static-result-feed",
                notes=str(error),
            )
        winner = winner_for(match_context, status, home_score, away_score, home_penalty, away_penalty)
        return ResultFetchOutcome(
            status="found",
            match_id=match_context.match_id,
            home_score=home_score,
            away_score=away_score,
            home_penalty_score=home_penalty,
            away_penalty_score=away_penalty,
            winner_team_id=winner,
            result_updated_at=raw.get("resultUpdatedAt") if isinstance(raw.get("resultUpdatedAt"), str) else utc_now(),
            confidence=float(raw.get("confidence", 1.0)),
            raw_source_name="static-result-feed",
            notes="trusted feed result accepted",
        )


def winner_for(
    match_context: MatchContext,
    status: str,
    home_score: int,
    away_score: int,
    home_penalty: int | None,
    away_penalty: int | None,
) -> str | None:
    if status == "penalties":
        return match_context.home_team_id if home_penalty > away_penalty else match_context.away_team_id
    if home_score > away_score:
        return match_context.home_team_id
    if away_score > home_score:
        return match_context.away_team_id
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def require_non_negative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def optional_non_negative_int(value: Any, field_name: str) -> int | None:
    if value is None:
        return None
    return require_non_negative_int(value, field_name)

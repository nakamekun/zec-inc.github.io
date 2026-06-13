from __future__ import annotations

import html
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

from .base import MatchContext, ResultFetchOutcome, ResultProvider
from .static_result_feed_provider import winner_for


FINAL_STATUS_HINTS = {
    "finished",
    "fulltime",
    "full_time",
    "full time",
    "ft",
    "after penalties",
    "penalties",
    "result",
}
LIVE_STATUS_HINTS = {"live", "inprogress", "in_progress", "half_time", "half time", "ht", "scheduled"}
FIFA_CALENDAR_API_URL = "https://api.fifa.com/api/v3/calendar/matches"
FIFA_WORLD_CUP_COMPETITION_ID = "17"
FIFA_WORLD_CUP_2026_SEASON_ID = "285023"
FINAL_MATCH_STATUS = 0
SCHEDULED_MATCH_STATUS = 1
TIME_MATCH_TOLERANCE = timedelta(hours=2)


class FifaMatchCentreProvider(ResultProvider):
    """Best-effort FIFA Match Centre provider that only updates high-confidence final results."""

    def __init__(self, timeout: int = 20, page_loader=None, json_loader=None) -> None:
        self.timeout = timeout
        self.page_loader = page_loader or self.load_page
        self.json_loader = json_loader or self.load_json

    def fetch_result(self, match_context: MatchContext) -> ResultFetchOutcome:
        api_outcome = self.fetch_calendar_result(match_context)
        if api_outcome.status != "provider_error":
            return api_outcome

        try:
            page = self.page_loader(match_context.match_centre_url)
        except Exception as error:  # noqa: BLE001
            return ResultFetchOutcome(
                status="provider_error",
                match_id=match_context.match_id,
                raw_source_name="fifa-match-centre",
                notes=f"fetch failed: {error.__class__.__name__}",
            )

        candidates = []
        for payload in extract_json_payloads(page):
            candidates.extend(find_match_like_objects(payload))
        best = choose_best_candidate(match_context, candidates)
        if best is None:
            return ResultFetchOutcome(
                status="not_found",
                match_id=match_context.match_id,
                raw_source_name="fifa-match-centre",
                notes="no high-structure match object found",
            )
        return candidate_to_outcome(match_context, best)

    def fetch_calendar_result(self, match_context: MatchContext) -> ResultFetchOutcome:
        try:
            payload = self.json_loader(calendar_url_for(match_context))
        except Exception as error:  # noqa: BLE001
            return ResultFetchOutcome(
                status="provider_error",
                match_id=match_context.match_id,
                raw_source_name="fifa-calendar-api",
                notes=f"calendar fetch failed: {error.__class__.__name__}",
            )
        matches = payload.get("Results") if isinstance(payload, dict) else None
        if not isinstance(matches, list):
            return ResultFetchOutcome(
                status="provider_error",
                match_id=match_context.match_id,
                raw_source_name="fifa-calendar-api",
                notes="calendar response missing Results array",
            )
        best = choose_best_calendar_candidate(match_context, matches)
        if best is None:
            return ResultFetchOutcome(
                status="not_found",
                match_id=match_context.match_id,
                raw_source_name="fifa-calendar-api",
                notes="no calendar match candidate matched number, teams, and kickoff",
            )
        return calendar_candidate_to_outcome(match_context, best)

    def load_page(self, url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ZEC Kickoff Bell result updater; contact: https://zec-inc.jp/support/"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")
            return response.read().decode("utf-8", errors="replace")

    def load_json(self, url: str) -> Any:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "ZEC Kickoff Bell result updater; contact: https://zec-inc.jp/support/"},
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            status = getattr(response, "status", 200)
            if status >= 400:
                raise RuntimeError(f"HTTP {status}")
            return json.loads(response.read().decode("utf-8", errors="replace"))


def calendar_url_for(match_context: MatchContext) -> str:
    start = (match_context.kickoff_utc - timedelta(hours=3)).date().isoformat()
    end = (match_context.kickoff_utc + timedelta(days=1)).date().isoformat()
    query = urlencode({
        "language": "en",
        "from": start,
        "to": end,
        "idCompetition": FIFA_WORLD_CUP_COMPETITION_ID,
        "idSeason": FIFA_WORLD_CUP_2026_SEASON_ID,
    })
    return f"{FIFA_CALENDAR_API_URL}?{query}"


def extract_json_payloads(page: str) -> list[Any]:
    payloads: list[Any] = []
    next_data = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*>(.*?)</script>',
        page,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if next_data:
        payload = decode_json(next_data.group(1))
        if payload is not None:
            payloads.append(payload)
    for match in re.finditer(r'<script[^>]+type=["\']application/json["\'][^>]*>(.*?)</script>', page, re.I | re.S):
        payload = decode_json(match.group(1))
        if payload is not None:
            payloads.append(payload)
    return payloads


def decode_json(raw: str) -> Any | None:
    try:
        return json.loads(html.unescape(raw).strip())
    except json.JSONDecodeError:
        return None


def find_match_like_objects(payload: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    stack = [payload]
    while stack:
        current = stack.pop()
        if isinstance(current, dict):
            keys = {str(key).lower() for key in current}
            if has_match_shape(keys):
                found.append(current)
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return found


def has_match_shape(keys: set[str]) -> bool:
    has_team = any("home" in key for key in keys) and any("away" in key for key in keys)
    has_score = any("score" in key or "goal" in key for key in keys)
    has_status = any("status" in key or "period" in key or "stage" in key for key in keys)
    return has_team and (has_score or has_status)


def choose_best_candidate(match_context: MatchContext, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    scored = []
    for candidate in candidates:
        confidence = candidate_confidence(match_context, candidate)
        if confidence > 0:
            scored.append((confidence, candidate))
    if not scored:
        return None
    scored.sort(key=lambda item: item[0], reverse=True)
    best_confidence, best = scored[0]
    copy = dict(best)
    copy["_zecConfidence"] = best_confidence
    return copy


def choose_best_calendar_candidate(match_context: MatchContext, candidates: list[Any]) -> dict[str, Any] | None:
    scored: list[tuple[float, dict[str, Any]]] = []
    rejected: list[dict[str, Any]] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        confidence, reject_reason = calendar_candidate_confidence(match_context, candidate)
        if confidence > 0:
            scored.append((confidence, candidate))
        elif reject_reason:
            rejected.append(calendar_diagnostics(match_context, candidate, reject_reason, confidence))
    if not scored:
        return {"_zecNoMatch": True, "_zecRejected": rejected[:8]}
    scored.sort(key=lambda item: item[0], reverse=True)
    best_confidence, best = scored[0]
    copy = dict(best)
    copy["_zecConfidence"] = best_confidence
    return copy


def calendar_candidate_confidence(match_context: MatchContext, candidate: dict[str, Any]) -> tuple[float, str | None]:
    if str(candidate.get("IdCompetition")) != FIFA_WORLD_CUP_COMPETITION_ID:
        return 0.0, "competition mismatch"
    if str(candidate.get("IdSeason")) != FIFA_WORLD_CUP_2026_SEASON_ID:
        return 0.0, "season mismatch"
    kickoff = parse_fifa_datetime(candidate.get("Date"))
    if kickoff is None:
        return 0.0, "missing kickoff"
    if abs(kickoff - match_context.kickoff_utc) > TIME_MATCH_TOLERANCE:
        return 0.0, "kickoff mismatch"
    home_name = team_name(candidate.get("Home"))
    away_name = team_name(candidate.get("Away"))
    if not team_names_match(match_context.home_team_name, home_name):
        return 0.0, "home team mismatch"
    if not team_names_match(match_context.away_team_name, away_name):
        return 0.0, "away team mismatch"

    confidence = 0.80
    if match_context.match_number is not None and candidate.get("MatchNumber") == match_context.match_number:
        confidence += 0.10
    if kickoff == match_context.kickoff_utc:
        confidence += 0.05
    if calendar_score_pair(candidate) is not None:
        confidence += 0.05
    if candidate.get("MatchStatus") == FINAL_MATCH_STATUS:
        confidence += 0.10
    return min(confidence, 1.0), None


def calendar_candidate_to_outcome(match_context: MatchContext, candidate: dict[str, Any]) -> ResultFetchOutcome:
    if candidate.get("_zecNoMatch") is True:
        rejected = candidate.get("_zecRejected")
        return ResultFetchOutcome(
            status="not_found",
            match_id=match_context.match_id,
            raw_source_name="fifa-calendar-api",
            notes=f"no calendar match candidate matched team and kickoff; rejected={json.dumps(rejected, ensure_ascii=False)}",
        )
    confidence = float(candidate.get("_zecConfidence", 0.0))
    status = candidate.get("MatchStatus")
    if status != FINAL_MATCH_STATUS:
        return ResultFetchOutcome(
            status="not_final_yet" if status == SCHEDULED_MATCH_STATUS else "low_confidence",
            match_id=match_context.match_id,
            confidence=min(confidence, 0.80),
            raw_source_name="fifa-calendar-api",
            notes=f"calendar candidate is not final: MatchStatus={status}",
        )
    scores = calendar_score_pair(candidate)
    if scores is None:
        return ResultFetchOutcome(
            status="low_confidence",
            match_id=match_context.match_id,
            confidence=min(confidence, 0.75),
            raw_source_name="fifa-calendar-api",
            notes="calendar candidate is missing complete score",
        )
    home_score, away_score = scores
    penalties = calendar_penalty_pair(candidate)
    winner = winner_for(
        match_context,
        "penalties" if penalties else "finished",
        home_score,
        away_score,
        penalties[0] if penalties else None,
        penalties[1] if penalties else None,
    )
    return ResultFetchOutcome(
        status="found" if confidence >= 0.9 else "low_confidence",
        match_id=match_context.match_id,
        home_score=home_score,
        away_score=away_score,
        home_penalty_score=penalties[0] if penalties else None,
        away_penalty_score=penalties[1] if penalties else None,
        winner_team_id=winner,
        result_updated_at=utc_now(),
        confidence=confidence,
        raw_source_name="fifa-calendar-api",
        notes=f"calendar API candidate parsed; {format_calendar_diagnostics(match_context, candidate, 'accepted', confidence)}",
    )


def calendar_diagnostics(
    match_context: MatchContext,
    candidate: dict[str, Any],
    reason: str,
    confidence: float,
) -> dict[str, Any]:
    kickoff = parse_fifa_datetime(candidate.get("Date"))
    return {
        "appMatchId": match_context.match_id,
        "appMatchNumber": match_context.match_number,
        "providerMatchNumber": candidate.get("MatchNumber"),
        "appKickoffUTC": match_context.kickoff_utc.isoformat().replace("+00:00", "Z"),
        "providerKickoffUTC": kickoff.isoformat().replace("+00:00", "Z") if kickoff else candidate.get("Date"),
        "appHome": match_context.home_team_name,
        "appAway": match_context.away_team_name,
        "providerHome": team_name(candidate.get("Home")),
        "providerAway": team_name(candidate.get("Away")),
        "rejectReason": reason,
        "confidence": confidence,
    }


def format_calendar_diagnostics(
    match_context: MatchContext,
    candidate: dict[str, Any],
    reason: str,
    confidence: float,
) -> str:
    return json.dumps(calendar_diagnostics(match_context, candidate, reason, confidence), ensure_ascii=False)


def candidate_confidence(match_context: MatchContext, candidate: dict[str, Any]) -> float:
    text = normalize_text(json.dumps(candidate, ensure_ascii=False))
    confidence = 0.0
    if match_context.home_team_name.lower() in text and match_context.away_team_name.lower() in text:
        confidence += 0.35
    elif match_context.home_team_id.lower() in text and match_context.away_team_id.lower() in text:
        confidence += 0.25
    else:
        return 0.0
    if match_context.match_id.lower() in text or (match_context.match_number and str(match_context.match_number) in text):
        confidence += 0.15
    kickoff = match_context.kickoff_utc.strftime("%Y-%m-%d")
    if kickoff in text:
        confidence += 0.15
    if any(hint in text for hint in FINAL_STATUS_HINTS):
        confidence += 0.25
    if score_pair(candidate) is not None:
        confidence += 0.15
    return min(confidence, 1.0)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower())


def parse_fifa_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return None


def team_name(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    names = value.get("TeamName")
    if isinstance(names, list):
        for item in names:
            if isinstance(item, dict) and isinstance(item.get("Description"), str):
                return item["Description"]
    for key in ["ShortClubName", "Abbreviation", "IdCountry"]:
        item = value.get(key)
        if isinstance(item, str):
            return item
    return ""


def team_names_match(expected: str, actual: str) -> bool:
    expected_normalized = normalize_team_name(expected)
    actual_normalized = normalize_team_name(actual)
    aliases = {
        "south korea": {"korea republic"},
        "czech republic": {"czechia"},
        "bosnia herzegovina": {"bosnia and herzegovina"},
        "usa": {"united states"},
        "ivory coast": {"cote divoire", "cotedivoire"},
        "dr congo": {"congo dr", "congo democratic republic"},
    }
    return actual_normalized == expected_normalized or actual_normalized in aliases.get(expected_normalized, set())


def normalize_team_name(value: str) -> str:
    value = html.unescape(value).lower()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def calendar_score_pair(candidate: dict[str, Any]) -> tuple[int, int] | None:
    home = candidate.get("HomeTeamScore")
    away = candidate.get("AwayTeamScore")
    if valid_score(home) and valid_score(away):
        return int(home), int(away)
    home_team = candidate.get("Home")
    away_team = candidate.get("Away")
    if isinstance(home_team, dict) and isinstance(away_team, dict):
        home = home_team.get("Score")
        away = away_team.get("Score")
        if valid_score(home) and valid_score(away):
            return int(home), int(away)
    return None


def calendar_penalty_pair(candidate: dict[str, Any]) -> tuple[int, int] | None:
    home = candidate.get("HomeTeamPenaltyScore")
    away = candidate.get("AwayTeamPenaltyScore")
    if not valid_score(home) or not valid_score(away):
        return None
    home_int = int(home)
    away_int = int(away)
    if home_int == 0 and away_int == 0:
        return None
    return home_int, away_int


def valid_score(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def candidate_to_outcome(match_context: MatchContext, candidate: dict[str, Any]) -> ResultFetchOutcome:
    confidence = float(candidate.get("_zecConfidence", 0.0))
    text = normalize_text(json.dumps(candidate, ensure_ascii=False))
    if any(hint in text for hint in LIVE_STATUS_HINTS) and not any(hint in text for hint in FINAL_STATUS_HINTS):
        return ResultFetchOutcome(
            status="not_final_yet",
            match_id=match_context.match_id,
            confidence=confidence,
            raw_source_name="fifa-match-centre",
            notes="candidate appears not final",
        )
    if not any(hint in text for hint in FINAL_STATUS_HINTS):
        return ResultFetchOutcome(
            status="low_confidence",
            match_id=match_context.match_id,
            confidence=min(confidence, 0.75),
            raw_source_name="fifa-match-centre",
            notes="score candidate has no final-state signal",
        )
    scores = score_pair(candidate)
    if scores is None:
        return ResultFetchOutcome(
            status="low_confidence",
            match_id=match_context.match_id,
            confidence=min(confidence, 0.75),
            raw_source_name="fifa-match-centre",
            notes="candidate is missing complete score",
        )
    home_score, away_score = scores
    penalties = penalty_pair(candidate)
    winner = winner_for(
        match_context,
        "penalties" if penalties else "finished",
        home_score,
        away_score,
        penalties[0] if penalties else None,
        penalties[1] if penalties else None,
    )
    return ResultFetchOutcome(
        status="found" if confidence >= 0.9 else "low_confidence",
        match_id=match_context.match_id,
        home_score=home_score,
        away_score=away_score,
        home_penalty_score=penalties[0] if penalties else None,
        away_penalty_score=penalties[1] if penalties else None,
        winner_team_id=winner,
        result_updated_at=utc_now(),
        confidence=confidence,
        raw_source_name="fifa-match-centre",
        notes="embedded JSON candidate parsed",
    )


def score_pair(candidate: dict[str, Any]) -> tuple[int, int] | None:
    flattened = flatten(candidate)
    home = first_int(flattened, ["homeScore", "home_score", "homeGoals", "homeTeamScore"])
    away = first_int(flattened, ["awayScore", "away_score", "awayGoals", "awayTeamScore"])
    if home is None or away is None:
        return None
    return home, away


def penalty_pair(candidate: dict[str, Any]) -> tuple[int, int] | None:
    flattened = flatten(candidate)
    home = first_int(flattened, ["homePenaltyScore", "home_penalty_score", "homePenalties"])
    away = first_int(flattened, ["awayPenaltyScore", "away_penalty_score", "awayPenalties"])
    if home is None or away is None:
        return None
    return home, away


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    output: dict[str, Any] = {}
    if isinstance(value, dict):
        for key, item in value.items():
            next_key = f"{prefix}.{key}" if prefix else str(key)
            output[next_key] = item
            output.update(flatten(item, next_key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            output.update(flatten(item, f"{prefix}.{index}"))
    return output


def first_int(values: dict[str, Any], suffixes: list[str]) -> int | None:
    lowered = {key.lower(): item for key, item in values.items()}
    for suffix in suffixes:
        suffix_lower = suffix.lower()
        for key, item in lowered.items():
            if key.endswith(suffix_lower) and isinstance(item, int) and not isinstance(item, bool) and item >= 0:
                return item
    return None


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

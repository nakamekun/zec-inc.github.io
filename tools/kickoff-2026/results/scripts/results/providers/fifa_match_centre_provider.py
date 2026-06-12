from __future__ import annotations

import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from typing import Any

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


class FifaMatchCentreProvider(ResultProvider):
    """Best-effort FIFA Match Centre provider that only updates high-confidence final results."""

    def __init__(self, timeout: int = 20, page_loader=None) -> None:
        self.timeout = timeout
        self.page_loader = page_loader or self.load_page

    def fetch_result(self, match_context: MatchContext) -> ResultFetchOutcome:
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

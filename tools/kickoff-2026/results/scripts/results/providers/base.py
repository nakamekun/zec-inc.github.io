from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MatchContext:
    match_id: str
    match_number: int | None
    kickoff_utc: datetime
    home_team_id: str
    away_team_id: str
    home_team_name: str
    away_team_name: str
    match_centre_url: str


@dataclass(frozen=True)
class ResultFetchOutcome:
    status: str
    match_id: str
    home_score: int | None = None
    away_score: int | None = None
    home_penalty_score: int | None = None
    away_penalty_score: int | None = None
    winner_team_id: str | None = None
    result_updated_at: str | None = None
    confidence: float = 0.0
    raw_source_name: str = ""
    notes: str = ""

    @property
    def is_found(self) -> bool:
        return self.status == "found"


class ResultProvider:
    def fetch_result(self, match_context: MatchContext) -> ResultFetchOutcome:
        raise NotImplementedError

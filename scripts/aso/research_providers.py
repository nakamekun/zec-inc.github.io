"""Research providers for ASO market discovery.

The research pipeline intentionally keeps provider output normalized and
serializable so future Apple Ads / ASC Analytics providers can be added
without changing proposal generation.
"""

from __future__ import annotations

import abc
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


class ResearchProvider(abc.ABC):
    """A source of keyword, competitor, or search-result research."""

    name = "abstract"

    @abc.abstractmethod
    def collect(self, request: dict) -> dict:
        """Return normalized research data for one request."""


def _locale_research(source: dict, locale: str) -> dict:
    locales = source.get("locales") or {}
    return (locales.get(locale) or {}).get("research") or {}


def _source_candidates(source: dict, locale: str) -> list[dict]:
    out: list[dict] = []
    loc = (source.get("locales") or {}).get(locale) or {}
    for raw in (loc.get("seed_keywords") or []):
        if isinstance(raw, str):
            out.append({"term": raw, "priority": 40, "source": "locale-seed"})
        elif isinstance(raw, dict) and raw.get("term"):
            out.append(
                {
                    "term": str(raw["term"]),
                    "priority": int(raw.get("priority") or 40),
                    "source": str(raw.get("source") or "locale-seed"),
                    "note": str(raw.get("note") or ""),
                }
            )
    for raw in _locale_research(source, locale).get("keyword_candidates") or []:
        if isinstance(raw, str):
            out.append({"term": raw, "priority": 100, "source": "aso-source"})
        elif isinstance(raw, dict) and raw.get("term"):
            out.append(
                {
                    "term": str(raw["term"]),
                    "priority": int(raw.get("priority") or 100),
                    "source": str(raw.get("source") or "aso-source"),
                    "note": str(raw.get("note") or ""),
                }
            )
    for raw in (_locale_research(source, locale).get("seed_keywords") or []):
        if isinstance(raw, str):
            out.append({"term": raw, "priority": 45, "source": "research-seed"})
    return out


def _source_competitors(source: dict, locale: str) -> list[dict]:
    out: list[dict] = []
    for raw in _locale_research(source, locale).get("competitors") or []:
        if isinstance(raw, str):
            out.append({"name": raw, "source": "aso-source"})
        elif isinstance(raw, dict) and raw.get("name"):
            item = dict(raw)
            item["name"] = str(item["name"])
            item.setdefault("source", "aso-source")
            out.append(item)
    return out


class StaticResearchProvider(ResearchProvider):
    """Reads research.keyword_candidates and competitors from aso-source.yaml."""

    name = "static"

    def collect(self, request: dict) -> dict:
        source = request.get("source") or {}
        locale = str(request["locale"])
        keywords = _source_candidates(source, locale)
        for term in request.get("seed_keywords") or []:
            if term and term.lower() not in {k["term"].lower() for k in keywords}:
                keywords.append(
                    {"term": term, "priority": 50, "source": "seed-keywords"}
                )
        competitors = _source_competitors(source, locale)
        for name in request.get("competitors") or []:
            if name and name.lower() not in {c["name"].lower() for c in competitors}:
                competitors.append({"name": name, "source": "cli"})
        return {
            "provider": self.name,
            "locale": locale,
            "country": request.get("country"),
            "keyword_candidates": keywords,
            "competitors": competitors,
            "search_results": [],
            "warnings": [],
        }


class AppStoreSearchProvider(ResearchProvider):
    """Fetches public App Store search results via Apple's iTunes Search API."""

    name = "appstore-search"
    endpoint = "https://itunes.apple.com/search"

    def __init__(
        self,
        cache_dir: Path,
        timeout: float = 8.0,
        refresh_cache: bool = False,
        use_cache: bool = True,
    ) -> None:
        self.cache_dir = cache_dir
        self.timeout = timeout
        self.refresh_cache = refresh_cache
        self.use_cache = use_cache

    def collect(self, request: dict) -> dict:
        locale = str(request["locale"])
        country = str(request.get("country") or "us").lower()
        terms = list(request.get("search_terms") or [])
        limit = int(request.get("max_results") or 20)
        all_results: list[dict] = []
        warnings: list[str] = []

        for term in terms:
            try:
                payload = self._fetch(country, term, limit)
            except Exception as exc:  # network is best-effort for v1
                warnings.append(f"{country}/{term}: {exc}")
                continue
            for raw in payload.get("results") or []:
                normalized = self._normalize_result(raw, country, term)
                if normalized:
                    all_results.append(normalized)

        return {
            "provider": self.name,
            "locale": locale,
            "country": country,
            "keyword_candidates": self._terms_from_results(all_results),
            "competitors": self._competitors_from_results(all_results),
            "search_results": all_results,
            "warnings": warnings,
        }

    def _fetch(self, country: str, term: str, limit: int) -> dict:
        if self.use_cache:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        key = hashlib.sha256(f"{country}\0{term}\0{limit}".encode("utf-8")).hexdigest()
        cache_path = self.cache_dir / f"{key}.json"
        if self.use_cache and not self.refresh_cache and cache_path.is_file():
            return json.loads(cache_path.read_text(encoding="utf-8"))

        params = urllib.parse.urlencode(
            {"country": country, "term": term, "limit": limit, "entity": "software"}
        )
        url = f"{self.endpoint}?{params}"
        req = urllib.request.Request(
            url, headers={"User-Agent": "zec-aso-research/1.0"}
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if self.use_cache:
            cache_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        time.sleep(0.1)
        return data

    @staticmethod
    def _normalize_result(raw: dict, country: str, query: str) -> dict:
        track_name = str(raw.get("trackName") or "").strip()
        if not track_name:
            return {}
        return {
            "query": query,
            "country": country,
            "trackName": track_name,
            "sellerName": str(raw.get("sellerName") or "").strip(),
            "description": str(raw.get("description") or "").strip(),
            "genres": list(raw.get("genres") or []),
            "averageUserRating": raw.get("averageUserRating"),
            "userRatingCount": raw.get("userRatingCount"),
            "price": raw.get("price"),
            "trackViewUrl": str(raw.get("trackViewUrl") or "").strip(),
        }

    @staticmethod
    def _terms_from_results(results: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for item in results:
            for token in _keywordish_terms(item.get("trackName") or ""):
                key = token.lower()
                if key not in seen:
                    seen.add(key)
                    out.append(
                        {
                            "term": token,
                            "priority": 120,
                            "source": "appstore-search-title",
                            "note": f"seen in result for {item.get('query')}",
                        }
                    )
        return out

    @staticmethod
    def _competitors_from_results(results: list[dict]) -> list[dict]:
        seen: set[str] = set()
        out: list[dict] = []
        for item in results:
            name = str(item.get("trackName") or "").strip()
            if not name or name.lower() in seen:
                continue
            seen.add(name.lower())
            out.append(
                {
                    "name": name,
                    "sellerName": item.get("sellerName") or "",
                    "source": "appstore-search",
                    "query": item.get("query") or "",
                    "rating": item.get("averageUserRating"),
                    "rating_count": item.get("userRatingCount"),
                    "url": item.get("trackViewUrl") or "",
                }
            )
        return out


def _keywordish_terms(text: str) -> list[str]:
    cleaned = (
        text.replace(":", " ")
        .replace("-", " ")
        .replace("|", " ")
        .replace("/", " ")
        .replace("・", " ")
    )
    out: list[str] = []
    stop_words = {
        "app", "apps", "the", "and", "for", "with", "you", "your", "all",
        "get", "in", "on", "to", "of", "my", "me", "mi", "la", "le", "pro",
        "free", "plus", "lite", "ai",
    }
    for raw in cleaned.split():
        term = raw.strip(".,()[]{}!?'\"®™+")
        if len(term) < 2:
            continue
        low = term.lower()
        if low in stop_words:
            continue
        if term.isascii() and len(term) < 3:
            continue
        if term.isascii() and not re.fullmatch(r"[A-Za-z][A-Za-z0-9]+", term):
            continue
        out.append(term)
    return out


def warn_provider_failures(result: dict) -> None:
    for warning in result.get("warnings") or []:
        print(f"warning: {result.get('provider')}: {warning}", file=sys.stderr)

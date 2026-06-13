"""Keyword research providers for the ASO pipeline.

generate_metadata.py only talks to the KeywordProvider interface so that
external data sources can be plugged in later without touching the
pipeline. The MVP ships with StaticSourceProvider, which reads research
curated by hand (or by an LLM session) into docs/aso/aso-source.yaml.

Planned future providers (not implemented yet):
- AppStoreSearchProvider: live App Store search suggestions / rankings
- AppleAdsProvider: Apple Search Ads keyword popularity scores
- AscAnalyticsProvider: App Store Connect search-term analytics
"""

from __future__ import annotations

import abc

from aso_core import KeywordCandidate


class KeywordProvider(abc.ABC):
    """A source of locale-specific keyword candidates."""

    name = "abstract"

    @abc.abstractmethod
    def candidates(self, source: dict, locale: str) -> list[KeywordCandidate]:
        """Return keyword candidates for one locale.

        `source` is the parsed aso-source.yaml so providers can read app
        context (slug, competitors, search intent) when querying.
        """


class StaticSourceProvider(KeywordProvider):
    """Reads locales.<locale>.research.keyword_candidates from the source YAML."""

    name = "static-source"

    def candidates(self, source: dict, locale: str) -> list[KeywordCandidate]:
        locales = source.get("locales") or {}
        research = (locales.get(locale) or {}).get("research") or {}
        out: list[KeywordCandidate] = []
        for raw in research.get("keyword_candidates") or []:
            if isinstance(raw, str):
                out.append(KeywordCandidate(term=raw, source=self.name))
            elif isinstance(raw, dict) and raw.get("term"):
                out.append(
                    KeywordCandidate(
                        term=str(raw["term"]),
                        priority=int(raw.get("priority") or 100),
                        source=str(raw.get("source") or self.name),
                        note=str(raw.get("note") or ""),
                    )
                )
        return out


def default_providers() -> list[KeywordProvider]:
    return [StaticSourceProvider()]

"""Keyword scoring for ASO research output."""

from __future__ import annotations

import re

import aso_core


def score_keywords(
    candidates: list[dict],
    current_metadata: dict,
    product_summary: str,
    search_results: list[dict],
    competitors: list[dict],
    locale: str,
) -> list[dict]:
    """Return scored keyword candidates sorted by descending total score."""
    deduped = _dedupe_candidates(candidates)
    result_count_by_query = _result_count_by_query(search_results)
    competitor_text = " ".join(c.get("name", "") for c in competitors)
    metadata_text = " ".join(str(v) for v in current_metadata.values())
    app_text = f"{product_summary} {metadata_text}"

    scored: list[dict] = []
    for cand in deduped:
        term = str(cand.get("term") or "").strip()
        if not term or _is_low_value_candidate(term):
            continue
        search_intent_fit = _fit(term, app_text)
        demand_proxy = _demand_proxy(term, result_count_by_query, search_results)
        competition_inverse = _competition_inverse(term, competitors, competitor_text)
        metadata_fit = _metadata_fit(term, metadata_text)
        conversion_fit = _conversion_fit(term, product_summary)
        character_efficiency = _character_efficiency(term, locale)
        risk_penalty = _risk_penalty(term)
        total = (
            search_intent_fit * 0.22
            + demand_proxy * 0.18
            + competition_inverse * 0.16
            + metadata_fit * 0.16
            + conversion_fit * 0.12
            + character_efficiency * 0.10
            - risk_penalty * 0.20
        )
        scored.append(
            {
                "term": term,
                "score": round(total, 4),
                "components": {
                    "search_intent_fit": round(search_intent_fit, 4),
                    "demand_proxy": round(demand_proxy, 4),
                    "competition_inverse": round(competition_inverse, 4),
                    "metadata_fit": round(metadata_fit, 4),
                    "conversion_fit": round(conversion_fit, 4),
                    "character_efficiency": round(character_efficiency, 4),
                    "risk_penalty": round(risk_penalty, 4),
                },
                "source": cand.get("source") or "unknown",
                "priority": cand.get("priority", 100),
                "note": cand.get("note") or "",
            }
        )
    return sorted(scored, key=lambda x: (-x["score"], x.get("priority", 100), x["term"]))


def _dedupe_candidates(candidates: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    for cand in candidates:
        term = str(cand.get("term") or "").strip()
        if not term:
            continue
        key = term.lower()
        old = by_key.get(key)
        if old is None or int(cand.get("priority") or 100) < int(old.get("priority") or 100):
            by_key[key] = dict(cand)
    return list(by_key.values())


def _result_count_by_query(search_results: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in search_results:
        query = str(item.get("query") or "").lower()
        if query:
            counts[query] = counts.get(query, 0) + 1
    return counts


def _fit(term: str, text: str) -> float:
    if aso_core.term_in_text(term, text):
        return 1.0
    tokens = _tokens(term)
    if not tokens:
        return 0.35
    hay = text.lower()
    hits = sum(1 for token in tokens if token in hay)
    return max(0.35, hits / len(tokens))


def _demand_proxy(term: str, result_count_by_query: dict[str, int], results: list[dict]) -> float:
    key = term.lower()
    direct = result_count_by_query.get(key, 0)
    title_hits = sum(1 for item in results if aso_core.term_in_text(term, item.get("trackName") or ""))
    desc_hits = sum(1 for item in results if aso_core.term_in_text(term, item.get("description") or ""))
    raw = direct + title_hits * 0.7 + desc_hits * 0.2
    return min(1.0, raw / 12.0) if raw else 0.45


def _competition_inverse(term: str, competitors: list[dict], competitor_text: str) -> float:
    if not competitors:
        return 0.55
    hits = sum(1 for comp in competitors if aso_core.term_in_text(term, comp.get("name") or ""))
    if hits:
        return max(0.10, 1.0 - hits / max(1, len(competitors)))
    if aso_core.term_in_text(term, competitor_text):
        return 0.4
    return 0.8


def _metadata_fit(term: str, metadata_text: str) -> float:
    return 0.9 if aso_core.term_in_text(term, metadata_text) else 0.55


def _conversion_fit(term: str, product_summary: str) -> float:
    benefit_words = {
        "simple", "fast", "quick", "daily", "habit", "widget", "private",
        "record", "log", "reminder", "tracking", "hydrate", "hydration",
        "シンプル", "簡単", "毎日", "習慣", "記録", "通知", "リマインダー",
        "ウィジェット", "水分補給",
    }
    if term.lower() in benefit_words or term in benefit_words:
        return 0.9
    return _fit(term, product_summary)


def _character_efficiency(term: str, locale: str) -> float:
    length = len(term)
    if not length:
        return 0.0
    if locale in {"ja", "ko", "zh-Hans", "zh-Hant"} or aso_core.contains_cjk(term):
        return max(0.35, min(1.0, 8 / length))
    return max(0.25, min(1.0, 12 / length))


def _risk_penalty(term: str) -> float:
    risky = {
        "#1", "best", "guarantee", "cure", "diagnosis", "medical", "doctor",
        "治療", "診断", "医療", "最高", "保証",
    }
    low = term.lower()
    if low in risky or term in risky:
        return 1.0
    if any(word in low for word in ("cure", "diagnos", "guarantee")):
        return 0.8
    return 0.0


def _tokens(text: str) -> list[str]:
    if aso_core.contains_cjk(text):
        return [text]
    return [t for t in re.split(r"[^0-9A-Za-z]+", text.lower()) if t]


def _is_low_value_candidate(term: str) -> bool:
    if aso_core.contains_cjk(term):
        return False
    low = term.lower().strip()
    stop_words = {
        "app", "apps", "the", "and", "for", "with", "you", "your", "all",
        "get", "in", "on", "to", "of", "my", "me", "mi", "la", "le", "pro",
        "free", "plus", "lite", "ai", "c", "est",
    }
    if low in stop_words:
        return True
    if len(low) < 3:
        return True
    if not re.fullmatch(r"[a-z0-9][a-z0-9 ]+[a-z0-9]", low):
        return True
    return False

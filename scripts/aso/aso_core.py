"""Shared model and validation rules for the ZEC ASO pipeline.

Both generate_metadata.py and validate_metadata.py import this module so
that LLM-authored copy is always machine-checked with the same rules.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# App Store Connect character limits (characters, not bytes).
LIMITS = {
    "name": 30,
    "subtitle": 30,
    "keywords": 100,
    "promotional_text": 170,
    "description": 4000,
    "release_notes": 4000,
}

METADATA_FIELDS = (
    "name",
    "subtitle",
    "keywords",
    "promotional_text",
    "description",
    "release_notes",
)
REQUIRED_FIELDS = ("name", "description", "keywords")
SINGLE_LINE_FIELDS = ("name", "subtitle", "keywords", "promotional_text")
URL_FIELDS = ("marketing_url", "privacy_url", "support_url")

# Below this, the 100-char keywords budget is probably being wasted.
# CJK locales can cover useful intent with fewer characters, so locale-aware
# callers should pass the locale to validate_locale / validate_keywords.
KEYWORDS_TARGET_MIN = 70
KEYWORDS_TARGET_MIN_BY_LOCALE = {
    "ja": 40,
    "ko": 40,
    "zh-Hans": 40,
    "zh-Hant": 40,
}

# ZEC standard App Store locales (used only for typo warnings).
KNOWN_LOCALES = {
    "ar-SA", "ca", "cs", "da", "de-DE", "el", "en-AU", "en-CA", "en-GB",
    "en-US", "es-ES", "es-MX", "fi", "fr-CA", "fr-FR", "he", "hi", "hr",
    "hu", "id", "it", "ja", "ko", "ms", "nl-NL", "no", "pl", "pt-BR",
    "pt-PT", "ro", "ru", "sk", "sv", "th", "tr", "uk", "vi", "zh-Hans",
    "zh-Hant",
}


@dataclass
class Issue:
    level: str  # "error" | "warning"
    code: str
    message: str
    field: str | None = None

    def as_dict(self) -> dict:
        return {
            "level": self.level,
            "code": self.code,
            "field": self.field,
            "message": self.message,
        }


@dataclass
class KeywordCandidate:
    term: str
    priority: int = 100
    source: str = "source-yaml"
    note: str = ""


_CJK_RE = re.compile(
    "[　-ヿ㐀-鿿豈-﫿ｦ-ﾟ가-힯]"
)


def contains_cjk(text: str) -> bool:
    return bool(_CJK_RE.search(text))


def ascii_tokens(text: str) -> set[str]:
    return {t for t in re.split(r"[^0-9A-Za-z]+", text.lower()) if t}


def term_in_text(term: str, text: str) -> bool:
    """Case-insensitive match; word-boundary for ASCII terms, substring for CJK."""
    term_l, text_l = term.strip().lower(), text.lower()
    if not term_l or not text_l:
        return False
    if term_l.isascii():
        pattern = r"(?<![0-9a-z])" + re.escape(term_l) + r"(?![0-9a-z])"
        return re.search(pattern, text_l) is not None
    return term_l in text_l


def keyword_overlaps_title(keyword: str, title_text: str) -> bool:
    """True if a keyword wastes budget by repeating the name/subtitle."""
    if contains_cjk(keyword):
        return keyword.lower() in title_text.lower()
    return keyword.lower() in ascii_tokens(title_text)


def assemble_keywords(
    candidates: list[KeywordCandidate],
    name: str,
    subtitle: str,
    limit: int = LIMITS["keywords"],
) -> tuple[str, list[str], list[tuple[str, str]]]:
    """Greedy keyword assembly: priority order, dedupe, drop terms already
    in name/subtitle, fill up to the character limit.

    Returns (keywords_string, used_terms, dropped_terms_with_reason).
    """
    title_text = f"{name} {subtitle}"
    used: list[str] = []
    dropped: list[tuple[str, str]] = []
    seen: set[str] = set()
    ordered = sorted(enumerate(candidates), key=lambda p: (p[1].priority, p[0]))
    for _, cand in ordered:
        term = cand.term.strip()
        if not term:
            continue
        key = term.lower()
        if key in seen:
            dropped.append((term, "duplicate candidate"))
            continue
        seen.add(key)
        if keyword_overlaps_title(term, title_text):
            dropped.append((term, "already in name/subtitle"))
            continue
        if len(",".join(used + [term])) > limit:
            dropped.append((term, f"over {limit}-char limit"))
            continue
        used.append(term)
    return ",".join(used), used, dropped


def normalize_avoid_terms(raw) -> list[dict]:
    out: list[dict] = []
    for entry in raw or []:
        if isinstance(entry, str):
            out.append({"term": entry, "level": "error", "reason": ""})
        elif isinstance(entry, dict) and entry.get("term"):
            level = str(entry.get("level") or "error")
            if level not in ("error", "warning"):
                level = "error"
            out.append(
                {
                    "term": str(entry["term"]),
                    "level": level,
                    "reason": str(entry.get("reason") or ""),
                }
            )
    return out


def keyword_target_min(locale: str | None = None) -> int:
    if locale in KEYWORDS_TARGET_MIN_BY_LOCALE:
        return KEYWORDS_TARGET_MIN_BY_LOCALE[locale]
    return KEYWORDS_TARGET_MIN


def validate_locale(
    fields: dict,
    avoid_terms: list[dict],
    locale: str | None = None,
) -> list[Issue]:
    """Machine checks for one locale's resolved metadata fields."""
    issues: list[Issue] = []
    name = str(fields.get("name") or "")
    subtitle = str(fields.get("subtitle") or "")

    for fname in METADATA_FIELDS:
        value = str(fields.get(fname) or "")
        if not value.strip():
            if fname in REQUIRED_FIELDS:
                issues.append(Issue("error", "empty-required", f"{fname} is empty", fname))
            elif fname in ("subtitle", "release_notes"):
                issues.append(Issue("warning", "empty-optional", f"{fname} is empty", fname))
            continue
        limit = LIMITS[fname]
        if len(value) > limit:
            issues.append(
                Issue("error", "over-limit",
                      f"{fname} is {len(value)} chars (limit {limit})", fname)
            )
        if fname in SINGLE_LINE_FIELDS and "\n" in value:
            issues.append(Issue("error", "newline", f"{fname} must be a single line", fname))

    issues += validate_keywords(str(fields.get("keywords") or ""), name, subtitle, locale)
    issues += check_avoid_terms(fields, avoid_terms)
    return issues


def validate_keywords(
    keywords: str,
    name: str,
    subtitle: str,
    locale: str | None = None,
) -> list[Issue]:
    issues: list[Issue] = []
    if not keywords.strip():
        return issues
    if ", " in keywords or " ," in keywords:
        issues.append(
            Issue("warning", "keyword-spaces",
                  "keywords contain spaces around commas; spaces count toward the 100-char limit",
                  "keywords")
        )
    terms = [t.strip() for t in keywords.split(",")]
    if any(not t for t in terms):
        issues.append(
            Issue("warning", "empty-keyword",
                  "keywords contain an empty entry (double or trailing comma)", "keywords")
        )
    title_text = f"{name} {subtitle}"
    seen: set[str] = set()
    for term in terms:
        if not term:
            continue
        key = term.lower()
        if key in seen:
            issues.append(
                Issue("warning", "duplicate-keyword", f"duplicate keyword: {term!r}", "keywords")
            )
        seen.add(key)
        if keyword_overlaps_title(term, title_text):
            issues.append(
                Issue("warning", "keyword-in-title",
                      f"keyword {term!r} already appears in name/subtitle", "keywords")
            )
    target_min = keyword_target_min(locale)
    if len(keywords) < target_min:
        issues.append(
            Issue("warning", "keywords-underused",
                  f"keywords use only {len(keywords)}/{LIMITS['keywords']} chars; "
                  f"target minimum is {target_min} for this locale; "
                  "consider adding candidates", "keywords")
        )
    return issues


def check_avoid_terms(fields: dict, avoid_terms: list[dict]) -> list[Issue]:
    issues: list[Issue] = []
    for entry in avoid_terms or []:
        term = str(entry.get("term") or "").strip()
        if not term:
            continue
        level = entry.get("level", "error")
        reason = str(entry.get("reason") or "")
        for fname in METADATA_FIELDS:
            value = str(fields.get(fname) or "")
            if value and term_in_text(term, value):
                message = f"avoid term {term!r} found in {fname}"
                if reason:
                    message += f" ({reason})"
                issues.append(Issue(level, "avoid-term", message, fname))
    return issues

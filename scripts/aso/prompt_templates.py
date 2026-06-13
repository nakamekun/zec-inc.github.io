"""Structured prompt generation for future LLM-assisted ASO metadata work."""

from __future__ import annotations

import json
from pathlib import Path

import aso_core


def build_metadata_research_prompt(
    app_summary: str,
    current_metadata: dict,
    locale: str,
    research: dict,
    scored_keywords: list[dict],
    competitor_summary: list[dict],
    validation_rules: dict,
) -> str:
    payload = {
        "task": "Create locale-specific App Store ASO metadata alternatives from research.",
        "locale": locale,
        "constraints": [
            "Return JSON only.",
            "Do not call external APIs.",
            "Do not directly translate the base locale.",
            "Treat the base locale only as product meaning and compliance context.",
            "Optimize for this locale's App Store search behavior.",
            "Use natural wording for this locale.",
            "Preserve product meaning and compliance constraints.",
            "Return reviewable alternatives, not only one answer.",
            "Respect App Store metadata limits.",
            "Avoid prohibited or risky terms.",
            "Avoid unsupported claims.",
            "Do not repeat keywords already in name/subtitle.",
            "Keep keywords comma-separated with no spaces around commas.",
        ],
        "expected_json_schema": {
            "proposals": [
                {
                    "strategy": "Search-first | Conversion-first | Long-tail / niche",
                    "name": "string",
                    "subtitle": "string",
                    "keywords": "comma-separated string",
                    "promotional_text": "string",
                    "description_outline": ["string"],
                    "rationale": "string",
                    "adopted_keywords": ["string"],
                    "excluded_keywords": [{"term": "string", "reason": "string"}],
                    "search_intent": "string",
                    "risks": ["string"],
                }
            ]
        },
        "app_product_summary": app_summary,
        "current_metadata": current_metadata,
        "base_locale_reference_policy": {
            "translation_first": False,
            "instruction": (
                "Use base-locale metadata to understand product meaning, feature scope, "
                "and compliance constraints. Redesign title, subtitle, keywords, "
                "promotional text, and description for this locale's search intent."
            ),
        },
        "research": research,
        "scored_keyword_candidates": scored_keywords,
        "competitor_summary": competitor_summary,
        "validation_rules": validation_rules,
    }
    return (
        "# ASO Metadata Research Prompt\n\n"
        "Use the following structured JSON as the only source of truth. "
        "The final proposal will be checked by the local ASO validator before use.\n\n"
        "```json\n"
        + json.dumps(payload, ensure_ascii=False, indent=2)
        + "\n```\n"
    )


def write_prompts(
    prompts_dir: Path,
    app_summary: str,
    locales_payload: dict,
    validation_rules: dict | None = None,
) -> list[Path]:
    prompts_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    rules = validation_rules or default_validation_rules()
    for locale, entry in locales_payload.items():
        prompt = build_metadata_research_prompt(
            app_summary=app_summary,
            current_metadata=entry.get("current_metadata") or {},
            locale=locale,
            research=entry.get("research") or {},
            scored_keywords=entry.get("scored_keywords") or [],
            competitor_summary=entry.get("competitors") or [],
            validation_rules=rules,
        )
        path = prompts_dir / f"metadata-research.{locale}.md"
        path.write_text(prompt, encoding="utf-8")
        written.append(path)
    return written


def default_validation_rules() -> dict:
    return {
        "limits": dict(aso_core.LIMITS),
        "required_fields": list(aso_core.REQUIRED_FIELDS),
        "single_line_fields": list(aso_core.SINGLE_LINE_FIELDS),
        "keywords_target_min": aso_core.KEYWORDS_TARGET_MIN,
        "keywords_target_min_by_locale": dict(aso_core.KEYWORDS_TARGET_MIN_BY_LOCALE),
        "notes": [
            "Generated proposals must be passed through aso_core.validate_locale.",
            "fastlane/metadata writes are handled only by generate_metadata.py --write.",
        ],
    }

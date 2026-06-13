"""Generate and validate metadata proposals from scored ASO research."""

from __future__ import annotations

import textwrap

import aso_core


PROPOSAL_KINDS = (
    ("A", "Search-first"),
    ("B", "Conversion-first"),
    ("C", "Long-tail / niche"),
)


def generate_locale_proposals(
    locale: str,
    current_metadata: dict,
    scored_keywords: list[dict],
    product_summary: str,
    avoid_terms: list[dict],
) -> list[dict]:
    proposals: list[dict] = []
    for label, strategy in PROPOSAL_KINDS:
        fields, used_terms, excluded = _fields_for_strategy(
            label, locale, current_metadata, scored_keywords, product_summary
        )
        issues = aso_core.validate_locale(fields, avoid_terms, locale)
        proposals.append(
            {
                "id": label,
                "strategy": strategy,
                "fields": fields,
                "rationale": _rationale(label, locale),
                "adopted_keywords": used_terms,
                "excluded_keywords": excluded,
                "search_intent": _search_intent(label, locale),
                "risks": _risks(label, issues),
                "issues": [issue.as_dict() for issue in issues],
            }
        )
    return proposals


def build_proposals_markdown(payload: dict) -> str:
    lines: list[str] = []
    app = payload["app"]
    lines.append(f"# ASO Metadata Proposals - {app['slug']}")
    lines.append("")
    lines.append(f"- Generated: {payload['generated_at']}")
    lines.append(f"- Source: `{payload.get('source') or 'none'}`")
    lines.append(f"- Providers: {', '.join(payload.get('providers') or []) or 'unknown'}")
    lines.append("- fastlane/metadata is not modified by this research command.")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    base_locale = app.get("base_locale")
    base_entry = (payload.get("locales") or {}).get(base_locale) if base_locale else None
    for locale, entry in payload["locales"].items():
        rec = _recommendation(entry)
        counts = _issue_counts(entry.get("proposals") or [])
        lines.append(
            f"- **{locale}**: recommend Proposal {rec['id']} ({rec['strategy']}) "
            f"because {rec['reason']} Validator: {counts['errors']} errors / "
            f"{counts['warnings']} warnings."
        )
    lines.append("")
    lines.append("## Proposal Comparison")
    lines.append("")
    lines.append("| Locale | Proposal | Strategy | Name | Subtitle | Keywords | Errors | Warnings | Role |")
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")
    for locale, entry in payload["locales"].items():
        for proposal in entry.get("proposals") or []:
            fields = proposal["fields"]
            counts = _issue_counts([proposal])
            lines.append(
                f"| {locale} | {proposal['id']} | {proposal['strategy']} "
                f"| {len(fields['name'])}/{aso_core.LIMITS['name']} "
                f"| {len(fields['subtitle'])}/{aso_core.LIMITS['subtitle']} "
                f"| {len(fields['keywords'])}/{aso_core.LIMITS['keywords']} "
                f"| {counts['errors']} | {counts['warnings']} "
                f"| {_md(_proposal_role(proposal['id']))} |"
            )
    lines.append("")
    for locale, entry in payload["locales"].items():
        lines.append(f"## {locale}")
        lines.append("")
        intents = (entry.get("locale_context") or {}).get("search_intents") or []
        if intents:
            lines.append("### Target User / Search Intent")
            lines.append("")
            for intent in intents[:6]:
                lines.append(f"- {_md(intent)}")
            lines.append("")
        lines.append("### Candidate Keywords")
        lines.append("")
        candidates = (entry.get("scored_keywords") or [])[:20]
        if candidates:
            lines.append("| Term | Score | Source |")
            lines.append("|---|---:|---|")
            for item in candidates:
                lines.append(
                    f"| {_md(item['term'])} | {item['score']:.4f} | "
                    f"{_md(item.get('source') or '')} |"
                )
        else:
            lines.append("- none")
        lines.append("")
        rec = _recommendation(entry)
        lines.append(
            f"**Recommendation:** Adopt Proposal {rec['id']} ({rec['strategy']}) "
            f"as the first human-review candidate. {rec['reason']}"
        )
        lines.append("")
        lines.append("### Competitor-Derived Candidates")
        lines.append("")
        competitor_terms = [
            item for item in (entry.get("scored_keywords") or [])
            if str(item.get("source") or "").startswith("appstore-search")
        ][:18]
        if competitor_terms:
            lines.append("| Term | Score | Source | Note |")
            lines.append("|---|---:|---|---|")
            for item in competitor_terms:
                lines.append(
                    f"| {_md(item['term'])} | {item['score']:.4f} | "
                    f"{_md(item.get('source') or '')} | {_md(item.get('note') or '')} |"
                )
        else:
            lines.append("- none")
        lines.append("")
        for proposal in entry.get("proposals") or []:
            fields = proposal["fields"]
            lines.append(f"### Proposal {proposal['id']}: {proposal['strategy']}")
            lines.append("")
            lines.append(f"**What it is optimizing:** {_proposal_role(proposal['id'])}")
            lines.append("")
            lines.append("| Field | Chars | Limit | Value |")
            lines.append("|---|---:|---:|---|")
            for fname in ("name", "subtitle", "keywords", "promotional_text"):
                lines.append(
                    f"| {fname} | {len(fields[fname])} | {aso_core.LIMITS[fname]} | "
                    f"{_md(fields[fname])} |"
                )
            lines.append("")
            lines.append("**Description outline**")
            lines.append("")
            for item in proposal["description_outline"]:
                lines.append(f"- {item}")
            lines.append("")
            lines.append(f"**Rationale:** {proposal['rationale']}")
            lines.append("")
            lines.append(f"**Why this proposal can win:** {_why_it_can_win(proposal['id'])}")
            lines.append("")
            lines.append(
                f"**Translation risk note:** "
                f"{_translation_risk_note(locale, proposal, base_locale, base_entry)}"
            )
            lines.append("")
            lines.append("**Adopted keywords:** " + ", ".join(proposal["adopted_keywords"]))
            lines.append("")
            lines.append("**Excluded keywords**")
            lines.append("")
            for item in proposal["excluded_keywords"][:12]:
                lines.append(f"- {item['term']}: {item['reason']}")
            if not proposal["excluded_keywords"]:
                lines.append("- none")
            lines.append("")
            lines.append(f"**Expected search intent:** {proposal['search_intent']}")
            lines.append("")
            lines.append("**Risks**")
            lines.append("")
            lines.append("| Risk | Impact |")
            lines.append("|---|---|")
            for risk in proposal["risks"]:
                lines.append(f"| {_md(risk)} | {_md(_risk_impact(risk))} |")
            lines.append("")
            lines.append("**Validator issues**")
            lines.append("")
            if proposal["issues"]:
                for issue in proposal["issues"]:
                    mark = "ERROR" if issue["level"] == "error" else "WARN"
                    where = f" [{issue['field']}]" if issue.get("field") else ""
                    lines.append(f"- **{mark}**{where} {issue['message']} ({issue['code']})")
            else:
                lines.append("- none")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _recommendation(entry: dict) -> dict:
    proposals = entry.get("proposals") or []
    if not proposals:
        return {"id": "-", "strategy": "none", "reason": "no proposals were generated."}

    def rank(proposal: dict) -> tuple[int, int, int, str]:
        counts = _issue_counts([proposal])
        keyword_len = len(proposal["fields"].get("keywords") or "")
        # Prefer Search-first when validation is clean and keyword coverage is
        # healthy; otherwise fall back to fewer issues and more coverage.
        strategy_bias = 0 if proposal["id"] == "A" else (1 if proposal["id"] == "B" else 2)
        return (counts["errors"], counts["warnings"], -keyword_len, str(strategy_bias))

    best = sorted(proposals, key=rank)[0]
    if best["id"] == "A":
        reason = "it gives the broadest search coverage while keeping validator issues low."
    elif best["id"] == "B":
        reason = "it balances clear benefit copy with enough keyword coverage."
    else:
        reason = "it avoids crowded head terms and targets narrower search intent."
    return {"id": best["id"], "strategy": best["strategy"], "reason": reason}


def _issue_counts(proposals: list[dict]) -> dict:
    issues = [issue for proposal in proposals for issue in proposal.get("issues") or []]
    return {
        "errors": sum(1 for issue in issues if issue.get("level") == "error"),
        "warnings": sum(1 for issue in issues if issue.get("level") == "warning"),
    }


def _proposal_role(label: str) -> str:
    return {
        "A": "Discovery first: covers high-fit category and intent terms.",
        "B": "Conversion first: keeps the store page promise clearer.",
        "C": "Niche first: uses efficient long-tail terms with less direct competition.",
    }.get(label, "")


def _why_it_can_win(label: str) -> str:
    return {
        "A": "It is the best default when the app needs more search surface area.",
        "B": "It is useful when screenshots and product-page copy need to convert cautious users.",
        "C": "It is useful when broad category terms are saturated or too generic.",
    }.get(label, "")


def _risk_impact(risk: str) -> str:
    if "Validator errors" in risk:
        return "Cannot ship until fixed."
    if "underused" in risk:
        return "May leave search reach unused."
    if "competitive" in risk:
        return "May rank slowly without stronger conversion signals."
    if "Conversion" in risk:
        return "May miss some query variants."
    if "Long-tail" in risk:
        return "May have smaller search volume."
    return "Review before copying into aso-source.yaml."


def _fields_for_strategy(
    label: str,
    locale: str,
    current: dict,
    scored: list[dict],
    product_summary: str,
) -> tuple[dict, list[str], list[dict]]:
    name = _clip(current.get("name") or _default_name(locale), aso_core.LIMITS["name"])
    top = _select_terms(label, scored)
    subtitle = _subtitle(label, locale, current, top)
    promo = _promotional_text(label, locale, current)
    candidates = [
        aso_core.KeywordCandidate(
            term=item["term"], priority=i + 1, source=item.get("source") or "scored"
        )
        for i, item in enumerate(top)
    ]
    keywords, used, dropped_pairs = aso_core.assemble_keywords(candidates, name, subtitle)
    description = _description(label, locale, name, product_summary)
    fields = {
        "name": name,
        "subtitle": subtitle,
        "keywords": keywords,
        "promotional_text": promo,
        "description": description,
        "release_notes": current.get("release_notes") or "Initial release.",
    }
    excluded = [{"term": term, "reason": reason} for term, reason in dropped_pairs]
    used_set = {term.lower() for term in used}
    for item in top:
        if item["term"].lower() not in used_set and not any(e["term"] == item["term"] for e in excluded):
            excluded.append({"term": item["term"], "reason": "lower priority or strategy fit"})
    return fields, used, excluded


def _select_terms(label: str, scored: list[dict]) -> list[dict]:
    if label == "A":
        return scored[:24]
    if label == "B":
        return sorted(
            scored,
            key=lambda x: (
                -x["components"].get("conversion_fit", 0),
                -x["components"].get("metadata_fit", 0),
                -x["score"],
            ),
        )[:24]
    return sorted(
        scored,
        key=lambda x: (
            -x["components"].get("competition_inverse", 0),
            -x["components"].get("character_efficiency", 0),
            -x["score"],
        ),
    )[:24]


def _subtitle(label: str, locale: str, current: dict, top: list[dict]) -> str:
    current_subtitle = str(current.get("subtitle") or "").strip()
    if label == "B" and current_subtitle:
        return _clip(current_subtitle, aso_core.LIMITS["subtitle"])
    if top:
        selected = _join_terms_for_subtitle([item["term"] for item in top[:3]], locale)
        if selected:
            return _clip(selected, aso_core.LIMITS["subtitle"])
    return _clip(current_subtitle or _default_subtitle(locale), aso_core.LIMITS["subtitle"])


def _promotional_text(label: str, locale: str, current: dict) -> str:
    current_promo = str(current.get("promotional_text") or "").strip()
    if current_promo:
        return _clip(current_promo, aso_core.LIMITS["promotional_text"])
    if locale == "ja":
        return "このlocaleの検索意図に合わせて、主要機能と使う場面を自然な日本語で伝えます。"
    return "Built around this locale's search intent with clear benefits and natural App Store wording."


def _description(label: str, locale: str, name: str, product_summary: str) -> str:
    if locale == "ja":
        body = f"""{name}のlocale別ASO提案です。

主な内容:
- このlocaleの検索意図に合わせたtitle/subtitle/keywords
- 自然な表現と検索語の両立
- base localeの直訳ではなく、機能意味と禁止表現を保った再設計

説明文は、実際の機能、スクリーンショット、App Review上の安全な表現に合わせて人間が最終確認してください。"""
    else:
        body = f"""{name} locale-specific ASO proposal.

Highlights:
- Title, subtitle, and keywords designed for this locale's search behavior
- Natural wording balanced with relevant search terms
- Product meaning and compliance constraints preserved without direct translation

Review final description wording against actual features, screenshots, and App Review-safe claims."""
    if product_summary.strip():
        body += "\n\nProduct context used for this proposal:\n" + product_summary.strip()
    return body[: aso_core.LIMITS["description"]]


def _rationale(label: str, locale: str) -> str:
    if label == "A":
        return "Prioritizes high-fit category and intent keywords for discoverability."
    if label == "B":
        return "Keeps clearer benefit language in subtitle and promo copy for product-page conversion."
    return "Uses efficient and less crowded terms to cover narrower search intent."


def _search_intent(label: str, locale: str) -> str:
    if locale == "ja":
        return {
            "A": "このlocaleの主要カテゴリ語と用途語で探すユーザー。",
            "B": "機能の分かりやすさと自然な説明で比較検討するユーザー。",
            "C": "より具体的な利用シーンやロングテール語で探すユーザー。",
        }[label]
    return {
        "A": "Users searching broad category and use-case terms for this locale.",
        "B": "Users comparing product-page clarity, benefits, and fit.",
        "C": "Users searching narrower long-tail use cases and specific workflows.",
    }[label]


def _risks(label: str, issues: list[aso_core.Issue]) -> list[str]:
    risks = []
    if any(i.level == "error" for i in issues):
        risks.append("Validator errors must be fixed before this can become aso-source.yaml.")
    if any(i.code == "keywords-underused" for i in issues):
        risks.append("Keyword budget is underused; add more locale-specific candidates if relevant.")
    if label == "A":
        risks.append("Broader category terms may be more competitive.")
    elif label == "B":
        risks.append("Conversion-friendly copy may sacrifice some keyword coverage.")
    else:
        risks.append("Long-tail terms can have lower demand.")
    return risks


def description_outline(locale: str) -> list[str]:
    if locale == "ja":
        return ["対象ユーザーと検索意図", "主要機能", "利用シーン", "禁止表現を避けた安全な説明"]
    return ["Target user and search intent", "Core features", "Use cases", "Compliance-safe wording"]


def attach_description_outlines(proposals: list[dict], locale: str) -> None:
    for proposal in proposals:
        proposal["description_outline"] = description_outline(locale)


def _default_name(locale: str) -> str:
    return "ASO App" if locale != "ja" else "ASOアプリ"


def _default_subtitle(locale: str) -> str:
    return "Locale ASO proposal" if locale != "ja" else "locale別ASO提案"


def _join_terms_for_subtitle(terms: list[str], locale: str) -> str:
    clean = [str(term).strip() for term in terms if str(term).strip()]
    if not clean:
        return ""
    if locale in {"ja", "ko", "zh-Hans", "zh-Hant"} or any(aso_core.contains_cjk(t) for t in clean):
        for count in (3, 2, 1):
            value = "・".join(clean[:count])
            if len(value) <= aso_core.LIMITS["subtitle"]:
                return value
    else:
        for count in (3, 2, 1):
            value = " ".join(clean[:count])
            if len(value) <= aso_core.LIMITS["subtitle"]:
                return value
    return clean[0][: aso_core.LIMITS["subtitle"]]


def _translation_risk_note(
    locale: str,
    proposal: dict,
    base_locale: str | None,
    base_entry: dict | None,
) -> str:
    if not base_locale or locale == base_locale or not base_entry:
        return "Base locale proposal; use as product meaning reference, not as a translation source."
    base_proposals = {p.get("id"): p for p in (base_entry.get("proposals") or [])}
    base = base_proposals.get(proposal.get("id"))
    if not base:
        return "No matching base-locale proposal to compare."
    copied = []
    for field in ("name", "subtitle", "keywords", "promotional_text"):
        if proposal["fields"].get(field) and proposal["fields"].get(field) == base["fields"].get(field):
            copied.append(field)
    if copied:
        return (
            "Review for direct-copy risk in "
            + ", ".join(copied)
            + "; this locale should use its own ASO wording where possible."
        )
    return "No exact base-locale copy detected in title, subtitle, keywords, or promotional text."


def _clip(value: str, limit: int) -> str:
    return textwrap.shorten(str(value).strip(), width=limit, placeholder="") if len(str(value).strip()) > limit else str(value).strip()


def _md(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")

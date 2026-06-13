#!/usr/bin/env python3
"""Run ASO market research and produce metadata proposal artifacts.

This command never writes fastlane metadata. It gathers static and optional
public App Store research, scores keywords, creates proposal drafts, validates
them through aso_core, and writes review artifacts under <app>/docs/aso/.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aso_core
import keyword_scoring
import miniyaml
import prompt_templates
import proposal_generator
from research_providers import (
    AppStoreSearchProvider,
    StaticResearchProvider,
    warn_provider_failures,
)


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Research ASO keywords and metadata proposals.")
    parser.add_argument("path", nargs="?", help="App directory (kept for compatibility)")
    parser.add_argument(
        "--app",
        dest="app",
        help="App directory (preferred, matches generate_metadata.py)",
    )
    parser.add_argument("--locale", "--locales", dest="locales", help="Comma-separated locales")
    parser.add_argument("--country", "--countries", dest="countries", help="Comma-separated countries")
    parser.add_argument("--seed-keywords", help="Comma-separated seed keywords")
    parser.add_argument("--competitors", help="Comma-separated competitor names")
    parser.add_argument("--max-results", type=int, default=20, help="App Store results per query")
    parser.add_argument("--offline", action="store_true", help="Skip public App Store search")
    parser.add_argument(
        "--refresh-cache",
        action="store_true",
        help="Ignore existing App Store search cache and rewrite it",
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Do not read or write App Store search cache for this run",
    )
    parser.add_argument(
        "--write-suggestion",
        action="store_true",
        help="Write docs/aso/aso-source.suggested.yaml for human review",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if not args.app and not args.path:
        print("error: app directory required (use --app <path> or positional path)", file=sys.stderr)
        return 2
    if args.app and args.path:
        print("error: provide either --app or positional path, not both", file=sys.stderr)
        return 2
    if args.max_results < 1 or args.max_results > 50:
        print("error: --max-results must be between 1 and 50", file=sys.stderr)
        return 2

    app_dir = Path(args.app or args.path).resolve()
    if not app_dir.is_dir():
        print(f"error: app directory not found: {app_dir}", file=sys.stderr)
        return 2

    aso_dir = app_dir / "docs" / "aso"
    aso_dir.mkdir(parents=True, exist_ok=True)
    source_path = aso_dir / "aso-source.yaml"
    source = _load_source(source_path)
    app_info = source.get("app") or {}
    locales = _split_arg(args.locales) or list((source.get("locales") or {}).keys()) or ["en-US"]
    countries = _split_arg(args.countries) or ["us"]
    if len(countries) not in (1, len(locales)):
        print(
            "error: --country must provide either one country for all locales "
            f"or exactly {len(locales)} countries for locales {','.join(locales)}",
            file=sys.stderr,
        )
        return 2
    seed_keywords = _split_arg(args.seed_keywords)
    if len(seed_keywords) < 3:
        print(
            "warning: fewer than 3 seed keywords supplied; research will rely on "
            "aso-source.yaml and current metadata",
            file=sys.stderr,
        )
    cli_competitors = _split_arg(args.competitors)
    product_summary = _read_product_summary(app_dir)
    current_by_locale = {
        locale: _read_current_metadata(app_dir, locale, source)
        for locale in locales
    }
    generated_at = _now()

    payload = {
        "schema": 1,
        "generated_at": generated_at,
        "app": {
            "slug": str(app_info.get("slug") or app_dir.name),
            "base_locale": str(app_info.get("base_locale") or locales[0]),
        },
        "source": str(source_path) if source_path.is_file() else "",
        "offline": bool(args.offline),
        "providers": ["static"] if args.offline else ["static", "appstore-search"],
        "cache": {
            "use_cache": not args.no_cache,
            "refresh_cache": bool(args.refresh_cache),
        },
        "locales": {},
        "future_provider_notes": _future_provider_notes(),
    }

    keyword_payload = {
        "schema": 1,
        "generated_at": generated_at,
        "app": payload["app"],
        "locales": {},
    }

    static_provider = StaticResearchProvider()
    appstore_provider = AppStoreSearchProvider(
        app_dir / ".cache" / "aso" / "appstore-search",
        refresh_cache=args.refresh_cache,
        use_cache=not args.no_cache,
    )

    for idx, locale in enumerate(locales):
        country = countries[min(idx, len(countries) - 1)].lower()
        current_metadata = current_by_locale[locale]
        locale_seed_keywords = _seed_keywords_for_locale(seed_keywords, locale)
        static_request = {
            "source": source,
            "locale": locale,
            "country": country,
            "seed_keywords": locale_seed_keywords,
            "competitors": cli_competitors,
        }
        static_result = static_provider.collect(static_request)
        search_terms = _search_terms(locale_seed_keywords, static_result["keyword_candidates"], current_metadata)
        provider_results = [static_result]
        print(f"{locale}: provider static ({len(static_result['keyword_candidates'])} keyword seeds)")
        if not args.offline:
            live_result = appstore_provider.collect(
                {
                    "locale": locale,
                    "country": country,
                    "search_terms": search_terms,
                    "max_results": args.max_results,
                }
            )
            warn_provider_failures(live_result)
            provider_results.append(live_result)
            print(
                f"{locale}: provider appstore-search "
                f"({len(live_result['search_results'])} results, "
                f"{len(live_result['warnings'])} warnings)"
            )
        else:
            print(f"{locale}: offline mode; skipped appstore-search")

        merged = _merge_provider_results(provider_results)
        scored = keyword_scoring.score_keywords(
            merged["keyword_candidates"],
            current_metadata,
            product_summary,
            merged["search_results"],
            merged["competitors"],
            locale,
        )
        avoid_terms = _avoid_terms(source, locale)
        proposals = proposal_generator.generate_locale_proposals(
            locale, current_metadata, scored, product_summary, avoid_terms
        )
        proposal_generator.attach_description_outlines(proposals, locale)

        entry = {
            "country": country,
            "current_metadata": current_metadata,
            "locale_context": _locale_context(source, locale),
            "research": {
                "search_terms": search_terms,
                "provider_results": provider_results,
                "search_results": merged["search_results"],
            },
            "competitors": merged["competitors"],
            "scored_keywords": scored,
            "proposals": proposals,
            "avoid_terms": avoid_terms,
        }
        payload["locales"][locale] = entry
        keyword_payload["locales"][locale] = {
            "country": country,
            "candidates": scored,
            "top_terms": [item["term"] for item in scored[:20]],
        }

    research_path = aso_dir / "research.generated.json"
    research_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    keyword_path = aso_dir / "keyword-candidates.generated.json"
    keyword_path.write_text(json.dumps(keyword_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    proposals_path = aso_dir / "metadata-proposals.md"
    proposals_path.write_text(proposal_generator.build_proposals_markdown(payload), encoding="utf-8")
    prompt_paths = prompt_templates.write_prompts(aso_dir / "prompts", product_summary, payload["locales"])

    suggestion_path = None
    if args.write_suggestion:
        suggestion_path = aso_dir / "aso-source.suggested.yaml"
        suggestion_path.write_text(_build_suggested_yaml(payload), encoding="utf-8")

    generated_files = [research_path, keyword_path, proposals_path]
    for path in prompt_paths:
        generated_files.append(path)
    if suggestion_path:
        generated_files.append(suggestion_path)
    print("Generated files:")
    for path in generated_files:
        print(f"  {path}")
    print("Dry-run: fastlane/metadata was not touched.")
    _print_summary(payload)
    return 0


def _load_source(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        return miniyaml.load_file(path)
    except miniyaml.YamlError as exc:
        print(f"warning: could not parse {path}: {exc}", file=sys.stderr)
        return {}


def _read_current_metadata(app_dir: Path, locale: str, source: dict | None = None) -> dict:
    out: dict[str, str] = {}
    source_meta = (((source or {}).get("locales") or {}).get(locale) or {}).get("metadata") or {}
    meta_dir = app_dir / "fastlane" / "metadata" / locale
    for fname in aso_core.METADATA_FIELDS:
        path = meta_dir / f"{fname}.txt"
        if path.is_file():
            out[fname] = path.read_text(encoding="utf-8").strip()
        else:
            out[fname] = str(source_meta.get(fname) or "").strip()
    return out


def _read_product_summary(app_dir: Path) -> str:
    for rel in ("docs/product-spec.md", "PRODUCT_SPEC.md", "docs/APP_STORE_METADATA.md"):
        path = app_dir / rel
        if path.is_file():
            return path.read_text(encoding="utf-8").strip()
    return ""


def _split_arg(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip().strip("\"'") for part in value.split(",") if part.strip().strip("\"'")]


def _seed_keywords_for_locale(seed_keywords: list[str], locale: str) -> list[str]:
    if not seed_keywords:
        return []
    cjk_locale = locale in {"ja", "ko", "zh-Hans", "zh-Hant"}
    filtered = [
        term for term in seed_keywords
        if aso_core.contains_cjk(term) == cjk_locale
    ]
    return filtered or seed_keywords


def _search_terms(seed_keywords: list[str], candidates: list[dict], current: dict) -> list[str]:
    terms: list[str] = []
    for term in seed_keywords:
        if term and term.lower() not in {t.lower() for t in terms}:
            terms.append(term)
    for cand in candidates:
        term = str(cand.get("term") or "").strip()
        if term and term.lower() not in {t.lower() for t in terms}:
            terms.append(term)
    for fname in ("name", "subtitle"):
        for token in str(current.get(fname) or "").replace("-", " ").split():
            token = token.strip()
            if len(token) > 2 and token.lower() not in {t.lower() for t in terms}:
                terms.append(token)
    return terms[:12]


def _merge_provider_results(results: list[dict]) -> dict:
    keywords: list[dict] = []
    competitors: list[dict] = []
    search_results: list[dict] = []
    seen_keywords: set[str] = set()
    seen_competitors: set[str] = set()
    for result in results:
        for item in result.get("keyword_candidates") or []:
            term = str(item.get("term") or "").strip()
            if term and term.lower() not in seen_keywords:
                seen_keywords.add(term.lower())
                keywords.append(item)
        for item in result.get("competitors") or []:
            name = str(item.get("name") or "").strip()
            if name and name.lower() not in seen_competitors:
                seen_competitors.add(name.lower())
                competitors.append(item)
        search_results.extend(result.get("search_results") or [])
    return {
        "keyword_candidates": keywords,
        "competitors": competitors,
        "search_results": search_results,
    }


def _avoid_terms(source: dict, locale: str) -> list[dict]:
    loc = ((source.get("locales") or {}).get(locale) or {})
    return aso_core.normalize_avoid_terms((source.get("defaults") or {}).get("avoid_terms")) + aso_core.normalize_avoid_terms(loc.get("avoid_terms"))


def _locale_context(source: dict, locale: str) -> dict:
    loc = ((source.get("locales") or {}).get(locale) or {})
    research = loc.get("research") or {}
    intents = []
    raw_intents = loc.get("search_intents") or research.get("search_intents") or []
    if isinstance(raw_intents, str):
        intents.append(raw_intents)
    else:
        intents += [str(item) for item in raw_intents if item]
    if research.get("search_intent"):
        intents.append(str(research.get("search_intent")))
    seeds = []
    for raw in (loc.get("seed_keywords") or []) + (research.get("seed_keywords") or []):
        if isinstance(raw, str):
            seeds.append(raw)
        elif isinstance(raw, dict) and raw.get("term"):
            seeds.append(str(raw["term"]))
    return {
        "seed_keywords": seeds,
        "search_intents": intents,
    }


def _build_suggested_yaml(payload: dict) -> str:
    app = payload["app"]
    lines = [
        "# Suggested ASO source generated for human review.",
        "# Copy selected values into aso-source.yaml only after reviewing validator issues.",
        "app:",
        f"  slug: {_yaml_scalar(app['slug'])}",
        f"  base_locale: {_yaml_scalar(app['base_locale'])}",
        "",
        "defaults:",
        "  avoid_terms:",
        "    - term: \"#1\"",
        "      level: error",
        "      reason: ranking claims are not allowed in App Store metadata",
        "    - term: best",
        "      level: warning",
        "      reason: superlative claims invite App Review pushback",
        "",
        "locales:",
    ]
    for locale, entry in payload["locales"].items():
        proposal = (entry.get("proposals") or [{}])[0]
        fields = proposal.get("fields") or {}
        context = entry.get("locale_context") or {}
        lines += [
            f"  {locale}:",
            "    seed_keywords:",
        ]
        for term in (context.get("seed_keywords") or [])[:20]:
            lines.append(f"      - {_yaml_scalar(term)}")
        lines += [
            "    search_intents:",
        ]
        for intent in (context.get("search_intents") or [proposal.get("search_intent", "")])[:8]:
            lines.append(f"      - {_yaml_scalar(intent)}")
        lines += [
            "    research:",
            "      search_intent: |",
            f"        {proposal.get('search_intent', '').replace(chr(10), ' ')}",
            "      keyword_candidates:",
        ]
        for item in (entry.get("scored_keywords") or [])[:20]:
            lines += [
                f"        - term: {_yaml_scalar(item['term'])}",
                f"          priority: {int((1.0 - float(item.get('score') or 0)) * 100) + 1}",
                f"          source: {_yaml_scalar(item.get('source') or 'research')}",
            ]
        lines.append("      competitors:")
        for comp in (entry.get("competitors") or [])[:10]:
            lines.append(f"        - {_yaml_scalar(comp.get('name') or '')}")
        lines += [
            "    metadata:",
            f"      name: {_yaml_scalar(fields.get('name') or '')}",
            f"      subtitle: {_yaml_scalar(fields.get('subtitle') or '')}",
            f"      promotional_text: {_yaml_scalar(fields.get('promotional_text') or '')}",
            "      description: |",
        ]
        for line in str(fields.get("description") or "").splitlines() or [""]:
            lines.append(f"        {line}")
        lines += [
            "      release_notes: |",
        ]
        for line in str(fields.get("release_notes") or "Initial release.").splitlines() or [""]:
            lines.append(f"        {line}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def _yaml_scalar(value: str) -> str:
    text = " ".join(str(value).splitlines()).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{text}"'


def _future_provider_notes() -> dict:
    return {
        "apple_ads_provider": [
            "keyword reports",
            "search term reports",
            "bid recommendation",
            "impressions / taps / installs / CPT / CPA",
        ],
        "app_store_connect_analytics_provider": [
            "impressions",
            "product page views",
            "downloads",
            "conversion rate",
            "source type",
            "territory",
        ],
        "ranking_tracker": "Store country / locale / keyword rank history.",
        "metadata_experiment_log": [
            "metadata change date",
            "version/build",
            "keywords",
            "change rationale",
            "post-change CTR/CVR/download trend",
        ],
    }


def _print_summary(payload: dict) -> None:
    total_errors = 0
    total_warnings = 0
    for locale, entry in payload["locales"].items():
        issues = [
            issue
            for proposal in entry.get("proposals") or []
            for issue in proposal.get("issues") or []
        ]
        errors = sum(1 for issue in issues if issue["level"] == "error")
        warnings = sum(1 for issue in issues if issue["level"] == "warning")
        total_errors += errors
        total_warnings += warnings
        print(
            f"{locale}: {len(entry.get('scored_keywords') or [])} keywords, "
            f"{len(entry.get('competitors') or [])} competitors, "
            f"proposal issues: {errors} errors / {warnings} warnings"
        )
    print(f"Validation summary: {total_errors} errors / {total_warnings} warnings across proposals")


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0).isoformat()


if __name__ == "__main__":
    sys.exit(main())

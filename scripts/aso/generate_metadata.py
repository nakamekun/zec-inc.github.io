#!/usr/bin/env python3
"""Generate locale-aware App Store metadata from docs/aso/aso-source.yaml.

Reads per-locale ASO research and copy from <app>/docs/aso/aso-source.yaml,
assembles keywords (priority order, dedupe against name/subtitle, 100-char
budget), validates everything against App Store limits and avoid-term rules,
and writes review artifacts. fastlane files are only written with --write.

Outputs (always, including dry-run):
  <app>/docs/aso/metadata.generated.json
  <app>/docs/aso/metadata-review.md

Outputs (--write only, overwrites existing files):
  <app>/fastlane/metadata/<locale>/{name,subtitle,keywords,promotional_text,
                                    description,release_notes}.txt
  <app>/fastlane/metadata/<locale>/{marketing,privacy,support}_url.txt
                                    (only when set in aso-source.yaml)

Examples:
  python scripts/aso/generate_metadata.py --app pilltap-ios --locales en-US,ja --dry-run
  python scripts/aso/generate_metadata.py --app . --write

Exit code: 0 on success (warnings allowed), 1 when any locale has errors.
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aso_core
import miniyaml
from aso_core import Issue
from providers import default_providers


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate locale-aware App Store metadata from aso-source.yaml.",
    )
    parser.add_argument(
        "--app", required=True,
        help="App directory (e.g. pilltap-ios, or . when run from the app root)",
    )
    parser.add_argument(
        "--source",
        help="Path to aso-source.yaml (default: <app>/docs/aso/aso-source.yaml)",
    )
    parser.add_argument(
        "--locales",
        help="Comma-separated App Store locales (default: every locale in the source)",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Also write fastlane/metadata/<locale>/*.txt (overwrites existing files)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Default mode: write review artifacts only, never touch fastlane",
    )
    args = parser.parse_args(argv)
    if args.write and args.dry_run:
        parser.error("--write and --dry-run are mutually exclusive")
    return args


def resolve_locale(source: dict, locale: str, base_locale: str, providers) -> dict:
    """Resolve one locale's fields with base-locale fallback and keyword assembly."""
    locales = source.get("locales") or {}
    loc = locales.get(locale) or {}
    base_meta = (locales.get(base_locale) or {}).get("metadata") or {}
    meta = loc.get("metadata") or {}

    issues: list[Issue] = []
    fallbacks: list[str] = []

    if locale not in aso_core.KNOWN_LOCALES:
        issues.append(Issue("warning", "unknown-locale",
                            f"{locale!r} is not a known App Store locale code"))
    if locale not in locales:
        issues.append(Issue("warning", "missing-locale",
                            f"locale {locale} is not in the source; "
                            f"all fields fall back to {base_locale}"))

    fields: dict[str, str] = {}
    for fname in aso_core.METADATA_FIELDS:
        if fname == "keywords":
            continue
        value = meta.get(fname)
        if value in (None, "") and locale != base_locale:
            value = base_meta.get(fname)
            if value not in (None, ""):
                fallbacks.append(fname)
        fields[fname] = str(value).strip() if value not in (None, "") else ""

    explicit = meta.get("keywords")
    if explicit not in (None, ""):
        fields["keywords"] = str(explicit).strip()
        used = [t.strip() for t in fields["keywords"].split(",") if t.strip()]
        keyword_report = {"mode": "explicit", "used": used, "dropped": []}
    else:
        candidates: list[aso_core.KeywordCandidate] = []
        for provider in providers:
            candidates += provider.candidates(source, locale)
        if not candidates and locale != base_locale:
            for provider in providers:
                candidates += provider.candidates(source, base_locale)
            if candidates:
                fallbacks.append("keywords")
        keywords, used, dropped = aso_core.assemble_keywords(
            candidates, fields["name"], fields["subtitle"]
        )
        fields["keywords"] = keywords
        keyword_report = {
            "mode": "assembled",
            "used": used,
            "dropped": [{"term": t, "reason": r} for t, r in dropped],
        }

    for fname in fallbacks:
        issues.append(Issue("warning", "fallback",
                            f"{fname} fell back to {base_locale}; "
                            "localize it to match this locale's search intent", fname))

    avoid_terms = aso_core.normalize_avoid_terms(
        (source.get("defaults") or {}).get("avoid_terms")
    ) + aso_core.normalize_avoid_terms(loc.get("avoid_terms"))
    issues += aso_core.validate_locale(fields, avoid_terms, locale)

    research = loc.get("research") or {}
    return {
        "fields": fields,
        "keyword_report": keyword_report,
        "fallbacks": fallbacks,
        "avoid_terms": avoid_terms,
        "search_intent": str(research.get("search_intent") or "").strip(),
        "issues": [issue.as_dict() for issue in issues],
    }


def _md_escape(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")


def build_review_md(payload: dict, mode: str) -> str:
    lines: list[str] = []
    app = payload["app"]
    lines.append(f"# ASO Metadata Review — {app['slug']}")
    lines.append("")
    lines.append(f"- Generated: {payload['generated_at']}")
    lines.append(f"- Source: `{payload['source']}`")
    lines.append(f"- Mode: {mode}")
    lines.append(f"- Base locale: {app['base_locale']}")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append("| Locale | Errors | Warnings | Name (chars) | Subtitle (chars) | Keywords (chars) |")
    lines.append("|---|---|---|---|---|---|")
    for locale, entry in payload["locales"].items():
        issues = entry["issues"]
        errors = sum(1 for i in issues if i["level"] == "error")
        warnings = sum(1 for i in issues if i["level"] == "warning")
        f = entry["fields"]
        lines.append(
            f"| {locale} | {errors} | {warnings} "
            f"| {len(f['name'])}/{aso_core.LIMITS['name']} "
            f"| {len(f['subtitle'])}/{aso_core.LIMITS['subtitle']} "
            f"| {len(f['keywords'])}/{aso_core.LIMITS['keywords']} |"
        )
    lines.append("")

    for locale, entry in payload["locales"].items():
        f = entry["fields"]
        lines.append(f"## {locale}")
        lines.append("")
        if entry["search_intent"]:
            lines.append("### Search intent")
            lines.append("")
            lines.append(entry["search_intent"])
            lines.append("")
        lines.append("### Proposed metadata")
        lines.append("")
        lines.append("| Field | Chars | Limit | Value |")
        lines.append("|---|---|---|---|")
        for fname in ("name", "subtitle", "keywords", "promotional_text"):
            lines.append(
                f"| {fname} | {len(f[fname])} | {aso_core.LIMITS[fname]} "
                f"| {_md_escape(f[fname])} |"
            )
        lines.append("")
        for fname in ("description", "release_notes"):
            lines.append(f"**{fname}** ({len(f[fname])}/{aso_core.LIMITS[fname]} chars)")
            lines.append("")
            lines.append("```text")
            lines.append(f[fname])
            lines.append("```")
            lines.append("")
        report = entry["keyword_report"]
        if report["dropped"]:
            lines.append("### Dropped keyword candidates")
            lines.append("")
            lines.append("| Term | Reason |")
            lines.append("|---|---|")
            for item in report["dropped"]:
                lines.append(f"| {_md_escape(item['term'])} | {item['reason']} |")
            lines.append("")
        lines.append("### Issues")
        lines.append("")
        if entry["issues"]:
            for issue in entry["issues"]:
                mark = "ERROR" if issue["level"] == "error" else "WARN"
                where = f" [{issue['field']}]" if issue["field"] else ""
                lines.append(f"- **{mark}**{where} {issue['message']} ({issue['code']})")
        else:
            lines.append("- none")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_fastlane(app_dir: Path, locale: str, fields: dict, urls: dict) -> list[Path]:
    out_dir = app_dir / "fastlane" / "metadata" / locale
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for fname in aso_core.METADATA_FIELDS:
        value = fields.get(fname) or ""
        if not value.strip():
            continue  # never clobber a hand-written file with an empty one
        path = out_dir / f"{fname}.txt"
        path.write_text(value.rstrip("\n") + "\n", encoding="utf-8")
        written.append(path)
    for fname, value in urls.items():
        path = out_dir / f"{fname}.txt"
        path.write_text(str(value).strip() + "\n", encoding="utf-8")
        written.append(path)
    return written


def main(argv=None) -> int:
    args = parse_args(argv)
    app_dir = Path(args.app).resolve()
    if not app_dir.is_dir():
        print(f"error: app directory not found: {app_dir}", file=sys.stderr)
        return 2
    source_path = Path(args.source) if args.source else app_dir / "docs" / "aso" / "aso-source.yaml"
    if not source_path.is_file():
        print(f"error: source not found: {source_path}", file=sys.stderr)
        print("hint: copy docs/aso/aso-source.yaml (template) from the apps repo root",
              file=sys.stderr)
        return 2

    try:
        source = miniyaml.load_file(source_path)
    except miniyaml.YamlError as exc:
        print(f"error: {source_path}: {exc}", file=sys.stderr)
        return 2

    app_info = source.get("app") or {}
    base_locale = str(app_info.get("base_locale") or "en-US")
    source_locales = list((source.get("locales") or {}).keys())
    if args.locales:
        locales = [loc.strip() for loc in args.locales.split(",") if loc.strip()]
    else:
        locales = source_locales
    if not locales:
        print("error: no locales to generate (source has no locales and --locales not given)",
              file=sys.stderr)
        return 2

    providers = default_providers()
    payload = {
        "schema": 1,
        "generated_at": datetime.datetime.now(datetime.timezone.utc)
        .replace(microsecond=0).isoformat(),
        "app": {
            "slug": str(app_info.get("slug") or app_dir.name),
            "base_locale": base_locale,
        },
        "source": str(source_path),
        "locales": {
            locale: resolve_locale(source, locale, base_locale, providers)
            for locale in locales
        },
    }

    aso_dir = app_dir / "docs" / "aso"
    aso_dir.mkdir(parents=True, exist_ok=True)
    json_path = aso_dir / "metadata.generated.json"
    json_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    mode = "write" if args.write else "dry-run"
    review_path = aso_dir / "metadata-review.md"
    review_path.write_text(build_review_md(payload, mode), encoding="utf-8")

    total_errors = sum(
        1 for entry in payload["locales"].values()
        for issue in entry["issues"] if issue["level"] == "error"
    )
    total_warnings = sum(
        1 for entry in payload["locales"].values()
        for issue in entry["issues"] if issue["level"] == "warning"
    )

    print(f"Wrote {json_path}")
    print(f"Wrote {review_path}")

    if args.write:
        if total_errors:
            print("Refusing to write fastlane metadata: fix the errors above first.",
                  file=sys.stderr)
        else:
            urls = {k: app_info[k] for k in aso_core.URL_FIELDS if app_info.get(k)}
            for locale in locales:
                written = write_fastlane(
                    app_dir, locale, payload["locales"][locale]["fields"], urls
                )
                print(f"Wrote {len(written)} files to fastlane/metadata/{locale}/")
    else:
        print("Dry-run: fastlane/metadata was not touched (use --write to export).")

    print(f"Locales: {len(locales)}  Errors: {total_errors}  Warnings: {total_warnings}")
    for locale, entry in payload["locales"].items():
        for issue in entry["issues"]:
            mark = "ERROR" if issue["level"] == "error" else "WARN "
            field = f" {issue['field']}:" if issue["field"] else ""
            print(f"  [{mark}] {locale}:{field} {issue['message']}")
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())

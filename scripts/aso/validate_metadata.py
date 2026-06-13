#!/usr/bin/env python3
"""Validate metadata.generated.json against App Store limits and avoid-term rules.

Re-runs the same machine checks the generator uses, so LLM- or hand-edited
output never reaches fastlane unchecked.

Usage:
  python scripts/aso/validate_metadata.py <app>/docs/aso/metadata.generated.json
  python scripts/aso/validate_metadata.py docs/aso/metadata.generated.json --strict

Exit code: 0 OK (warnings allowed), 1 errors (or warnings with --strict), 2 usage.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import aso_core


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate generated App Store metadata JSON."
    )
    parser.add_argument("json_path", help="Path to metadata.generated.json")
    parser.add_argument("--strict", action="store_true",
                        help="Treat warnings as errors")
    args = parser.parse_args(argv)

    path = Path(args.json_path)
    if not path.is_file():
        print(f"error: file not found: {path}", file=sys.stderr)
        return 2
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON in {path}: {exc}", file=sys.stderr)
        return 2

    locales = data.get("locales") or {}
    if not locales:
        print(f"error: no locales found in {path}", file=sys.stderr)
        return 2

    total_errors = total_warnings = 0
    for locale, entry in locales.items():
        fields = entry.get("fields") or {}
        avoid_terms = aso_core.normalize_avoid_terms(entry.get("avoid_terms"))
        issues = aso_core.validate_locale(fields, avoid_terms, locale)
        errors = [i for i in issues if i.level == "error"]
        warnings = [i for i in issues if i.level == "warning"]
        total_errors += len(errors)
        total_warnings += len(warnings)

        status = "OK" if not errors and not warnings else \
                 ("ERRORS" if errors else "warnings")
        counts = " ".join(
            f"{fname}={len(str(fields.get(fname) or ''))}/{aso_core.LIMITS[fname]}"
            for fname in ("name", "subtitle", "keywords")
        )
        print(f"{locale}: {status}  ({counts})")
        for issue in errors + warnings:
            mark = "ERROR" if issue.level == "error" else "WARN "
            field = f" {issue.field}:" if issue.field else ""
            print(f"  [{mark}]{field} {issue.message} ({issue.code})")

    print(f"\nTotal: {len(locales)} locales, {total_errors} errors, {total_warnings} warnings")
    if total_errors:
        return 1
    if args.strict and total_warnings:
        print("--strict: warnings treated as errors", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Validate generated ZEC Apps static pages."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
SITE_ORIGIN = "https://zec-inc.jp"
APPS_DIR = ROOT_DIR / "apps"
SITEMAP_XML = ROOT_DIR / "sitemap.xml"
DETAIL_MARKER = ".generated-app-detail"
CATEGORY_MARKER = ".generated-app-category"
EXPECTED_CATEGORIES = {"photo-memory", "travel", "tap-tools", "widgets", "family", "productivity"}


class PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []
        self.json_ld_blocks: list[str] = []
        self._in_json_ld = False
        self._json_buffer: list[str] = []
        self.title_seen = False
        self.meta_description_seen = False
        self.canonical_seen = False
        self.og_title_seen = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {name: value or "" for name, value in attrs}
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag == "title":
            self.title_seen = True
        if tag == "meta" and attrs_dict.get("name") == "description" and attrs_dict.get("content"):
            self.meta_description_seen = True
        if tag == "link" and attrs_dict.get("rel") == "canonical" and attrs_dict.get("href"):
            self.canonical_seen = True
        if tag == "meta" and attrs_dict.get("property") == "og:title" and attrs_dict.get("content"):
            self.og_title_seen = True
        if tag == "script" and attrs_dict.get("type") == "application/ld+json":
            self._in_json_ld = True
            self._json_buffer = []

    def handle_data(self, data: str) -> None:
        if self._in_json_ld:
            self._json_buffer.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_json_ld:
            self._in_json_ld = False
            self.json_ld_blocks.append("".join(self._json_buffer).strip())


def page_path_for_url(url: str, source_path: Path) -> Path | None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme and parsed.netloc and parsed.netloc != "zec-inc.jp":
        return None
    if parsed.scheme in {"mailto", "tel", "itms-apps"}:
        return None
    path = parsed.path or "/"
    if not parsed.scheme and not parsed.netloc and not url.startswith("/"):
        base_dir = source_path.parent
        if path.endswith("/"):
            return base_dir / path / "index.html"
        return base_dir / path
    if path == "/":
        return ROOT_DIR / "index.html"
    if path.endswith("/"):
        return ROOT_DIR / path.lstrip("/") / "index.html"
    return ROOT_DIR / path.lstrip("/")


def collect_pages() -> tuple[list[Path], list[Path]]:
    detail_pages = sorted(path.parent / "index.html" for path in APPS_DIR.glob(f"*/{DETAIL_MARKER}"))
    category_pages = sorted(path.parent / "index.html" for path in APPS_DIR.glob(f"*/{CATEGORY_MARKER}"))
    return detail_pages, category_pages


def parse_page(path: Path) -> PageParser:
    parser = PageParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser


def validate_json_ld(path: Path, parser: PageParser, errors: list[str]) -> None:
    for block in parser.json_ld_blocks:
        try:
            json.loads(block)
        except json.JSONDecodeError as exc:
            errors.append(f"{path}: invalid JSON-LD: {exc}")


def validate_links(path: Path, parser: PageParser, errors: list[str]) -> None:
    for href in parser.links:
        if href.startswith("#"):
            continue
        target = page_path_for_url(href, path)
        if target is None:
            continue
        if not target.exists():
            errors.append(f"{path}: broken internal link {href} -> {target.relative_to(ROOT_DIR)}")


def validate_page_head(path: Path, parser: PageParser, errors: list[str]) -> None:
    if path not in {ROOT_DIR / "index.html", APPS_DIR / "index.html"}:
        if not parser.title_seen:
            errors.append(f"{path}: missing title")
        if not parser.meta_description_seen:
            errors.append(f"{path}: missing meta description")
        if not parser.canonical_seen:
            errors.append(f"{path}: missing canonical")
        if not parser.og_title_seen:
            errors.append(f"{path}: missing og:title")


def validate_sitemap(expected_urls: set[str], errors: list[str]) -> None:
    if not SITEMAP_XML.exists():
        errors.append("missing sitemap.xml")
        return
    try:
        root = ET.parse(SITEMAP_XML).getroot()
    except ET.ParseError as exc:
        errors.append(f"invalid sitemap.xml: {exc}")
        return
    namespace = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = {loc.text.strip() for loc in root.findall(".//sm:loc", namespace) if loc.text}
    missing = sorted(expected_urls - locs)
    for url in missing:
        errors.append(f"sitemap.xml missing {url}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected-detail-count", type=int, default=24)
    args = parser.parse_args(argv)

    errors: list[str] = []
    detail_pages, category_pages = collect_pages()
    if len(detail_pages) != args.expected_detail_count:
        errors.append(f"expected {args.expected_detail_count} detail pages, found {len(detail_pages)}")

    category_slugs = {path.parent.name for path in category_pages}
    missing_categories = sorted(EXPECTED_CATEGORIES - category_slugs)
    for slug in missing_categories:
        errors.append(f"missing category page apps/{slug}/index.html")

    pages = [ROOT_DIR / "index.html", APPS_DIR / "index.html"] + detail_pages + category_pages
    expected_sitemap_urls = {SITE_ORIGIN + "/", SITE_ORIGIN + "/apps/"}
    for path in detail_pages + category_pages:
        rel = path.parent.relative_to(ROOT_DIR).as_posix()
        expected_sitemap_urls.add(f"{SITE_ORIGIN}/{rel}/")

    for path in pages:
        if not path.exists():
            errors.append(f"missing page {path.relative_to(ROOT_DIR)}")
            continue
        parsed = parse_page(path)
        validate_page_head(path, parsed, errors)
        validate_json_ld(path, parsed, errors)
        validate_links(path, parsed, errors)

    validate_sitemap(expected_sitemap_urls, errors)

    if errors:
        for error in errors:
            print(f"error: {error}", file=sys.stderr)
        return 1

    print(f"validated {len(detail_pages)} detail pages and {len(category_pages)} category pages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

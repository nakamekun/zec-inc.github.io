#!/usr/bin/env python3
"""
Update apps/index.html, app detail pages, category pages, and crawl files.

App Store Lookup API data is the canonical app list. Optional copy, slug,
category, locale, FAQ, and screenshot overrides live in:
    data/app-details-overrides.json

Usage:
    python3 scripts/update_apps_page.py
    python3 scripts/update_apps_page.py --strict
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEVELOPER_ID = "1889726396"
DEVELOPER_NAME = "ZEC Inc."
LOOKUP_URL = (
    "https://itunes.apple.com/lookup"
    f"?id={DEVELOPER_ID}&entity=software&country=us&limit=200"
)
SITE_ORIGIN = "https://zec-inc.jp"
ROOT_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT_DIR / "apps"
ASSETS_APPS_DIR = ROOT_DIR / "assets" / "apps"
APPS_PAGE = APPS_DIR / "index.html"
DETAIL_OVERRIDES = ROOT_DIR / "data" / "app-details-overrides.json"
LOOKUP_CACHE = ROOT_DIR / "data" / "app-store-lookup-cache.json"
APPS_MANIFEST = ROOT_DIR / "data" / "apps-manifest.json"
SITEMAP_XML = ROOT_DIR / "sitemap.xml"
ROBOTS_TXT = ROOT_DIR / "robots.txt"
LLMS_TXT = ROOT_DIR / "llms.txt"
START_MARKER = "<!-- APPS_LIST_START -->"
END_MARKER = "<!-- APPS_LIST_END -->"
DETAIL_MARKER = ".generated-app-detail"
CATEGORY_MARKER = ".generated-app-category"
LOCALE_INDEX_MARKER = ".generated-app-locale-index"

DEFAULT_LOCALE = "en"

CATEGORY_DEFINITIONS = {
    "photo-memory": {
        "en": {
            "title": "Photo and Memory Apps",
            "description": "Simple iPhone apps for keeping everyday photos, memories, and visual records easier to continue.",
        },
        "ja": {
            "title": "写真・思い出のアプリ",
            "description": "毎日の写真や思い出、目で見て残す記録を続けやすくする、シンプルなiPhoneアプリです。",
        },
    },
    "travel": {
        "en": {
            "title": "Travel Apps",
            "description": "Small iPhone tools for trips, packing, phrases, schedules, and quick checks while away from home.",
        },
        "ja": {
            "title": "旅行のアプリ",
            "description": "旅行の持ち物・フレーズ・予定・出先でのちょっとした確認に使える、小さなiPhoneツールです。",
        },
    },
    "tap-tools": {
        "en": {
            "title": "Tap Tools",
            "description": "Fast one-purpose apps designed around quick taps, daily records, and small repeated actions.",
        },
        "ja": {
            "title": "タップ記録ツール",
            "description": "ワンタップの記録や毎日の小さな繰り返しに特化した、素早く使える単機能アプリです。",
        },
    },
    "widgets": {
        "en": {
            "title": "Widget-Friendly Apps",
            "description": "ZEC apps with widget-oriented use cases for glancing, checking, or continuing from the Home Screen.",
        },
        "ja": {
            "title": "ウィジェット対応アプリ",
            "description": "ホーム画面からひと目で確認・継続できる、ウィジェット活用を想定したZECアプリです。",
        },
    },
    "family": {
        "en": {
            "title": "Family Apps",
            "description": "Apps for household routines, family records, shared preparation, and simple daily checks.",
        },
        "ja": {
            "title": "家族向けアプリ",
            "description": "家庭のルーティンや家族の記録、準備の共有、毎日の簡単なチェックに使えるアプリです。",
        },
    },
    "productivity": {
        "en": {
            "title": "Productivity Apps",
            "description": "Focused iPhone apps for notes, planning, cleaning links, tracking, and getting small tasks done.",
        },
        "ja": {
            "title": "仕事効率化アプリ",
            "description": "メモ・計画・リンク整理・記録など、小さなタスクを片づけることに集中したiPhoneアプリです。",
        },
    },
}

UI_STRINGS = {
    "en": {
        "overview": "Overview",
        "audience": "Who It Is For",
        "features": "Main Features",
        "usage": "How to Use",
        "pricing": "Pricing",
        "pricing_note": "Pricing and availability can vary by country and may change on the App Store.",
        "privacy": "Privacy",
        "screenshots": "Screenshots",
        "faq": "FAQ",
        "app_store": "App Store",
        "view_on_app_store": "View on the App Store",
        "open_on_app_store": "Open {name} on the App Store",
        "all_apps": "All ZEC Apps",
        "last_updated": "Last updated",
        "details": "Details",
        "app_store_link": "App Store →",
        "apps_nav": "Apps",
        "apps_heading": "Apps",
        "language_names": {"en": "English", "ja": "日本語"},
        "apps_index_title": "ZEC Apps",
        "apps_index_description": "Official list of iPhone apps from ZEC Inc. Small, focused tools for daily records, quick checks, travel, family routines, and widgets.",
        "icon_alt": "{name} app icon",
        "screenshot_alt": "{name} screenshot",
    },
    "ja": {
        "overview": "概要",
        "audience": "こんな方に",
        "features": "主な機能",
        "usage": "使い方",
        "pricing": "価格",
        "pricing_note": "価格・提供状況は国や地域によって異なり、App Store上で変更される場合があります。",
        "privacy": "プライバシー",
        "screenshots": "スクリーンショット",
        "faq": "よくある質問",
        "app_store": "App Store",
        "view_on_app_store": "App Storeで見る",
        "open_on_app_store": "{name} をApp Storeで開く",
        "all_apps": "ZECアプリ一覧",
        "last_updated": "最終更新日",
        "details": "詳細",
        "app_store_link": "App Store →",
        "apps_nav": "アプリ",
        "apps_heading": "アプリ一覧",
        "language_names": {"en": "English", "ja": "日本語"},
        "apps_index_title": "ZECのアプリ一覧",
        "apps_index_description": "合同会社ゼク（ZEC Inc.）が開発するiPhoneアプリの公式一覧です。毎日の記録・すばやい確認・旅行・家族の習慣・ウィジェットのための、小さくて目的のはっきりした道具を揃えています。",
        "icon_alt": "{name} のアプリアイコン",
        "screenshot_alt": "{name} のスクリーンショット",
    },
}

APP_OVERRIDE_FIELDS = {
    "slug",
    "name",
    "tagline",
    "short_description",
    "meta_description",
    "overview",
    "audience",
    "target_users",
    "features",
    "usage",
    "how_to_use",
    "pricing",
    "privacy",
    "faq",
    "screenshots",
    "categories",
    "locales",
}
LOCALE_OVERRIDE_FIELDS = APP_OVERRIDE_FIELDS - {"slug", "categories", "locales"}


@dataclass
class BuildContext:
    strict: bool = False
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def fetch_lookup_payload() -> dict[str, Any]:
    request = urllib.request.Request(
        LOOKUP_URL,
        headers={
            "User-Agent": "zec-inc.github.io apps updater/2.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        LOOKUP_CACHE.parent.mkdir(parents=True, exist_ok=True)
        LOOKUP_CACHE.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        if LOOKUP_CACHE.exists():
            print(f"note: using cached App Store lookup data because live fetch failed: {exc}", file=sys.stderr)
            try:
                return json.loads(LOOKUP_CACHE.read_text(encoding="utf-8"))
            except json.JSONDecodeError as cache_exc:
                raise RuntimeError(f"Failed to read cached App Store data: {cache_exc}") from cache_exc
        raise RuntimeError(f"Failed to fetch App Store data and no cache exists: {exc}") from exc


def fetch_apps() -> list[dict[str, Any]]:
    payload = fetch_lookup_payload()

    apps: list[dict[str, Any]] = []
    for item in payload.get("results", []):
        if item.get("kind") != "software":
            continue
        if str(item.get("artistId", "")).strip() != DEVELOPER_ID:
            continue
        names = {str(item.get("artistName", "")).strip(), str(item.get("sellerName", "")).strip()}
        if DEVELOPER_NAME not in names:
            continue

        track_name = str(item.get("trackName", "")).strip()
        track_url = str(item.get("trackViewUrl", "")).strip()
        if not track_name or not track_url:
            continue

        apps.append(
            {
                "trackId": str(item.get("trackId", "")).strip(),
                "trackName": track_name,
                "bundleId": str(item.get("bundleId", "")).strip(),
                "primaryGenreName": str(item.get("primaryGenreName", "")).strip(),
                "trackViewUrl": track_url,
                "artworkUrl100": str(item.get("artworkUrl100", "")).strip(),
                "artworkUrl512": str(item.get("artworkUrl512", "")).strip(),
                "description": str(item.get("description", "")).strip(),
                "releaseNotes": str(item.get("releaseNotes", "")).strip(),
                "screenshotUrls": item.get("screenshotUrls") if isinstance(item.get("screenshotUrls"), list) else [],
                "ipadScreenshotUrls": item.get("ipadScreenshotUrls") if isinstance(item.get("ipadScreenshotUrls"), list) else [],
                "formattedPrice": str(item.get("formattedPrice", "")).strip(),
                "price": item.get("price"),
                "currency": str(item.get("currency", "")).strip(),
                "version": str(item.get("version", "")).strip(),
                "releaseDate": str(item.get("releaseDate", "")).strip(),
                "currentVersionReleaseDate": str(item.get("currentVersionReleaseDate", "")).strip(),
                "minimumOsVersion": str(item.get("minimumOsVersion", "")).strip(),
                "contentAdvisoryRating": str(item.get("contentAdvisoryRating", "")).strip(),
            }
        )

    if not apps:
        raise RuntimeError("No ZEC Inc. software apps were found in the App Store payload.")
    return apps


def slugify(text: str, fallback: str = "") -> str:
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    return slug or fallback


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip()


def truncate_text(text: str, max_length: int) -> str:
    text = clean_text(text)
    if len(text) <= max_length:
        return text
    clipped = text[: max_length - 3].rstrip()
    boundary = max(clipped.rfind(" "), clipped.rfind("、"))
    if boundary >= max_length // 2:
        clipped = clipped[:boundary].rstrip(" ,;:-")
    return clipped + "..."


def load_overrides(ctx: BuildContext) -> dict[str, Any]:
    if not DETAIL_OVERRIDES.exists():
        return {}
    try:
        payload = json.loads(DETAIL_OVERRIDES.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid app detail overrides JSON: {exc}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("App detail overrides must be a JSON object.")
    validate_overrides(payload, ctx)
    return payload


def validate_overrides(overrides: dict[str, Any], ctx: BuildContext) -> None:
    for key, value in overrides.items():
        if not isinstance(value, dict):
            ctx.warn(f"Override '{key}' must be an object.")
            continue
        validate_override_object(f"Override '{key}'", value, APP_OVERRIDE_FIELDS, ctx)
        locales = value.get("locales")
        if locales is not None:
            if not isinstance(locales, dict):
                ctx.warn(f"Override '{key}'.locales must be an object.")
            else:
                for locale, locale_value in locales.items():
                    if not isinstance(locale_value, dict):
                        ctx.warn(f"Override '{key}'.locales.{locale} must be an object.")
                        continue
                    validate_override_object(
                        f"Override '{key}'.locales.{locale}",
                        locale_value,
                        LOCALE_OVERRIDE_FIELDS,
                        ctx,
                    )


def validate_override_object(label: str, value: dict[str, Any], allowed: set[str], ctx: BuildContext) -> None:
    for field_name, field_value in value.items():
        if field_name not in allowed:
            ctx.warn(f"{label} has unknown field '{field_name}'.")
            continue
        if field_name in {"slug", "name", "tagline", "short_description", "meta_description", "pricing", "privacy"}:
            if not isinstance(field_value, str):
                ctx.warn(f"{label}.{field_name} must be a string.")
        elif field_name in {"overview", "audience", "target_users", "features", "usage", "how_to_use", "screenshots", "categories"}:
            if not isinstance(field_value, list) or not all(isinstance(item, str) for item in field_value):
                ctx.warn(f"{label}.{field_name} must be a list of strings.")
        elif field_name == "faq":
            if not isinstance(field_value, list):
                ctx.warn(f"{label}.faq must be a list of question/answer objects.")
            else:
                for index, item in enumerate(field_value):
                    if not isinstance(item, dict) or not isinstance(item.get("question"), str) or not isinstance(item.get("answer"), str):
                        ctx.warn(f"{label}.faq[{index}] must contain string question and answer fields.")


def app_override_for(app: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        str(app.get("trackId", "")).strip(),
        str(app.get("slug", "")).strip(),
        slugify(str(app.get("trackName", "")).strip()),
    ]
    for key in candidates:
        if key and isinstance(overrides.get(key), dict):
            return overrides[key]
    return {}


def localized_override(app: dict[str, Any], overrides: dict[str, Any], locale: str) -> dict[str, Any]:
    app_override = app_override_for(app, overrides)
    locales = app_override.get("locales")
    if isinstance(locales, dict) and isinstance(locales.get(locale), dict):
        merged = {key: value for key, value in app_override.items() if key != "locales"}
        merged.update(locales[locale])
        return merged
    return app_override


def app_locales(app: dict[str, Any], overrides: dict[str, Any]) -> list[str]:
    override = app_override_for(app, overrides)
    locales = override.get("locales")
    extra: list[str] = []
    if isinstance(locales, dict):
        extra = sorted(
            locale
            for locale, value in locales.items()
            if locale != DEFAULT_LOCALE and isinstance(value, dict) and locale in UI_STRINGS
        )
    return [DEFAULT_LOCALE] + extra


def site_locales(overrides: dict[str, Any]) -> list[str]:
    found: set[str] = set()
    for value in overrides.values():
        if isinstance(value, dict) and isinstance(value.get("locales"), dict):
            found.update(
                locale
                for locale, locale_value in value["locales"].items()
                if locale != DEFAULT_LOCALE and isinstance(locale_value, dict) and locale in UI_STRINGS
            )
    return sorted(found)


def ui_strings(locale: str) -> dict[str, Any]:
    return UI_STRINGS.get(locale, UI_STRINGS[DEFAULT_LOCALE])


def assign_slugs(apps: list[dict[str, Any]], overrides: dict[str, Any], ctx: BuildContext) -> list[dict[str, Any]]:
    used: dict[str, str] = {}
    for app in apps:
        app_override = app_override_for(app, overrides)
        preferred = str(app_override.get("slug", "")).strip()
        bundle_tail = str(app.get("bundleId", "")).strip().split(".")[-1]
        fallback = slugify(bundle_tail, f"app-{app.get('trackId') or len(used) + 1}")
        base_slug = slugify(preferred or str(app.get("trackName", "")), fallback)
        if not base_slug:
            raise RuntimeError(f"Could not create slug for app {app!r}")
        slug = base_slug
        suffix = 2
        while slug in used:
            ctx.warn(f"Slug collision for '{base_slug}' between '{used[slug]}' and '{app.get('trackName')}'.")
            slug = f"{base_slug}-{suffix}"
            suffix += 1
        used[slug] = str(app.get("trackName", ""))
        app["slug"] = slug
    return apps


def short_description(app: dict[str, Any], overrides: dict[str, Any] | None = None, locale: str = DEFAULT_LOCALE) -> str:
    override = localized_override(app, overrides or {}, locale)
    explicit = override.get("short_description") or override.get("tagline")
    if isinstance(explicit, str) and explicit.strip():
        return truncate_text(explicit, 110)

    text = app.get("description") or app.get("releaseNotes") or ""
    text = clean_text(text)
    track_name = str(app.get("trackName", "")).strip()
    stripped_title_prefix = False
    if track_name and text.casefold().startswith(track_name.casefold()):
        remainder = text[len(track_name):]
        if remainder.startswith("?") or remainder.startswith("!"):
            text = remainder.lstrip(" -–—:?!.,")
            stripped_title_prefix = True
    if text:
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text) if segment.strip()]
        sentence = next((candidate for candidate in sentences if len(candidate) >= 20), sentences[0] if sentences else text)
        if stripped_title_prefix and sentence and sentence[:1].islower():
            sentence = f"{track_name} {sentence}"
        return truncate_text(sentence, 110)
    genre = str(app.get("primaryGenreName", "")).strip()
    return genre or "Focused iPhone app from ZEC Inc."


def paragraphs_from_description(app: dict[str, Any], limit: int = 2) -> list[str]:
    description = str(app.get("description", "")).strip()
    if not description:
        return [f"{app_name(app)} is a focused iPhone app from ZEC Inc. for a small everyday task."]
    raw_paragraphs = [clean_text(part) for part in re.split(r"\n\s*\n", description) if clean_text(part)]
    paragraphs = [part for part in raw_paragraphs if part.casefold() != app_name(app).casefold()]
    return paragraphs[:limit] or [clean_text(description)]


def sentence_candidates(app: dict[str, Any]) -> list[str]:
    text = clean_text(app.get("description") or app.get("releaseNotes") or "")
    if not text:
        return []
    return [part.strip(" -") for part in re.split(r"(?<=[.!?])\s+", text) if len(part.strip()) >= 18]


def generated_features(app: dict[str, Any]) -> list[str]:
    features: list[str] = []
    for sentence in sentence_candidates(app):
        if sentence.casefold().startswith(app_name(app).casefold()) and len(sentence) < 42:
            continue
        features.append(truncate_text(sentence, 120))
        if len(features) >= 4:
            break
    fallback = [
        "Quick access to the app's main task",
        "Simple screens designed for repeated daily use",
        "Focused controls without unnecessary setup",
        "Available from the App Store for iPhone users",
    ]
    for item in fallback:
        if len(features) >= 4:
            break
        features.append(item)
    return features


def generated_audience(app: dict[str, Any]) -> list[str]:
    genre = str(app.get("primaryGenreName") or "Utilities").lower()
    return [
        f"People looking for a simple {genre} app for one focused task",
        "Users who prefer lightweight tools over complex all-in-one apps",
        "iPhone users who want an official source before installing from the App Store",
    ]


def generated_usage(app: dict[str, Any]) -> list[str]:
    return [
        f"Install {app_name(app)} from the App Store.",
        "Open the app and complete the first screen or setup shown in the app.",
        "Use the main action whenever the task comes up.",
        "Return to the app when you want to review, adjust, or repeat the task.",
    ]


def generated_faq(app: dict[str, Any]) -> list[dict[str, str]]:
    name = app_name(app)
    price = price_text(app)
    return [
        {
            "question": f"What is {name} for?",
            "answer": f"{name} is a focused iPhone app from ZEC Inc. The page above summarizes its purpose, intended users, and basic usage.",
        },
        {
            "question": f"Where can I download {name}?",
            "answer": f"You can download {name} from its official App Store page linked on this page.",
        },
        {
            "question": f"How much does {name} cost?",
            "answer": f"The App Store currently reports the price as {price}. App Store pricing and availability may vary by country or change over time.",
        },
        {
            "question": "Where can I check privacy information?",
            "answer": "The App Store product page contains Apple's current privacy labels and related disclosure information for this app.",
        },
    ]


def app_name(app: dict[str, Any]) -> str:
    return str(app.get("trackName") or "ZEC App").strip() or "ZEC App"


def override_string(value: Any, fallback: str) -> str:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return fallback


def override_list(value: Any, fallback: list[str]) -> list[str]:
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        cleaned = [clean_text(item) for item in value if clean_text(item)]
        if cleaned:
            return cleaned
    return fallback


def override_faq(value: Any, fallback: list[dict[str, str]]) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return fallback
    faq: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        question = clean_text(item.get("question", ""))
        answer = clean_text(item.get("answer", ""))
        if question and answer:
            faq.append({"question": question, "answer": answer})
    return faq or fallback


def price_text(app: dict[str, Any]) -> str:
    formatted = str(app.get("formattedPrice", "")).strip()
    if formatted:
        return formatted
    if app.get("price") in (0, 0.0, "0"):
        return "Free"
    return "See the App Store"


def last_updated(app: dict[str, Any]) -> str:
    raw = str(app.get("currentVersionReleaseDate") or app.get("releaseDate") or "")
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def page_href(app: dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    slug = str(app.get("slug", "")).strip()
    if locale == DEFAULT_LOCALE:
        return f"/apps/{slug}/"
    return f"/apps/{slug}/{locale}/"


def page_url(app: dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    return SITE_ORIGIN + page_href(app, locale)


def category_href(slug: str, locale: str = DEFAULT_LOCALE) -> str:
    if locale == DEFAULT_LOCALE:
        return f"/apps/{slug}/"
    return f"/apps/{slug}/{locale}/"


def category_url(slug: str, locale: str = DEFAULT_LOCALE) -> str:
    return SITE_ORIGIN + category_href(slug, locale)


def apps_index_href(locale: str = DEFAULT_LOCALE) -> str:
    if locale == DEFAULT_LOCALE:
        return "/apps/"
    return f"/apps/{locale}/"


def apps_index_url(locale: str = DEFAULT_LOCALE) -> str:
    return SITE_ORIGIN + apps_index_href(locale)


def hreflang_alternates(locales: list[str], url_for) -> list[tuple[str, str]]:
    if len(locales) < 2:
        return []
    alternates = [(locale, url_for(locale)) for locale in locales]
    alternates.append(("x-default", url_for(DEFAULT_LOCALE)))
    return alternates


def language_links(locales: list[str], current: str, href_for) -> list[tuple[str, str]]:
    names = ui_strings(current).get("language_names", {})
    return [
        (href_for(locale), str(names.get(locale, locale)))
        for locale in locales
        if locale != current
    ]


def asset_url(path: Path) -> str:
    return "/" + path.relative_to(ROOT_DIR).as_posix()


def resolve_screenshots(app: dict[str, Any], override: dict[str, Any], ctx: BuildContext) -> list[str]:
    screenshots: list[str] = []
    local_dir = ASSETS_APPS_DIR / str(app["slug"]) / "screenshots"
    if local_dir.exists():
        for path in sorted(local_dir.iterdir()):
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"} and path.is_file():
                screenshots.append(asset_url(path))

    explicit = override.get("screenshots")
    if isinstance(explicit, list):
        for item in explicit:
            if not isinstance(item, str) or not item.strip():
                continue
            value = item.strip()
            if value.startswith(("http://", "https://")):
                screenshots.append(value)
            else:
                candidate = (ROOT_DIR / value.lstrip("/")).resolve()
                try:
                    candidate.relative_to(ROOT_DIR.resolve())
                except ValueError:
                    ctx.warn(f"Screenshot path escapes site root for {app_name(app)}: {value}")
                    continue
                if candidate.exists() and candidate.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}:
                    screenshots.append("/" + candidate.relative_to(ROOT_DIR).as_posix())
                else:
                    ctx.warn(f"Screenshot path not found for {app_name(app)}: {value}")

    api_screenshots = [
        str(url)
        for url in (app.get("screenshotUrls") or []) + (app.get("ipadScreenshotUrls") or [])
        if isinstance(url, str) and url.startswith(("http://", "https://"))
    ]
    screenshots.extend(api_screenshots)

    deduped: list[str] = []
    seen: set[str] = set()
    for screenshot in screenshots:
        if screenshot not in seen:
            seen.add(screenshot)
            deduped.append(screenshot)
    return deduped[:5]


def detail_content(app: dict[str, Any], overrides: dict[str, Any], ctx: BuildContext, locale: str = "en") -> dict[str, Any]:
    override = localized_override(app, overrides, locale)
    name = override_string(override.get("name"), app_name(app))
    tagline = override_string(override.get("short_description"), override_string(override.get("tagline"), short_description(app, overrides)))
    overview = override_list(override.get("overview"), paragraphs_from_description(app))
    audience = override_list(override.get("target_users"), override_list(override.get("audience"), generated_audience(app)))
    features = override_list(override.get("features"), generated_features(app))
    usage = override_list(override.get("how_to_use"), override_list(override.get("usage"), generated_usage(app)))
    pricing = override_string(override.get("pricing"), price_text(app))
    privacy = override_string(
        override.get("privacy"),
        "This page uses App Store metadata as its source. For the current Apple privacy labels and regional availability, check the linked App Store product page.",
    )
    faq = override_faq(override.get("faq"), generated_faq(app))
    meta_description = override_string(override.get("meta_description"), tagline)
    meta_description = truncate_text(meta_description, 155) or f"{name} official app page by ZEC Inc."
    screenshots = resolve_screenshots(app, override, ctx)

    if not name or not tagline or not meta_description:
        raise RuntimeError(f"Generated empty SEO content for {app_name(app)}.")
    return {
        "name": name,
        "tagline": tagline,
        "overview": overview,
        "audience": audience,
        "features": features,
        "usage": usage,
        "pricing": pricing,
        "privacy": privacy,
        "faq": faq,
        "screenshots": screenshots,
        "meta_description": meta_description,
    }


def app_categories(app: dict[str, Any], overrides: dict[str, Any], ctx: BuildContext) -> list[str]:
    override = app_override_for(app, overrides)
    categories = override.get("categories", [])
    if not isinstance(categories, list):
        return []
    cleaned: list[str] = []
    for category in categories:
        if not isinstance(category, str):
            continue
        slug = slugify(category)
        if slug not in CATEGORY_DEFINITIONS:
            ctx.warn(f"Unknown category '{category}' for {app_name(app)}.")
            continue
        if slug not in cleaned:
            cleaned.append(slug)
    return cleaned


def html_list(items: list[str]) -> str:
    return "\n".join(f"            <li>{html.escape(item)}</li>" for item in items)


def html_paragraphs(items: list[str]) -> str:
    return "\n".join(f"          <p>{html.escape(item)}</p>" for item in items)


APP_STORE_STOREFRONTS = {"ja": "jp"}


def app_store_url(app: dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    url = str(app.get("trackViewUrl", "")).strip() or "https://apps.apple.com/us/developer/zec-inc/id1889726396"
    storefront = APP_STORE_STOREFRONTS.get(locale)
    if storefront:
        url = re.sub(r"(apps\.apple\.com)/[a-z]{2}/", rf"\1/{storefront}/", url, count=1)
    return url


def icon_url(app: dict[str, Any]) -> str:
    return str(app.get("artworkUrl512") or app.get("artworkUrl100") or "").strip()


def json_ld(app: dict[str, Any], content: dict[str, Any], locale: str) -> str:
    offer_price = "0" if price_text(app).lower() == "free" else app.get("price", "")
    app_node: dict[str, Any] = {
        "@type": "SoftwareApplication",
        "name": content["name"],
        "description": content["meta_description"],
        "operatingSystem": "iOS",
        "applicationCategory": app.get("primaryGenreName") or "MobileApplication",
        "offers": {
            "@type": "Offer",
            "price": str(offer_price) if offer_price is not None else "",
            "priceCurrency": app.get("currency") or "USD",
            "url": app_store_url(app, locale),
        },
        "url": page_url(app, locale),
        "inLanguage": locale,
        "downloadUrl": app_store_url(app, locale),
        "publisher": {
            "@type": "Organization",
            "name": DEVELOPER_NAME,
            "url": SITE_ORIGIN,
        },
    }
    if icon_url(app):
        app_node["image"] = icon_url(app)
    if app.get("version"):
        app_node["softwareVersion"] = str(app["version"])
    if app.get("contentAdvisoryRating"):
        app_node["contentRating"] = str(app["contentAdvisoryRating"])

    graph: list[dict[str, Any]] = [app_node]
    if content["faq"]:
        graph.append(
            {
                "@type": "FAQPage",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": item["question"],
                        "acceptedAnswer": {"@type": "Answer", "text": item["answer"]},
                    }
                    for item in content["faq"]
                ],
            }
        )
    return json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, indent=2)


def base_css() -> str:
    return """
    :root {
      --bg: #f5f8ff;
      --surface: #ffffff;
      --soft: #f8fbff;
      --text: #1e293b;
      --muted: #64748b;
      --line: #e2e8f0;
      --accent: #2563eb;
      --header: #2c3e50;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
      line-height: 1.7;
    }

    header { background: var(--header); color: #ffffff; padding: 20px; }
    .topbar, main, footer { max-width: 920px; margin: 0 auto; }
    .topbar { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
    .brand { font-weight: 600; }
    a { color: var(--accent); }
    .topbar a { color: #ffffff; text-decoration: none; }
    .topbar a:hover, a:hover { text-decoration: underline; }
    main { padding: 44px 20px; }
    .hero, .section { background: var(--surface); border: 1px solid var(--line); border-radius: 12px; padding: 28px; box-shadow: 0 10px 30px rgba(37, 99, 235, 0.06); }
    .hero { display: grid; grid-template-columns: auto 1fr; gap: 22px; align-items: center; }
    .app-icon { width: 96px; height: 96px; border-radius: 22px; border: 1px solid rgba(226, 232, 240, 0.9); box-shadow: 0 8px 22px rgba(15, 23, 42, 0.1); }
    h1 { margin: 0 0 8px; font-size: 34px; line-height: 1.2; letter-spacing: 0; }
    .tagline { margin: 0 0 18px; color: var(--muted); font-size: 17px; }
    .actions, .app-actions, .category-links { display: flex; gap: 12px; flex-wrap: wrap; }
    .button, .app-link { display: inline-flex; align-items: center; justify-content: center; min-height: 40px; padding: 0 14px; border-radius: 8px; border: 1px solid var(--line); background: #ffffff; text-decoration: none; font-weight: 600; }
    .button.primary, .app-link.primary { background: var(--accent); border-color: var(--accent); color: #ffffff; }
    .section { margin-top: 18px; }
    h2 { margin: 0 0 14px; font-size: 22px; color: var(--header); }
    p { margin: 0 0 12px; }
    ul, ol { margin: 0; padding-left: 1.25em; }
    .app-grid, .screenshots { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 14px; }
    .app-mini-card, .screenshot { margin: 0; background: var(--soft); border: 1px solid var(--line); border-radius: 10px; padding: 14px; }
    .app-mini-card h2, .app-mini-card h3 { margin: 0 0 6px; font-size: 18px; line-height: 1.3; }
    .app-mini-card p { color: var(--muted); font-size: 14px; }
    .mini-icon { width: 56px; height: 56px; border-radius: 12px; margin-bottom: 10px; }
    .screenshot img { display: block; width: 100%; height: auto; border-radius: 8px; }
    details { border-top: 1px solid var(--line); padding: 14px 0; }
    details:first-child { border-top: 0; }
    summary { cursor: pointer; font-weight: 600; }
    .meta { color: var(--muted); font-size: 14px; }
    footer { padding: 0 20px 40px; color: var(--muted); font-size: 14px; }
    .footer { border-top: 1px solid var(--line); padding-top: 16px; }
    @media (max-width: 640px) {
      main { padding-top: 28px; }
      .hero { grid-template-columns: 1fr; padding: 22px; }
      .section { padding: 22px; }
      h1 { font-size: 30px; }
    }
"""


def render_head(
    title: str,
    description: str,
    canonical: str,
    og_image: str = "",
    alternates: list[tuple[str, str]] | None = None,
) -> str:
    title = title.strip() or "ZEC Apps"
    description = truncate_text(description, 155) or "Official ZEC Apps page."
    image_meta = f'  <meta property="og:image" content="{html.escape(og_image, quote=True)}">\n' if og_image else ""
    alternate_meta = "".join(
        f'  <link rel="alternate" hreflang="{html.escape(hreflang, quote=True)}" href="{html.escape(href, quote=True)}">\n'
        for hreflang, href in (alternates or [])
    )
    return f"""  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(title)}</title>
  <meta name="description" content="{html.escape(description, quote=True)}">
  <link rel="canonical" href="{html.escape(canonical, quote=True)}">
{alternate_meta}  <link rel="icon" href="/favicon.svg" type="image/svg+xml">
  <meta property="og:type" content="website">
  <meta property="og:site_name" content="ZEC Apps">
  <meta property="og:title" content="{html.escape(title, quote=True)}">
  <meta property="og:description" content="{html.escape(description, quote=True)}">
  <meta property="og:url" content="{html.escape(canonical, quote=True)}">
{image_meta}"""


def render_shell(
    title: str,
    description: str,
    canonical: str,
    body: str,
    og_image: str = "",
    lang: str = "en",
    json_payload: str = "",
    alternates: list[tuple[str, str]] | None = None,
    lang_links: list[tuple[str, str]] | None = None,
) -> str:
    json_block = ""
    if json_payload:
        json_block = f"""  <script type="application/ld+json">
{json_payload.replace("</", "<\\/")}
  </script>
"""
    strings = ui_strings(lang)
    nav_items = [
        f'<a href="{html.escape(apps_index_href(lang), quote=True)}">{html.escape(str(strings["apps_nav"]))}</a>'
    ]
    for href, label in lang_links or []:
        nav_items.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>')
    nav_html = "\n        ".join(nav_items)
    return f"""<!DOCTYPE html>
<html lang="{html.escape(lang)}">
<head>
{render_head(title, description, canonical, og_image, alternates)}{json_block}  <style>
{base_css()}
  </style>
</head>
<body>
  <header>
    <div class="topbar">
      <div class="brand">ZEC Inc.</div>
      <nav aria-label="Secondary">
        {nav_html}
      </nav>
    </div>
  </header>
{body}
  <footer>
    <div class="footer">&copy; 2026 ZEC Inc.</div>
  </footer>
</body>
</html>
"""


def render_cards(apps: list[dict[str, Any]], overrides: dict[str, Any]) -> str:
    lines = [START_MARKER]
    for app in apps:
        name = html.escape(app_name(app))
        alt = html.escape(f"{app_name(app)} app icon", quote=True)
        desc = html.escape(short_description(app, overrides))
        url = html.escape(app_store_url(app), quote=True)
        detail_url = html.escape(f"{app['slug']}/", quote=True)
        img = icon_url(app)
        icon_html = ""
        if img:
            icon_html = f'            <img class="app-icon" src="{html.escape(img, quote=True)}" alt="{alt}" width="64" height="64" loading="lazy">'
        lines.extend(
            [
                '        <article class="app-card">',
                '          <div class="app-card-main">',
                icon_html,
                '            <div class="app-copy">',
                f'              <h2><a href="{detail_url}">{name}</a></h2>',
                f"              <p>{desc}</p>",
                "            </div>",
                "          </div>",
                '          <div class="app-actions">',
                f'            <a class="app-link primary" href="{detail_url}">Details</a>',
                f'            <a class="app-link" href="{url}">App Store →</a>',
                "          </div>",
                "        </article>",
                "",
            ]
        )
    if lines[-1] == "":
        lines.pop()
    lines.append(f"      {END_MARKER}")
    return "\n".join(lines)


def render_detail_page(app: dict[str, Any], overrides: dict[str, Any], ctx: BuildContext, locale: str = "en") -> str:
    content = detail_content(app, overrides, ctx, locale)
    strings = ui_strings(locale)
    locales = app_locales(app, overrides)
    alternates = hreflang_alternates(locales, lambda loc: page_url(app, loc))
    lang_links = language_links(locales, locale, lambda loc: page_href(app, loc))
    title = f"{content['name']} | ZEC Apps"
    canonical = page_url(app, locale)
    img = icon_url(app)
    screenshot_alt = str(strings["screenshot_alt"]).format(name=content["name"])
    screenshot_html = ""
    if content["screenshots"]:
        screenshot_html = f"""
    <section class="section">
      <h2>{html.escape(str(strings['screenshots']))}</h2>
      <div class="screenshots">
{chr(10).join(f'        <figure class="screenshot"><img src="{html.escape(url, quote=True)}" alt="{html.escape(screenshot_alt, quote=True)}" loading="lazy"></figure>' for url in content["screenshots"])}
      </div>
    </section>
"""
    faq_html = "\n".join(
        "\n".join(
            [
                "          <details>",
                f"            <summary>{html.escape(item['question'])}</summary>",
                f"            <p>{html.escape(item['answer'])}</p>",
                "          </details>",
            ]
        )
        for item in content["faq"]
    )
    icon_alt = str(strings["icon_alt"]).format(name=content["name"])
    open_label = str(strings["open_on_app_store"]).format(name=content["name"])
    body = f"""
  <main>
    <section class="hero">
      {f'<img class="app-icon" src="{html.escape(img, quote=True)}" alt="{html.escape(icon_alt, quote=True)}" width="96" height="96">' if img else ''}
      <div>
        <h1>{html.escape(content['name'])}</h1>
        <p class="tagline">{html.escape(content['tagline'])}</p>
        <div class="actions">
          <a class="button primary" href="{html.escape(app_store_url(app, locale), quote=True)}">{html.escape(str(strings['view_on_app_store']))}</a>
          <a class="button" href="{html.escape(apps_index_href(locale), quote=True)}">{html.escape(str(strings['all_apps']))}</a>
        </div>
      </div>
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['overview']))}</h2>
{html_paragraphs(content['overview'])}
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['audience']))}</h2>
      <ul>
{html_list(content['audience'])}
      </ul>
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['features']))}</h2>
      <ul>
{html_list(content['features'])}
      </ul>
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['usage']))}</h2>
      <ol>
{html_list(content['usage'])}
      </ol>
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['pricing']))}</h2>
      <p>{html.escape(content['pricing'])}</p>
      <p class="meta">{html.escape(str(strings['pricing_note']))}</p>
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['privacy']))}</h2>
      <p>{html.escape(content['privacy'])}</p>
    </section>
{screenshot_html}
    <section class="section">
      <h2>{html.escape(str(strings['faq']))}</h2>
{faq_html}
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['app_store']))}</h2>
      <p><a class="button primary" href="{html.escape(app_store_url(app, locale), quote=True)}">{html.escape(open_label)}</a></p>
      <p class="meta">{html.escape(str(strings['last_updated']))}: {html.escape(last_updated(app))}</p>
    </section>
  </main>
"""
    return render_shell(
        title,
        content["meta_description"],
        canonical,
        body,
        img,
        locale,
        json_ld(app, content, locale),
        alternates,
        lang_links,
    )


def render_app_mini_card(app: dict[str, Any], overrides: dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    strings = ui_strings(locale)
    localized_name = override_string(localized_override(app, overrides, locale).get("name"), app_name(app))
    icon_alt = str(strings["icon_alt"]).format(name=localized_name)
    img = icon_url(app)
    icon = f'<img class="mini-icon" src="{html.escape(img, quote=True)}" alt="{html.escape(icon_alt, quote=True)}" loading="lazy">' if img else ""
    detail_href = html.escape(page_href(app, locale), quote=True)
    return f"""        <article class="app-mini-card">
          {icon}
          <h2><a href="{detail_href}">{html.escape(localized_name)}</a></h2>
          <p>{html.escape(short_description(app, overrides, locale))}</p>
          <div class="app-actions">
            <a class="app-link primary" href="{detail_href}">{html.escape(str(strings['details']))}</a>
            <a class="app-link" href="{html.escape(app_store_url(app, locale), quote=True)}">{html.escape(str(strings['app_store_link']))}</a>
          </div>
        </article>"""


def category_definition(slug: str, locale: str) -> dict[str, str]:
    definition = CATEGORY_DEFINITIONS[slug]
    return definition.get(locale, definition[DEFAULT_LOCALE])


def render_category_page(
    slug: str,
    apps: list[dict[str, Any]],
    overrides: dict[str, Any],
    locale: str = DEFAULT_LOCALE,
    locales: list[str] | None = None,
) -> str:
    definition = category_definition(slug, locale)
    strings = ui_strings(locale)
    page_locales = locales or [DEFAULT_LOCALE]
    alternates = hreflang_alternates(page_locales, lambda loc: category_url(slug, loc))
    lang_links = language_links(page_locales, locale, lambda loc: category_href(slug, loc))
    title = f"{definition['title']} | ZEC Apps"
    description = definition["description"]
    cards = "\n".join(render_app_mini_card(app, overrides, locale) for app in apps)
    body = f"""
  <main>
    <section class="hero">
      <div>
        <h1>{html.escape(definition['title'])}</h1>
        <p class="tagline">{html.escape(description)}</p>
        <div class="actions">
          <a class="button" href="{html.escape(apps_index_href(locale), quote=True)}">{html.escape(str(strings['all_apps']))}</a>
        </div>
      </div>
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['apps_heading']))}</h2>
      <div class="app-grid">
{cards}
      </div>
    </section>
  </main>
"""
    return render_shell(
        title,
        description,
        category_url(slug, locale),
        body,
        "",
        locale,
        "",
        alternates,
        lang_links,
    )


def render_locale_apps_index(
    apps: list[dict[str, Any]],
    overrides: dict[str, Any],
    locale: str,
    locales: list[str],
) -> str:
    strings = ui_strings(locale)
    title = str(strings["apps_index_title"])
    description = str(strings["apps_index_description"])
    alternates = hreflang_alternates(locales, apps_index_url)
    lang_links = language_links(locales, locale, apps_index_href)
    cards = "\n".join(render_app_mini_card(app, overrides, locale) for app in apps)
    body = f"""
  <main>
    <section class="hero">
      <div>
        <h1>{html.escape(title)}</h1>
        <p class="tagline">{html.escape(description)}</p>
      </div>
    </section>

    <section class="section">
      <h2>{html.escape(str(strings['apps_heading']))}</h2>
      <div class="app-grid">
{cards}
      </div>
    </section>
  </main>
"""
    return render_shell(
        f"{title} | ZEC Inc.",
        description,
        apps_index_url(locale),
        body,
        "",
        locale,
        "",
        alternates,
        lang_links,
    )


def remove_generated_dirs(valid_slugs: set[str], marker_name: str) -> None:
    if not APPS_DIR.exists():
        return
    for child in APPS_DIR.iterdir():
        if child.is_dir() and child.name not in valid_slugs and (child / marker_name).exists():
            for path in sorted(child.rglob("*"), reverse=True):
                if path.is_file():
                    path.unlink()
                elif path.is_dir():
                    path.rmdir()
            child.rmdir()


def remove_stale_locale_dirs(parent_dir: Path, expected_locales: set[str]) -> None:
    """Remove locale subdirectories of a generated page dir that are no longer produced."""
    if not parent_dir.exists():
        return
    for child in parent_dir.iterdir():
        if not child.is_dir() or child.name in expected_locales:
            continue
        if not (child / "index.html").exists():
            continue
        for path in sorted(child.rglob("*"), reverse=True):
            if path.is_file():
                path.unlink()
            elif path.is_dir():
                path.rmdir()
        child.rmdir()


def write_detail_pages(apps: list[dict[str, Any]], overrides: dict[str, Any], ctx: BuildContext) -> list[str]:
    generated_urls: list[str] = []
    valid_slugs = {str(app["slug"]) for app in apps} | set(CATEGORY_DEFINITIONS)
    remove_generated_dirs(valid_slugs, DETAIL_MARKER)
    for app in apps:
        app_dir = APPS_DIR / str(app["slug"])
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / DETAIL_MARKER).write_text("Generated by scripts/update_apps_page.py\n", encoding="utf-8")
        (app_dir / "index.html").write_text(render_detail_page(app, overrides, ctx), encoding="utf-8", newline="\n")
        generated_urls.append(page_url(app))

        extra_locales = [locale for locale in app_locales(app, overrides) if locale != DEFAULT_LOCALE]
        remove_stale_locale_dirs(app_dir, set(extra_locales))
        for locale in extra_locales:
            locale_dir = app_dir / locale
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "index.html").write_text(render_detail_page(app, overrides, ctx, locale), encoding="utf-8", newline="\n")
            generated_urls.append(page_url(app, locale))
    return generated_urls


def write_category_pages(
    apps: list[dict[str, Any]], overrides: dict[str, Any], ctx: BuildContext, locales: list[str]
) -> list[str]:
    category_apps: dict[str, list[dict[str, Any]]] = {slug: [] for slug in CATEGORY_DEFINITIONS}
    for app in apps:
        for slug in app_categories(app, overrides, ctx):
            category_apps[slug].append(app)

    extra_locales = [locale for locale in locales if locale != DEFAULT_LOCALE]
    generated_urls: list[str] = []
    valid_slugs = {str(app["slug"]) for app in apps} | set(CATEGORY_DEFINITIONS)
    remove_generated_dirs(valid_slugs, CATEGORY_MARKER)
    for slug, apps_for_category in category_apps.items():
        if not apps_for_category:
            continue
        category_dir = APPS_DIR / slug
        category_dir.mkdir(parents=True, exist_ok=True)
        (category_dir / CATEGORY_MARKER).write_text("Generated by scripts/update_apps_page.py\n", encoding="utf-8")
        page_locales = [DEFAULT_LOCALE] + extra_locales
        (category_dir / "index.html").write_text(
            render_category_page(slug, apps_for_category, overrides, DEFAULT_LOCALE, page_locales),
            encoding="utf-8",
            newline="\n",
        )
        generated_urls.append(category_url(slug))
        remove_stale_locale_dirs(category_dir, set(extra_locales))
        for locale in extra_locales:
            locale_dir = category_dir / locale
            locale_dir.mkdir(parents=True, exist_ok=True)
            (locale_dir / "index.html").write_text(
                render_category_page(slug, apps_for_category, overrides, locale, page_locales),
                encoding="utf-8",
                newline="\n",
            )
            generated_urls.append(category_url(slug, locale))
    return generated_urls


def write_locale_indexes(apps: list[dict[str, Any]], overrides: dict[str, Any], locales: list[str]) -> list[str]:
    extra_locales = [locale for locale in locales if locale != DEFAULT_LOCALE]
    remove_generated_dirs(set(extra_locales), LOCALE_INDEX_MARKER)
    generated_urls: list[str] = []
    page_locales = [DEFAULT_LOCALE] + extra_locales
    for locale in extra_locales:
        locale_dir = APPS_DIR / locale
        locale_dir.mkdir(parents=True, exist_ok=True)
        (locale_dir / LOCALE_INDEX_MARKER).write_text("Generated by scripts/update_apps_page.py\n", encoding="utf-8")
        (locale_dir / "index.html").write_text(
            render_locale_apps_index(apps, overrides, locale, page_locales),
            encoding="utf-8",
            newline="\n",
        )
        generated_urls.append(apps_index_url(locale))
    return generated_urls


def update_apps_index(apps: list[dict[str, Any]], overrides: dict[str, Any]) -> None:
    if not APPS_PAGE.exists():
        raise RuntimeError(f"Apps page not found: {APPS_PAGE}")
    html_text = APPS_PAGE.read_text(encoding="utf-8")
    marker_pattern = re.compile(rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}", flags=re.DOTALL)
    if not marker_pattern.search(html_text):
        raise RuntimeError("Apps page markers were not found. Refusing to overwrite the page.")
    updated = marker_pattern.sub(render_cards(apps, overrides), html_text, count=1)
    if updated != html_text:
        APPS_PAGE.write_text(updated, encoding="utf-8", newline="\n")


def write_sitemap(urls: list[str]) -> None:
    unique_urls = []
    seen: set[str] = set()
    for url in [SITE_ORIGIN + "/", SITE_ORIGIN + "/apps/"] + urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    today = datetime.now(timezone.utc).date().isoformat()
    entries = "\n".join(
        f"  <url>\n    <loc>{html.escape(url)}</loc>\n    <lastmod>{today}</lastmod>\n  </url>"
        for url in unique_urls
    )
    SITEMAP_XML.write_text(
        f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{entries}
</urlset>
""",
        encoding="utf-8",
        newline="\n",
    )


def write_robots() -> None:
    ROBOTS_TXT.write_text(
        f"""User-agent: *
Allow: /
Allow: /apps/

Sitemap: {SITE_ORIGIN}/sitemap.xml
""",
        encoding="utf-8",
        newline="\n",
    )


def write_llms(apps: list[dict[str, Any]], overrides: dict[str, Any]) -> None:
    priority_names = {
        "PhotoDay: One Photo a Day",
        "Packed by ZEC",
        "PillTap",
        "LaundryTap",
        "Big Text Note",
        "CleanURL Tap - Tidy Long Links",
        "PoopTap",
    }
    priority_apps = [app for app in apps if app_name(app) in priority_names]
    if len(priority_apps) < 7:
        priority_apps = apps[:7]
    lines = [
        "# ZEC Apps",
        "",
        "ZEC Apps are small iPhone apps from ZEC Inc. for everyday records, quick checks, travel, family routines, widgets, and focused utilities.",
        "",
        "Canonical app index: https://zec-inc.jp/apps/",
        "",
        "## Main Apps",
    ]
    for app in priority_apps:
        lines.append(f"- {app_name(app)}: {short_description(app, overrides)} https://zec-inc.jp/apps/{app['slug']}/")
    lines.extend(
        [
            "",
            "## Category Pages",
        ]
    )
    for slug in CATEGORY_DEFINITIONS:
        definition = category_definition(slug, DEFAULT_LOCALE)
        lines.append(f"- {definition['title']}: https://zec-inc.jp/apps/{slug}/")
    lines.extend(
        [
            "",
            "Use the pages above as the canonical first-party source for ZEC app purpose, intended users, privacy notes, FAQs, and App Store links.",
        ]
    )
    LLMS_TXT.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def write_manifest(apps: list[dict[str, Any]], category_urls: list[str]) -> None:
    detail_slugs = sorted(str(app["slug"]) for app in apps)
    category_slugs = sorted(
        {
            slug
            for slug in (url.rstrip("/").rsplit("/", 1)[-1] for url in category_urls)
            if slug in CATEGORY_DEFINITIONS
        }
    )
    APPS_MANIFEST.write_text(
        json.dumps(
            {"detail_slugs": detail_slugs, "category_slugs": category_slugs},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def run_build(strict: bool = False) -> tuple[list[dict[str, Any]], list[str]]:
    ctx = BuildContext(strict=strict)
    overrides = load_overrides(ctx)
    apps = assign_slugs(fetch_apps(), overrides, ctx)
    locales = [DEFAULT_LOCALE] + site_locales(overrides)
    update_apps_index(apps, overrides)
    detail_urls = write_detail_pages(apps, overrides, ctx)
    locale_index_urls = write_locale_indexes(apps, overrides, locales)
    category_urls = write_category_pages(apps, overrides, ctx, locales)
    write_manifest(apps, category_urls)
    write_sitemap(detail_urls + locale_index_urls + category_urls)
    write_robots()
    write_llms(apps, overrides)

    for warning in ctx.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if strict and ctx.warnings:
        raise RuntimeError(f"Strict mode failed with {len(ctx.warnings)} warning(s).")
    return apps, detail_urls + category_urls


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true", help="Treat warnings as build failures.")
    args = parser.parse_args(argv)
    try:
        run_build(strict=args.strict)
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

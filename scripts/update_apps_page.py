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
LOOKUP_URL_JP = LOOKUP_URL.replace("country=us", "country=jp")
SITE_ORIGIN = "https://zec-inc.jp"
ROOT_DIR = Path(__file__).resolve().parent.parent
APPS_DIR = ROOT_DIR / "apps"
ASSETS_APPS_DIR = ROOT_DIR / "assets" / "apps"
APPS_PAGE = APPS_DIR / "index.html"
DETAIL_OVERRIDES = ROOT_DIR / "data" / "app-details-overrides.json"
LOOKUP_CACHE = ROOT_DIR / "data" / "app-store-lookup-cache.json"
LOOKUP_CACHE_JP = ROOT_DIR / "data" / "app-store-lookup-cache-jp.json"
APPS_MANIFEST = ROOT_DIR / "data" / "apps-manifest.json"
SITEMAP_XML = ROOT_DIR / "sitemap.xml"
HOME_PAGE = ROOT_DIR / "index.html"

FONTS_CSS = "https://fonts.googleapis.com/css2?family=Zen+Maru+Gothic:wght@700;900&family=Zen+Kaku+Gothic+New:wght@400;500;700&family=DM+Mono:wght@400;500&display=swap"
SITE_HEADER = """  <header class="site">
    <div class="site-in">
      <a class="logo" href="/"><i></i>ZEC</a>
      <nav aria-label="Primary">
        {nav}
      </nav>
    </div>
  </header>"""
SITE_FOOTER = """  <footer class="site-foot">
    <div class="site-in">
      <span>&copy; 2026 ZEC Inc.</span>
      <nav aria-label="Footer"><a href="/apps/">Apps</a><a href="/works/">Works</a><a href="/privacy.html">Privacy</a><a href="/support.html">Support</a></nav>
    </div>
  </footer>"""
HOME_FEATURED_JSON = ROOT_DIR / "data" / "home-featured.json"
HOME_FEATURED_START = "<!-- HOME_FEATURED_START -->"
HOME_FEATURED_END = "<!-- HOME_FEATURED_END -->"
HOME_COUNT_START = "<!-- HOME_COUNT_START -->"
HOME_COUNT_END = "<!-- HOME_COUNT_END -->"
ROBOTS_TXT = ROOT_DIR / "robots.txt"
LLMS_TXT = ROOT_DIR / "llms.txt"
START_MARKER = "<!-- APPS_LIST_START -->"
END_MARKER = "<!-- APPS_LIST_END -->"
DETAIL_MARKER = ".generated-app-detail"
CATEGORY_MARKER = ".generated-app-category"
LOCALE_INDEX_MARKER = ".generated-app-locale-index"

DEFAULT_LOCALE = "en"
HOME_PAGE_EN = ROOT_DIR / "en" / "index.html"

# Lightweight localized pages built only from the App Store's own localized listing (name, description,
# screenshots). An app gets a page in one of these languages only when its storefront listing is really
# written in that language (see localized_listing_ok).
LIGHT_LOCALES = {
    "zh-hans": {"country": "cn", "lang": "zh_cn", "html": "zh-Hans", "store_lang": "ZH"},
    "zh-hant": {"country": "tw", "lang": "zh_tw", "html": "zh-Hant", "store_lang": "ZH"},
    "ko": {"country": "kr", "lang": "ko_kr", "html": "ko", "store_lang": "KO"},
}
HTML_LANG = {code: value["html"] for code, value in LIGHT_LOCALES.items()}
LANGUAGE_NAMES = {"en": "English", "ja": "日本語", "zh-hans": "简体中文", "zh-hant": "繁體中文", "ko": "한국어"}

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
        "official_site": "Official site",
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
        "language_names": LANGUAGE_NAMES,
        "home_nav": "Home",
        "apps_index_title": "ZEC Apps",
        "apps_index_description": "Official list of iPhone apps from ZEC Inc. Small, focused tools for daily records, quick checks, travel, family routines, and widgets.",
        "icon_alt": "{name} app icon",
        "screenshot_alt": "{name} screenshot",
    },
    "ja": {
        "official_site": "公式サイト",
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
        "language_names": LANGUAGE_NAMES,
        "home_nav": "ホーム",
        "apps_index_title": "ZECのアプリ一覧",
        "apps_index_description": "合同会社ゼク（ZEC Inc.）が開発するiPhoneアプリの公式一覧です。毎日の記録・すばやい確認・旅行・家族の習慣・ウィジェットのための、小さくて目的のはっきりした道具を揃えています。",
        "icon_alt": "{name} のアプリアイコン",
        "screenshot_alt": "{name} のスクリーンショット",
    },
}
UI_STRINGS.update({
    "zh-hans": {
        "overview": "简介",
        "screenshots": "截图",
        "app_store": "App Store",
        "view_on_app_store": "在 App Store 查看",
        "open_on_app_store": "在 App Store 打开 {name}",
        "all_apps": "ZEC 应用一览",
        "last_updated": "最后更新",
        "details": "详情",
        "app_store_link": "App Store →",
        "apps_nav": "应用",
        "home_nav": "首页",
        "apps_heading": "应用一览",
        "language_names": LANGUAGE_NAMES,
        "apps_index_title": "ZEC 的 iPhone 应用",
        "apps_index_description": "ZEC Inc.（合同会社ゼク）开发的 iPhone 应用官方一览。这里列出已提供简体中文版的应用，都是专注于一件小事、简单好用的工具。",
        "store_note_heading": "价格与隐私",
        "store_note": "价格、App 内购买与最新的隐私信息，请以 App Store 页面为准。本页介绍文字来自 App Store 的应用说明。",
        "icon_alt": "{name} 的应用图标",
        "screenshot_alt": "{name} 的截图",
    },
    "zh-hant": {
        "overview": "簡介",
        "screenshots": "截圖",
        "app_store": "App Store",
        "view_on_app_store": "在 App Store 查看",
        "open_on_app_store": "在 App Store 開啟 {name}",
        "all_apps": "ZEC App 一覽",
        "last_updated": "最後更新",
        "details": "詳情",
        "app_store_link": "App Store →",
        "apps_nav": "App",
        "home_nav": "首頁",
        "apps_heading": "App 一覽",
        "language_names": LANGUAGE_NAMES,
        "apps_index_title": "ZEC 的 iPhone App",
        "apps_index_description": "ZEC Inc.（合同会社ゼク）開發的 iPhone App 官方一覽。這裡列出已提供繁體中文版的 App，每一款都專注於一件小事，簡單好用。",
        "store_note_heading": "價格與隱私",
        "store_note": "價格、App 內購買與最新的隱私權資訊，請以 App Store 頁面為準。本頁的介紹文字取自 App Store 的 App 說明。",
        "icon_alt": "{name} 的 App 圖示",
        "screenshot_alt": "{name} 的截圖",
    },
    "ko": {
        "overview": "소개",
        "screenshots": "스크린샷",
        "app_store": "App Store",
        "view_on_app_store": "App Store에서 보기",
        "open_on_app_store": "App Store에서 {name} 열기",
        "all_apps": "ZEC 앱 목록",
        "last_updated": "최종 업데이트",
        "details": "자세히",
        "app_store_link": "App Store →",
        "apps_nav": "앱",
        "home_nav": "홈",
        "apps_heading": "앱 목록",
        "language_names": LANGUAGE_NAMES,
        "apps_index_title": "ZEC의 iPhone 앱",
        "apps_index_description": "ZEC Inc.(合同会社ゼク)가 만든 iPhone 앱 공식 목록입니다. 한국어를 지원하는 앱만 모았으며, 모두 한 가지 일에 집중한 간단한 도구입니다.",
        "store_note_heading": "가격 및 개인정보",
        "store_note": "가격, 앱 내 구입, 최신 개인정보 처리 정보는 App Store 페이지에서 확인해 주세요. 이 페이지의 소개 문구는 App Store의 앱 설명에서 가져왔습니다.",
        "icon_alt": "{name} 앱 아이콘",
        "screenshot_alt": "{name} 스크린샷",
    },
})

for _code, _extra in {'en': {'chip_free': 'Free download', 'chip_iphone': 'iPhone', 'chip_both': 'iPhone & iPad', 'chip_languages': '{n} languages', 'related': 'More apps in this category', 'breadcrumb': 'Breadcrumb', 'highlights': 'At a glance'}, 'ja': {'chip_free': 'ダウンロード無料', 'chip_iphone': 'iPhone', 'chip_both': 'iPhone・iPad', 'chip_languages': '{n}言語に対応', 'related': '同じカテゴリのアプリ', 'breadcrumb': 'パンくずリスト', 'highlights': 'ひと目でわかるポイント'}, 'zh-hans': {'chip_free': '免费下载', 'chip_iphone': 'iPhone', 'chip_both': 'iPhone 和 iPad', 'chip_languages': '支持 {n} 种语言', 'related': '同类应用', 'breadcrumb': '导航路径', 'highlights': '要点'}, 'zh-hant': {'chip_free': '免費下載', 'chip_iphone': 'iPhone', 'chip_both': 'iPhone 與 iPad', 'chip_languages': '支援 {n} 種語言', 'related': '同類 App', 'breadcrumb': '導覽路徑', 'highlights': '重點'}, 'ko': {'chip_free': '무료 다운로드', 'chip_iphone': 'iPhone', 'chip_both': 'iPhone·iPad', 'chip_languages': '{n}개 언어 지원', 'related': '같은 카테고리의 앱', 'breadcrumb': '이동 경로', 'highlights': '한눈에 보기'}}.items():
    UI_STRINGS[_code].update(_extra)

APP_OVERRIDE_FIELDS = {
    "slug",
    "site_url",  # optional: the app's own site (adds a button next to the App Store link)
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


CHANGED_PAGES: set[Path] = set()


def write_page(path: Path, text: str) -> None:
    """Write a generated page and remember whether its content changed (drives sitemap lastmod)."""
    try:
        previous = path.read_text(encoding="utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        previous = None
    if previous != text:
        CHANGED_PAGES.add(path)
        path.write_text(text, encoding="utf-8", newline="\n")


@dataclass
class BuildContext:
    strict: bool = False
    warnings: list[str] = field(default_factory=list)

    def warn(self, message: str) -> None:
        self.warnings.append(message)


def fetch_lookup_payload(url: str = LOOKUP_URL, cache: Path = LOOKUP_CACHE) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "zec-inc.github.io apps updater/2.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return payload
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        if cache.exists():
            print(f"note: using cached App Store lookup data because live fetch failed: {exc}", file=sys.stderr)
            try:
                return json.loads(cache.read_text(encoding="utf-8"))
            except json.JSONDecodeError as cache_exc:
                raise RuntimeError(f"Failed to read cached App Store data: {cache_exc}") from cache_exc
        raise RuntimeError(f"Failed to fetch App Store data and no cache exists: {exc}") from exc


def fetch_apps() -> list[dict[str, Any]]:
    payload = fetch_lookup_payload()
    try:
        jp_payload = fetch_lookup_payload(LOOKUP_URL_JP, LOOKUP_CACHE_JP)
    except RuntimeError as exc:
        print(f"note: Japan storefront lookup unavailable: {exc}", file=sys.stderr)
        jp_payload = {}
    jp_by_id = {str(item.get("trackId", "")): item for item in jp_payload.get("results", [])}

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

        jp_item = jp_by_id.get(str(item.get("trackId", "")).strip(), {})
        apps.append(
            {
                "trackId": str(item.get("trackId", "")).strip(),
                "languages": [str(c) for c in item.get("languageCodesISO2A") or []],
                "screenshotUrlsJa": jp_item.get("screenshotUrls") if isinstance(jp_item.get("screenshotUrls"), list) else [],
                "ipadScreenshotUrlsJa": jp_item.get("ipadScreenshotUrls") if isinstance(jp_item.get("ipadScreenshotUrls"), list) else [],
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
                "formattedPriceJa": str(jp_item.get("formattedPrice", "")).strip(),
                "supportedDevices": [str(d) for d in item.get("supportedDevices") or []],
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
    attach_localized_listings(apps)
    return apps


KANA_RE = re.compile(r"[\u3040-\u30ff]")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
HANGUL_RE = re.compile(r"[\uac00-\ud7af]")


def localized_listing_ok(description: str, store_lang: str) -> bool:
    """True when a storefront description is really written in that language (not the ja/en fallback)."""
    if store_lang == "ZH":
        return len(HAN_RE.findall(description)) >= 30 and len(KANA_RE.findall(description)) < 3
    if store_lang == "KO":
        return len(HANGUL_RE.findall(description)) >= 30
    return False


def attach_localized_listings(apps: list[dict[str, Any]]) -> None:
    for code, spec in LIGHT_LOCALES.items():
        url = LOOKUP_URL.replace("country=us", f"country={spec['country']}&lang={spec['lang']}")
        cache = ROOT_DIR / "data" / f"app-store-lookup-cache-{code}.json"
        try:
            payload = fetch_lookup_payload(url, cache)
        except RuntimeError as exc:
            print(f"note: {code} storefront lookup unavailable: {exc}", file=sys.stderr)
            continue
        by_id = {str(item.get("trackId", "")): item for item in payload.get("results", [])}
        for app in apps:
            item = by_id.get(app["trackId"])
            if not item or spec["store_lang"] not in app.get("languages", []):
                continue
            description = str(item.get("description", "")).strip()
            if not localized_listing_ok(description, spec["store_lang"]):
                continue
            app.setdefault("l10n", {})[code] = {
                "trackName": str(item.get("trackName", "")).strip() or app["trackName"],
                "description": description,
                "screenshotUrls": [u for u in (item.get("screenshotUrls") or []) + (item.get("ipadScreenshotUrls") or []) if isinstance(u, str) and u.startswith("https://")],
            }


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
    light = [code for code in LIGHT_LOCALES if code in app.get("l10n", {})]
    return [DEFAULT_LOCALE] + extra + light


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


def display_name(app: dict[str, Any], overrides: dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    if locale in LIGHT_LOCALES:
        return str(app.get("l10n", {}).get(locale, {}).get("trackName") or app_name(app))
    return override_string(localized_override(app, overrides, locale).get("name"), app_name(app))


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
    alternates = [(HTML_LANG.get(locale, locale), url_for(locale)) for locale in locales]
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


def resolve_screenshots(app: dict[str, Any], override: dict[str, Any], ctx: BuildContext, locale: str = "en") -> list[str]:
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

    if locale == "ja":
        # 日本語ページには日本のストア(ja ローカライズ済み)のスクショだけを出す。ja 未対応アプリは英語画像になるので出さない。
        api_urls = (app.get("screenshotUrlsJa") or []) + (app.get("ipadScreenshotUrlsJa") or []) if "JA" in app.get("languages", []) else []
    else:
        api_urls = (app.get("screenshotUrls") or []) + (app.get("ipadScreenshotUrls") or [])
    screenshots.extend(url for url in api_urls if isinstance(url, str) and url.startswith(("http://", "https://")))

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
    screenshots = resolve_screenshots(app, override, ctx, locale)

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


APP_STORE_STOREFRONTS = {"ja": "jp", **{code: spec["country"] for code, spec in LIGHT_LOCALES.items()}}


def app_store_url(app: dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    url = str(app.get("trackViewUrl", "")).strip() or "https://apps.apple.com/us/developer/zec-inc/id1889726396"
    storefront = APP_STORE_STOREFRONTS.get(locale)
    if storefront:
        url = re.sub(r"(apps\.apple\.com)/[a-z]{2}/", rf"\1/{storefront}/", url, count=1)
    return url


def icon_url(app: dict[str, Any]) -> str:
    return str(app.get("artworkUrl512") or app.get("artworkUrl100") or "").strip()


def json_ld(app: dict[str, Any], content: dict[str, Any], locale: str, crumbs: list[tuple[str, str]] | None = None) -> str:
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
        "inLanguage": HTML_LANG.get(locale, locale),
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
    if crumbs:
        graph.append(
            {
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": i + 1, "name": name, "item": url}
                    for i, (name, url) in enumerate(crumbs)
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
        f'<a href="{"/" if lang == "ja" else "/en/"}">{html.escape(str(strings.get("home_nav", "Home")))}</a>',
        f'<a href="{html.escape(apps_index_href(lang), quote=True)}">{html.escape(str(strings["apps_nav"]))}</a>'
    ]
    for href, label in lang_links or []:
        nav_items.append(f'<a href="{html.escape(href, quote=True)}">{html.escape(label)}</a>')
    nav_html = "\n        ".join(nav_items)
    return f"""<!DOCTYPE html>
<html lang="{html.escape(HTML_LANG.get(lang, lang))}">
<head>
{render_head(title, description, canonical, og_image, alternates)}{json_block}  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link rel="stylesheet" href="{FONTS_CSS}">
  <link rel="stylesheet" href="/assets/site.css">
</head>
<body>
{SITE_HEADER.replace("{nav}", nav_html)}
{body}
{SITE_FOOTER}
</body>
</html>
"""


def render_cards(apps: list[dict[str, Any]], overrides: dict[str, Any]) -> str:
    lines = [START_MARKER]
    for app in apps:
        name = html.escape(display_name(app, overrides))
        alt = html.escape(f"{display_name(app, overrides)} app icon", quote=True)
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



RELATED_BY_CATEGORY: dict[str, list[dict[str, Any]]] = {}
APP_CATEGORY_CACHE: dict[str, list[str]] = {}


def home_href(locale: str) -> str:
    return "/en/" if locale == DEFAULT_LOCALE else "/"


def screenshot_size(url: str) -> tuple[int, int] | None:
    match = re.search(r"/(\d+)x(\d+)(?:bb|sr)?\.(?:jpg|jpeg|png|webp)$", url)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None


def render_screenshot_strip(urls: list[str], alt: str, heading: str) -> str:
    if not urls:
        return ""
    figures = []
    for url in urls:
        size = screenshot_size(url)
        dims = f' width="{size[0]}" height="{size[1]}"' if size else ""
        figures.append(
            f'        <figure class="shot"><img src="{html.escape(url, quote=True)}" alt="{html.escape(alt, quote=True)}"{dims} loading="lazy" decoding="async"></figure>'
        )
    return f"""
    <section class="shots" aria-label="{html.escape(heading, quote=True)}">
      <h2 class="visually-hidden">{html.escape(heading)}</h2>
      <div class="shot-strip">
{chr(10).join(figures)}
      </div>
    </section>
"""


def fact_chips(app: dict[str, Any], locale: str, categories: list[str]) -> str:
    strings = ui_strings(locale)
    chips: list[str] = []
    if app.get("price") in (0, 0.0, "0"):
        chips.append(html.escape(str(strings["chip_free"])))
    else:
        price = app.get("formattedPriceJa") if locale == "ja" and app.get("formattedPriceJa") else app.get("formattedPrice")
        if price:
            chips.append(html.escape(str(price)))
    devices = " ".join(app.get("supportedDevices") or [])
    has_ipad = "iPad" in devices
    has_iphone = "iPhone" in devices or not devices
    if has_iphone:
        chips.append(html.escape(str(strings["chip_both"] if has_ipad else strings["chip_iphone"])))
    languages = {code for code in app.get("languages", []) if code}
    if len(languages) > 1:
        chips.append(html.escape(str(strings["chip_languages"]).format(n=len(languages))))
    items = [f'<li class="chip">{chip}</li>' for chip in chips]
    for slug in categories:
        title = category_definition(slug, locale)["title"]
        items.append(f'<li class="chip chip-link"><a href="{html.escape(category_href(slug, locale), quote=True)}">{html.escape(title)}</a></li>')
    if not items:
        return ""
    return f'        <ul class="chips" aria-label="{html.escape(str(strings["highlights"]), quote=True)}">' + "".join(items) + "</ul>"


def render_breadcrumb(crumbs: list[tuple[str, str]], locale: str) -> str:
    strings = ui_strings(locale)
    parts = []
    for i, (name, href) in enumerate(crumbs):
        if i == len(crumbs) - 1:
            parts.append(f'<li aria-current="page">{html.escape(name)}</li>')
        else:
            parts.append(f'<li><a href="{html.escape(href, quote=True)}">{html.escape(name)}</a></li>')
    return f'    <nav class="crumbs" aria-label="{html.escape(str(strings["breadcrumb"]), quote=True)}"><ol>{"".join(parts)}</ol></nav>'


LEAD_DELIMITERS = ("、", "。", "：", " - ", ": ", ", ")


def emphasize_lead(text: str) -> str:
    positions = [text.find(d) for d in LEAD_DELIMITERS if text.find(d) > 0]
    if positions:
        cut = min(positions)
        lead = text[:cut]
        if len(lead) >= 4 and len(lead) <= 0.45 * len(text):
            return f"<strong>{html.escape(lead)}</strong>{html.escape(text[cut:])}"
    return html.escape(text)


CHECK_SVG = '<svg class="tick" viewBox="0 0 20 20" aria-hidden="true"><path d="M5 10.5l3.2 3.2L15 7" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>'


def render_related(app: dict[str, Any], overrides: dict[str, Any], locale: str, categories: list[str]) -> str:
    strings = ui_strings(locale)
    seen = {str(app.get("slug"))}
    picks: list[dict[str, Any]] = []
    for slug in categories:
        for other in RELATED_BY_CATEGORY.get(slug, []):
            key = str(other.get("slug"))
            if key in seen or locale not in app_locales(other, overrides):
                continue
            seen.add(key)
            picks.append(other)
            if len(picks) == 3:
                break
        if len(picks) == 3:
            break
    if not picks:
        return ""
    cards = []
    for other in picks:
        name = display_name(other, overrides, locale)
        img = icon_url(other)
        icon = f'<img src="{html.escape(img, quote=True)}" alt="" width="56" height="56" loading="lazy">' if img else ""
        desc = short_description(other, overrides, locale)
        cards.append(
            f'        <a class="related-card" href="{html.escape(page_href(other, locale), quote=True)}">{icon}'
            f'<span><h3>{html.escape(name)}</h3><p>{html.escape(truncate_text(desc, 80))}</p></span></a>'
        )
    return f"""
    <section class="block">
      <h2>{html.escape(str(strings['related']))}</h2>
      <div class="related">
{chr(10).join(cards)}
      </div>
    </section>
"""


def render_detail_page(app: dict[str, Any], overrides: dict[str, Any], ctx: BuildContext, locale: str = "en") -> str:
    content = detail_content(app, overrides, ctx, locale)
    strings = ui_strings(locale)
    # 任意: アプリ専用サイトがあれば、その導線を足す（overrides の site_url。ロケール別も可）
    _site_url = localized_override(app, overrides, locale).get('site_url')
    site_button = (
        f'<a class="button" href="{html.escape(str(_site_url), quote=True)}">'
        f'{html.escape(str(strings.get("official_site", "Official site")))}</a>\n          '
    ) if _site_url else ''
    locales = app_locales(app, overrides)
    alternates = hreflang_alternates(locales, lambda loc: page_url(app, loc))
    lang_links = language_links(locales, locale, lambda loc: page_href(app, loc))
    title = f"{content['name']} | ZEC Apps"
    canonical = page_url(app, locale)
    img = icon_url(app)
    screenshot_alt = str(strings["screenshot_alt"]).format(name=content["name"])
    categories = APP_CATEGORY_CACHE.get(str(app.get("slug")), [])
    crumbs = [(str(strings["home_nav"]), home_href(locale)), (str(strings["apps_nav"]), apps_index_href(locale))]
    if categories:
        crumbs.append((category_definition(categories[0], locale)["title"], category_href(categories[0], locale)))
    crumbs.append((content["name"], page_href(app, locale)))
    store = html.escape(app_store_url(app, locale), quote=True)
    overview = content["overview"]
    overview_html = ""
    if overview:
        overview_html = f'      <p class="lead-para">{html.escape(overview[0])}</p>\n' + "\n".join(
            f"      <p>{html.escape(item)}</p>" for item in overview[1:]
        )
    features_html = "\n".join(f'        <li>{CHECK_SVG}<span>{emphasize_lead(item)}</span></li>' for item in content["features"])
    audience_html = "\n".join(f"        <li>{html.escape(item)}</li>" for item in content["audience"])
    usage_html = "\n".join(f"        <li><span>{html.escape(item)}</span></li>" for item in content["usage"])
    faq_html = "\n".join(
        f"""        <details>
          <summary>{html.escape(item['question'])}</summary>
          <p>{html.escape(item['answer'])}</p>
        </details>"""
        for item in content["faq"]
    )
    icon_alt = str(strings["icon_alt"]).format(name=content["name"])
    open_label = str(strings["open_on_app_store"]).format(name=content["name"])
    body = f"""
  <main class="detail">
{render_breadcrumb(crumbs, locale)}
    <section class="hero">
      {f'<img class="app-icon" src="{html.escape(img, quote=True)}" alt="{html.escape(icon_alt, quote=True)}" width="96" height="96">' if img else ''}
      <div>
        <h1>{html.escape(content['name'])}</h1>
        <p class="tagline">{html.escape(content['tagline'])}</p>
        <div class="actions">
          <a class="button primary" href="{store}">{html.escape(str(strings['view_on_app_store']))}</a>
          {site_button}<a class="button" href="{html.escape(apps_index_href(locale), quote=True)}">{html.escape(str(strings['all_apps']))}</a>
        </div>
{fact_chips(app, locale, categories)}
      </div>
    </section>
{render_screenshot_strip(content['screenshots'], screenshot_alt, str(strings['screenshots']))}
    <section class="block prose">
      <h2>{html.escape(str(strings['overview']))}</h2>
{overview_html}
    </section>

    <section class="block">
      <h2>{html.escape(str(strings['features']))}</h2>
      <ul class="feature-grid">
{features_html}
      </ul>
    </section>

    <section class="block">
      <h2>{html.escape(str(strings['audience']))}</h2>
      <ul class="audience-grid">
{audience_html}
      </ul>
    </section>

    <section class="block">
      <h2>{html.escape(str(strings['usage']))}</h2>
      <ol class="steps">
{usage_html}
      </ol>
    </section>

    <div class="info-pair">
      <section class="info-card">
        <h2>{html.escape(str(strings['pricing']))}</h2>
        <p>{html.escape(content['pricing'])}</p>
        <p class="meta">{html.escape(str(strings['pricing_note']))}</p>
      </section>
      <section class="info-card">
        <h2>{html.escape(str(strings['privacy']))}</h2>
        <p>{html.escape(content['privacy'])}</p>
      </section>
    </div>

    <section class="block faq">
      <h2>{html.escape(str(strings['faq']))}</h2>
{faq_html}
    </section>
{render_related(app, overrides, locale, categories)}
    <section class="cta">
      <h2>{html.escape(str(strings['app_store']))}</h2>
      <a class="button primary big" href="{store}">{html.escape(open_label)}</a>
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
        json_ld(app, content, locale, [(name, SITE_ORIGIN + href) for name, href in crumbs]),
        alternates,
        lang_links,
    )


def light_paragraphs(app: dict[str, Any], locale: str, limit: int = 3) -> list[str]:
    listing = app.get("l10n", {}).get(locale, {})
    name = str(listing.get("trackName", "")).strip()
    parts = [clean_text(part) for part in re.split(r"\n\s*\n", str(listing.get("description", ""))) if clean_text(part)]
    return [part for part in parts if part.casefold() != name.casefold()][:limit]


def light_short_description(app: dict[str, Any], locale: str) -> str:
    for paragraph in light_paragraphs(app, locale):
        sentences = [part.strip() for part in re.split(r"(?<=[。！？.!?])\s*", paragraph) if part.strip()]
        for sentence in sentences:
            if len(sentence) >= 18:
                return truncate_text(sentence, 110)
    return display_name(app, {}, locale)


def render_light_detail_page(app: dict[str, Any], overrides: dict[str, Any], locale: str) -> str:
    """Detail page for a LIGHT_LOCALES language, built only from the App Store's localized listing."""
    strings = ui_strings(locale)
    listing = app["l10n"][locale]
    name = display_name(app, overrides, locale)
    tagline = light_short_description(app, locale)
    overview = light_paragraphs(app, locale)
    screenshots = listing.get("screenshotUrls", [])[:5]
    locales = app_locales(app, overrides)
    alternates = hreflang_alternates(locales, lambda loc: page_url(app, loc))
    lang_links = language_links(locales, locale, lambda loc: page_href(app, loc))
    img = icon_url(app)
    store_url = app_store_url(app, locale)
    icon_alt = str(strings["icon_alt"]).format(name=name)
    screenshot_alt = str(strings["screenshot_alt"]).format(name=name)
    crumbs = [(str(strings["home_nav"]), home_href(locale)), (str(strings["apps_nav"]), apps_index_href(locale)), (name, page_href(app, locale))]
    overview_html = ""
    if overview:
        overview_html = f'      <p class="lead-para">{html.escape(overview[0])}</p>\n' + "\n".join(f"      <p>{html.escape(item)}</p>" for item in overview[1:])
    body = f"""
  <main class="detail">
{render_breadcrumb(crumbs, locale)}
    <section class="hero">
      {f'<img class="app-icon" src="{html.escape(img, quote=True)}" alt="{html.escape(icon_alt, quote=True)}" width="96" height="96">' if img else ''}
      <div>
        <h1>{html.escape(name)}</h1>
        <p class="tagline">{html.escape(tagline)}</p>
        <div class="actions">
          <a class="button primary" href="{html.escape(store_url, quote=True)}">{html.escape(str(strings['view_on_app_store']))}</a>
          <a class="button" href="{html.escape(apps_index_href(locale), quote=True)}">{html.escape(str(strings['all_apps']))}</a>
        </div>
{fact_chips(app, locale, [])}
      </div>
    </section>
{render_screenshot_strip(screenshots, screenshot_alt, str(strings['screenshots']))}
    <section class="block prose">
      <h2>{html.escape(str(strings['overview']))}</h2>
{overview_html}
    </section>

    <section class="cta">
      <h2>{html.escape(str(strings['store_note_heading']))}</h2>
      <p>{html.escape(str(strings['store_note']))}</p>
      <a class="button primary big" href="{html.escape(store_url, quote=True)}">{html.escape(str(strings['open_on_app_store']).format(name=name))}</a>
      <p class="meta">{html.escape(str(strings['last_updated']))}: {html.escape(last_updated(app))}</p>
    </section>
  </main>
"""
    content = {"name": name, "meta_description": truncate_text(tagline, 120), "faq": []}
    return render_shell(
        f"{name} | ZEC Apps",
        content["meta_description"],
        page_url(app, locale),
        body,
        img,
        locale,
        json_ld(app, content, locale, [(n, SITE_ORIGIN + h) for n, h in crumbs]),
        alternates,
        lang_links,
    )


def render_app_mini_card(app: dict[str, Any], overrides: dict[str, Any], locale: str = DEFAULT_LOCALE) -> str:
    strings = ui_strings(locale)
    localized_name = display_name(app, overrides, locale)
    icon_alt = str(strings["icon_alt"]).format(name=localized_name)
    img = icon_url(app)
    icon = f'<img class="mini-icon" src="{html.escape(img, quote=True)}" alt="{html.escape(icon_alt, quote=True)}" loading="lazy">' if img else ""
    detail_href = html.escape(page_href(app, locale), quote=True)
    return f"""        <article class="app-mini-card">
          {icon}
          <h2><a href="{detail_href}">{html.escape(localized_name)}</a></h2>
          <p>{html.escape(light_short_description(app, locale) if locale in LIGHT_LOCALES else short_description(app, overrides, locale))}</p>
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
    RELATED_BY_CATEGORY.clear()
    APP_CATEGORY_CACHE.clear()
    for app in apps:
        cats = app_categories(app, overrides, BuildContext())
        APP_CATEGORY_CACHE[str(app["slug"])] = cats
        for slug in cats:
            RELATED_BY_CATEGORY.setdefault(slug, []).append(app)
    for app in apps:
        app_dir = APPS_DIR / str(app["slug"])
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / DETAIL_MARKER).write_text("Generated by scripts/update_apps_page.py\n", encoding="utf-8")
        write_page(app_dir / "index.html", render_detail_page(app, overrides, ctx))
        generated_urls.append(page_url(app))

        extra_locales = [locale for locale in app_locales(app, overrides) if locale != DEFAULT_LOCALE]
        remove_stale_locale_dirs(app_dir, set(extra_locales))
        for locale in extra_locales:
            locale_dir = app_dir / locale
            locale_dir.mkdir(parents=True, exist_ok=True)
            page = render_light_detail_page(app, overrides, locale) if locale in LIGHT_LOCALES else render_detail_page(app, overrides, ctx, locale)
            write_page(locale_dir / "index.html", page)
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
        write_page(
            category_dir / "index.html",
            render_category_page(slug, apps_for_category, overrides, DEFAULT_LOCALE, page_locales),
        )
        generated_urls.append(category_url(slug))
        remove_stale_locale_dirs(category_dir, set(extra_locales))
        for locale in extra_locales:
            locale_dir = category_dir / locale
            locale_dir.mkdir(parents=True, exist_ok=True)
            write_page(
                locale_dir / "index.html",
                render_category_page(slug, apps_for_category, overrides, locale, page_locales),
            )
            generated_urls.append(category_url(slug, locale))
    return generated_urls


def light_index_locales(apps: list[dict[str, Any]]) -> list[str]:
    return [code for code in LIGHT_LOCALES if any(code in app.get("l10n", {}) for app in apps)]


def write_locale_indexes(apps: list[dict[str, Any]], overrides: dict[str, Any], locales: list[str]) -> list[str]:
    extra_locales = [locale for locale in locales if locale != DEFAULT_LOCALE] + light_index_locales(apps)
    remove_generated_dirs(set(extra_locales), LOCALE_INDEX_MARKER)
    generated_urls: list[str] = []
    page_locales = [DEFAULT_LOCALE] + extra_locales
    for locale in extra_locales:
        locale_apps = [app for app in apps if locale in app.get("l10n", {})] if locale in LIGHT_LOCALES else apps
        locale_dir = APPS_DIR / locale
        locale_dir.mkdir(parents=True, exist_ok=True)
        (locale_dir / LOCALE_INDEX_MARKER).write_text("Generated by scripts/update_apps_page.py\n", encoding="utf-8")
        write_page(
            locale_dir / "index.html",
            render_locale_apps_index(locale_apps, overrides, locale, page_locales),
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
        CHANGED_PAGES.add(APPS_PAGE)
        APPS_PAGE.write_text(updated, encoding="utf-8", newline="\n")


def update_home_featured(apps: list[dict[str, Any]], ctx: "BuildContext") -> None:
    """Fill the top pages' featured-app cards and app count from the App Store lookup."""
    if not HOME_FEATURED_JSON.exists():
        return
    entries = json.loads(HOME_FEATURED_JSON.read_text(encoding="utf-8"))
    by_bundle = {str(app.get("bundleId", "")).strip(): app for app in apps}
    for page, locale in ((HOME_PAGE, "ja"), (HOME_PAGE_EN, DEFAULT_LOCALE)):
        if not page.exists():
            continue
        html_text = page.read_text(encoding="utf-8")
        if HOME_FEATURED_START not in html_text:
            continue
        items = []
        for entry in entries:
            app = by_bundle.get(entry["bundleId"])
            if not app:
                if locale == "ja":
                    ctx.warnings.append(f"home featured app not on the App Store: {entry['bundleId']}")
                continue
            text = entry if locale == "ja" else entry.get(locale)
            if not isinstance(text, dict):
                ctx.warnings.append(f"home featured app has no {locale} text: {entry['bundleId']}")
                continue
            items.append({"name": text["name"], "q": text["q"], "d": text["d"],
                          "icon": icon_url(app), "url": app_store_url(app, locale)})
        cards = []
        for it in items:
            e = {k: html.escape(v, quote=True) for k, v in it.items()}
            cards.append(
                f'      <a class="work" href="{e["url"]}" target="_blank" rel="noopener">'
                f'<img alt="" src="{e["icon"]}" width="64" height="64" loading="lazy">'
                f'<q>{e["q"]}</q><b>{e["name"]}</b><p>{e["d"]}</p><span class="go">App Store ↗</span></a>'
            )
        data = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
        block = "\n".join([HOME_FEATURED_START, '    <div class="works">', *cards, "    </div>",
                             f'    <script type="application/json" id="featured-data">{data}</script>',
                             f"    {HOME_FEATURED_END}"])
        updated = re.sub(rf"{re.escape(HOME_FEATURED_START)}.*?{re.escape(HOME_FEATURED_END)}", lambda _: block, html_text, count=1, flags=re.DOTALL)
        updated = re.sub(rf"{re.escape(HOME_COUNT_START)}.*?{re.escape(HOME_COUNT_END)}",
                         lambda _: f"{HOME_COUNT_START}{len(apps)}{HOME_COUNT_END}", updated, flags=re.DOTALL)
        if updated != html_text:
            CHANGED_PAGES.add(page)
            page.write_text(updated, encoding="utf-8", newline="\n")


def write_sitemap(urls: list[str]) -> None:
    unique_urls = []
    seen: set[str] = set()
    for url in [SITE_ORIGIN + "/", SITE_ORIGIN + "/en/", SITE_ORIGIN + "/apps/", SITE_ORIGIN + "/works/"] + urls:
        if url not in seen:
            seen.add(url)
            unique_urls.append(url)
    today = datetime.now(timezone.utc).date().isoformat()
    previous: dict[str, str] = {}
    if SITEMAP_XML.exists():
        previous = dict(
            re.findall(
                r"<loc>([^<]+)</loc>\s*<lastmod>([^<]+)</lastmod>",
                SITEMAP_XML.read_text(encoding="utf-8"),
            )
        )

    def lastmod_for(url: str) -> str:
        # Keep the previous date unless this run actually rewrote the page, so the
        # weekly run does not stamp every URL as modified.
        relative = url[len(SITE_ORIGIN):].strip("/")
        page = ROOT_DIR / relative / "index.html" if relative else ROOT_DIR / "index.html"
        old = previous.get(html.escape(url)) or previous.get(url)
        if old and page not in CHANGED_PAGES:
            return old
        return today

    entries = "\n".join(
        f"  <url>\n    <loc>{html.escape(url)}</loc>\n    <lastmod>{lastmod_for(url)}</lastmod>\n  </url>"
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
    lines = [
        "# ZEC Apps",
        "",
        "ZEC Apps are small iPhone apps from ZEC Inc. for everyday records, quick checks, travel, family routines, widgets, and focused utilities.",
        "",
        "Canonical app index: https://zec-inc.jp/apps/",
        "",
        "## Apps",
    ]
    for app in apps:
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
    lines.extend(["", "## Localized App Indexes"])
    for locale in ["ja"] + light_index_locales(apps):
        lines.append(f"- {LANGUAGE_NAMES[locale]}: {apps_index_url(locale)}")
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
    update_home_featured(apps, ctx)
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

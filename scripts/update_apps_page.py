#!/usr/bin/env python3
"""
Update apps/index.html from the App Store Lookup API.

Usage:
    python scripts/update_apps_page.py
"""

from __future__ import annotations

import html
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

DEVELOPER_ID = "1889726396"
DEVELOPER_NAME = "ZEC Inc."
LOOKUP_URL = (
    "https://itunes.apple.com/lookup"
    f"?id={DEVELOPER_ID}&entity=software&country=us&limit=200"
)
ROOT_DIR = Path(__file__).resolve().parent.parent
APPS_PAGE = ROOT_DIR / "apps" / "index.html"
START_MARKER = "<!-- APPS_LIST_START -->"
END_MARKER = "<!-- APPS_LIST_END -->"


def fetch_apps() -> list[dict]:
    request = urllib.request.Request(
        LOOKUP_URL,
        headers={
            "User-Agent": "zec-inc.github.io apps updater/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Failed to fetch App Store data: {exc}") from exc

    apps = []
    for item in payload.get("results", []):
        if item.get("kind") != "software":
            continue
        if str(item.get("artistId")) != DEVELOPER_ID:
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
                "trackName": track_name,
                "primaryGenreName": str(item.get("primaryGenreName", "")).strip(),
                "trackViewUrl": track_url,
                "description": str(item.get("description", "")).strip(),
                "releaseNotes": str(item.get("releaseNotes", "")).strip(),
            }
        )

    if not apps:
        raise RuntimeError("No ZEC Inc. software apps were found in the App Store payload.")

    return apps


def short_description(app: dict) -> str:
    text = app.get("description") or app.get("releaseNotes") or ""
    text = re.sub(r"\s+", " ", text).strip()
    track_name = str(app.get("trackName", "")).strip()
    stripped_title_prefix = False
    if track_name and text.casefold().startswith(track_name.casefold()):
        remainder = text[len(track_name):]
        if remainder.startswith("?") or remainder.startswith("!"):
            text = remainder.lstrip(" -–—:?!.,")
            stripped_title_prefix = True
    if text:
        sentences = [segment.strip() for segment in re.split(r"(?<=[.!?])\s+", text) if segment.strip()]
        sentence = ""
        for candidate in sentences:
            if len(candidate) >= 20:
                sentence = candidate
                break
        if not sentence:
            sentence = sentences[0] if sentences else text
        if stripped_title_prefix and sentence and sentence[:1].islower():
            sentence = f"{track_name} {sentence}"
        if len(sentence) > 110:
            sentence = sentence[:107].rstrip() + "..."
        return sentence
    genre = app.get("primaryGenreName", "").strip()
    return genre or "App Store app"


def render_cards(apps: list[dict]) -> str:
    lines = [START_MARKER]
    for app in apps:
        name = html.escape(app["trackName"])
        desc = html.escape(short_description(app))
        url = html.escape(app["trackViewUrl"], quote=True)
        lines.extend(
            [
                '        <article class="app-card">',
                f"          <h2>{name}</h2>",
                f"          <p>{desc}</p>",
                f'          <a class="app-link" href="{url}">App Store で見る</a>',
                "        </article>",
                "",
            ]
        )
    if lines[-1] == "":
        lines.pop()
    lines.append(f"      {END_MARKER}")
    return "\n".join(lines)


def update_apps_page() -> None:
    if not APPS_PAGE.exists():
        raise RuntimeError(f"Apps page not found: {APPS_PAGE}")

    html_text = APPS_PAGE.read_text(encoding="utf-8")
    marker_pattern = re.compile(
        rf"{re.escape(START_MARKER)}.*?{re.escape(END_MARKER)}",
        flags=re.DOTALL,
    )
    if not marker_pattern.search(html_text):
        raise RuntimeError("Apps page markers were not found. Refusing to overwrite the page.")

    rendered = render_cards(fetch_apps())
    updated = marker_pattern.sub(rendered, html_text, count=1)
    if updated != html_text:
        APPS_PAGE.write_text(updated, encoding="utf-8", newline="\n")


def main() -> int:
    try:
        update_apps_page()
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

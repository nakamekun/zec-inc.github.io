#!/usr/bin/env python3
"""手書き overrides が App Store の現状とずれていないかを検知する。

data/overrides-reviewed.json に「最後に人が内容を確認した時点」の
version / 言語数 / 価格を持ち、Lookup キャッシュと食い違うアプリを列挙する。

  python3 scripts/check_overrides_drift.py            # 一覧(ずれがあれば exit 1)
  python3 scripts/check_overrides_drift.py --markdown # Issue 用の本文
  python3 scripts/check_overrides_drift.py --mark SLUG [SLUG...]  # 確認済みにする
  python3 scripts/check_overrides_drift.py --mark-all             # 全部確認済みにする
"""
from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "app-store-lookup-cache.json"
OVERRIDES = ROOT / "data" / "app-details-overrides.json"
REVIEWED = ROOT / "data" / "overrides-reviewed.json"


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def snapshot(app: dict) -> dict:
    return {
        "version": app.get("version", ""),
        "languages": len(app.get("languageCodesISO2A") or []),
        "price": app.get("formattedPrice", ""),
    }


def apps_by_id() -> dict[str, dict]:
    results = load(CACHE).get("results", [])
    return {str(r["trackId"]): r for r in results if r.get("wrapperType") == "software"}


def slug_by_id(apps: dict[str, dict]) -> dict[str, str]:
    overrides = load(OVERRIDES)
    return {k: o.get("slug", k) for k, o in overrides.items() if isinstance(o, dict) and k in apps}


def drift(apps: dict[str, dict], reviewed: dict) -> list[dict]:
    rows = []
    for track_id, app in apps.items():
        now = snapshot(app)
        before = reviewed.get(track_id)
        reasons = []
        if before is None:
            reasons.append("未確認(新規掲載)")
        else:
            if now["version"] != before.get("version"):
                reasons.append(f"版 {before.get('version')} → {now['version']}")
            if now["languages"] != before.get("languages"):
                reasons.append(f"言語数 {before.get('languages')} → {now['languages']}")
            if now["price"] != before.get("price"):
                reasons.append(f"価格 {before.get('price')} → {now['price']}")
        if reasons:
            rows.append({"id": track_id, "name": app["trackName"], "reasons": reasons, "notes": app.get("releaseNotes", "")})
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--markdown", action="store_true")
    parser.add_argument("--mark", nargs="+", metavar="SLUG")
    parser.add_argument("--mark-all", action="store_true")
    args = parser.parse_args()

    apps = apps_by_id()
    reviewed = load(REVIEWED)
    slugs = slug_by_id(apps)

    if args.mark or args.mark_all:
        targets = list(apps) if args.mark_all else []
        by_slug = {v: k for k, v in slugs.items()}
        for s in args.mark or []:
            if s not in by_slug:
                print(f"unknown slug: {s}", file=sys.stderr)
                return 2
            targets.append(by_slug[s])
        today = datetime.date.today().isoformat()
        for track_id in targets:
            reviewed[track_id] = {**snapshot(apps[track_id]), "reviewed_at": today}
        REVIEWED.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"marked {len(targets)} app(s) as reviewed")
        return 0

    rows = drift(apps, reviewed)
    if not rows:
        print("overrides are in sync with the App Store listing")
        return 0
    if args.markdown:
        print("手書きの `data/app-details-overrides.json` が App Store の現状とずれている可能性があります。")
        print("説明・機能・FAQ・言語・価格の記述を確認し、直したら `python3 scripts/check_overrides_drift.py --mark <slug>` で確認済みにしてください。\n")
        for r in rows:
            print(f"- **{r['name']}** (`{slugs.get(r['id'], r['id'])}`): " + " / ".join(r["reasons"]))
            first = (r["notes"] or "").strip().splitlines()[:3]
            if first:
                print("  - 最新のリリースノート: " + " ".join(first)[:200])
    else:
        for r in rows:
            print(f"{r['name']}: " + " / ".join(r["reasons"]))
    return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Send optional Discord alerts for Kickoff result update outcomes."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def load_summary(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def notification_lines(summary: dict[str, Any], trigger_source: str) -> list[str]:
    lines: list[str] = []
    target_count = int(summary.get("targetCount", 0))
    updated_count = int(summary.get("updatedCount", 0))
    provider_failure_count = int(summary.get("providerFailureCount", 0))
    due_no_update = int(summary.get("dueMatchNoUpdateCount", 0))

    if bool(summary.get("scheduleMissSuspected")):
        overdue = ", ".join(summary.get("overdueMatches", [])) or "unknown"
        lines.append(f"schedule未起動疑い: overdue={overdue}, trigger={trigger_source}")
    if provider_failure_count > 0:
        lines.append(f"provider取得失敗: providerFailureCount={provider_failure_count}, trigger={trigger_source}")
    if target_count > 0 and updated_count == 0 and due_no_update > 0:
        lines.append(f"due matchありだが更新なし: targetCount={target_count}, dueMatchNoUpdateCount={due_no_update}, trigger={trigger_source}")
    return lines


def post_discord(webhook: str, content: str) -> None:
    payload = json.dumps({"content": content}).encode("utf-8")
    request = urllib.request.Request(webhook, data=payload, method="POST", headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=20) as response:
        response.read()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Notify Kickoff auto update monitoring events.")
    parser.add_argument("--summary-json", type=Path, required=True)
    parser.add_argument("--trigger-source", default="unknown")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = load_summary(args.summary_json)
    lines = notification_lines(summary, args.trigger_source)
    if not lines:
        print("notification: none")
        return 0
    content = "Kickoff Results Auto Update\n" + "\n".join(f"- {line}" for line in lines)
    webhook = os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("KICKOFF_DISCORD_WEBHOOK_URL")
    if args.dry_run or not webhook:
        print(content)
        if not webhook:
            print("notification: skipped missing webhook")
        return 0
    try:
        post_discord(webhook, content)
    except (urllib.error.URLError, TimeoutError) as error:
        print(f"notification: failed {type(error).__name__}", file=sys.stderr)
        return 1
    print("notification: sent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

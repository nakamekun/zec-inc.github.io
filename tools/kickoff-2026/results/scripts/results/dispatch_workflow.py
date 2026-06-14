#!/usr/bin/env python3
"""Dispatch Kickoff result update workflow without gh keychain auth."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


DEFAULT_REPO = "nakamekun/zec-inc.github.io"
DEFAULT_WORKFLOW = "kickoff-results-auto-update.yml"
DEFAULT_REF = "main"
API_ROOT = "https://api.github.com"


def read_token(args: argparse.Namespace) -> tuple[str | None, str]:
    env_token = os.environ.get(args.token_env)
    if env_token:
        return env_token, f"env:{args.token_env}"
    token_file_value = os.environ.get(args.token_file_env)
    token_file = Path(token_file_value).expanduser() if token_file_value else args.token_file
    if token_file:
        try:
            token = token_file.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            return None, f"file-missing:{token_file}"
        if token:
            return token, f"file:{token_file}"
    return None, "missing"


def notify_discord(message: str) -> None:
    webhook = os.environ.get("DISCORD_WEBHOOK_URL") or os.environ.get("KICKOFF_DISCORD_WEBHOOK_URL")
    if not webhook:
        return
    payload = json.dumps({"content": message}).encode("utf-8")
    request = urllib.request.Request(webhook, data=payload, method="POST", headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            response.read()
    except Exception as error:  # noqa: BLE001
        print(f"discord notification failed: {type(error).__name__}", file=sys.stderr)


def dispatch(args: argparse.Namespace, token: str) -> int:
    endpoint = f"{API_ROOT}/repos/{args.repo}/actions/workflows/{args.workflow}/dispatches"
    payload = {
        "ref": args.ref,
        "inputs": {
            "force": "true" if args.force else "false",
            "trigger_source": args.trigger_source,
        },
    }
    if args.dry_run:
        print(f"dryRun: true")
        print(f"endpoint: {endpoint}")
        print(f"ref: {args.ref}")
        print(f"tokenPresent: true")
        return 0
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "kickoff-results-dispatch/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            response.read()
            print(f"workflowDispatch: success status={response.status} endpoint={endpoint}")
            return 0
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")
        print(
            f"workflowDispatch: failed status={error.code} endpoint={endpoint} tokenPresent=true body={redact_body(body)}",
            file=sys.stderr,
        )
        if error.code in {401, 403}:
            notify_discord(
                "Kickoff Results Auto Update external dispatch auth failed "
                f"(status={error.code}, endpoint={endpoint}, tokenPresent=true)."
            )
        return 1
    except urllib.error.URLError as error:
        print(f"workflowDispatch: failed networkError={error.reason} endpoint={endpoint} tokenPresent=true", file=sys.stderr)
        return 1


def redact_body(body: str) -> str:
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return "<non-json>"
    message = payload.get("message")
    return str(message) if isinstance(message, str) else "<json>"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dispatch the Kickoff result update workflow via GitHub REST API.")
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--workflow", default=DEFAULT_WORKFLOW)
    parser.add_argument("--ref", default=DEFAULT_REF)
    parser.add_argument("--token-env", default="KICKOFF_WORKFLOW_DISPATCH_TOKEN")
    parser.add_argument("--token-file-env", default="KICKOFF_WORKFLOW_DISPATCH_TOKEN_FILE")
    parser.add_argument("--token-file", type=Path)
    parser.add_argument("--trigger-source", default="external-cron")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    token, token_source = read_token(args)
    endpoint = f"{API_ROOT}/repos/{args.repo}/actions/workflows/{args.workflow}/dispatches"
    if not token:
        print(f"workflowDispatch: failed status=missing-token endpoint={endpoint} tokenPresent=false tokenSource={token_source}", file=sys.stderr)
        notify_discord(
            "Kickoff Results Auto Update external dispatch auth failed "
            f"(status=missing-token, endpoint={endpoint}, tokenPresent=false)."
        )
        return 1
    print(f"tokenSource: {token_source}")
    return dispatch(args, token)


if __name__ == "__main__":
    raise SystemExit(main())

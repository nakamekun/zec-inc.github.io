#!/usr/bin/env python3
"""Deploy generated Kickoff JSON files inside the zec-inc.github.io repo."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[2]
REPO_ROOT = APP_DIR.parents[2]
GENERATED_MATCH_RESULTS = APP_DIR / "data" / "generated" / "matchResults.json"
GENERATED_GROUP_STANDINGS = APP_DIR / "data" / "generated" / "groupStandings.json"
PUBLIC_MATCH_RESULTS = Path("data/kickoff-2026/matchResults.json")
PUBLIC_GROUP_STANDINGS = Path("data/kickoff-2026/groupStandings.json")
ALLOWED_PUBLIC_PATHS = {str(PUBLIC_MATCH_RESULTS), str(PUBLIC_GROUP_STANDINGS)}
ALLOWED_TOOL_PATH_PREFIXES = (
    "tools/kickoff-2026/results/data/results/",
    "tools/kickoff-2026/results/data/generated/",
)
MATCH_RESULTS_URL = "https://zec-inc.jp/data/kickoff-2026/matchResults.json"
GROUP_STANDINGS_URL = "https://zec-inc.jp/data/kickoff-2026/groupStandings.json"
COMMIT_MESSAGE = "Update Kickoff 2026 results and group standings"


def validate_json(path: Path) -> None:
    with path.open("r", encoding="utf-8") as file:
        json.load(file)


def run_git(repo: Path, args: list[str], check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=check)


def status_entries(repo: Path) -> list[tuple[str, str]]:
    output = run_git(repo, ["status", "--porcelain", "--ignored=no"], check=True).stdout.splitlines()
    entries: list[tuple[str, str]] = []
    for line in output:
        if line:
            entries.append((line[:2], line[3:]))
    return entries


def is_allowed_existing_change(status: str, path: str) -> bool:
    if path in ALLOWED_PUBLIC_PATHS:
        return True
    if any(path.startswith(prefix) for prefix in ALLOWED_TOOL_PATH_PREFIXES):
        return True
    if status == "??" and path == ".DS_Store":
        return True
    return False


def ensure_no_unexpected_changes(repo: Path) -> None:
    unexpected = [f"{status} {path}" for status, path in status_entries(repo) if not is_allowed_existing_change(status, path)]
    if unexpected:
        raise RuntimeError("unexpected repo changes:\n" + "\n".join(unexpected))


def deploy_files(repo: Path) -> None:
    validate_json(GENERATED_MATCH_RESULTS)
    validate_json(GENERATED_GROUP_STANDINGS)
    target_dir = repo / "data" / "kickoff-2026"
    if not target_dir.is_dir():
        raise FileNotFoundError(f"missing target directory: {target_dir}")
    ensure_no_unexpected_changes(repo)
    shutil.copyfile(GENERATED_MATCH_RESULTS, repo / PUBLIC_MATCH_RESULTS)
    shutil.copyfile(GENERATED_GROUP_STANDINGS, repo / PUBLIC_GROUP_STANDINGS)
    validate_json(repo / PUBLIC_MATCH_RESULTS)
    validate_json(repo / PUBLIC_GROUP_STANDINGS)
    ensure_no_unexpected_changes(repo)


def commit_and_push(repo: Path, push: bool) -> str | None:
    run_git(repo, ["add", str(PUBLIC_MATCH_RESULTS), str(PUBLIC_GROUP_STANDINGS)])
    diff = run_git(repo, ["diff", "--cached", "--quiet"], check=False)
    if diff.returncode == 0:
        print("No public JSON diff; skipping deploy commit.")
        return None
    run_git(repo, ["commit", "-m", COMMIT_MESSAGE])
    commit_hash = run_git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    if push:
        run_git(repo, ["push"])
    return commit_hash


def curl_check(url: str) -> None:
    with urllib.request.urlopen(url, timeout=30) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} returned HTTP {response.status}")
        payload = response.read()
    json.loads(payload.decode("utf-8"))
    print(f"HTTP 200 JSON OK: {url}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Deploy generated Kickoff JSON inside zec-inc.github.io.")
    parser.add_argument("--repo", type=Path, default=REPO_ROOT)
    parser.add_argument("--no-push", action="store_true")
    parser.add_argument("--no-curl", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    deploy_files(args.repo)
    commit_hash = commit_and_push(args.repo, push=not args.no_push)
    if commit_hash:
        print(f"Committed {commit_hash}")
    if not args.no_curl:
        curl_check(MATCH_RESULTS_URL)
        curl_check(GROUP_STANDINGS_URL)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:  # noqa: BLE001
        print(f"deploy failed: {error}", file=sys.stderr)
        raise

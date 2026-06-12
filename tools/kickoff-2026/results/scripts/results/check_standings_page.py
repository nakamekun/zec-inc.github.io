#!/usr/bin/env python3
"""Print standings verification guidance without scraping external pages."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


APP_DIR = Path(__file__).resolve().parents[2]
DEFAULT_STANDINGS_PATH = APP_DIR / "data" / "generated" / "groupStandings.json"
STANDINGS_URL = "https://www.fifa.com/en/tournaments/mens/worldcup/canadamexicousa2026/standings"


def read_json(path: Path) -> dict:
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Show manual standings verification targets.")
    parser.add_argument("--standings", type=Path, default=DEFAULT_STANDINGS_PATH)
    parser.add_argument("--url", default=STANDINGS_URL)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    payload = read_json(args.standings)
    print(f"Open standings page for manual verification: {args.url}")
    print("Compare factual table values only. Do not copy prose, images, logos, or page text.")
    for group in payload.get("groups", []):
        print(f"\n{group['group']}")
        for team in group.get("teams", []):
            print(
                f"  {team['rank']}. {team['teamId']} "
                f"P{team['played']} W{team['won']} D{team['drawn']} L{team['lost']} "
                f"GF{team['goalsFor']} GA{team['goalsAgainst']} GD{team['goalDifference']} Pts{team['points']}"
            )


if __name__ == "__main__":
    main()

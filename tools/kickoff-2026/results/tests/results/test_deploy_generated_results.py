from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "results" / "deploy_generated_results.py"
spec = importlib.util.spec_from_file_location("deploy_generated_results", SCRIPT_PATH)
deploy_generated_results = importlib.util.module_from_spec(spec)
assert spec.loader is not None
sys.modules["deploy_generated_results"] = deploy_generated_results
spec.loader.exec_module(deploy_generated_results)


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=repo, text=True, capture_output=True, check=True).stdout


class DeployGeneratedResultsTests(unittest.TestCase):
    def make_repo(self, root: Path) -> Path:
        repo = root / "pages"
        (repo / "data" / "kickoff-2026").mkdir(parents=True)
        git_root = repo
        subprocess.run(["git", "init"], cwd=git_root, check=True, capture_output=True)
        git(git_root, "config", "user.email", "test@example.com")
        git(git_root, "config", "user.name", "Test")
        (repo / "data" / "kickoff-2026" / "matchResults.json").write_text('{"source":{},"results":[]}\n', encoding="utf-8")
        (repo / "data" / "kickoff-2026" / "groupStandings.json").write_text('{"source":{},"groups":[]}\n', encoding="utf-8")
        git(git_root, "add", "data/kickoff-2026/matchResults.json", "data/kickoff-2026/groupStandings.json")
        git(git_root, "commit", "-m", "initial")
        return repo

    def test_generated_json_broken_stops_deploy(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            good = root / "good.json"
            bad = root / "bad.json"
            good.write_text('{"source":{},"results":[]}\n', encoding="utf-8")
            bad.write_text('{"source":', encoding="utf-8")
            original_match = deploy_generated_results.GENERATED_MATCH_RESULTS
            original_group = deploy_generated_results.GENERATED_GROUP_STANDINGS
            try:
                deploy_generated_results.GENERATED_MATCH_RESULTS = good
                deploy_generated_results.GENERATED_GROUP_STANDINGS = bad
                with self.assertRaises(json.JSONDecodeError):
                    deploy_generated_results.deploy_files(repo)
            finally:
                deploy_generated_results.GENERATED_MATCH_RESULTS = original_match
                deploy_generated_results.GENERATED_GROUP_STANDINGS = original_group

    def test_deploy_stages_only_target_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = self.make_repo(root)
            match = root / "matchResults.json"
            standings = root / "groupStandings.json"
            match.write_text('{"source":{"name":"new"},"results":[]}\n', encoding="utf-8")
            standings.write_text('{"source":{"name":"new"},"groups":[]}\n', encoding="utf-8")
            (repo / ".DS_Store").write_text("ignored", encoding="utf-8")
            original_match = deploy_generated_results.GENERATED_MATCH_RESULTS
            original_group = deploy_generated_results.GENERATED_GROUP_STANDINGS
            try:
                deploy_generated_results.GENERATED_MATCH_RESULTS = match
                deploy_generated_results.GENERATED_GROUP_STANDINGS = standings
                deploy_generated_results.deploy_files(repo)
                deploy_generated_results.commit_and_push(repo, push=False)
                changed = git(repo, "show", "--name-only", "--format=", "HEAD").splitlines()
                self.assertEqual(
                    sorted(changed),
                    ["data/kickoff-2026/groupStandings.json", "data/kickoff-2026/matchResults.json"],
                )
            finally:
                deploy_generated_results.GENERATED_MATCH_RESULTS = original_match
                deploy_generated_results.GENERATED_GROUP_STANDINGS = original_group


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from pathlib import Path


WORKFLOW_PATH = Path(__file__).resolve().parents[5] / ".github" / "workflows" / "kickoff-results-auto-update.yml"


class WorkflowPushTests(unittest.TestCase):
    def test_workflow_has_concurrency_and_staggered_schedule(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertIn('cron: "7,17,27,37,47,57 * * * *"', workflow)
        self.assertIn("concurrency:", workflow)
        self.assertIn("group: kickoff-results-auto-update", workflow)
        self.assertIn("trigger_source:", workflow)
        self.assertIn("--summary-json \"$SUMMARY_JSON\"", workflow)

    def test_push_step_compares_local_head_to_upstream(self):
        workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
        self.assertNotIn("git log --branches --not --remotes --quiet", workflow)
        self.assertIn('LOCAL_HEAD="$(git rev-parse HEAD)"', workflow)
        self.assertIn('UPSTREAM_HEAD="$(git rev-parse @{u})"', workflow)
        self.assertIn('if [ "$LOCAL_HEAD" = "$UPSTREAM_HEAD" ]; then', workflow)
        self.assertIn("git push", workflow)


if __name__ == "__main__":
    unittest.main()

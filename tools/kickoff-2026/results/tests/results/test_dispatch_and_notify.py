from __future__ import annotations

import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts" / "results"


def load_module(name: str, filename: str):
    path = SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


dispatch_workflow = load_module("dispatch_workflow", "dispatch_workflow.py")
notify_auto_update = load_module("notify_auto_update", "notify_auto_update.py")


class DispatchAndNotifyTests(unittest.TestCase):
    def test_dispatch_missing_token_reports_presence_only(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch("sys.argv", ["dispatch_workflow.py"]):
                with mock.patch("sys.stderr") as stderr:
                    exit_code = dispatch_workflow.main()
        self.assertEqual(exit_code, 1)
        written = "".join(call.args[0] for call in stderr.write.call_args_list if call.args)
        self.assertIn("tokenPresent=false", written)
        self.assertIn("status=missing-token", written)

    def test_dispatch_dry_run_does_not_call_network(self):
        with mock.patch.dict(os.environ, {"KICKOFF_WORKFLOW_DISPATCH_TOKEN": "secret-token"}, clear=True):
            with mock.patch("sys.argv", ["dispatch_workflow.py", "--dry-run"]):
                with mock.patch("urllib.request.urlopen") as urlopen:
                    exit_code = dispatch_workflow.main()
        self.assertEqual(exit_code, 0)
        urlopen.assert_not_called()

    def test_notify_classifies_provider_failure_due_no_update_and_schedule_miss(self):
        summary = {
            "targetCount": 1,
            "updatedCount": 0,
            "providerFailureCount": 1,
            "dueMatchNoUpdateCount": 1,
            "scheduleMissSuspected": True,
            "overdueMatches": ["match-006"],
        }
        lines = notify_auto_update.notification_lines(summary, "external-cron")
        self.assertTrue(any("provider取得失敗" in line for line in lines))
        self.assertTrue(any("due matchありだが更新なし" in line for line in lines))
        self.assertTrue(any("schedule未起動疑い" in line for line in lines))

    def test_notify_noop_for_no_due_matches(self):
        summary = {
            "targetCount": 0,
            "updatedCount": 0,
            "providerFailureCount": 0,
            "dueMatchNoUpdateCount": 0,
            "scheduleMissSuspected": False,
        }
        self.assertEqual(notify_auto_update.notification_lines(summary, "github-schedule"), [])

    def test_notify_dry_run_reads_summary_without_webhook(self):
        with tempfile.TemporaryDirectory() as tmp:
            summary_path = Path(tmp) / "summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "targetCount": 1,
                        "updatedCount": 0,
                        "providerFailureCount": 0,
                        "dueMatchNoUpdateCount": 1,
                        "scheduleMissSuspected": False,
                    }
                ),
                encoding="utf-8",
            )
            with mock.patch.dict(os.environ, {}, clear=True):
                with mock.patch("sys.argv", ["notify_auto_update.py", "--summary-json", str(summary_path), "--dry-run"]):
                    self.assertEqual(notify_auto_update.main(), 0)


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import aso_core
import generate_metadata
import keyword_scoring
import proposal_generator
import research_metadata
from research_providers import AppStoreSearchProvider, StaticResearchProvider, _keywordish_terms


class ResearchPipelineTests(unittest.TestCase):
    def test_static_provider_reads_source_and_seed_keywords(self) -> None:
        source = {
            "locales": {
                "en-US": {
                    "research": {
                        "keyword_candidates": [
                            {"term": "hydration", "priority": 1},
                            "water log",
                        ],
                        "competitors": ["WaterMinder"],
                    }
                }
            }
        }
        result = StaticResearchProvider().collect(
            {
                "source": source,
                "locale": "en-US",
                "country": "us",
                "seed_keywords": ["daily water"],
                "competitors": ["Waterllama"],
            }
        )

        self.assertEqual(result["provider"], "static")
        self.assertEqual(
            [item["term"] for item in result["keyword_candidates"]],
            ["hydration", "water log", "daily water"],
        )
        self.assertEqual([item["name"] for item in result["competitors"]], ["WaterMinder", "Waterllama"])

    def test_locale_seed_keywords_are_independent(self) -> None:
        source = {
            "locales": {
                "en-US": {"seed_keywords": ["packing list", "travel checklist"]},
                "ja": {"seed_keywords": ["持ち物リスト", "旅行準備"]},
            }
        }

        en = StaticResearchProvider().collect({"source": source, "locale": "en-US", "country": "us"})
        ja = StaticResearchProvider().collect({"source": source, "locale": "ja", "country": "jp"})

        self.assertEqual(
            [item["term"] for item in en["keyword_candidates"]],
            ["packing list", "travel checklist"],
        )
        self.assertEqual(
            [item["term"] for item in ja["keyword_candidates"]],
            ["持ち物リスト", "旅行準備"],
        )
        self.assertNotIn("packing list", [item["term"] for item in ja["keyword_candidates"]])

    def test_appstore_provider_failure_returns_warning_not_exception(self) -> None:
        provider = AppStoreSearchProvider(Path("/tmp/unused-aso-cache"), use_cache=False)
        with mock.patch.object(provider, "_fetch", side_effect=OSError("network down")):
            result = provider.collect(
                {
                    "locale": "en-US",
                    "country": "us",
                    "search_terms": ["water tracker"],
                    "max_results": 10,
                }
            )

        self.assertEqual(result["search_results"], [])
        self.assertEqual(result["keyword_candidates"], [])
        self.assertIn("network down", result["warnings"][0])

    def test_generic_filter_keeps_important_terms(self) -> None:
        terms = _keywordish_terms("Get Water Tracker AI Pro Reminder 水分補給")
        self.assertNotIn("Get", terms)
        self.assertNotIn("AI", terms)
        self.assertIn("Water", terms)
        self.assertIn("Tracker", terms)
        self.assertIn("Reminder", terms)
        self.assertIn("水分補給", terms)

    def test_keyword_scoring_handles_empty_seed_and_filters_low_value(self) -> None:
        scored = keyword_scoring.score_keywords(
            [
                {"term": "in", "priority": 1},
                {"term": "hydration", "priority": 2},
                {"term": "水分補給", "priority": 3},
            ],
            {"name": "WaterDone", "subtitle": "Hydration tracker"},
            "Fast water logging with reminders",
            [],
            [],
            "ja",
        )
        terms = [item["term"] for item in scored]
        self.assertNotIn("in", terms)
        self.assertIn("hydration", terms)
        self.assertIn("水分補給", terms)

    def test_locale_keyword_thresholds_match_validator_character_counting(self) -> None:
        en_keywords = "aqua,drink,habit,water,log"
        ja_keywords = "水分補給,水分記録,リマインダー,ウィジェット,毎日の習慣,飲水ログ,通知,履歴,目標"

        en_issues = aso_core.validate_keywords(en_keywords, "WaterDone", "", "en-US")
        ja_issues = aso_core.validate_keywords(ja_keywords, "WaterDone", "", "ja")

        self.assertTrue(any(issue.code == "keywords-underused" for issue in en_issues))
        self.assertFalse(any(issue.code == "keywords-underused" for issue in ja_issues))
        self.assertGreaterEqual(len(ja_keywords), aso_core.keyword_target_min("ja"))

    def test_proposals_include_validator_issues_and_use_aso_core(self) -> None:
        proposals = proposal_generator.generate_locale_proposals(
            "en-US",
            {"name": "WaterDone", "subtitle": "Hydration tracker", "release_notes": "Initial."},
            [{"term": "best", "score": 0.9, "components": {}, "source": "test"}],
            "Hydration tracker",
            [{"term": "best", "level": "warning", "reason": "superlative"}],
        )

        self.assertEqual(len(proposals), 3)
        self.assertIn("issues", proposals[0])
        self.assertEqual(
            [
                issue.as_dict()
                for issue in aso_core.validate_locale(
                    proposals[0]["fields"],
                    [{"term": "best", "level": "warning", "reason": "superlative"}],
                    "en-US",
                )
            ],
            proposals[0]["issues"],
        )

    def test_locale_avoid_terms_are_reflected_in_proposal_issues(self) -> None:
        proposals = proposal_generator.generate_locale_proposals(
            "ja",
            {"name": "Packed", "subtitle": "旅行準備", "release_notes": "初回。"},
            [{"term": "保証", "score": 0.9, "components": {}, "source": "test"}],
            "旅行の持ち物リスト",
            [{"term": "保証", "level": "warning", "reason": "unsupported claim"}],
        )

        issues = [issue for proposal in proposals for issue in proposal["issues"]]
        self.assertTrue(any(issue["code"] == "avoid-term" for issue in issues))
        self.assertTrue(any("保証" in issue["message"] for issue in issues))

    def test_ja_proposal_is_not_simple_en_copy_when_locale_seeds_differ(self) -> None:
        en = proposal_generator.generate_locale_proposals(
            "en-US",
            {"name": "Packed", "subtitle": "Packing checklist", "release_notes": "Initial."},
            [{"term": "packing list", "score": 0.9, "components": {}, "source": "locale-seed"}],
            "Travel packing checklist",
            [],
        )[0]
        ja = proposal_generator.generate_locale_proposals(
            "ja",
            {"name": "Packed", "subtitle": "持ち物リスト", "release_notes": "初回。"},
            [{"term": "旅行準備", "score": 0.9, "components": {}, "source": "locale-seed"}],
            "旅行の持ち物リスト",
            [],
        )[0]

        self.assertNotEqual(en["fields"]["subtitle"], ja["fields"]["subtitle"])
        self.assertIn("旅行準備", ja["fields"]["keywords"] + ja["fields"]["subtitle"])

    def test_research_cli_offline_does_not_write_suggestion_or_fastlane(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            app_dir = self._make_app(Path(td))
            fastlane_file = app_dir / "fastlane" / "metadata" / "en-US" / "keywords.txt"
            before = fastlane_file.read_text(encoding="utf-8")

            code = research_metadata.main(
                [
                    "--app",
                    str(app_dir),
                    "--locale",
                    "en-US,ja",
                    "--country",
                    "us,jp",
                    "--seed-keywords",
                    "hydration,水分補給",
                    "--offline",
                ]
            )

            self.assertEqual(code, 0)
            self.assertTrue((app_dir / "docs" / "aso" / "research.generated.json").is_file())
            self.assertTrue((app_dir / "docs" / "aso" / "metadata-proposals.md").is_file())
            self.assertFalse((app_dir / "docs" / "aso" / "aso-source.suggested.yaml").exists())
            self.assertEqual(before, fastlane_file.read_text(encoding="utf-8"))

            data = json.loads((app_dir / "docs" / "aso" / "research.generated.json").read_text(encoding="utf-8"))
            self.assertEqual(data["providers"], ["static"])
            for locale_entry in data["locales"].values():
                self.assertEqual(len(locale_entry["proposals"]), 3)
            first_keywords = json.loads(
                (app_dir / "docs" / "aso" / "keyword-candidates.generated.json").read_text(
                    encoding="utf-8"
                )
            )["locales"]

            code = research_metadata.main(
                [
                    "--app",
                    str(app_dir),
                    "--locale",
                    "en-US,ja",
                    "--country",
                    "us,jp",
                    "--seed-keywords",
                    "hydration,水分補給",
                    "--offline",
                ]
            )
            self.assertEqual(code, 0)
            second_keywords = json.loads(
                (app_dir / "docs" / "aso" / "keyword-candidates.generated.json").read_text(
                    encoding="utf-8"
                )
            )["locales"]
            self.assertEqual(first_keywords, second_keywords)

    def test_research_cli_rejects_mismatched_country_count(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            app_dir = self._make_app(Path(td))
            code = research_metadata.main(
                [
                    "--app",
                    str(app_dir),
                    "--locale",
                    "en-US,ja",
                    "--country",
                    "us,jp,gb",
                    "--offline",
                ]
            )
            self.assertEqual(code, 2)

    def test_research_cli_provider_failure_still_outputs_locale_proposals(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            app_dir = self._make_app(Path(td))
            with mock.patch.object(AppStoreSearchProvider, "_fetch", side_effect=OSError("down")):
                code = research_metadata.main(
                    [
                        "--app",
                        str(app_dir),
                        "--locale",
                        "en-US,ja",
                        "--country",
                        "us,jp",
                        "--seed-keywords",
                        "hydration,水分補給,旅行準備",
                        "--max-results",
                        "5",
                    ]
                )
            self.assertEqual(code, 0)
            data = json.loads((app_dir / "docs" / "aso" / "research.generated.json").read_text(encoding="utf-8"))
            for locale, entry in data["locales"].items():
                self.assertEqual(len(entry["proposals"]), 3, locale)
                self.assertTrue(entry["research"]["provider_results"][1]["warnings"])

    def test_generate_metadata_dry_run_does_not_write_fastlane_but_write_does(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            app_dir = self._make_app(Path(td))
            fastlane_file = app_dir / "fastlane" / "metadata" / "en-US" / "subtitle.txt"
            before = fastlane_file.read_text(encoding="utf-8")
            source = app_dir / "docs" / "aso" / "aso-source.yaml"

            dry_code = generate_metadata.main(
                ["--app", str(app_dir), "--source", str(source), "--locales", "en-US", "--dry-run"]
            )
            self.assertEqual(dry_code, 0)
            self.assertEqual(before, fastlane_file.read_text(encoding="utf-8"))

            write_code = generate_metadata.main(
                ["--app", str(app_dir), "--source", str(source), "--locales", "en-US", "--write"]
            )
            self.assertEqual(write_code, 0)
            self.assertNotEqual(before, fastlane_file.read_text(encoding="utf-8"))

    def _make_app(self, root: Path) -> Path:
        app_dir = root / "SampleApp"
        aso_dir = app_dir / "docs" / "aso"
        meta_en = app_dir / "fastlane" / "metadata" / "en-US"
        meta_ja = app_dir / "fastlane" / "metadata" / "ja"
        aso_dir.mkdir(parents=True)
        meta_en.mkdir(parents=True)
        meta_ja.mkdir(parents=True)
        (app_dir / "docs" / "product-spec.md").write_text(
            "Simple hydration logging with reminders and widgets.",
            encoding="utf-8",
        )
        for meta_dir, name, subtitle, keywords in (
            (meta_en, "WaterDone", "Hydration tracker", "water,hydration,log,reminder"),
            (meta_ja, "WaterDone", "水分補給を記録", "水分補給,記録,通知"),
        ):
            (meta_dir / "name.txt").write_text(name, encoding="utf-8")
            (meta_dir / "subtitle.txt").write_text(subtitle, encoding="utf-8")
            (meta_dir / "keywords.txt").write_text(keywords, encoding="utf-8")
            (meta_dir / "promotional_text.txt").write_text("Log water quickly.", encoding="utf-8")
            (meta_dir / "description.txt").write_text("Log water quickly.", encoding="utf-8")
            (meta_dir / "release_notes.txt").write_text("Initial.", encoding="utf-8")
        (aso_dir / "aso-source.yaml").write_text(
            """
app:
  slug: sample-ios
  base_locale: en-US
defaults:
  avoid_terms:
    - term: "#1"
      level: error
locales:
  en-US:
    seed_keywords:
      - hydration
      - water reminder
    search_intents:
      - track water intake
    research:
      keyword_candidates:
        - hydration
        - reminder
      competitors:
        - WaterMinder
    metadata:
      name: WaterDone
      subtitle: Daily water log
      promotional_text: Log water quickly.
      description: |
        Log water quickly.
      release_notes: |
        Initial.
  ja:
    seed_keywords:
      - 水分補給
      - 水分記録
    search_intents:
      - 水分補給を記録したい
    avoid_terms:
      - term: 治療
        level: error
    research:
      keyword_candidates:
        - 水分補給
        - 記録
      competitors:
        - WaterMinder
    metadata:
      name: WaterDone
      subtitle: 水分補給を記録
      promotional_text: すばやく水分を記録できます。
      description: |
        すばやく水分を記録できます。
      release_notes: |
        初回。
""".lstrip(),
            encoding="utf-8",
        )
        return app_dir


if __name__ == "__main__":
    unittest.main()

# ASO Metadata Research Prompt

Use the following structured JSON as the only source of truth. The final proposal will be checked by the local ASO validator before use.

```json
{
  "task": "Create locale-specific App Store ASO metadata alternatives from research.",
  "locale": "ja",
  "constraints": [
    "Return JSON only.",
    "Do not call external APIs.",
    "Do not directly translate the base locale.",
    "Treat the base locale only as product meaning and compliance context.",
    "Optimize for this locale's App Store search behavior.",
    "Use natural wording for this locale.",
    "Preserve product meaning and compliance constraints.",
    "Return reviewable alternatives, not only one answer.",
    "Respect App Store metadata limits.",
    "Avoid prohibited or risky terms.",
    "Avoid unsupported claims.",
    "Do not repeat keywords already in name/subtitle.",
    "Keep keywords comma-separated with no spaces around commas."
  ],
  "expected_json_schema": {
    "proposals": [
      {
        "strategy": "Search-first | Conversion-first | Long-tail / niche",
        "name": "string",
        "subtitle": "string",
        "keywords": "comma-separated string",
        "promotional_text": "string",
        "description_outline": [
          "string"
        ],
        "rationale": "string",
        "adopted_keywords": [
          "string"
        ],
        "excluded_keywords": [
          {
            "term": "string",
            "reason": "string"
          }
        ],
        "search_intent": "string",
        "risks": [
          "string"
        ]
      }
    ]
  },
  "app_product_summary": "# Product Spec\n\n## One-line Description\n\nPacked helps users manage reusable packing groups and check items for the day.\n\n## Core Value\n\n- Reduce forgotten items through repeatable daily checklists.\n- Keep packing setup lightweight.\n\n## Target Users\n\n- People preparing for school, work, travel, gym, or daily routines.\n\n## Core Operation\n\n- Create a group, add items, check today's packed state, and optionally get reminders.\n\n## Free Features\n\n- Packing groups and items.\n- Daily check state.\n- Settings and local reminders.\n\n## Paid Feature Candidates\n\n- Unknown. Possible candidates: unlimited groups, templates, themes.\n\n## Non-goals\n\n- Inventory management.\n- Shared household/team packing.\n- Server sync in v1.",
  "current_metadata": {
    "name": "Packed",
    "subtitle": "旅行の持ち物リスト",
    "keywords": "",
    "promotional_text": "旅行や出張の持ち物をリスト化。出発前に準備できたものをすばやく確認できます。",
    "description": "Packedは、旅行や出張の持ち物を整理するためのシンプルなチェックリストアプリです。\n\n持ち物をリストにして、準備できたものをチェック。次の旅行でも同じリストを見直せます。\n子連れ旅行、出張、短い外出など、出発前の確認を軽くしたいときに使えます。",
    "release_notes": "初回リリース。"
  },
  "base_locale_reference_policy": {
    "translation_first": false,
    "instruction": "Use base-locale metadata to understand product meaning, feature scope, and compliance constraints. Redesign title, subtitle, keywords, promotional text, and description for this locale's search intent."
  },
  "research": {
    "search_terms": [
      "持ち物リスト",
      "パッキングリスト",
      "旅行準備",
      "旅行チェックリスト",
      "出張 持ち物",
      "子連れ旅行 持ち物",
      "出張",
      "子連れ旅行",
      "忘れ物防止",
      "Packed",
      "旅行の持ち物リスト"
    ],
    "provider_results": [
      {
        "provider": "static",
        "locale": "ja",
        "country": "jp",
        "keyword_candidates": [
          {
            "term": "持ち物リスト",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "パッキングリスト",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "旅行準備",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "旅行チェックリスト",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "出張 持ち物",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "子連れ旅行 持ち物",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "持ち物リスト",
            "priority": 1,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "パッキングリスト",
            "priority": 1,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "旅行準備",
            "priority": 2,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "旅行チェックリスト",
            "priority": 2,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "出張",
            "priority": 3,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "子連れ旅行",
            "priority": 3,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "忘れ物防止",
            "priority": 4,
            "source": "aso-source",
            "note": ""
          }
        ],
        "competitors": [
          {
            "name": "PackPoint",
            "source": "aso-source"
          },
          {
            "name": "Packr",
            "source": "aso-source"
          }
        ],
        "search_results": [],
        "warnings": []
      }
    ],
    "search_results": []
  },
  "scored_keyword_candidates": [
    {
      "term": "出張",
      "score": 0.715,
      "components": {
        "search_intent_fit": 1.0,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.9,
        "conversion_fit": 0.35,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "aso-source",
      "priority": 3,
      "note": ""
    },
    {
      "term": "子連れ旅行",
      "score": 0.715,
      "components": {
        "search_intent_fit": 1.0,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.9,
        "conversion_fit": 0.35,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "aso-source",
      "priority": 3,
      "note": ""
    },
    {
      "term": "持ち物リスト",
      "score": 0.715,
      "components": {
        "search_intent_fit": 1.0,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.9,
        "conversion_fit": 0.35,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "忘れ物防止",
      "score": 0.516,
      "components": {
        "search_intent_fit": 0.35,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.35,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "aso-source",
      "priority": 4,
      "note": ""
    },
    {
      "term": "パッキングリスト",
      "score": 0.516,
      "components": {
        "search_intent_fit": 0.35,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.35,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "出張 持ち物",
      "score": 0.516,
      "components": {
        "search_intent_fit": 0.35,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.35,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "旅行準備",
      "score": 0.516,
      "components": {
        "search_intent_fit": 0.35,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.35,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "子連れ旅行 持ち物",
      "score": 0.5049,
      "components": {
        "search_intent_fit": 0.35,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.35,
        "character_efficiency": 0.8889,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "旅行チェックリスト",
      "score": 0.5049,
      "components": {
        "search_intent_fit": 0.35,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.35,
        "character_efficiency": 0.8889,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    }
  ],
  "competitor_summary": [
    {
      "name": "PackPoint",
      "source": "aso-source"
    },
    {
      "name": "Packr",
      "source": "aso-source"
    }
  ],
  "validation_rules": {
    "limits": {
      "name": 30,
      "subtitle": 30,
      "keywords": 100,
      "promotional_text": 170,
      "description": 4000,
      "release_notes": 4000
    },
    "required_fields": [
      "name",
      "description",
      "keywords"
    ],
    "single_line_fields": [
      "name",
      "subtitle",
      "keywords",
      "promotional_text"
    ],
    "keywords_target_min": 70,
    "keywords_target_min_by_locale": {
      "ja": 40,
      "ko": 40,
      "zh-Hans": 40,
      "zh-Hant": 40
    },
    "notes": [
      "Generated proposals must be passed through aso_core.validate_locale.",
      "fastlane/metadata writes are handled only by generate_metadata.py --write."
    ]
  }
}
```

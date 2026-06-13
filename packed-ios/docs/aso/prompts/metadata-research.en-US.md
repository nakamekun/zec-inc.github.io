# ASO Metadata Research Prompt

Use the following structured JSON as the only source of truth. The final proposal will be checked by the local ASO validator before use.

```json
{
  "task": "Create locale-specific App Store ASO metadata alternatives from research.",
  "locale": "en-US",
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
    "subtitle": "Packing checklist",
    "keywords": "",
    "promotional_text": "Build reusable packing lists for trips and check off what is ready before you leave.",
    "description": "Packed helps you prepare for trips with a simple packing checklist.\n\nCreate a list, check off what is ready, and reuse your packing plan for future travel.\nIt is designed for lightweight travel preparation without accounts or complex planning.",
    "release_notes": "Initial release."
  },
  "base_locale_reference_policy": {
    "translation_first": false,
    "instruction": "Use base-locale metadata to understand product meaning, feature scope, and compliance constraints. Redesign title, subtitle, keywords, promotional text, and description for this locale's search intent."
  },
  "research": {
    "search_terms": [
      "packing list",
      "travel checklist",
      "trip planner",
      "suitcase list",
      "vacation packing",
      "suitcase",
      "vacation",
      "reminder",
      "Packed",
      "Packing",
      "checklist"
    ],
    "provider_results": [
      {
        "provider": "static",
        "locale": "en-US",
        "country": "us",
        "keyword_candidates": [
          {
            "term": "packing list",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "travel checklist",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "trip planner",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "suitcase list",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "vacation packing",
            "priority": 40,
            "source": "locale-seed"
          },
          {
            "term": "packing list",
            "priority": 1,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "travel checklist",
            "priority": 1,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "trip planner",
            "priority": 2,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "suitcase",
            "priority": 3,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "vacation",
            "priority": 3,
            "source": "aso-source",
            "note": ""
          },
          {
            "term": "reminder",
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
      "term": "packing list",
      "score": 0.737,
      "components": {
        "search_intent_fit": 1.0,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 1.0,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "reminder",
      "score": 0.725,
      "components": {
        "search_intent_fit": 1.0,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.9,
        "character_efficiency": 1.0,
        "risk_penalty": 0.0
      },
      "source": "aso-source",
      "priority": 4,
      "note": ""
    },
    {
      "term": "travel checklist",
      "score": 0.712,
      "components": {
        "search_intent_fit": 1.0,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 1.0,
        "character_efficiency": 0.75,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "suitcase list",
      "score": 0.5593,
      "components": {
        "search_intent_fit": 0.5,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.5,
        "character_efficiency": 0.9231,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "trip planner",
      "score": 0.549,
      "components": {
        "search_intent_fit": 0.5,
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
      "term": "vacation packing",
      "score": 0.542,
      "components": {
        "search_intent_fit": 0.5,
        "demand_proxy": 0.45,
        "competition_inverse": 0.8,
        "metadata_fit": 0.55,
        "conversion_fit": 0.5,
        "character_efficiency": 0.75,
        "risk_penalty": 0.0
      },
      "source": "locale-seed",
      "priority": 40,
      "note": ""
    },
    {
      "term": "suitcase",
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
      "priority": 3,
      "note": ""
    },
    {
      "term": "vacation",
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
      "priority": 3,
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

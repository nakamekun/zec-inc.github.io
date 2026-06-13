# ASO Metadata Proposals - packed-ios

- Generated: 2026-06-13T10:04:30+00:00
- Source: `/Users/kt/zec-inc.github.io/packed-ios/docs/aso/aso-source.yaml`
- Providers: static
- fastlane/metadata is not modified by this research command.

## Executive Summary

- **en-US**: recommend Proposal B (Conversion-first) because it balances clear benefit copy with enough keyword coverage. Validator: 0 errors / 0 warnings.
- **ja**: recommend Proposal B (Conversion-first) because it balances clear benefit copy with enough keyword coverage. Validator: 0 errors / 0 warnings.

## Proposal Comparison

| Locale | Proposal | Strategy | Name | Subtitle | Keywords | Errors | Warnings | Role |
|---|---|---|---:|---:|---:|---:|---:|---|
| en-US | A | Search-first | 6/30 | 21/30 | 91/100 | 0 | 0 | Discovery first: covers high-fit category and intent terms. |
| en-US | B | Conversion-first | 6/30 | 17/30 | 100/100 | 0 | 0 | Conversion first: keeps the store page promise clearer. |
| en-US | C | Long-tail / niche | 6/30 | 21/30 | 91/100 | 0 | 0 | Niche first: uses efficient long-tail terms with less direct competition. |
| ja | A | Search-first | 6/30 | 15/30 | 46/100 | 0 | 0 | Discovery first: covers high-fit category and intent terms. |
| ja | B | Conversion-first | 6/30 | 9/30 | 55/100 | 0 | 0 | Conversion first: keeps the store page promise clearer. |
| ja | C | Long-tail / niche | 6/30 | 15/30 | 46/100 | 0 | 0 | Niche first: uses efficient long-tail terms with less direct competition. |

## en-US

### Target User / Search Intent

- plan what to pack before a trip
- reuse a checklist for travel
- avoid forgetting travel essentials
- English-speaking users tend to search for category terms such as "packing list" and "travel checklist". The metadata should cover checklist, packing, trip, and reminder intent without claiming that the app guarantees a perfect trip.

### Candidate Keywords

| Term | Score | Source |
|---|---:|---|
| packing list | 0.7370 | locale-seed |
| reminder | 0.7250 | aso-source |
| travel checklist | 0.7120 | locale-seed |
| suitcase list | 0.5593 | locale-seed |
| trip planner | 0.5490 | locale-seed |
| vacation packing | 0.5420 | locale-seed |
| suitcase | 0.5160 | aso-source |
| vacation | 0.5160 | aso-source |

**Recommendation:** Adopt Proposal B (Conversion-first) as the first human-review candidate. it balances clear benefit copy with enough keyword coverage.

### Competitor-Derived Candidates

- none

### Proposal A: Search-first

**What it is optimizing:** Discovery first: covers high-fit category and intent terms.

| Field | Chars | Limit | Value |
|---|---:|---:|---|
| name | 6 | 30 | Packed |
| subtitle | 21 | 30 | packing list reminder |
| keywords | 91 | 100 | packing list,travel checklist,suitcase list,trip planner,vacation packing,suitcase,vacation |
| promotional_text | 84 | 170 | Build reusable packing lists for trips and check off what is ready before you leave. |

**Description outline**

- Target user and search intent
- Core features
- Use cases
- Compliance-safe wording

**Rationale:** Prioritizes high-fit category and intent keywords for discoverability.

**Why this proposal can win:** It is the best default when the app needs more search surface area.

**Translation risk note:** Base locale proposal; use as product meaning reference, not as a translation source.

**Adopted keywords:** packing list, travel checklist, suitcase list, trip planner, vacation packing, suitcase, vacation

**Excluded keywords**

- reminder: already in name/subtitle

**Expected search intent:** Users searching broad category and use-case terms for this locale.

**Risks**

| Risk | Impact |
|---|---|
| Broader category terms may be more competitive. | May rank slowly without stronger conversion signals. |

**Validator issues**

- none

### Proposal B: Conversion-first

**What it is optimizing:** Conversion first: keeps the store page promise clearer.

| Field | Chars | Limit | Value |
|---|---:|---:|---|
| name | 6 | 30 | Packed |
| subtitle | 17 | 30 | Packing checklist |
| keywords | 100 | 100 | packing list,travel checklist,reminder,suitcase list,vacation packing,trip planner,suitcase,vacation |
| promotional_text | 84 | 170 | Build reusable packing lists for trips and check off what is ready before you leave. |

**Description outline**

- Target user and search intent
- Core features
- Use cases
- Compliance-safe wording

**Rationale:** Keeps clearer benefit language in subtitle and promo copy for product-page conversion.

**Why this proposal can win:** It is useful when screenshots and product-page copy need to convert cautious users.

**Translation risk note:** Base locale proposal; use as product meaning reference, not as a translation source.

**Adopted keywords:** packing list, travel checklist, reminder, suitcase list, vacation packing, trip planner, suitcase, vacation

**Excluded keywords**

- none

**Expected search intent:** Users comparing product-page clarity, benefits, and fit.

**Risks**

| Risk | Impact |
|---|---|
| Conversion-friendly copy may sacrifice some keyword coverage. | May miss some query variants. |

**Validator issues**

- none

### Proposal C: Long-tail / niche

**What it is optimizing:** Niche first: uses efficient long-tail terms with less direct competition.

| Field | Chars | Limit | Value |
|---|---:|---:|---|
| name | 6 | 30 | Packed |
| subtitle | 21 | 30 | packing list reminder |
| keywords | 91 | 100 | packing list,trip planner,suitcase,vacation,suitcase list,travel checklist,vacation packing |
| promotional_text | 84 | 170 | Build reusable packing lists for trips and check off what is ready before you leave. |

**Description outline**

- Target user and search intent
- Core features
- Use cases
- Compliance-safe wording

**Rationale:** Uses efficient and less crowded terms to cover narrower search intent.

**Why this proposal can win:** It is useful when broad category terms are saturated or too generic.

**Translation risk note:** Base locale proposal; use as product meaning reference, not as a translation source.

**Adopted keywords:** packing list, trip planner, suitcase, vacation, suitcase list, travel checklist, vacation packing

**Excluded keywords**

- reminder: already in name/subtitle

**Expected search intent:** Users searching narrower long-tail use cases and specific workflows.

**Risks**

| Risk | Impact |
|---|---|
| Long-tail terms can have lower demand. | May have smaller search volume. |

**Validator issues**

- none

## ja

### Target User / Search Intent

- 旅行前に忘れ物を防ぎたい
- 出張の持ち物を確認したい
- 子連れ旅行の準備をリスト化したい
- 日本語では「持ち物リスト」「旅行準備」「旅行チェックリスト」のように、 旅行前の不安や忘れ物防止の意図で検索されやすい。en-USの直訳ではなく、 出張や子連れ旅行など日本語で自然な検索語をkeywordsで広く拾う。

### Candidate Keywords

| Term | Score | Source |
|---|---:|---|
| 出張 | 0.7150 | aso-source |
| 子連れ旅行 | 0.7150 | aso-source |
| 持ち物リスト | 0.7150 | locale-seed |
| 忘れ物防止 | 0.5160 | aso-source |
| パッキングリスト | 0.5160 | locale-seed |
| 出張 持ち物 | 0.5160 | locale-seed |
| 旅行準備 | 0.5160 | locale-seed |
| 子連れ旅行 持ち物 | 0.5049 | locale-seed |
| 旅行チェックリスト | 0.5049 | locale-seed |

**Recommendation:** Adopt Proposal B (Conversion-first) as the first human-review candidate. it balances clear benefit copy with enough keyword coverage.

### Competitor-Derived Candidates

- none

### Proposal A: Search-first

**What it is optimizing:** Discovery first: covers high-fit category and intent terms.

| Field | Chars | Limit | Value |
|---|---:|---:|---|
| name | 6 | 30 | Packed |
| subtitle | 15 | 30 | 出張・子連れ旅行・持ち物リスト |
| keywords | 46 | 100 | 忘れ物防止,パッキングリスト,出張 持ち物,旅行準備,子連れ旅行 持ち物,旅行チェックリスト |
| promotional_text | 38 | 170 | 旅行や出張の持ち物をリスト化。出発前に準備できたものをすばやく確認できます。 |

**Description outline**

- 対象ユーザーと検索意図
- 主要機能
- 利用シーン
- 禁止表現を避けた安全な説明

**Rationale:** Prioritizes high-fit category and intent keywords for discoverability.

**Why this proposal can win:** It is the best default when the app needs more search surface area.

**Translation risk note:** Review for direct-copy risk in name; this locale should use its own ASO wording where possible.

**Adopted keywords:** 忘れ物防止, パッキングリスト, 出張 持ち物, 旅行準備, 子連れ旅行 持ち物, 旅行チェックリスト

**Excluded keywords**

- 出張: already in name/subtitle
- 子連れ旅行: already in name/subtitle
- 持ち物リスト: already in name/subtitle

**Expected search intent:** このlocaleの主要カテゴリ語と用途語で探すユーザー。

**Risks**

| Risk | Impact |
|---|---|
| Broader category terms may be more competitive. | May rank slowly without stronger conversion signals. |

**Validator issues**

- none

### Proposal B: Conversion-first

**What it is optimizing:** Conversion first: keeps the store page promise clearer.

| Field | Chars | Limit | Value |
|---|---:|---:|---|
| name | 6 | 30 | Packed |
| subtitle | 9 | 30 | 旅行の持ち物リスト |
| keywords | 55 | 100 | 出張,子連れ旅行,忘れ物防止,パッキングリスト,出張 持ち物,旅行準備,子連れ旅行 持ち物,旅行チェックリスト |
| promotional_text | 38 | 170 | 旅行や出張の持ち物をリスト化。出発前に準備できたものをすばやく確認できます。 |

**Description outline**

- 対象ユーザーと検索意図
- 主要機能
- 利用シーン
- 禁止表現を避けた安全な説明

**Rationale:** Keeps clearer benefit language in subtitle and promo copy for product-page conversion.

**Why this proposal can win:** It is useful when screenshots and product-page copy need to convert cautious users.

**Translation risk note:** Review for direct-copy risk in name; this locale should use its own ASO wording where possible.

**Adopted keywords:** 出張, 子連れ旅行, 忘れ物防止, パッキングリスト, 出張 持ち物, 旅行準備, 子連れ旅行 持ち物, 旅行チェックリスト

**Excluded keywords**

- 持ち物リスト: already in name/subtitle

**Expected search intent:** 機能の分かりやすさと自然な説明で比較検討するユーザー。

**Risks**

| Risk | Impact |
|---|---|
| Conversion-friendly copy may sacrifice some keyword coverage. | May miss some query variants. |

**Validator issues**

- none

### Proposal C: Long-tail / niche

**What it is optimizing:** Niche first: uses efficient long-tail terms with less direct competition.

| Field | Chars | Limit | Value |
|---|---:|---:|---|
| name | 6 | 30 | Packed |
| subtitle | 15 | 30 | 出張・子連れ旅行・持ち物リスト |
| keywords | 46 | 100 | 忘れ物防止,パッキングリスト,出張 持ち物,旅行準備,子連れ旅行 持ち物,旅行チェックリスト |
| promotional_text | 38 | 170 | 旅行や出張の持ち物をリスト化。出発前に準備できたものをすばやく確認できます。 |

**Description outline**

- 対象ユーザーと検索意図
- 主要機能
- 利用シーン
- 禁止表現を避けた安全な説明

**Rationale:** Uses efficient and less crowded terms to cover narrower search intent.

**Why this proposal can win:** It is useful when broad category terms are saturated or too generic.

**Translation risk note:** Review for direct-copy risk in name; this locale should use its own ASO wording where possible.

**Adopted keywords:** 忘れ物防止, パッキングリスト, 出張 持ち物, 旅行準備, 子連れ旅行 持ち物, 旅行チェックリスト

**Excluded keywords**

- 出張: already in name/subtitle
- 子連れ旅行: already in name/subtitle
- 持ち物リスト: already in name/subtitle

**Expected search intent:** より具体的な利用シーンやロングテール語で探すユーザー。

**Risks**

| Risk | Impact |
|---|---|
| Long-tail terms can have lower demand. | May have smaller search volume. |

**Validator issues**

- none

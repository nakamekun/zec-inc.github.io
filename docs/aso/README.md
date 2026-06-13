# ASO Pipeline

ZEC Apps共通の言語別ASO生成・検証パイプライン。各アプリの `product-spec.md` を元に、localeごとの検索意図に合わせたApp Store metadata案を生成し、文字数制限・キーワード重複・禁止語を機械チェックしてから `fastlane/metadata/<locale>/` に出力する。

## 構成

```text
scripts/aso/
  research_metadata.py   # 市場調査+提案CLI (fastlaneには書かない)
  research_providers.py  # Static/App Store Search research providers
  keyword_scoring.py     # keyword candidate scoring
  proposal_generator.py  # proposal A/B/C生成とaso_core検証
  prompt_templates.py    # LLM投入用structured prompt生成
  generate_metadata.py   # 生成CLI (デフォルトdry-run)
  validate_metadata.py   # 検証CLI (生成物の再チェック)
  aso_core.py            # 文字数制限・検証ルール・キーワード組み立て
  providers.py           # キーワード調査のproviderインターフェース
  miniyaml.py            # stdlibのみのYAMLサブセットパーサ

docs/aso/aso-source.yaml          # テンプレート (このディレクトリ)
<app>/docs/aso/aso-source.yaml    # 各アプリの入力 (localeごとの調査+原稿)
<app>/docs/aso/research.generated.json          # 調査結果
<app>/docs/aso/keyword-candidates.generated.json # スコア済み候補
<app>/docs/aso/metadata-proposals.md            # Proposal A/B/Cレビュー
<app>/docs/aso/prompts/metadata-research.<locale>.md # LLM用prompt
<app>/docs/aso/aso-source.suggested.yaml        # --write-suggestion時のみ
<app>/docs/aso/metadata.generated.json  # 生成結果 (機械検証の対象)
<app>/docs/aso/metadata-review.md       # レビュー用Markdown (案+警告)
<app>/fastlane/metadata/<locale>/*.txt  # --write 指定時のみ出力
```

## 基本フロー

1. `research_metadata.py` で検索市場調査と proposal を作る。
2. `metadata-proposals.md` で Proposal A/B/C をレビューする。
3. `--write-suggestion` で作った `aso-source.suggested.yaml` を人間が確認し、必要な値だけ `aso-source.yaml` に反映する。
4. `generate_metadata.py --dry-run` で `metadata.generated.json` と `metadata-review.md` を作る。
5. `validate_metadata.py --strict` で最終チェックする。
6. 必要時のみ `generate_metadata.py --write` で `fastlane/metadata` に出力する。

`research_metadata.py` は提案生成までのツールで、`fastlane/metadata` には絶対に書かない。最終的なmetadata品質は既存の `aso_core.validate_locale`、`generate_metadata.py`、`validate_metadata.py` を門番にする。

## Locale-Specific ASO Generation

このpipelineは translation-first ではなく ASO-first で使う。`base_locale` は意味、機能範囲、禁止表現、トーンの参照元にすぎず、他localeの最終成果物を直訳で作らない。

基本方針:

- localeごとの検索意図を優先する。
- `title` / `subtitle` / `keywords` はlocaleごとに再設計する。
- `description` は自然な表現と検索語の両立を重視する。
- `seed_keywords`、App Store候補、static fallback、avoid terms、validatorをlocaleごとに独立して扱う。
- en-US候補をjaへ機械翻訳して流用しない。jaはjaのseed、jaのApp Store検索結果、jaの自然な検索語を優先する。
- `metadata-proposals.md` の Translation risk note で base locale の直コピーになっていないか確認する。

`aso-source.yaml` では、従来の `research.keyword_candidates` に加えて、locale直下に `seed_keywords` と `search_intents` を置ける。

```yaml
locales:
  en-US:
    seed_keywords:
      - packing list
      - travel checklist
    search_intents:
      - plan what to pack before a trip
      - reuse a checklist for travel
    avoid_terms:
      - term: guarantee
        level: warning
  ja:
    seed_keywords:
      - 持ち物リスト
      - パッキングリスト
      - 旅行準備
      - 出張 持ち物
    search_intents:
      - 旅行前に忘れ物を防ぎたい
      - 出張や子連れ旅行の持ち物を確認したい
    avoid_terms:
      - term: 保証
        level: warning
```

## 実行例

Online research。外部APIキーは不要。App Store公開検索が失敗した場合も警告にしてStatic providerだけで続行する。

   ```sh
   python3 scripts/aso/research_metadata.py --app <app> \
     --locale en-US,ja \
     --country us,jp \
     --seed-keywords "water tracker,hydration,水分補給,水分記録" \
     --max-results 20
   ```

Offline research。CIや横展開の初回確認に使う。

   ```sh
   python3 scripts/aso/research_metadata.py --app <app> \
     --locale en-US,ja \
     --country us,jp \
     --seed-keywords "water tracker,hydration,水分補給,水分記録" \
     --offline
   ```

Suggestion生成。`aso-source.yaml` は上書きしない。

   ```sh
   python3 scripts/aso/research_metadata.py --app <app> \
     --locale en-US,ja \
     --country us,jp \
     --seed-keywords "water tracker,hydration,水分補給,水分記録" \
     --write-suggestion
   ```

Dry-run metadata生成。

   ```sh
   python3 scripts/aso/generate_metadata.py \
     --app <app> \
     --source <app>/docs/aso/aso-source.suggested.yaml \
     --locales en-US,ja \
     --dry-run
   ```

Strict validate。

   ```sh
   python3 scripts/aso/validate_metadata.py <app>/docs/aso/metadata.generated.json --strict
   ```

必要時のみ fastlane write。

   ```sh
   python3 scripts/aso/generate_metadata.py --app <app> --write
   ```

## aso-source.yaml 作成

テンプレートを各アプリにコピーする。`aso-source.suggested.yaml` を出した場合も、人間が確認してから必要な値だけ `aso-source.yaml` に反映する。

   ```sh
   mkdir -p <app>/docs/aso
   cp docs/aso/aso-source.yaml <app>/docs/aso/aso-source.yaml
   ```

`product-spec.md` を元に、localeごとに `research`(search_intent、keyword_candidates、competitors)と `metadata` を埋める。単なる翻訳ではなく、各言語の検索語に合わせて書く。LLMに下書きさせてよいが、出力は必ず機械チェックを通す。

## 生成物とcommit方針

| Path | 内容 | Commit方針 |
|---|---|---|
| `<app>/docs/aso/aso-source.yaml` | 人間確認済みのASO入力 | commitする |
| `<app>/docs/aso/research.generated.json` | providerの生調査結果 | 必要な監査・比較時のみcommit可。通常は再生成物 |
| `<app>/docs/aso/keyword-candidates.generated.json` | スコア済みkeyword候補 | 必要な監査・比較時のみcommit可。通常は再生成物 |
| `<app>/docs/aso/metadata-proposals.md` | 人間レビュー用Proposal A/B/C | PRレビューで議論したい場合はcommit可 |
| `<app>/docs/aso/prompts/metadata-research.<locale>.md` | LLM投入用structured prompt | 通常はcommit不要。調査再現性が必要な場合のみcommit可 |
| `<app>/docs/aso/aso-source.suggested.yaml` | `aso-source.yaml` 反映前の提案 | レビュー用としてcommit可。ただし最終入力ではない |
| `<app>/docs/aso/metadata.generated.json` | 既存generateの機械出力 | 従来運用に合わせる |
| `<app>/docs/aso/metadata-review.md` | 既存generateのレビュー出力 | 従来運用に合わせる |
| `<app>/fastlane/metadata/<locale>/*.txt` | App Store提出metadata | `generate_metadata.py --write` 明示時のみ変更 |
| `<app>/.cache/aso/appstore-search/` | App Store検索API cache | commitしない (`.gitignore`) |

Generated reportsをCIやPRで読まない方針がある場合は、`metadata-proposals.md` や `aso-source.suggested.yaml` をcommitせず、`aso-source.yaml` だけをレビュー対象にする。

## 検証ルール

| チェック | レベル |
|---|---|
| name / subtitle 30文字、keywords 100文字、promotional_text 170文字、description / release_notes 4000文字超過 | error |
| name / description / keywords が空 | error |
| 単一行フィールドに改行 | error |
| avoid_terms (level: error) の語が出現 | error |
| avoid_terms (level: warning) の語が出現 | warning |
| keywords内の重複語、name/subtitleとの重複語 | warning |
| keywordsのカンマ前後のスペース、空エントリ | warning |
| keywordsがlocale別target未満(枠の使い残し) | warning |
| localeがbase_localeへフォールバック | warning |
| subtitle / release_notes が空 | warning |

文字数はコードポイント数で数える(日本語・中国語も1文字=1)。CJKキーワードのname/subtitle重複は部分一致、ASCIIは単語一致で判定する。

Keyword targetは `en-US` など英語圏では70文字、`ja` / `ko` / `zh-Hans` / `zh-Hant` では40文字を初期値にしている。CJK localeは短い語で検索意図を表せるため、英語と同じ70文字基準だと `--strict` で不要な警告が出やすい。

## キーワード組み立て

`metadata.keywords` を明示した場合はそのまま使う(検証はかかる)。未指定の場合は `research.keyword_candidates` から組み立てる:

1. `priority` 昇順(同値は記述順)に採用
2. 重複候補、name/subtitleに既に含まれる語は除外(review.mdに理由つきで記録)
3. カンマ区切りで100文字に収まるまで詰める

## Providerインターフェース

キーワード調査は `providers.py` の `KeywordProvider` 経由で取得する。MVPは `StaticSourceProvider`(aso-source.yamlの手動調査を読む)のみ。将来、App Store検索サジェスト・Apple Search Ads・ASC Analyticsをproviderとして追加しても、generate/validate側は変更不要。

調査側は `research_providers.py` の `ResearchProvider` 経由で取得する。v1は次の2つ:

- `StaticResearchProvider`: `aso-source.yaml` の `research.keyword_candidates` / `competitors` とCLI seedを読む。
- `AppStoreSearchProvider`: Apple iTunes Search APIで `country` / `term` / `limit` ごとに公開App Store検索結果を取得し、`.cache/aso/appstore-search/` にJSONキャッシュする。失敗時は警告のみ。

Providerの責務:

- 外部API、CSV、手動データなどprovider固有の入力を読む。
- `keyword_candidates`、`competitors`、`search_results`、`warnings` を正規化して返す。
- 認証・レート制限・ネットワーク失敗をprovider内で扱い、失敗時は例外でpipeline全体を止めず `warnings` に入れる。
- scoring側にはprovider固有レスポンスを渡さず、正規化済みdictだけを渡す。

正規化形式:

```python
{
  "provider": "provider-name",
  "locale": "en-US",
  "country": "us",
  "keyword_candidates": [
    {"term": "hydration", "priority": 50, "source": "provider", "note": "..."}
  ],
  "competitors": [
    {"name": "Competitor", "sellerName": "...", "source": "provider"}
  ],
  "search_results": [
    {
      "query": "hydration",
      "country": "us",
      "trackName": "...",
      "sellerName": "...",
      "description": "...",
      "genres": ["Health & Fitness"],
      "averageUserRating": 4.7,
      "userRatingCount": 1200,
      "price": 0,
      "trackViewUrl": "https://..."
    }
  ],
  "warnings": []
}
```

追加しやすいprovider:

- Apple Search Ads provider: keyword reports、search term reports、bid recommendation、impressions / taps / installs / CPT / CPA。
- App Store Connect Analytics provider: impressions、product page views、downloads、conversion rate、source type、territory。
- Ranking tracker provider: country / locale / keyword ごとの順位推移。
- Competitor metadata provider: 競合のtitle、subtitle、description、価格、カテゴリ、rating。
- Manual CSV provider: 手動調査や外部レポートをCSVから取り込む。

API keyや認証情報を扱うproviderは、キーをrepoに置かない。環境変数、ローカルkeychain、CI secretなどから読み、生成物にもsecretを出さない。認証失敗時は警告にしてStatic providerだけで続行できるようにする。

将来拡張メモ:

- Apple Ads Provider: keyword reports、search term reports、bid recommendation、impressions / taps / installs / CPT / CPA を正規化して `ResearchProvider` に接続する。
- App Store Connect Analytics Provider: impressions、product page views、downloads、conversion rate、source type、territory をlocale/country軸で取り込む。
- Ranking tracker: country / locale / keyword ごとの順位推移を日次JSONLなどで保存し、`demand_proxy` と `competition_inverse` の補助シグナルにする。
- Metadata experiment log: metadata変更日、version/build、keywords、変更理由、変更後のCTR/CVR/DL推移を保存し、次回proposalの学習材料にする。

## Locale別注意点

- `en-US` は単語境界で重複判定する。`water` と `water tracker` は意図が重なることがあるため、人間が最終確認する。
- `ja` / `ko` / `zh-Hans` / `zh-Hant` は部分一致で重複判定する。短い語の組み合わせで十分な場合があるため、keyword targetは低め。
- App Store検索結果には競合アプリ名、ブランド語、汎用語が混ざる。scoringは低価値語をある程度落とすが、出力は正解ではなく候補。
- 医療・金融・安全系アプリでは、効果保証、診断、治療、投資成果、安全保証、ランキング主張を避ける。`avoid_terms` にapp固有の禁止語を追加する。
- App Store公開検索は時点、country、Apple側のランキングに依存する。調査結果は再現性のある真実ではなく、その時点の判断材料として扱う。

## 依存

Python 3.10+ のstdlibのみ。PyYAML等の外部パッケージ・外部APIは不要(`miniyaml.py` がテンプレートのYAMLサブセットを読む)。

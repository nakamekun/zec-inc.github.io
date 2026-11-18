## SITE-WHY-1: アプリ詳細ページに「なぜ要るか・比較・向いている人」と地域の言語を足す

目的: 検索と AI の回答で選ばれるよう、アプリ詳細ページを「機能の紹介」から「なぜこのアプリが要るか・ほかの手段と比べてどうか」まで答えるページにする。ダウンロードのある地域の言語(まず es・de・fr)のページを足す。2026-11-18 ユーザー決定。試作は OCR Copy(6780724192)・Foot Size Check(6789844290)・Blur Before Share(6789844137)の3本。

背景:
- 生成は `scripts/update_apps_page.py`。手書き内容は `data/app-details-overrides.json`(App Store の app id がキー)。en と `locales.ja` は手書き、zh-hans/zh-hant/ko は App Store の現地語説明から自動生成(LIGHT_LOCALES)。
- 詳細ページには SoftwareApplication と FAQPage の JSON-LD がある。
- 週次の GitHub Actions(`.github/workflows/update-apps-page.yml`)が `--strict` で再生成・検証してコミットする。

推奨モデル: gpt-6-astra / high

作業内容:
1. overrides に任意のフィールドを足す(en とロケール両方で使える):
   - `why`: 段落の配列。困りごと → それを解くのにこのアプリが要る理由。最初の1文で答えを言い切る形を想定。
   - `comparison`: `{ "intro": str, "checked_on": "YYYY-MM-DD", "rows": [ { "option": str, "kind": "built-in"|"app"|"web"|"manual", "good_at": str, "trade_off": str } ], "summary": str }`。
   - `best_for`: 文字列の配列(向いている人)。`not_for`: 文字列の配列(向いていない人と、その人に合う別の手段)。
   - 検証(`validate` 系と `ctx.warn`)に型チェックを足す。無い場合は今まで通り表示しない。
2. 詳細ページに表示する。順番: ヒーロー → スクショ → **なぜ要るか** → 機能 → 使い方 → **比較**(表。スマホ幅では行ごとのカードに崩す。横スクロールにしない) → **向いている人／向いていない人** → 料金 → プライバシー → FAQ。見出しは UI_STRINGS に全ロケール分。比較の下に「◯年◯月◯日時点の情報」を小さく出す(checked_on)。
3. 新しい手書きロケールを足す: `es`・`de`・`fr`。ja と同じく `locales.<code>` に手書き内容があるアプリだけページを作る(URL `/apps/<slug>/<code>/`)。hreflang・sitemap・言語切り替え・カテゴリ/一覧ページ(内容のあるアプリだけ並べる)・App Store リンクの国(es→`/es/`、de→`/de/`、fr→`/fr/`)・UI_STRINGS・CATEGORY_DEFINITIONS を対応する。LIGHT_LOCALES の仕組みはそのまま。
4. llms.txt: `why` があるアプリは、要約の後ろに `why` の1文目を足す(長さは今の切り詰め規則に合わせる)。
5. README の「Localization」節に、新しいフィールドとロケールの足し方を追記。

触ってはいけないもの:
- `data/app-details-overrides.json` の既存の文章(新フィールドの中身は別の作業で入れる。テスト用の内容は tests 側の fixture に置く)。
- 運営者個人に関する情報を増やさない(`docs/site-improvement-plan.md` の禁止事項: 個人名・詳細住所・電話・個人アカウントの外部サービス・Organization の JSON-LD)。
- privacy.html・support.html・トップページの手書き部分(マーカー外)。

受け入れ条件:
- 新フィールドを入れた fixture で、なぜ要るか・比較・向いている人の3節が en/ja/es で出る。入れていないアプリのページは今と同じ(差分が出ない)。
- 比較の表がスマホ幅(375px)でカードになり、横スクロールが出ない。
- es/de/fr は内容のあるアプリだけページができ、hreflang と sitemap に入る。内容のないアプリには作られない。
- `python3 scripts/update_apps_page.py --strict` とバリデータが通る(既存のテストも)。ネットワークが使えない場合は、キャッシュ(`data/app-store-lookup-cache*.json`)で回せる方法を使い、その旨を報告。
- git commit / push はしない。

テスト方法:
- 既存のテスト(`scripts/` か `tests/` にあるもの)を実行。fixture で生成した HTML を確認する小さなテストを追加。

スコープ外の扱い:
- 範囲外は実装せず、報告に「スコープ外の提案」として書く。

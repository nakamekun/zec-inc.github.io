# zec-inc.jp 多言語化計画(調査メモ・実装は未着手)

作成: 2026-10-20 / 対象: `~/zec-inc.github.io`(GitHub Pages・public)

現状は **en(正本)+ ja** の 2 言語。ストアの対応言語は最大 25 ロケールなので、HP だけ言語が狭い。この文書は「どの言語をどの順で、どう翻訳を用意し、何が壊れうるか」の調査結果と最小着手案。実装はしない。

## 0. 前提(ロープロファイル運用)

`docs/site-improvement-plan.md` の運用方針を守る。多言語化でも次は足さない: 代表者名・番地・電話、個人アカウント連携サービス(Google フォーム等の新設、Naver/Baidu 等のウェブマスター登録で個人アカウントを使うもの)、Organization 単独の JSON-LD、ニュース/プレス欄。翻訳ページにも会社名 `合同会社ゼク / ZEC Inc.` と `info@zec-inc.jp` 以外の連絡先情報は載せない。

## 1. 現状の事実(2026-10-20 時点の Apple Lookup と fastlane)

### 1.1 アプリの対応言語の分布(公開 33 本・Lookup `languageCodesISO2A`)

| 対応言語数 | アプリ数 | 中身 |
|---|---|---|
| 23〜24(ストア 25 ロケール) | 11 | Foot Size Check, Big Text Note, Laundry Tap, OCR Copy, DailyAlbum, UndoCam, Mute Video, ExifOff, GohanSnap, Caffeine, Blur Before Share |
| 8〜12 | 5 | Number Forge(12), Study Buddy(11), DoneToday(10), PinLog(10), CleanURL Tap(8) |
| 2(en+ja のみ) | 15 | BaroNote, Today Ready, PillTap, PoopTap, Sheep to Sleep, WaterDone, Packed, Moodwash, AssetCurve, Silly Word Beat, 年齢プロフィール, Access Lens, Korean Travel Phrase Card, Animal Face Hide, ClipMD |
| 1 | 2 | Body Rhythm Log(en), Hong Kong Phrase Card(ja) |

言語別のアプリ数(Lookup は zh-Hans/zh-Hant を ZH 1 つに畳む): EN 32 / JA 32 / **ZH 16 / KO 16 / DE 16 / FR 16 / ES 16** / IT・PT 15 / NL 13 / その他(CS DA FI ID NB PL RU SV TH TR UK VI)11 / AR 4。
つまり **ZH と KO は「ほぼ全言語対応の 16 本」が揃っている言語**で、これ以上の優先度根拠は en/ja の次に強い。逆に en+ja のみの 15 本は、どの言語でもストア側に訳文がない。

### 1.2 Apple Lookup は言語別ストアの訳文を返す(実測)

`https://itunes.apple.com/lookup?id=1889726396&entity=software&country=<cc>&lang=<ll_CC>&limit=200` を `cn/zh_cn`・`tw/zh_tw`・`kr/ko_kr`・`de/de_de` で実測した。いずれも 33 本を返し、そのうち **20 本は `trackName` と `description` が US 版と異なる(現地語)**。残り 13 本(en+ja のみのアプリ)は US の英語のまま返る。

例: Big Text Note → cn「大字备忘」/ tw「大字備忘」/ kr「큰 글자 메모」、UndoCam → cn「视频倒放 - UndoCam」/ tw「影片倒放」/ kr「동영상 거꾸로 재생」、Mute Video → cn「视频消音后分享」/ tw「影片消音後分享」/ kr「동영상 음소거 후 공유」。`trackViewUrl` も各ストアフロント(`apps.apple.com/cn/...`)になる。

→ **名前・説明文・ストアへのリンクは API だけで多言語化できる**(新しい取得元も個人アカウントも不要)。取れないのは、HP 独自の構造化文章(特徴リスト・使い方・FAQ・プライバシー注記・価格注記)。

### 1.3 ASC メタデータ(fastlane)

25 ロケール分の `name / subtitle / keywords / description / promotional_text / release_notes` が `apps/<app>-ios/fastlane/metadata/<locale>/` にある(例: foot-size-check-ios に ar-SA cs da de-DE en-US es-ES es-MX fi fr-FR id it ja ko nl-NL no pl pt-BR ru sv th tr uk vi zh-Hans zh-Hant)。zh-Hans/zh-Hant/ko にも subtitle・keywords がある。Lookup の description と同じ内容だが、**keywords と subtitle は Lookup に出ない**ので、検索語の整合を取るときはこちらを使う。en+ja のみの 15 本は en-US と ja しかない。

### 1.4 現状のジェネレータ(`scripts/update_apps_page.py`)の拡張点

- `locales.<code>`(overrides)+ `UI_STRINGS[code]` + `CATEGORY_DEFINITIONS[...][code]` を足すと、詳細/一覧/カテゴリ/hreflang/sitemap が自動派生する(README の「Localization (ja)」)。
- ページは `app_locales()`(アプリごとに `locales.<code>` がある言語)で出し分けるため、**一部のアプリだけ翻訳する段階導入は設計上できる**。
- ただし未対応が 3 点ある(実装時に要対応):
  1. `render_locale_apps_index` / `render_app_mini_card` は全アプリを新言語のカードにして `/apps/<slug>/<locale>/` へリンクする。訳文のないアプリは **404 リンクになる**。訳文のないアプリは en ページ(または en のカード)へフォールバックさせる必要がある。
  2. `APP_STORE_STOREFRONTS = {"ja": "jp"}` のみ。`zh-Hans→cn`、`zh-Hant→tw`、`ko→kr` を足す。
  3. `fetch_lookup_payload` は `country=us` の 1 回だけ。言語別 Lookup を取り、`data/app-store-lookup-cache-<locale>.json` のようにロケール別キャッシュを持たせる(失敗時に既存キャッシュを使う現行の流儀を踏襲)。

## 2. 言語の優先順

| 順 | 言語 | 根拠 |
|---|---|---|
| 1 | **zh-Hans(簡体字)** | 依頼者が中国需要を強く期待。16 本が ZH 対応・20 本に cn の訳文あり。ストアの中華圏需要は大きく、App Store 側では既に cn/tw で現地語名(例: 视频倒放)が出ている。 |
| 2 | **ko(韓国語)** | 16 本が KO 対応。Korean Travel Phrase Card の存在と合わせ、韓国向けの発見性を HP 側でも補える。 |
| 3 | **zh-Hant(繁体字)** | 台湾・香港。訳文は zh-Hans とは独立に ASC に存在(例: 影片倒放)。香港は Hong Kong Phrase Card もある。zh-Hans の字面変換では品質が出ない(語彙差: 视频/影片、消音/静音)ため別訳。 |
| 4 | de / fr / es / pt-BR / it | 16 本前後が対応。需要は大きいがスコープが増えるので、2〜3 の結果(Search Console のインプレッション)を見てから。 |
| 5 | その他(nl, id, th, vi, tr 等) | 後回し。Lookup 訳文があるうちは流用可能。 |

zh-Hans を 1 位にする際の留意(調査上の推測を含む): HP は GitHub Pages(`zec-inc.jp` 独自ドメイン)。中国本土からの到達性・Baidu のインデックスは保証されず(Baidu は ICP 届出済みサイトを優遇する、とされる)、**HP の中国向け SEO 効果は限定的**と見るのが無難。中国のユーザーは主に App Store 検索で見つけるので、HP の役割は「Google/Bing 経由の中華圏(台湾・香港・海外華人)」と「リンク先として信頼を補う」ことが主。この点を期待値として共有しておく。Baidu/Naver のウェブマスター登録は個人アカウントが要るので、ロープロファイル方針により行わない(Google/Bing は `robots.txt` の Sitemap 通知で足りる)。

## 3. 翻訳をどう用意するか

層を 3 つに分ける。

| 層 | 例 | 用意の仕方 | 保守 |
|---|---|---|---|
| A. API で自動 | アプリ名、App Store 説明文(段落)、ストア URL、アイコン、更新日 | Lookup を `country/lang` 付きで取得 | **自動**。週次 Action で追従 |
| B. ASC メタデータから流用 | サブタイトル相当の 1 行説明(短い tagline)、`name` | fastlane の subtitle/name を人が転記し overrides に置く | 版ごとにずれうる。更新が少ない項目なので許容 |
| C. 新規翻訳が必要 | 特徴リスト、使い方、FAQ、プライバシー注記、価格注記、カテゴリ説明、UI 見出し(`UI_STRINGS`) | 日本語/英語から AI 翻訳→日本語ネイティブでなく**言語ネイティブ確認が必要** | 英語正本の変更に追従しないと古くなる |

### 3.1 推奨: 「A+B 中心の軽量ページ」から始める

- 新言語ページは **ストア説明文(A)を overview に使い、特徴/FAQ(C)は持たない**簡易ページにする。現行の `short_description` の取得元にも Lookup の description を使える(ジェネレータの既定動作: override が無い場合は `paragraphs_from_description`)。
- これなら 20 本(訳文のあるアプリ)は **翻訳作業ほぼゼロ**でページが出せ、週次更新で自動追従する。FAQ の JSON-LD は出さない(日本語/英語の FAQ を黙って流用しない)。
- ページ下部のプライバシー/価格は短い共通文言を `UI_STRINGS` に 1 本だけ持たせる(「価格・アプリ内課金の詳細は App Store をご確認ください。入力した記録は原則として端末内に保存されます」程度)。アプリ別の断定(「広告なし」等)は、ストア説明文に書かれているものだけ表示する(= 根拠は A に限る)。
- 品質ゲート: 機械翻訳を HP の C 層に直接入れない。入れるなら `docs/ai-rules` の「現地語は確認してから」を適用し、`blog-fact-gate` 相当の断定チェック(価格・機能・プライバシー)を通す。

### 3.2 追加翻訳が要るもの(C 層)の見積もり

アプリ 1 本あたり overrides の en テキストは約 3,000〜4,000 字(overview 3 + 対象 4 + 特徴 6 + 使い方 5 + 価格 + プライバシー + FAQ 6〜10)。3 言語×20 本をフル翻訳すると約 20 万字規模で、**英語正本が変わるたびの追従**も要る。割に合わないので、C 層は「主要 5 本×3 言語」を上限にして、それ以外は 3.1 の軽量ページにとどめる。

### 3.3 保守コストと週次自動更新との整合

- 週次 Action(`update-apps-page.yml`)は `update_apps_page.py` を回し、変更があれば生成物だけコミットする。A 層は自動追従、B/C 層は overrides の手編集なので **陳腐化しうる**。
- 対策案: 各 `locales.<code>` に `source_version`(翻訳時点の英語正本のハッシュまたはアプリ version)を持たせ、週次で「英語正本が変わったが翻訳が古い」ページを Action ログと issue に出す(自動で書き換えない)。
- ストア説明文が大きく変わると(2026-10 は 25 言語化・サブスク化で多数)、A 層は自動で正しくなる。**A 層優先にするほど「HP とストアのずれ」事故は構造的に減る**(今回の監査で見つかった誤りは、ほとんどが overrides の手書き部分だった)。
- ロケール別 Lookup は言語ごとに +1 リクエスト(計 +3)。Apple 側のレート制限を受けることがあるので、リトライとキャッシュ継続(失敗時に前回キャッシュを使う)を入れる。

## 4. hreflang・sitemap・llms.txt への影響

### hreflang
- 現状: en / ja / x-default(= en)。新言語は `hreflang="zh-Hans"`・`"zh-Hant"`・`"ko"`(Google は zh-Hans/zh-Hant スクリプト表記をサポート)。地域コードは付けない(`zh-CN` 等は避ける)。
- **全言語が相互に alternate を持つ必要がある**(en ページにも zh-Hans を足す)。訳文が無いアプリは、そのアプリのページでは新言語の alternate を出さない(`app_locales()` が既にそうなっている)。一覧・カテゴリは alternates を全言語に出す。
- ディレクトリ: `/apps/<slug>/zh-hans/` のように **小文字**にするか、`/zh-Hans/` の大文字を許すかを決める(ジェネレータはロケールコードをそのままディレクトリ名にする。大文字は URL の重複リスクがあるので小文字推奨。`locales.zh-hans` のように小文字コードで持ち、`<html lang>`/hreflang 側だけ `zh-Hans` に変換する小変更が要る)。
- `<html lang>`・`og:locale`(現状未出力。多言語化と同時に `og:locale` と `og:locale:alternate` を足すのが望ましい)。

### sitemap.xml
- 現状 82 URL。3 言語を全 33 本+6 カテゴリ+一覧で出すと +120 URL ほど(約 200)。最小案(3 章)なら +40 程度。
- 現在は各 URL に `lastmod` がある。今回の監査で「毎回全 URL が当日付になる」問題を直した(ページ内容が変わった URL のみ更新)ので、URL が増えても週次の差分は小さいままになる。
- 任意: `xhtml:link rel="alternate"` を sitemap にも出す。hreflang は HTML 側で足りているので不要。

### llms.txt
- 現在は en の正本リンクのみ。言語別一覧(`/apps/ja/` `/apps/zh-hans/` `/apps/zh-hant/` `/apps/ko/`)を 1 行ずつ「Localized app indexes」として足す。アプリ別リンクの言語展開は不要(1 アプリ × 言語数で行が爆発するため)。

### その他
- 内部リンク: 言語切替(`language_links`)は今の `language_names` に新言語の自称(`简体中文`・`繁體中文`・`한국어`)を足す。
- カテゴリ説明(6 本×言語)と `UI_STRINGS`(約 25 キー)の訳が最小限必要。
- `support.html` / `privacy.html` は日英併記が基本。今回、サポートには中国語(簡/繁)・韓国語の短い案内を足した(2 章参照)。プライバシーポリシー全文の翻訳は法務的な意味を持つので、**当面は日英のまま**とし、新言語ページからは日本語/英語版へリンクする。

## 5. 検索面(SEO)の観点

- 言語別の検索語は、各アプリの ASC `keywords.txt` / `subtitle.txt`(zh-Hans / zh-Hant / ko)が一次情報。例: 動画の音消し系は cn「视频消音」、tw「影片消音/影片靜音」、kr「동영상 음소거」と語が割れる。ストアが現地語名で出している語を、HP のタイトル・H1・meta description の先頭に自然に入れる(A 層をそのまま使えば一致する)。
- 詰め込みはしない。ストア説明文は読みやすく書かれているので、先頭 1〜2 文を meta description に使い、155 字(CJK は約 70〜80 字)に収める。
- `<title>` は「現地語名 | ZEC Apps」。名前だけで用途語を含むアプリ(視频倒放 など)は十分。
- 構造化データ: `SoftwareApplication` の `inLanguage`・`offers.url`(各ストアフロント)は既に言語別に出る。`FAQPage` は訳文のある FAQ がある場合だけ出す。
- Search Console は個人 Google アカウントに紐づくため、ロープロファイル方針上は見送り。効果測定は App Store Connect の「ウェブ参照元(ページ表示の参照元)」で足りる。

## 6. 最小着手案

**フェーズ 1(1〜2 日): zh-Hans・zh-Hant・ko の 3 言語を、軽量ページ(A+B 層)で出す**

1. ジェネレータの 3 点修正(1.4 の 1〜3)+ `UI_STRINGS` 3 言語 + カテゴリ説明 3 言語 + `language_names`。
2. 対象アプリは **20 本のうち、3 言語とも Lookup の訳文がある 11 本(25 ロケール対応のアプリ)** から開始する: Foot Size Check, Big Text Note, Laundry Tap, OCR Copy, DailyAlbum, UndoCam, Mute Video Before Share, ExifOff, GohanSnap, Caffeine Tap, Blur Before Share。残り(8〜12 言語のアプリ)は ZH/KO の有無を見て第 2 段階。
3. ページの中身: 現地語名 / 説明文(Lookup description の段落)/ アイコン / スクショ / App Store(各ストアフロント)/ 共通の価格・プライバシー注記。特徴/FAQ(C 層)は出さない。
4. 一覧ページ `/apps/zh-hans/` `/apps/zh-hant/` `/apps/ko/` は **訳文のあるアプリだけ**並べる(1.4-1 のフォールバック対応が前提)。カテゴリページは作らない(en/ja のみ)。
5. hreflang・sitemap・llms.txt の更新(上記 4 章)。`validate_apps_pages.py` が locale ごとの検証を持つか要確認(現状は ja 前提の可能性)。

**フェーズ 2(様子見後)**: 検索流入(Bing Webmaster 等、個人アカウント不要な範囲)と App Store Connect の参照元を 4〜8 週見て、効果があれば主要 5 本に C 層(特徴/FAQ)を足す。de/fr/es は同じ仕組みで A 層だけ追加できる(ジェネレータの追加作業はほぼゼロ)。

**やらないこと**: 15 本の en+ja のみのアプリの新言語ページ(訳文がなく、機械翻訳で断定を作ることになる)/ プライバシーポリシー全文の翻訳 / 個人アカウント連携のウェブマスターツール。

## 7. 未確認点

- 中国本土からの GitHub Pages(独自ドメイン)の到達性・Baidu のインデックス状況(実測していない。一般論)。
- cn ストアでの各アプリの配信可否(Lookup はリンクを返すが、実際に購入可能かは ASC の提供地域設定で未確認)。
- Lookup 訳文の更新タイミング(ASC 反映から数時間〜数日のずれがありうる)。
- `validate_apps_pages.py` の新言語対応可否。
- zh-Hans/zh-Hant の語彙(ストアの訳文自体の品質)は人手確認していない。

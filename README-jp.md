# docx-redline

> このドキュメントが正本（日本語）です。英語版は [README.md](README.md)。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/y-marui/python-docx-redline/actions/workflows/ci.yml/badge.svg)](https://github.com/y-marui/python-docx-redline/actions/workflows/ci.yml)
[![Charter Check](https://github.com/y-marui/python-docx-redline/actions/workflows/dev-charter-check.yml/badge.svg)](https://github.com/y-marui/python-docx-redline/actions/workflows/dev-charter-check.yml)

Word (`.docx`) 文書を、その場でスクリプトを書かずに安全な最小差分の変更履歴（Track Changes）として編集するコマンドラインツール。

もともとは校閲（proofreading）作業のたびに `lxml` で OOXML を直接いじる使い捨てPythonスクリプトを書いていたのを、恒久的なCLIコマンド一式に置き換えたもの。すべての編集は：

- 元ファイルを変更しない（`--out` に別ファイルとして書き出す）
- 実際のWord変更履歴（`w:ins` / `w:del`）として記録される（後から通常のWordで承諾・却下できる）
- run（書式の最小単位）境界をまたぐ場合でも、書式・フィールド・ブックマークなどの周辺構造を壊さない
- 対象箇所が一意に定まらない場合は、黙って実行せずエラーで止まる

## Setup

```sh
git clone https://github.com/y-marui/python-docx-redline.git
cd python-docx-redline
make install
```

一度ビルドしてインストールすれば、他のプロジェクトから `uv tool install --from git+https://github.com/y-marui/python-docx-redline docx-redline` として単体コマンドを導入できる。

Shell completionを有効にするには `docx-redline --install-completion` を実行する（現在のシェル用のcompletionを検出・有効化する）。completionスクリプトの内容を確認したい場合は `docx-redline --show-completion` を使う。

## Commands

| コマンド | 用途 |
|---|---|
| `inspect` | 段落ごとに style・改ページ・ins/del件数・変更履歴付きテキストをダンプする |
| `list-comments` | 既存のWordコメントを一覧する（id・著者・日時・本文） |
| `replace` | 文字列を最小差分の変更履歴（del+ins）として置換する |
| `replace-batch` | JSON配列で与えた置換の並びを順番に適用する（旧・使い捨てスクリプトの置き換え） |
| `replace-paragraph` | 段落全体を変更履歴として置換する |
| `insert-paragraph` | 指定段落の直後に新しい段落を変更履歴として挿入する |
| `add-comment` | 段落にWordコメントを付与する（`comments.xml` の配管も自動生成） |
| `strip-comments` | すべてのコメントとその参照を削除する |
| `strip-format-revisions` | 書式のみの変更履歴（`w:pPrChange`）を除去し、差分を見やすくする |
| `accept-revisions` | 既存の変更履歴をすべて承諾した別ファイルを作る |
| `enable-tracking` | Track Changes を有効化する |
| `validate` | 納品前の安全確認（後述） |
| `verify-word` | Microsoft Word（macOS限定）でレイアウト・ページ割りを検証し、フォントを監査する |
| `export-pdf` | Microsoft Word（macOS限定）経由で `.docx` を PDF に変換する |

### `replace`: exactly one match by default

```sh
docx-redline replace draft.docx "旧い表現" "新しい表現" --out draft-fix1.docx --author "Review Agent"
```

一致が複数ある場合はエラーで止まる。誤った箇所を書き換える事故を防ぐための既定動作。意図して複数ある場合は `--occurrence N`（N番目だけ）か `--all`（全件）を指定する。`--paragraph-contains TEXT` で探索範囲を特定の段落に絞ることもできる。

### `replace-batch`: apply a sequence of edits in one pass

```json
[
  { "old": "そんな中で", "new": "このような状況下で" },
  { "old": "研究が多くなされてきた", "new": "研究が多く行われてきた" }
]
```

```sh
docx-redline replace-batch draft.docx --pairs pairs.json --out draft-fix1.docx --author "Review Agent"
```

`all` / `occurrence` / `bold` / `paragraph_contains` を各要素に指定することもできる（`replace` の同名オプションと同じ意味）。

### `accept-revisions`: create a review copy with existing revisions accepted

```sh
docx-redline accept-revisions draft.docx --out draft-accepted.docx
```

元ファイルを変更せず、本文・ヘッダー・フッター・脚注などの WordprocessingML パートに含まれる既存の挿入、削除、移動、および書式変更履歴を承諾する。コメントと無関係なパッケージ部品は保持する。出力には、承諾した変更と削除した空段落の件数を表示する。

### Authorship

変更履歴やコメントを作成するすべてのコマンドは `--author` の指定を必須とする。レビューを実際に行う人物またはコードエージェントの名前を渡すこと。本ツールは汎用的なレビュアー名を自動生成しない。

### `validate`: pre-delivery safety checks

```sh
docx-redline validate draft-fix1.docx --original draft.docx --max-deletion-length 60
```

- zipとして壊れていないか
- Track Changes が有効か
- 変更が実際に入っているか（`--no-require-changes` で無効化可）
- 挿入テキストに目立つ書式（太字・斜体・下線・取り消し線・上付き/下付き文字・文字スタイル）が付いていないか
- コメントの開始・終了・参照アンカーが過不足なく揃っているか
- （`--original` 指定時）本文の段落数が変わっていないか、数値・単位（既定は正規表現 `--number-pattern`）が変化していないか、変更履歴の対象外（未編集）テキストの書式が変わっていないか
- `--contains` / `--not-contains`（複数指定可）で、特定の文言が残っている・消えていることを確認する

いずれか1つでも失敗すれば終了コード1。

### `export-pdf`: convert a `.docx` to PDF via Microsoft Word (macOS only)

```sh
docx-redline export-pdf draft.docx
docx-redline export-pdf draft.docx --output review/draft.pdf
```

入力を読み取り専用でMicrosoft Word経由で開きPDFとして書き出す。入力の `.docx` 自体は変更しない。`--output` を省略した場合、入力と同じ場所に拡張子だけ `.pdf` に置き換えたパスへ出力する。出力先が既に存在する場合はエラーで止まり、上書きしない。

## Usage

```sh
make all    # lint + type + test
```

| Command | Description |
|---|---|
| `make install` | `uv sync` |
| `make lint` | `ruff check .` |
| `make type` | `mypy src` |
| `make test` | `pytest` |
| `make all` | lint + type + test |

## Known limitations (v1)

- 編集対象は `word/document.xml`（本文）のみ。ヘッダー・フッター内の本文置換は未対応（`strip-comments` のコメント除去はヘッダー・フッターも対象）
- 表内の段落も `replace` の対象になるが、表の構造そのもの（行・列の追加削除）は扱わない
- 数式（OMML）・コンテンツコントロール・フィールドをまたぐ置換は非対応。安全に分割できない場合はエラーで止まる

## License

MIT License — see [LICENSE](LICENSE)

## PowerPoint: `pptx-redline`

同じインストールに `pptx-redline` コマンドを同梱しています。PPTX の本文を変更せず、
修正する文言の**文字範囲**にモダンコメントを追加します。Word の変更履歴とは別機能です。
新しい依存関係は不要です。既存の ZIP パート読み書きと `lxml` を再利用します。

```sh
pptx-redline inspect draft.pptx
pptx-redline add-comment draft.pptx --slide 1 --match 'Autum' --text 'Use Autumn.' --author 'Reviewer' --out review.pptx
pptx-redline add-comments-batch draft.pptx --comments comments.json --author 'Reviewer' --out review.pptx
pptx-redline list-comments review.pptx
pptx-redline validate review.pptx --original draft.pptx
```

一括入力の例:

```json
[
  {"slide": 1, "match": "Autum", "text": "Use Autumn."},
  {"slide": 5, "object_id": "9", "text": "Please add the purpose of this study."}
]
```

- 通常は `text` と `match` が必須。`slide`（1始まり）、`shape_id`（文字列）、
  `occurrence`（絞り込み後の一致箇所、1始まり）で対象を指定できます。
- 空のテキストボックスや図に付ける場合は、`inspect` で確認した `object_id` と
  `slide` を指定します。通常の図とスライド直下のテキスト図形に対応します。
- 一意に見つからない文言には追加しません。検索は大文字・小文字や空白も区別します。
  段落境界は JSON の `\r`、手動改行は `\u000b` として指定します。
- スライド全体への指摘は `slide_level: true` と `slide` を明示してください。
  `match` やその他の文字選択条件とは併用できません。
- 保存先は新規ファイルのみ。一括処理が失敗した場合は出力を残しません。
  元のスライド順、本文・ノート・メディア、既存コメントを保存後に比較します。
- 文字範囲はスライド直下の通常のテキスト図形に対応し、run をまたぐ文言、日本語、
  絵文字、改行を扱えます。グループ内の図形、表、数式、SmartArt、画像内の文字、
  ノートは文字範囲アンカーの対象外です。画像内の文字への指摘は、画像そのものに
  `object_id` で付けられます。`inspect` は対応する文字とオブジェクトを JSON で出力します。
- コメント位置は固定座標ではなく、スライド ID・図形 ID・UTF-16 の開始位置と長さを
  保存します。スライド・図形に既存の作成 ID がある場合は、それも参照します。
  対象文言やレイアウトを自動修正する機能ではありません。
- モダンコメントに対応した PowerPoint が必要です。構造検証は PowerPoint 上での
  ハイライト表示を保証しません。古い PowerPoint や他のビューアーの対応は異なります。
  既存の未対応形式のモダンアンカーがある場合も、安全のため追加を停止します。

形式の根拠:
[Microsoft のコメント仕様](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-pptx/161bc2c9-98fc-46b7-852b-ba7ee77e2e54)、
[文字範囲モニカー](https://learn.microsoft.com/en-us/openspecs/office_standards/ms-odrawxml/e719d016-58bb-4656-a3e5-533cd2d50519)。

---
*この文書の英語版は [README.md](README.md)。同じコミットで両方更新すること。*

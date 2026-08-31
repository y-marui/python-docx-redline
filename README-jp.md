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

### `replace`：既定では一致が1件のときだけ実行する

```sh
docx-redline replace draft.docx "旧い表現" "新しい表現" --out draft-fix1.docx
```

一致が複数ある場合はエラーで止まる。誤った箇所を書き換える事故を防ぐための既定動作。意図して複数ある場合は `--occurrence N`（N番目だけ）か `--all`（全件）を指定する。`--paragraph-contains TEXT` で探索範囲を特定の段落に絞ることもできる。

### `replace-batch`：一連の置換をまとめて適用する

```json
[
  { "old": "そんな中で", "new": "このような状況下で" },
  { "old": "研究が多くなされてきた", "new": "研究が多く行われてきた" }
]
```

```sh
docx-redline replace-batch draft.docx --pairs pairs.json --out draft-fix1.docx
```

`all` / `occurrence` / `bold` / `paragraph_contains` を各要素に指定することもできる（`replace` の同名オプションと同じ意味）。

### `accept-revisions`：既存の変更履歴を承諾したレビュー用コピーを作る

```sh
docx-redline accept-revisions draft.docx --out draft-accepted.docx
```

元ファイルを変更せず、本文・ヘッダー・フッター・脚注などの WordprocessingML パートに含まれる既存の挿入、削除、移動、および書式変更履歴を承諾する。コメントと無関係なパッケージ部品は保持する。出力には、承諾した変更と削除した空段落の件数を表示する。

### `validate`：納品前の安全確認

```sh
docx-redline validate draft-fix1.docx --original draft.docx --max-deletion-length 60
```

- zipとして壊れていないか
- Track Changes が有効か
- 変更が実際に入っているか（`--no-require-changes` で無効化可）
- 挿入テキストが意図せず太字になっていないか
- コメントの開始・終了・参照アンカーが過不足なく揃っているか
- （`--original` 指定時）本文の段落数が変わっていないか、数値・単位（既定は正規表現 `--number-pattern`）が変化していないか
- `--contains` / `--not-contains`（複数指定可）で、特定の文言が残っている・消えていることを確認する

いずれか1つでも失敗すれば終了コード1。

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

## 既知の制約（v1）

- 編集対象は `word/document.xml`（本文）のみ。ヘッダー・フッター内の本文置換は未対応（`strip-comments` のコメント除去はヘッダー・フッターも対象）
- 表内の段落も `replace` の対象になるが、表の構造そのもの（行・列の追加削除）は扱わない
- 数式（OMML）・コンテンツコントロール・フィールドをまたぐ置換は非対応。安全に分割できない場合はエラーで止まる

## License

MIT License — see [LICENSE](LICENSE)

---
*この文書の英語版は [README.md](README.md)。同じコミットで両方更新すること。*

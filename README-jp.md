# Python Package Template

> **このファイルは正本（日本語版）です。**
> 英語版（参照）は [README.md](README.md) を参照してください。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/y-marui/python-package-template/actions/workflows/ci.yml/badge.svg)](https://github.com/y-marui/python-package-template/actions/workflows/ci.yml)
[![Charter Check](https://github.com/y-marui/python-package-template/actions/workflows/dev-charter-check.yml/badge.svg)](https://github.com/y-marui/python-package-template/actions/workflows/dev-charter-check.yml)

| 項目 | 内容 |
|---|---|
| 開発対象 | Python パッケージ / アプリケーション |
| 開発環境 | 個人〜小規模チーム（1〜3人） |
| 主言語 | 英語 |
| ライセンス | MIT |
| AI ツール | Claude Code / GitHub Copilot / Gemini CLI |
| 動作環境 | Python ^3.11 |

AI支援開発向けの Python パッケージ/アプリケーションテンプレート。
uv + Claude Code + GitHub Copilot 前提の OSS テンプレート。

## Features

✅ uv による依存管理
✅ ruff による linting / formatting（line-length=88）
✅ mypy による型チェック（strict モード）
✅ pytest によるテスト（unit / integration 分離）
✅ GitHub Actions CI（ruff → mypy → pytest）
✅ Claude Code + GitHub Copilot 向け AI コンテキスト設定済み
✅ pre-commit セキュリティフック設定済み

## Quick Start

```sh
# 1. テンプレートからリポジトリを作成
#    GitHub の "Use this template" ボタンを使用するか、クローンする
git clone https://github.com/[user]/[repo].git my-project
cd my-project

# 2. パッケージ名を変更
mv src/project_name src/your_package_name
# pyproject.toml の name フィールドも更新すること

# 3. プロジェクト用 README をセットアップ（テンプレートの README ファイルと差し替え）
mv README_TEMPLATE-jp.md README-jp.md
mv README_TEMPLATE.md README.md
# プレースホルダを置換：{user}・{repo}・{workflow}・[USERNAME]・[BMC_USERNAME]
# ※ 上記でテンプレートの README ファイルをプロジェクト用に差し替えます

# 4. 依存関係をインストール
make install

# 5. 動作確認
make all
```

## Commands

| コマンド | 内容 |
|---|---|
| `make install` | `uv sync`（依存関係インストール） |
| `make lint` | `ruff check .`（linting） |
| `make type` | `mypy src`（型チェック） |
| `make test` | `pytest`（テスト実行） |
| `make all` | lint + type + test |
| `make update-charter` | dev-charter を最新化（git subtree pull） |

## Project Structure

```
.
├── src/
│   └── project_name/      # パッケージ本体（名前を変更すること）
├── tests/
│   ├── unit/              # 単体テスト
│   └── integration/       # 統合テスト
├── ai/
│   ├── context/           # AI 向け制約要約
│   ├── review/            # AI レビューチェックリスト
│   └── tasks/             # AI タスクプロンプトテンプレート
├── docs/
│   ├── dev-charter/       # 開発憲章（git subtree）
│   ├── architecture.md    # アーキテクチャ設計
│   ├── file-map.md        # ファイルレベル依存マップ
│   ├── specification.md   # 仕様書
│   └── ui-design.md       # UI設計（このテンプレートは該当なし）
├── examples/              # 実装パターンサンプル
├── README_TEMPLATE.md     # プロジェクト用 README 雛形（README.md にリネームして使う）
├── README_TEMPLATE-jp.md  # プロジェクト用 README 雛形（日本語版）
├── AI_CONTEXT.md          # AI ツール向けコンテキスト
├── CONTRIBUTING.md        # 開発フロー・ガイドライン
├── pyproject.toml         # プロジェクト設定
└── Makefile               # 開発コマンド
```

## Documentation

| ドキュメント | 内容 |
|---|---|
| [docs/architecture.md](docs/architecture.md) | アーキテクチャ設計 |
| [docs/file-map.md](docs/file-map.md) | ファイルレベル依存マップ |
| [docs/specification.md](docs/specification.md) | 仕様書 |
| [docs/ui-design.md](docs/ui-design.md) | UI設計 |
| [README_TEMPLATE.md](README_TEMPLATE.md) | プロジェクト用 README 雛形 |
| [AI_CONTEXT.md](AI_CONTEXT.md) | AI ツール向けコンテキスト |
| [CONTRIBUTING.md](CONTRIBUTING.md) | 開発フロー・ガイドライン |

## AI-Assisted Development

`AI_CONTEXT.md` に AI ツール向けコンテキストが設定済みです。

| ツール | 担当 |
|---|---|
| Claude Code | 立ち上げ・大規模変更・アーキテクチャ設計 |
| GitHub Copilot | バグ修正・細かな実装・テスト作成 |
| Gemini CLI | ドキュメント管理・翻訳補助 |

## Customization

1. `src/project_name/` → `src/your_package_name/` にリネーム
2. `pyproject.toml` の `name` フィールドを更新
3. `AI_CONTEXT.md` のプロジェクト概要を更新
4. `LICENSE` の `[YEAR]` と `[AUTHOR]` を置換
5. `README_TEMPLATE-jp.md` → `README-jp.md`、`README_TEMPLATE.md` → `README.md` にリネーム
6. README のプレースホルダを置換：`{user}`・`{repo}`・`{workflow}`・`[USERNAME]`・`[BMC_USERNAME]`
7. `make all` で動作確認

## License

MIT License — [LICENSE](LICENSE) を参照

---
*この文書には英語版 [README.md](README.md) があります。編集時は同一コミットで更新してください。*

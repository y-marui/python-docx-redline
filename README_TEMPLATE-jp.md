# {project-name}

> **このファイルは正本（日本語版）です。**
> 英語版（参照）は [README_TEMPLATE.md](README_TEMPLATE.md) を参照してください。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/{user}/{repo}/actions/workflows/{workflow}.yml/badge.svg)](https://github.com/{user}/{repo}/actions/workflows/{workflow}.yml)
[![Charter Check](https://github.com/{user}/{repo}/actions/workflows/dev-charter-check.yml/badge.svg)](https://github.com/{user}/{repo}/actions/workflows/dev-charter-check.yml)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/[USERNAME]?style=social)](https://github.com/sponsors/[USERNAME])
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-donate-yellow.svg)](https://www.buymeacoffee.com/[BMC_USERNAME])

一行概要：何を・誰のために・どう解決するか。

## Setup

```sh
git clone https://github.com/{user}/{repo}.git
cd {repo}
make install
```

## Usage

```sh
make all    # lint + type + test
```

| コマンド | 内容 |
|---|---|
| `make install` | `uv sync`（依存関係インストール） |
| `make lint` | `ruff check .`（linting） |
| `make type` | `mypy src`（型チェック） |
| `make test` | `pytest`（テスト実行） |
| `make all` | lint + type + test |

## License

MIT License — [LICENSE](LICENSE) を参照

---
*この文書には英語版 [README_TEMPLATE.md](README_TEMPLATE.md) があります。編集時は同一コミットで更新してください。*

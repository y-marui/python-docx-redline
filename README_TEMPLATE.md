# {project-name}

> **This is the reference (English) version.**
> The canonical (Japanese) version is [README_TEMPLATE-jp.md](README_TEMPLATE-jp.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/{user}/{repo}/actions/workflows/{workflow}.yml/badge.svg)](https://github.com/{user}/{repo}/actions/workflows/{workflow}.yml)
[![Charter Check](https://github.com/{user}/{repo}/actions/workflows/dev-charter-check.yml/badge.svg)](https://github.com/{user}/{repo}/actions/workflows/dev-charter-check.yml)
[![GitHub Sponsors](https://img.shields.io/github/sponsors/[USERNAME]?style=social)](https://github.com/sponsors/[USERNAME])
[![Buy Me a Coffee](https://img.shields.io/badge/Buy%20Me%20a%20Coffee-donate-yellow.svg)](https://www.buymeacoffee.com/[BMC_USERNAME])

One-line description: what this does, for whom, and how it solves the problem.

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

| Command | Description |
|---|---|
| `make install` | `uv sync` |
| `make lint` | `ruff check .` |
| `make type` | `mypy src` |
| `make test` | `pytest` |
| `make all` | lint + type + test |

## License

MIT License — see [LICENSE](LICENSE)

---
*This document has a Japanese canonical version [README_TEMPLATE-jp.md](README_TEMPLATE-jp.md). Update both in the same commit when editing.*

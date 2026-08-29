# Python Package Template

> **This is the reference (English) version.**
> The canonical (Japanese) version is [README-jp.md](README-jp.md).

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![CI](https://github.com/y-marui/python-package-template/actions/workflows/ci.yml/badge.svg)](https://github.com/y-marui/python-package-template/actions/workflows/ci.yml)
[![Charter Check](https://github.com/y-marui/python-package-template/actions/workflows/dev-charter-check.yml/badge.svg)](https://github.com/y-marui/python-package-template/actions/workflows/dev-charter-check.yml)

| Field | Value |
|---|---|
| Target | Python package / application |
| Team | Solo to small team (1–3 people) |
| Language | English |
| License | MIT |
| AI Tools | Claude Code / GitHub Copilot / Gemini CLI |
| Runtime | Python ^3.11 |

A Python package/application template for AI-assisted development.
Built on uv + Claude Code + GitHub Copilot.

## Features

✅ Dependency management with uv
✅ Linting and formatting with ruff (line-length=88)
✅ Type checking with mypy (strict mode)
✅ Testing with pytest (unit / integration split)
✅ GitHub Actions CI (ruff → mypy → pytest)
✅ AI context pre-configured for Claude Code + GitHub Copilot
✅ Pre-commit security hooks included

## Quick Start

```sh
# 1. Create a repository from this template
#    Use the "Use this template" button on GitHub, or clone directly
git clone https://github.com/[user]/[repo].git my-project
cd my-project

# 2. Rename the package
mv src/project_name src/your_package_name
# Also update the name field in pyproject.toml

# 3. Set up project README (replaces this template's README files)
mv README_TEMPLATE-jp.md README-jp.md
mv README_TEMPLATE.md README.md
# Then replace placeholders: {user}, {repo}, {workflow}, [USERNAME], [BMC_USERNAME]
# Note: the above replaces the template's README files with your project's README

# 4. Install dependencies
make install

# 5. Verify
make all
```

## Commands

| Command | Description |
|---|---|
| `make install` | `uv sync` |
| `make lint` | `ruff check .` |
| `make type` | `mypy src` |
| `make test` | `pytest` |
| `make all` | lint + type + test |
| `make update-charter` | Update dev-charter via git subtree pull |

## Project Structure

```
.
├── src/
│   └── project_name/      # Package source (rename this)
├── tests/
│   ├── unit/              # Unit tests
│   └── integration/       # Integration tests
├── ai/
│   ├── context/           # AI constraint summaries
│   ├── review/            # AI review checklists
│   └── tasks/             # AI task prompt templates
├── docs/
│   ├── dev-charter/       # Development charter (git subtree)
│   ├── architecture.md    # Architecture design
│   ├── file-map.md        # File-level dependency map
│   ├── specification.md   # Specification
│   └── ui-design.md       # UI design (N/A for this template)
├── examples/              # Implementation pattern samples
├── README_TEMPLATE.md     # Project README template (rename to README.md)
├── README_TEMPLATE-jp.md  # Project README template in Japanese
├── AI_CONTEXT.md          # AI tool context
├── CONTRIBUTING.md        # Development workflow and guidelines
├── pyproject.toml         # Project configuration
└── Makefile               # Development commands
```

## Documentation

| Document | Description |
|---|---|
| [docs/architecture.md](docs/architecture.md) | Architecture design |
| [docs/file-map.md](docs/file-map.md) | File-level dependency map |
| [docs/specification.md](docs/specification.md) | Specification |
| [docs/ui-design.md](docs/ui-design.md) | UI design |
| [README_TEMPLATE.md](README_TEMPLATE.md) | Project README template |
| [AI_CONTEXT.md](AI_CONTEXT.md) | AI tool context |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Development workflow and guidelines |

## AI-Assisted Development

AI context is pre-configured in `AI_CONTEXT.md`.

| Tool | Role |
|---|---|
| Claude Code | Setup, large-scale changes, architecture design |
| GitHub Copilot | Bug fixes, small implementations, test writing |
| Gemini CLI | Documentation management, translation assistance |

## Customization

1. Rename `src/project_name/` → `src/your_package_name/`
2. Update the `name` field in `pyproject.toml`
3. Update the project overview in `AI_CONTEXT.md`
4. Replace `[YEAR]` and `[AUTHOR]` in `LICENSE`
5. Rename `README_TEMPLATE.md` → `README.md` (and `README_TEMPLATE-jp.md` → `README-jp.md`)
6. Replace placeholders in README: `{user}`, `{repo}`, `{workflow}`, `[USERNAME]`, `[BMC_USERNAME]`
7. Run `make all` to verify

## License

MIT License — see [LICENSE](LICENSE)

---
*This document has a Japanese canonical version [README-jp.md](README-jp.md). Update both in the same commit when editing.*

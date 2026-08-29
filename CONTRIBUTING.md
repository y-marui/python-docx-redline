# Contributing

## Development Flow

### Branch Model

| Branch | Purpose |
|---|---|
| `main` | Production-ready code |
| `develop` | Integration branch |
| `feature/*` | Feature development |

### Workflow

1. Create an Issue describing the task
2. Create a `feature/*` branch from `develop`
3. Implement (with AI assistance as needed)
4. Open a Pull Request
5. Code review
6. Merge to `develop`, then `main`

### Commit Convention

Follow [Conventional Commits](https://www.conventionalcommits.org/):

| Type | Purpose |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `refactor` | Code refactoring |
| `docs` | Documentation only |
| `chore` | Build/tooling changes |

- **No WIP commits**: Do not commit non-working code
- Commit granularity: one logical unit per commit, after verifying it works

## Local Development

```sh
make install   # uv sync (install dependencies)
make lint      # ruff check .
make format    # ruff format .
make type      # mypy src
make test      # pytest
make all       # lint + type + test
```

CI runs on every push and PR: `security` → `lint` (ruff / mypy) → `test` (pytest) → `build`.

## Pre-commit Hooks

Security and quality checks run automatically via `.pre-commit-config.yaml`.

Setup:

```sh
cp docs/dev-charter/.pre-commit-config.yaml .
cp docs/dev-charter/.gitleaks.toml .
# If core.hooksPath is already set, pre-commit install is not needed
git config core.hooksPath 2>/dev/null \
  && echo "core.hooksPath already set" \
  || pre-commit install
pre-commit run --all-files  # verify
```

| Hook | Description |
|---|---|
| gitleaks | Secret detection (`.gitleaks.toml`) |
| detect-private-key | SSH private key detection |
| detect-dotenv | Block `.env` commits |
| no-hardcoded-local-paths | Block hardcoded local paths |
| check-added-large-files | Block files > 500 KB |
| trailing-whitespace / end-of-file-fixer | Whitespace normalization |
| check-yaml / check-json / check-merge-conflict | Syntax and conflict checks |
| shellcheck | Shell script static analysis |

**Two-layer security model:**
- **Layer 1**: Personal global git hook (`~/.config/git/hooks/pre-commit`) — safety net across all repos
- **Layer 2**: Per-repo `.pre-commit-config.yaml` — team enforcement, also runs in CI

## Code Review

- Every commit reaching `main` must be reviewed by another developer
- Changes involving auth, encryption, or data access require a security review
- See [AI_CONTEXT.md](AI_CONTEXT.md#review-checklist) for the review checklist

## Naming Conventions

Follow existing code patterns:

| Target | Convention |
|---|---|
| Modules, functions, variables | `snake_case` |
| Classes | `PascalCase` |
| Constants | `UPPER_SNAKE_CASE` |
| File names | `snake_case.py` |

- Follow existing naming patterns before introducing new ones
- Do not abbreviate unless the abbreviation is universally understood in context

.PHONY: install lint format type test all setup-charter update-charter

install:
	uv sync

lint:
	uv run ruff check .

format:
	uv run ruff format .

type:
	uv run mypy src

test:
	uv run pytest

all: lint type test

## dev-charter helpers
setup-charter:
	git remote add dev-charter https://github.com/y-marui/dev-charter
	git fetch dev-charter
	git subtree add --prefix=docs/dev-charter dev-charter main --squash

update-charter:
	git remote | grep -q '^dev-charter$$' || \
	  git remote add dev-charter https://github.com/y-marui/dev-charter
	git fetch dev-charter
	@STASHED=0; \
	if ! git diff --quiet || ! git diff --cached --quiet || [ -n "$$(git ls-files --others --exclude-standard)" ]; then \
		git stash push -u -m "update-charter"; \
		STASHED=1; \
	fi; \
	git subtree pull --prefix=docs/dev-charter dev-charter main --squash; \
	if [ "$$STASHED" = "1" ]; then git stash pop; fi

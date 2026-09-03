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
	CHARTER_UPDATE_ONLY=1 bash <(curl -fsSL https://raw.githubusercontent.com/y-marui/dev-charter/main/scripts/install.sh)

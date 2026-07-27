# Slate — dev shortcuts. The product itself is just the `slate` CLI.

.PHONY: install test demo dogfood clean

## Editable install with dev deps into ./.venv
install:
	python3 -m venv .venv
	.venv/bin/pip install -q -e ".[dev]"

test:
	.venv/bin/python -m pytest

## Throwaway repo walking the core loop: init -> code change -> status/verify
demo:
	@rm -rf /tmp/slate-demo && mkdir -p /tmp/slate-demo/src && cd /tmp/slate-demo \
		&& git init -q && echo "# Demo" > README.md && echo "def main(): pass" > src/main.py \
		&& git add -A && git -c user.email=demo@slate -c user.name=demo commit -qm init \
		&& "$(CURDIR)/.venv/bin/slate" init \
		&& git add -A && git -c user.email=demo@slate -c user.name=demo commit -qm layer \
		&& echo "x = 1" > src/new_feature.py \
		&& printf '\n--- slate status after a code change ---\n' && "$(CURDIR)/.venv/bin/slate" status \
		&& printf '\n--- slate verify ---\n' && "$(CURDIR)/.venv/bin/slate" verify

## Slate runs on its own repo — keep our context layer honest
dogfood:
	.venv/bin/slate status

clean:
	rm -rf .venv dist build *.egg-info .pytest_cache

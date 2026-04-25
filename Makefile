.PHONY: lint format check install install-dev

lint:
	ruff check bt_sync.py

format:
	ruff format bt_sync.py

check:
	ruff check bt_sync.py && ruff format --check bt_sync.py

install:
	pip install .

install-dev:
	pip install -e ".[dev]"

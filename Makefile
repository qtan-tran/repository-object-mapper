.PHONY: install dev test lint format type demo clean all

install:
	pip install -e .

dev:
	pip install -e ".[dev]"

test:
	pytest -q

lint:
	ruff check src tests

format:
	ruff format src tests

type:
	mypy src

demo:
	rom harvest --config config/sample_v0_2.yaml --mock
	rom classify
	rom resolve-pilot --mock
	rom resolve --mock
	rom score
	rom analyze
	rom visualize
	rom report

clean:
	rm -rf output/ data/cache/ .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

all: lint type test

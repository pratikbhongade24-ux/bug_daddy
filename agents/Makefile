# Agents-folder developer workflow. Run with: `make <target>` from agents/.
#
# All targets are idempotent and run inside the local .venv.

PY := .venv/bin/python
PIP := .venv/bin/pip
PYTEST := .venv/bin/pytest
RUFF := .venv/bin/ruff
MYPY := .venv/bin/mypy

.PHONY: help venv install dev test test-orchestrator test-fast cov lint typecheck check demo clean

help:
	@echo "Common targets:"
	@echo "  make install         — install package + dev deps into .venv"
	@echo "  make test            — run the full test suite"
	@echo "  make test-orchestrator — run only the orchestrator tests"
	@echo "  make cov             — run tests with coverage report"
	@echo "  make lint            — ruff check"
	@echo "  make typecheck       — mypy on orchestrator + hardened modules"
	@echo "  make check           — lint + typecheck + tests (CI gate)"
	@echo "  make demo            — run the orchestrator demo end-to-end"
	@echo "  make clean           — drop caches and the venv"

venv:
	@if [ ! -d .venv ]; then python -m venv .venv && $(PIP) install -U pip; fi

install: venv
	$(PIP) install -e ".[dev]"

dev: install

test:
	$(PYTEST) tests -q

test-orchestrator:
	$(PYTEST) tests/orchestrator -q

test-fast:
	$(PYTEST) tests -q -x --ff

cov:
	$(PYTEST) tests --cov --cov-report=term-missing --cov-report=xml

lint:
	$(RUFF) check src tests

typecheck:
	$(MYPY)

check: lint typecheck test

demo:
	$(PY) -m agentic_solution.orchestrator.demo

clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov coverage.xml .coverage
	find . -type d -name __pycache__ -prune -exec rm -rf {} +

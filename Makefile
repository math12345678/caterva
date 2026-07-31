# Terrium developer commands.
# Run `make` with no arguments to see what's available.

PYTHON  ?= python3
VENV    := .venv
BIN     := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup check test test-fast test-sim test-lit test-slow cli clean

help:
	@echo "Terrium"
	@echo ""
	@echo "  make setup      create .venv and install everything"
	@echo "  make check      verify the environment actually works"
	@echo "  make test       run every test suite"
	@echo "  make test-fast  skip the slow property/robustness suites"
	@echo "  make test-sim   simulation engine only (Tellurium/)"
	@echo "  make test-lit   literature layer only (Tests/)"
	@echo "  make cli        Tellurium CLI help (python -m Tellurium.cli)"
	@echo "  make clean      remove caches and build artifacts"
	@echo ""
	@echo "First time here? Run: make setup && make check && make test"

setup:
	@echo ">> creating virtualenv in $(VENV)"
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip --quiet
	@echo ">> installing dependencies (this builds C extensions; give it a minute)"
	$(BIN)/pip install -r requirements-dev.txt
	@echo ""
	@echo ">> done. Verify with: make check"

# Use the venv interpreter when it exists, otherwise fall back to the system
# one. Resolved once here rather than per-recipe: each make recipe line runs in
# its own shell, so an inline `cd X && ... || (cd X && ...)` fallback would try
# to cd twice within the same shell and fail.
PY := $(shell if [ -x "$(BIN)/python" ]; then echo "$(CURDIR)/$(BIN)/python"; \
	else command -v $(PYTHON); fi)

check:
	@$(PY) scripts/check_env.py

test:
	@echo ">> simulation engine"
	@cd Tellurium && $(PY) -m pytest
	@echo ""
	@echo ">> literature layer"
	@cd Tests && $(PY) -m pytest

test-fast:
	@cd Tellurium && $(PY) -m pytest \
		--ignore=tests/test_properties.py \
		--ignore=tests/test_numerical_robustness.py
	@cd Tests && $(PY) -m pytest

test-sim:
	@cd Tellurium && $(PY) -m pytest

test-lit:
	@cd Tests && $(PY) -m pytest

test-slow:
	@cd Tellurium && $(PY) -m pytest tests/test_properties.py \
		tests/test_numerical_robustness.py -v

cli:
	@$(PY) -m Tellurium.cli --help
	@echo ""
	@echo "Examples:"
	@echo "  python -m Tellurium.cli wf --population-size 100 --generations 200 --seed 42"
	@echo "  python -m Tellurium.cli wf --scenario bottleneck --out results.csv"
	@echo "  python -m Tellurium.cli kimura --p0 0.3 --s 0.03 --population-size 50"

clean:
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .hypothesis -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@echo ">> cleaned"

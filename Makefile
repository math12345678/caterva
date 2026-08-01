# Terrium developer commands.
# Run `make` with no arguments to see what's available.

PYTHON  ?= python3
VENV    := .venv
BIN     := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup check check-python test test-fast test-sim test-lit test-slow cli clean

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

# Resolve one supported interpreter for every recipe. An incomplete/stale
# repository venv must not shadow a supported interpreter, and an unsupported
# system Python must never be selected merely because it has pytest installed.
# Missing packages then fail transparently under the supported interpreter.
PY := $(shell \
	is_supported() { "$$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 10), (3, 11), (3, 12)) else 1)' >/dev/null 2>&1; }; \
	if [ -n "$$VIRTUAL_ENV" ] && [ -x "$$VIRTUAL_ENV/bin/python" ] && is_supported "$$VIRTUAL_ENV/bin/python"; then \
		echo "$$VIRTUAL_ENV/bin/python"; \
	elif [ -x "$(BIN)/python" ] && is_supported "$(BIN)/python"; then \
		echo "$(CURDIR)/$(BIN)/python"; \
	else \
		chosen=""; \
		for candidate in python3.12 python3.11 python3.10; do \
			if command -v "$$candidate" >/dev/null 2>&1 && is_supported "$$candidate"; then \
				chosen="$$(command -v "$$candidate")"; break; \
			fi; \
		done; \
		if [ -n "$$chosen" ]; then echo "$$chosen"; \
		else echo ""; fi; \
	fi)

check-python:
	@if [ -z "$(PY)" ]; then \
		echo "No supported Python 3.10–3.12 interpreter found."; \
		echo "Install Python 3.12 and run: make setup"; \
		exit 2; \
	fi
	@echo ">> using $(PY)"

check: check-python
	@$(PY) scripts/check_env.py

test: check-python
	@echo ">> simulation engine"
	@cd Tellurium && $(PY) -m pytest
	@echo ""
	@echo ">> literature layer"
	@cd Tests && $(PY) -m pytest

test-fast: check-python
	@cd Tellurium && $(PY) -m pytest \
		--ignore=tests/test_properties.py \
		--ignore=tests/test_numerical_robustness.py
	@cd Tests && $(PY) -m pytest

test-sim: check-python
	@cd Tellurium && $(PY) -m pytest

test-lit: check-python
	@cd Tests && $(PY) -m pytest

test-slow: check-python
	@cd Tellurium && $(PY) -m pytest tests/test_properties.py \
		tests/test_numerical_robustness.py -v

cli: check-python
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

# Terrium developer commands.
# Run `make` with no arguments to see what's available.

PYTHON  ?= python3
TERRIUM_PYTHON ?=
TERRIUM_PYTHON_ABS := $(if $(TERRIUM_PYTHON),$(if $(filter /%,$(TERRIUM_PYTHON)),$(TERRIUM_PYTHON),$(CURDIR)/$(TERRIUM_PYTHON)),)
VENV    := .venv
BIN     := $(VENV)/bin

.DEFAULT_GOAL := help
.PHONY: help setup check check-python require-pytest test test-fast test-sim test-lit test-slow cli clean

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

setup: check-python
	@echo ">> creating virtualenv in $(VENV) with $(PY)"
	"$(PY)" -m venv $(VENV)
	$(BIN)/pip install --upgrade pip --quiet
	@echo ">> installing dependencies (this builds C extensions; give it a minute)"
	$(BIN)/pip install -r requirements-dev.txt
	@echo ""
	@echo ">> done. Verify with: make check"

# Resolve one supported interpreter for every recipe. An incomplete/stale
# repository venv must not shadow a supported interpreter, and an unsupported
# system Python must never be selected merely because it has pytest installed.
#
# Version support is 3.10-3.13 and that gate is authoritative: libroadrunner
# 2.8.0 and numpy 2.2.6 publish cp313 wheels (and keep cp310), verified against
# PyPI. Windows outside it cannot install this project's dependencies. The
# 2.9.x libroadrunner line drops cp310, so we stay on 2.8.0 to keep the floor.
#
# Among supported interpreters, one that can actually run pytest is preferred
# over one that merely has the right version number. The previous resolver
# checked version only, so on a machine with a corrupt .venv it selected a
# bare system python3.12 and `make test` died with "No module named pytest" --
# an accurate message that named the wrong problem. `is_usable` makes the
# selection reflect what the recipe needs; `check-python` explains the
# remaining cases rather than failing bare, and `require-pytest` (a separate
# target, depended on only by the targets that RUN tests) explains the
# no-pytest case without blocking `setup`, which is what installs it.
PY := $(shell \
	is_supported() { "$$1" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] in ((3, 10), (3, 11), (3, 12), (3, 13)) else 1)' >/dev/null 2>&1; }; \
	is_usable() { "$$1" -c 'import pytest' >/dev/null 2>&1; }; \
	if [ -n "$(TERRIUM_PYTHON_ABS)" ]; then \
		if [ -x "$(TERRIUM_PYTHON_ABS)" ] && is_supported "$(TERRIUM_PYTHON_ABS)"; then echo "$(TERRIUM_PYTHON_ABS)"; else echo ""; fi; \
	elif [ -n "$$VIRTUAL_ENV" ]; then \
		if [ -x "$$VIRTUAL_ENV/bin/python" ] && is_supported "$$VIRTUAL_ENV/bin/python"; then echo "$$VIRTUAL_ENV/bin/python"; else echo ""; fi; \
	elif [ -x "$(BIN)/python" ] && is_supported "$(BIN)/python"; then \
		echo "$(CURDIR)/$(BIN)/python"; \
	else \
		chosen=""; fallback=""; \
		for candidate in python3.13 python3.12 python3.11 python3.10; do \
			command -v "$$candidate" >/dev/null 2>&1 || continue; \
			is_supported "$$candidate" || continue; \
			resolved="$$(command -v "$$candidate")"; \
			[ -n "$$fallback" ] || fallback="$$resolved"; \
			if is_usable "$$candidate"; then chosen="$$resolved"; break; fi; \
		done; \
		if [ -n "$$chosen" ]; then echo "$$chosen"; \
		else echo "$$fallback"; fi; \
	fi)

# True when .venv exists but cannot execute. A venv whose interpreter symlink
# is dangling is invisible to `[ -x ]` above, so it is silently skipped and
# the user is left guessing why their environment is ignored.
VENV_BROKEN := $(shell \
	if [ -d "$(VENV)" ] && ! "$(BIN)/python" -c '' >/dev/null 2>&1; then echo 1; fi)

check-python:
	@if [ -z "$(PY)" ]; then \
		echo "No supported Python 3.10-3.13 interpreter found."; \
		echo ""; \
		echo "Terrium pins libroadrunner 2.8.0 and numpy 2.2.6, which publish"; \
		echo "wheels for Python 3.10 through 3.13. Install one of python3.13,"; \
		echo "python3.12, python3.11 or python3.10, then:"; \
		echo ""; \
		echo "    make setup"; \
		exit 2; \
	fi
	@if [ -n "$(VENV_BROKEN)" ]; then \
		echo "The .venv in this repository cannot execute."; \
		echo ""; \
		echo "  $(BIN)/python does not run (dangling symlink or removed interpreter)."; \
		if [ -f "$(VENV)/pyvenv.cfg" ]; then \
			echo "  It was created from: $$(sed -n 's/^home = //p' "$(VENV)/pyvenv.cfg")"; \
		fi; \
		echo ""; \
		echo "Rebuild it:"; \
		echo ""; \
		echo "    rm -rf $(VENV) && make setup"; \
		exit 2; \
	fi
	@echo ">> using $(PY)"

# Targets that RUN tests need pytest; `setup` is the target that installs it,
# so it must not require it. Keeping this separate from check-python is the
# whole point: depending on it from `setup` makes `make setup` fail on the
# very condition it exists to fix.
require-pytest: check-python
	@if ! "$(PY)" -c 'import pytest' >/dev/null 2>&1; then \
		echo ""; \
		echo "That interpreter is a supported version but has no pytest, so no"; \
		echo "test target can run. Create the project venv:"; \
		echo ""; \
		echo "    make setup"; \
		echo ""; \
		echo "(or install into the current interpreter:"; \
		echo "    $(PY) -m pip install -r requirements-dev.txt)"; \
		exit 2; \
	fi

check: check-python
	@"$(PY)" scripts/check_env.py

test: require-pytest
	@echo ">> simulation engine"
	@cd Tellurium && "$(PY)" -m pytest
	@echo ""
	@echo ">> literature layer"
	@cd Tests && "$(PY)" -m pytest

test-fast: require-pytest
	@cd Tellurium && "$(PY)" -m pytest \
		--ignore=tests/test_properties.py \
		--ignore=tests/test_numerical_robustness.py
	@cd Tests && "$(PY)" -m pytest

test-sim: require-pytest
	@cd Tellurium && "$(PY)" -m pytest

test-lit: require-pytest
	@cd Tests && "$(PY)" -m pytest

test-slow: require-pytest
	@cd Tellurium && "$(PY)" -m pytest tests/test_properties.py \
		tests/test_numerical_robustness.py -v

cli: check-python
	@"$(PY)" -m Tellurium.cli --help
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

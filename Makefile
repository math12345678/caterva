# Terrium developer commands.
# Run `make` with no arguments to see what's available.

PYTHON  ?= python3
TERRIUM_PYTHON ?=
TERRIUM_PYTHON_ABS := $(if $(TERRIUM_PYTHON),$(if $(filter /%,$(TERRIUM_PYTHON)),$(TERRIUM_PYTHON),$(CURDIR)/$(TERRIUM_PYTHON)),)
VENV    := .venv

# A Windows virtualenv puts its entry points in Scripts\, not bin/. This is
# recursively expanded on purpose: `setup` creates the venv inside a recipe,
# long after this line is parsed, so a simply-expanded := would have decided
# the answer before the directory existed. The rest of this file is still
# POSIX shell, so WSL2 or the Dev Container remains the supported Windows
# route -- see CONTRIBUTING.md "Windows".
BIN      = $(VENV)/$(if $(wildcard $(VENV)/Scripts/python.exe),Scripts,bin)

.DEFAULT_GOAL := help
.PHONY: help setup doctor check check-python require-pytest test test-fast test-sim test-lit test-slow guards pr demo publish-check evidence cli clean release-artifacts release-app

help:
	@echo "Terrium"
	@echo ""
	@echo "  make demo       SEE A REAL REPORT -- 30s, no network, no account"
	@echo "  make setup      create .venv and install everything"
	@echo "  make doctor     diagnose a setup that will not work"
	@echo "  make check      verify the environment actually works"
	@echo "  make test       run every test suite"
	@echo "  make test-fast  skip the slow property/robustness suites"
	@echo "  make test-sim   simulation engine only (Terium/)"
	@echo "  make test-lit   literature layer only (Tests/)"
	@echo "  make guards     the guards CI runs (no test suites)"
	@echo "  make counts-fix update README counts after adding a test/guard/ADR"
	@echo "  make pr         everything CI runs -- do this before opening a PR"
	@echo "  make cli        Terium CLI help (python -m Terium.cli)"
	@echo "  make clean      remove caches and build artifacts"
	@echo ""
	@echo "  make publish-check   all offline checks before going public"
	@echo "  make evidence        measured figures, for writing about Terrium"
	@echo "  make release-artifacts  wheel + sdist into dist/, as CI builds them"
	@echo "  make release-app        the one-folder app (needs requirements-release.txt)"
	@echo ""
	@echo "First time here? Run: make setup && make demo"
	@echo "About to open a PR? Run: make pr"
	@echo "Something not working? Run: make doctor"

setup: check-python
	@echo ">> creating virtualenv in $(VENV) with $(PY)"
	"$(PY)" -m venv $(VENV)
	$(BIN)/pip install --upgrade pip --quiet
	@echo ">> installing dependencies"
	@echo "   About 120 MB of prebuilt wheels for the direct pins alone"
	@echo "   (libroadrunner 50 MB, scipy 35 MB, numpy 14 MB), plus their"
	@echo "   transitive dependencies. Two to five minutes on a normal"
	@echo "   connection. pip prints nothing while it resolves; that is"
	@echo "   normal and not a hang."
	@echo ""
	@$(BIN)/pip install -r requirements-dev.txt || { \
		echo ""; \
		echo "Dependency install FAILED. Read pip's last error above -- the"; \
		echo "line that matters is usually 20 lines up, not the last one."; \
		echo ""; \
		echo "Then run:"; \
		echo ""; \
		echo "    make doctor"; \
		echo ""; \
		echo "which names the interpreter it found, what is already"; \
		echo "installed, and the two causes that account for nearly every"; \
		echo "failure here: a Python outside 3.10-3.13, and stdpopsim on"; \
		echo "linux/arm64, where msprime has no wheel and needs libgsl-dev"; \
		echo "plus a C compiler to build from source."; \
		exit 1; }
	@echo ""
	@echo ">> done. Verify with: make check"

# Deliberately does NOT depend on check-python. check-python exits 2 when it
# cannot find a supported interpreter, which is precisely the situation
# doctor exists to explain -- gating the diagnosis on the thing being
# diagnosed is how you get a tool nobody can reach when they need it.
doctor:
	@if command -v "$(PYTHON)" >/dev/null 2>&1; then \
		"$(PYTHON)" scripts/doctor.py; \
	else \
		echo "No '$(PYTHON)' on PATH, so nothing here can run."; \
		echo ""; \
		echo "Install Python 3.10-3.13 and try again:"; \
		echo "  macOS          brew install python@3.13"; \
		echo "  Debian/Ubuntu  apt install python3.13 python3.13-venv"; \
		echo "  Windows        use WSL2 or the Dev Container (see CONTRIBUTING.md)"; \
		exit 2; \
	fi

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
		echo ""; \
		echo "To see every interpreter this looked at: make doctor"; \
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
	@cd Terium && "$(PY)" -m pytest
	@echo ""
	@echo ">> literature layer"
	@cd Tests && "$(PY)" -m pytest

test-fast: require-pytest
	@cd Terium && "$(PY)" -m pytest \
		--ignore=tests/test_properties.py \
		--ignore=tests/test_numerical_robustness.py
	@cd Tests && "$(PY)" -m pytest

test-sim: require-pytest
	@cd Terium && "$(PY)" -m pytest

test-lit: require-pytest
	@cd Tests && "$(PY)" -m pytest

test-slow: require-pytest
	@cd Terium && "$(PY)" -m pytest tests/test_properties.py \
		tests/test_numerical_robustness.py -v

# The guards CI runs, in CI's order, minus the test suites -- plus the
# two that keep this target and the docs honest, which run under pytest
# rather than in the workflow.
#
# These existed and ran in CI long before this target did. Nothing local
# invoked them, so `make test` -- the command CONTRIBUTING tells you to run
# before opening a PR -- reproduced two of the eleven steps in the `test`
# job. The other nine arrived as a red X.
#
# Kept honest by scripts/check_ci_reproducible_locally.py, which fails when
# a CI step has neither a local route nor a written reason it cannot have
# one. Add a step to CI, and that guard tells you to add it here too.
#
# Not included, and deliberately: check_codegen_loads.py and the api-server
# suite, both of which need a completed pnpm install. `make pr` names them
# at the end rather than pretending they ran.
guards: require-pytest
	@echo ">> environment"
	@"$(PY)" scripts/check_env.py
	@echo ">> citation format"
	@"$(PY)" scripts/check_citation_format.py
	@echo ">> documented counts"
	@"$(PY)" scripts/check_documented_counts.py
	@echo ">> documented equations match the engine"
	@"$(PY)" scripts/check_documented_equations_match_engine.py --selftest
	@"$(PY)" scripts/check_documented_equations_match_engine.py
	@echo ">> agent constraints are actionable"
	@"$(PY)" scripts/check_constraints_are_actionable.py --selftest
	@"$(PY)" scripts/check_constraints_are_actionable.py
	@echo ">> EC numbers still current"
	@"$(PY)" scripts/check_ec_numbers_current.py --selftest
	@"$(PY)" scripts/check_ec_numbers_current.py
	@echo ">> landing-page test counts"
	@"$(PY)" scripts/check_landing_test_counts.py --selftest
	@"$(PY)" scripts/check_landing_test_counts.py
	@echo ">> python support claim"
	@"$(PY)" scripts/check_python_support_claim.py
	@echo ">> forbidden packages (constitution rules 7 and 8)"
	@"$(PY)" scripts/check_forbidden_packages.py
	@echo ">> guard wiring"
	@"$(PY)" scripts/check_guard_wiring.py
	@echo ">> pinned versions resolve on PyPI"
	@"$(PY)" scripts/check_pins_resolve.py
	@echo ">> no Tellurium integration claims"
	@"$(PY)" scripts/check_no_tellurium_integration_claims.py --selftest
	@"$(PY)" scripts/check_no_tellurium_integration_claims.py
	@echo ">> LLM disclosure"
	@"$(PY)" scripts/check_llm_disclosure.py --selftest
	@"$(PY)" scripts/check_llm_disclosure.py
	@echo ">> privacy notice"
	@"$(PY)" scripts/check_privacy_notice.py --selftest
	@"$(PY)" scripts/check_privacy_notice.py
	@echo ">> deployment warning"
	@"$(PY)" scripts/check_deployment_warning.py --selftest
	@"$(PY)" scripts/check_deployment_warning.py
	@echo ">> published repo READMEs"
	@"$(PY)" scripts/check_published_repo_readmes.py --selftest
	@"$(PY)" scripts/check_published_repo_readmes.py
	@echo ">> split repos ship LICENSE and NOTICE (Apache-2.0 4(a), 4(d))"
	@"$(PY)" scripts/check_split_repo_legal_files.py --selftest
	@"$(PY)" scripts/check_split_repo_legal_files.py
	@echo ">> model citations cite models"
	@"$(PY)" scripts/check_model_citations_cite_models.py
	@echo ">> release artifacts (LGPL/GPL conveyance)"
	@"$(PY)" scripts/check_release_artifacts.py --selftest
	@"$(PY)" scripts/check_release_artifacts.py
	@echo ">> CI reproducible locally"
	@"$(PY)" scripts/check_ci_reproducible_locally.py
	@echo ">> documented paths resolve"
	@"$(PY)" scripts/check_doc_paths_resolve.py
	@echo ">> data source attribution"
	@"$(PY)" scripts/check_data_source_attribution.py
	@echo ">> package spelling"
	@"$(PY)" scripts/check_package_spelling.py --selftest
	@"$(PY)" scripts/check_package_spelling.py
	@echo ">> port binding"
	@"$(PY)" scripts/check_port_binding.py --selftest
	@"$(PY)" scripts/check_port_binding.py
	@echo ">> subprocess safety"
	@"$(PY)" scripts/check_subprocess_safety.py --selftest
	@"$(PY)" scripts/check_subprocess_safety.py
	@echo ">> public images reviewed"
	@"$(PY)" scripts/check_public_images_reviewed.py
	@echo ">> no fabricated endorsements"
	@"$(PY)" scripts/check_no_fabricated_endorsements.py
	@echo ">> non-affiliation notice"
	@"$(PY)" scripts/check_non_affiliation_notice.py
	@echo ">> dependency licences"
	@"$(PY)" scripts/check_dependency_licenses.py
	@echo ">> citations name the right enzyme"
	@"$(PY)" scripts/check_citations_match_their_enzyme.py --selftest
	@"$(PY)" scripts/check_citations_match_their_enzyme.py
	@echo ">> documented links resolve"
	@"$(PY)" scripts/check_doc_links.py --selftest
	@"$(PY)" scripts/check_doc_links.py
	@echo ">> build guards (this is the slow one -- several minutes)"
	@"$(PY)" scripts/verify_build.py --quick
	@echo ">> silent skips"
	@"$(PY)" scripts/check_no_silent_skips.py

# Correct the counts in README.md that are derived from the tree.
#
# Adding a test changes three numbers; adding a guard changes two; adding
# an ADR changes one. `make guards` fails on all of them and used to say
# "Update README.md", which is a six-line hand-edit for figures a script
# already knows. That is a contribution barrier built out of a correct
# check.
#
# Deliberately not folded into `guards`: a check that silently edits your
# working tree is not a check. You ask for the write.
counts-fix: check-python
	@"$(PY)" scripts/check_documented_counts.py --write

# What CI will run, in CI's order, as far as a laptop can go.
pr: guards test
	@echo ""
	@echo "Local checks passed. Three things CI runs that this did not:"
	@echo ""
	@echo "  - scripts/check_codegen_loads.py   (needs Node + pnpm install)"
	@echo "  - pnpm run typecheck               (does the TypeScript COMPILE)"
	@echo "  - the api-server TypeScript suite  (see RUN_TESTS.md)"
	@echo ""
	@echo "All three need a pnpm install in Science-Agent-Pipeline. If you"
	@echo "touched the API server, the landing app or the OpenAPI spec, run"
	@echo "them; see RUN_TESTS.md."

# The first thing to run, and the only one that needs nothing but `make
# setup`. No network, no BRENDA account, no Node: it drives the same
# `report_lab.py` the CLI spawns and prints the document it produced.
#
# Before this, seeing one output meant clearing six separate hurdles, so
# nobody had ever seen it without being told how. Possible only since
# `report` learned `--fixture` (ADR 0149).
# Everything checkable before publishing, in one command. Publication is
# the last thing between Terrium and anybody using it, and PUBLISHING.md is
# a careful five-section manual procedure — which is exactly the kind of
# thing that gets put off. This says either "the only thing left is the
# push" or precisely what is not ready, and is honest that it cannot see
# GitHub.
# The numbers a paper about Terrium would need, each computed by the run
# rather than transcribed. Every figure carries the command that produced
# it, and anything that cannot be measured offline is printed as "not
# measurable here" with the reason rather than estimated.
evidence: check-python
	@"$(PY)" scripts/evidence_table.py

publish-check: check-python
	@"$(PY)" scripts/publish_preflight.py

# The release artifacts, exactly as .github/workflows/release.yml builds them
# (ADR 0177). `release-app` needs PyInstaller: pip install -r requirements-release.txt
release-artifacts: check-python
	@"$(PY)" scripts/build_release.py

release-app: check-python
	@"$(PY)" scripts/build_app.py

demo: check-python
	@"$(PY)" scripts/demo.py

cli: check-python
	@"$(PY)" -m Terium.cli --help
	@echo ""
	@echo "Examples:"
	@echo "  python -m Terium.cli wf --population-size 100 --generations 200 --seed 42"
	@echo "  python -m Terium.cli wf --scenario bottleneck --out results.csv"
	@echo "  python -m Terium.cli kimura --p0 0.3 --s 0.03 --population-size 50"

clean:
	find . -type d -name __pycache__ -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .pytest_cache -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name .hypothesis -not -path "./.venv/*" -exec rm -rf {} + 2>/dev/null || true
	@echo ">> cleaned"

# Changelog

No versioned releases exist yet -- there's no published package, no tagged
release, just an active `main` branch. Entries below are grouped by real
date from git history, not semantic version numbers, because assigning
version numbers to a pre-release research tool would imply a release
process that doesn't exist yet. This file should switch to
[Semantic Versioning](https://semver.org/) once there's an actual first
release to version.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).

## Unreleased

Nothing currently staged beyond what's listed below.

## 2026-07-25

### Added
- PCR amplification as a third live simulation domain: exact closed-form
  exponential growth, optional discrete-logistic plateau mode, validation
  with an `ok`/`flagged` distinction consistent with the rest of the engine.
  32 new tests, mutation-verified.
- Sandbox: `Dockerfile` + `.devcontainer/devcontainer.json` for a one-command
  reproducible environment.
- `Business/` scaffolding: incorporation checklist, cap table placeholder,
  fundraising tracker, roadmap.

## 2026-07-23

### Added
- Tellurium simulation engine (`tellurium_engine.py`): Michaelis-Menten
  enzyme kinetics and SIR/SEIR epidemiology, built on antimony/roadrunner
  rather than the full `tellurium` umbrella package.
- 258-test simulation-engine suite, verified against exact closed-form
  solutions, an independent solver (scipy), and property-based tests
  (Hypothesis) -- not just internal self-consistency.
- `requirements.txt` / `requirements-dev.txt`, `Makefile`, GitHub Actions CI,
  `scripts/check_env.py`, `README.md`.
- Investor pitch deck (`terrium_pitch_deck.pptx`).
- `tests/test_dependencies_declared.py`: automated guard that fails CI if
  any import isn't declared in `requirements*.txt`.

### Fixed
- `KM_PLAUSIBLE_MAX_MM` mismatch between the literature layer
  (`Tests/brenda_client.py`) and the simulation engine (1e4 vs 1e3) -- a
  real bug that would have let a Km value flagged as implausible upstream
  arrive as "confirmed" downstream. Pinned equal, with a regression test.
- CI dependency install failures: `libroadrunner==2.9.0` had no Python 3.10
  wheels (reverted to `2.7.0`), and `httpx`/`pydantic` were imported by
  `brenda_client.py` but never declared as dependencies.
- A broken git submodule reference: `Science-Agent-Pipeline` had been
  committed as a gitlink with no `.gitmodules`, which made GitHub Actions'
  checkout step fail outright. Untracked it; it's an independent repo.

## 2026-07-21 to 2026-07-22

### Added
- Initial BRENDA/KEGG/PubMed literature-scraping layer (`Tests/`), 124 tests.
- Verified project specification and planning documents (`Docw/`).

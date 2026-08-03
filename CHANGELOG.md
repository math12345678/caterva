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

### Added
- **ADR 0012**: kcat is resolved from literature but is not a simulation parameter.
- **ADR 0013**: Enzyme concentration bridges kcat to Vmax (Vmax = kcat * [E]0).
- **ADR 0014**: Python 3.10-3.12 support window documented with the correct
  constraint (libroadrunner + numpy, not libSBML).
- **ADR 0015**: A constitution rule that nothing executes is not enforced —
  adding tellurium to requirements.txt passed every guard.
- **ADR 0016**: Cached results lose per-parameter provenance — schema column,
  persistence, cache read, and serialisation guard all implemented.
- 11 guard scripts with automated wiring check (`check_guard_wiring.py`).
- Documented-counts guard (`check_documented_counts.py`) that fails if README
  test/domain counts don't match the repository.
- Python support claim guard (`check_python_support_claim.py`) across all
  files that state the version window.
- Constitution Rules 7+8 guard (`check_forbidden_packages.py`) — forbids the
  tellurium umbrella package and verifies every ADR is indexed.
- **Eleventh simulation domain**: Michaelis-Menten with competitive
  inhibition (`v = Vmax·S / (Km·(1+I/Ki) + S)`), verified against the
  apparent-Km closed form `Km_app = Km·(1 + I/Ki)` and against plain MM
  exactly at I=0. Reachable end-to-end (engine, API dispatch, TS schema).
- **Python 3.13 support** (ADR 0014 follow-through): `numpy` and
  `libroadrunner` bumped to publish cp310-cp313 wheels, verified against
  PyPI with `--online`, not assumed from the pin bump alone.

### Changed
- Engine test suite: 715 -> 883 tests (Gillespie SSA, SSA bimolecular,
  SSA replicates, two-locus WF, competitive-inhibition MM).
- Literature test suite: 182 -> 214 tests.
- TypeScript test suite: 111 -> 224 tests (16 files).
- README Layout section now lists all six top-level directories.
- README domain count: ten -> eleven, kept consistent across both
  places it's stated (guarded by `check_documented_counts.py`).

### Fixed
- ADR 0016: parameter provenance now survives cache hits (was silently
  returning {} on every cached result).
- ADR 0014: the documented reason for the Python version constraint corrected
  in README, CONTRIBUTING, and requirements.txt.
- Rule 8: ADR indexing verified automatically; two unindexed ADRs found and
  fixed during guard development.
- README.md Layout and scripts/README.md stale counts corrected.
- Two real environment bugs: `pipeline.ts`'s and `scienceAgent.ts`'s health
  check / literature bridge both hardcoded `spawn("python3", ...)` instead
  of resolving the actual configured interpreter — silently wrong on any
  machine where the venv Python isn't literally named `python3` on PATH.
- A false capability claim: `RESOLVABLE_FIELDS` said the new domain's `ki`
  is resolved from BRENDA; nothing populates it, so it always silently fell
  back to a default. Narrowed the claim rather than fake a lookup path —
  same precedent as ADR 0012 excluding kcat.
- The parameter-provenance fix and the competitive-inhibition domain were
  both originally built on a branch that turned out to be 92 commits behind
  main; ported the real diffs onto current main by hand after the naive
  cherry-pick failed outright.

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

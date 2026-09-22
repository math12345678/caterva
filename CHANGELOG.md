# Changelog

> **⚠️ CORRECTION (2026-08-12):** the `## Unreleased` section's counts are stale — the repo has moved well past the state they describe:
> - **"11 guard scripts"**: running `python3 scripts/verify_build.py --quick` today shows the Guard Wiring Guard reporting **"all 22 guards run in at least one harness"** — 22 guards now exist, not 11.
> - **"Engine test suite: 715 -> 883 tests"**: `python3 -m pytest --collect-only` in `Terium/` now collects **1,014** tests.
> - **"Literature test suite: 182 -> 214 tests"**: `Tests/` now collects **277** tests.
> - **"TypeScript test suite: 111 -> 224 tests (16 files)"**: `Science-Agent-Pipeline/artifacts/api-server` now has **433** test cases across **32** `*.test.ts` files (`npx vitest list`).
> This is ordinary changelog staleness (the Unreleased section wasn't updated as later work landed, and later work was logged in `OVERNIGHT_LOG.md` instead — see that file's own correction banner for the same underlying drift), not fabrication.

This file follows [Semantic Versioning](https://semver.org/) from 0.1.0
onward and [Keep a Changelog](https://keepachangelog.com/) in shape.
Entries before 0.1.0 are grouped by date, because that is how the work was
done: there was no release to version.

## [0.3.0] - 2026-09-21

The first release that reaches GitHub's Releases page, and the first that
is downloadable as an app. v0.2.0 built and verified a wheel; the Release
itself needed a token the machine did not have, so the tag sat on the
remote with nothing attached. From this version a pushed tag is published
by a workflow with the run's own token, after it has rebuilt, reinstalled
and run everything it is about to attach (ADR 0177).

### Added
- **A release workflow.** `.github/workflows/release.yml`: on a `v*` tag
  (or by hand for an existing tag), builds the wheel and sdist, rebuilds
  them independently and fails if the checksums differ, installs the wheel
  into a fresh interpreter on Linux, macOS and Windows at Python 3.10 and
  3.13 and runs `terium-compose` to a `VERDICT:` from an empty directory,
  freezes the app folders, and only then creates the Release with the
  notes, every artifact and one `SHA256SUMS`.
- **A downloadable app folder per platform** (`terrium-<version>-<os>-
  <arch>.tar.gz` / `.zip`, Linux x86_64, macOS arm64, Windows x86_64):
  one executable, `terrium`, with `terrium compose "..."` and
  `terrium sim ...`. No Python, no install. Built from the released wheel
  by `scripts/build_app.py`, which refuses the folder unless python-
  libsbml's extension is a separate replaceable file, every conveyed
  component's licence is inside, and the frozen binary runs from an empty
  directory. libSBML is in the folder three times (python-libsbml's copy
  and the copies libroadrunner and Antimony compile in); the script finds
  and lists them, and the release page carries the corresponding source
  of every version, and of the two libraries, beside the folders.
- **`terrium`, a single entry point.** `Terium/app.py` dispatches to the
  two existing commands unchanged (`python -m Terium.app` from the wheel;
  the executable in the folder). 83 modules in the wheel, up from 82.
- **`third_party_licenses/LGPL-2.1.txt`.** The LGPL text python-libsbml's
  wheel refers to but does not carry; the app folder ships it.
- **`requirements-release.txt`** pins PyInstaller for the release workflow
  only, with its licence (GPL-2.0-or-later WITH Bootloader-exception)
  recorded in the dependency-licence guard.

### Changed
- **Both artifacts are byte-reproducible from the commit.** The sdist is
  normalised after the build (sorted members, epoch mtimes, gzip mtime 0);
  0.2.0's notes said the wheel was and the sdist was not. Measured:
  identical `SHA256SUMS` from two independent checkouts of the tag.
- **NOTICE now states the licence position artifact by artifact.** The
  wheel and sdist name libSBML and do not convey it; the app folder does,
  and the section says how each LGPL-2.1 obligation is met (notice, and a
  separate replaceable file). The sentence "this repository has exactly
  one CI workflow and it publishes nothing" was true from 2026-08-15 to
  2026-09-19 and is replaced with that history. `docs/LICENSING.md` and the
  dependency-licence guard no longer say replacement is "a pip install
  away" without qualification.
- `SECURITY.md` names which versions receive fixes; it said there were no
  released builds.

### Fixed
- **`terium-compose --export sbml` and `--export antimony` crashed from
  every installed copy of 0.2.0** with `FileNotFoundError`: two files the
  engine reads at import, `docs/data-sources.json` and
  `Tests/fixtures/identifiers/identifiers_org_namespaces.json`, were
  resolved relative to the checkout and shipped in neither the wheel nor
  the sdist. Copies now live in `Terium/core/data/`; the loaders read the
  checkout's original when it exists and the packaged copy otherwise, and
  `Terium/tests/test_packaged_data.py` fails if a copy and its original
  ever differ. Proved from an installed wheel in an empty directory. The
  0.2.0 notes' "Known limits" did not record this; it was found by reading
  every `Path(__file__)` in the package for the app folder.
- `CHANGELOG.md` carried a duplicated, truncated block (a second correction
  banner and a stale `[0.1.0] - 2026-09-19` section) introduced by the
  0.2.0 commit's edit anchoring on the wrong `## Unreleased`. Removed.

### Known limits, stated
- **Not on PyPI.** A separate decision; the name has not been checked.
- **Not signed.** The macOS and Windows folders carry no code signature;
  each folder's `README.txt` says what the operating system asks on first
  run. Signing needs certificates the repository does not hold.
- **No Intel-Mac folder.** Intel Mac users install the wheel.
- **The repository is still private**, so the Release is visible to
  collaborators. Going public is blocked by owner decisions listed in
  `docs/status/2026-09-21.md`, not by anything in this release.
- **The freeze could not be run where this was written** (no PyPI in the
  sandbox). The workflow's first run is the first real freeze; it verifies
  the folder by running it, and publishes nothing if that fails.

## [0.2.0] - 2026-09-19

The first release with built artifacts. A source distribution, a
pure-Python wheel, and two installed commands. 0.1.0 (below) was a tag and
a source archive; this is the version you can `pip install`. Everything
under the `Unreleased` heading further down was already in the tree; this
entry records what makes 0.2.0 an installable release rather than a
checkout.

### Added
- **Installable package.** `pip install terrium-0.2.0-py3-none-any.whl`
  installs `Terium` (engine, composer, agents; 82 modules) with pinned
  dependencies. Verified by installing the wheel into an empty directory
  and building a model from there with nothing of the repository on the
  path.
- **Two commands.** `terium` (the simulation engine: `wf`, `kimura`, `ne`,
  `sweep`, `scenarios`, `ld`, `ssa`) and `terium-compose` (the model
  builder and its analyses). Before this the composer was reachable only
  as `python -m Terium.compose` from a checkout.
- **A version.** `Terium.__version__` is the single source; `pyproject.toml`
  reads it, and `CITATION.cff` and `package.json` are kept equal to it.
  `terium-compose` and the package metadata cannot disagree.
- **`scripts/build_release.py`.** Builds the sdist, then the wheel from
  the extracted sdist, checks the wheel against what the release notes
  claim (no tests, no conftest, LICENSE and NOTICE inside, every module
  under `Terium/`), and writes `SHA256SUMS`. With `SOURCE_DATE_EPOCH`
  pinned to the tagged commit the wheel is byte-reproducible; the sdist is
  content-identical but not byte-identical (setuptools writes fresh
  mtimes into `PKG-INFO`), and the script says so rather than hiding it.
- **A conveyance section in NOTICE** stating what the artifacts do and do
  not distribute: Terrium's own code only; python-libsbml (LGPL-2.1) is
  named as a dependency and not bundled, so its conveyance obligations do
  not attach. (This is also why there is no frozen desktop bundle in this
  release: PR #21's onefile DMG froze libSBML in, and that changes the
  obligations. See NOTICE.)

### Fixed
- **Packaging built nothing.** Setuptools' flat-layout discovery saw
  `Terium/` beside `Tests/`, `Business/`, `node_modules/` and a dozen more,
  and an editable install registered `dist-info` and no code: `import
  Terium` failed from any directory but the repository root. Packages are
  now named explicitly. The sdist also swept the whole `Tests/` tree in
  through a case-folded `tests/` glob; a `MANIFEST.in` prunes it.
- **A wheel built straight from the tree carried `Terium/conftest.py`.**
  `MANIFEST.in` governs the sdist and `exclude-package-data` governs data
  files; neither excludes a module from a wheel built directly. Building
  the wheel from the sdist does, which is what the build script enforces.
- **ADR 0176's mutation table had no set file.** Seven mutations across
  four files, run through `scripts/mutate.py`, all caught.
- Everything under `Unreleased` below, which this release ships.

### Known limits, stated
- **Literature search needs the source checkout.** `Terium.agents` reaches
  into `Tests/` (the BRENDA resolvers) lazily; those modules are not part
  of the package. From the wheel, `terium-compose ... --subject <enzyme>`
  builds the model and the verdict page says, correctly, that no search
  was run. Running the search means cloning the repository.
- **The api-server and landing site are not in this release.** They are
  TypeScript, deploy separately, and their test suite could not be run in
  the environment this release was built in (port binding is sandboxed).
  They are unversioned until they can be verified.
- **0.2.0, not 1.0.0.** The public API has not been frozen and the
  composer's library is eleven mechanisms. The number says "usable,
  changing," which is true.

## [0.1.0] - 2026-08-29

Tagged and released as a source archive only, deliberately: the licence
position rested on distributing nothing that contains libSBML, and a
source archive contains none. `pyproject.toml` said 0.1.0 but its
packaging built an empty install (see 0.2.0, Fixed), so this version was
never `pip install`-able. The record of the release and its measured
figures is in `docs/EXPERT_FEEDBACK.md` ("Seventy-ninth pass").

## Unreleased

### Added
- **ADR 0012**: kcat is resolved from literature but is not a simulation parameter.
- **ADR 0013**: Enzyme concentration bridges kcat to Vmax (Vmax = kcat * [E]0).
- **ADR 0014**: Python 3.10-3.12 support window documented with the correct
  constraint (libroadrunner + numpy, not libSBML).
- **ADR 0015**: A constitution rule that nothing executes is not enforced —
  adding terium to requirements.txt passed every guard.
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
- Terium simulation engine (`terium_engine.py`): Michaelis-Menten
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

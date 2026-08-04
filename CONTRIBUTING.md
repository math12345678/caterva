# Contributing to Terrium

This project is pre-launch and the team is small (currently two confirmed
people, one backend/infra role still open -- see `Business/CAP_TABLE.md`),
so this document is written for that scale, not for a large open-source
project with a governance process. It'll need to grow as the team does.

## Before you start

Read `README.md` first, specifically the "Two gotchas worth knowing"
section. Both gotchas documented there were real bugs that cost real time
to find -- don't rediscover them.

## Getting set up

Two ways to get a working environment, pick whichever you're more
comfortable with:

```bash
# Option 1: native
make setup && make check && make test

# Option 2: container (no local Python needed)
docker build -t terrium-sandbox . && docker run -it --rm terrium-sandbox
```

`make check` / the Docker build both run `scripts/check_env.py`, which
builds a real Michaelis-Menten model end to end and checks it against the
exact closed-form solution. If that fails, something about the environment
is actually broken -- not just a version mismatch warning.

## The standard this codebase holds itself to

This is the part that matters most, more than any specific style rule:

**Every numerical claim gets checked against something that isn't the
solver checking itself.** That means one of:
- an exact closed-form solution (see `Tellurium/tests/test_kinetics_correctness.py`,
  `test_pcr_correctness.py`)
- an independent integrator, e.g. scipy's `solve_ivp`, which shares no code
  with roadrunner (see `test_numerical_robustness.py`)
- a physical invariant (conservation, monotonicity, non-negativity) checked
  across the input space with Hypothesis, not just hand-picked values (see
  `test_properties.py`)

If you add a new domain or a new claim about correctness, it needs one of
these, not just "the output looked reasonable when I ran it once."

**New code should be mutation-tested before you trust the test suite you
wrote for it.** Concretely: deliberately break the logic you just wrote (a
sign flip, a wrong operator, a removed guard) and confirm your own tests
catch it. If they don't, the tests are decorative. This isn't optional
ceremony -- it's how the KM_PLAUSIBLE_MAX_MM bug and the PCR
exponential-vs-linear check were both actually validated, not just written
and assumed correct.

## Supported Python versions

Terrium supports Python 3.9–3.13. This is a hard constraint, but not for the
reason this file used to give. It is **not** "the SBML C extensions stop at
cp312" — `python-libsbml` 5.21.1 already ships cp314 wheels, and `antimony`
2.14.0 ships `py3-none-<platform>` wheels that are Python-version agnostic.

The window is bounded by `libroadrunner` 2.8.0 and `numpy` 2.2.6, which
publish cp310–cp313 wheels (verified against PyPI). The 2.9.x libroadrunner
line drops cp310, so we stay on 2.8.0 to keep the floor — see
[ADR 0014](docs/adr/0014-python-version-support.md).

CI tests 3.10, 3.12 and 3.13 (see
`.github/workflows/tests.yml`); `requirements.txt` pins `numpy==2.2.6` and
`libroadrunner==2.8.0`. A green run with unpinned dependencies is not
evidence about the supported configuration. The eigenvector-sign bug is the
worked example: LAPACK chose different signs across builds, producing silent
NaN rather than an exception; it passed under one numpy build but failed
deterministically under another.

The one-line setup for a correct environment is:

```bash
python3.13 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
```

## Running tests

```bash
make test        # everything
make test-fast    # skip the slow property/robustness suites
make test-sim     # Tellurium/ only
make test-lit     # Tests/ (literature layer) only
```

Never skip a test to make the suite pass. If a test is skipping because of
a real, explainable data condition (see
`test_flagged_brenda_entries_do_not_become_confident_numbers` for the one
legitimate example in this codebase), the skip must be explained in a
docstring or comment, and if possible, backed by a deterministic sibling
test that exercises the same contract without depending on the same
lucky/unlucky data condition.

## Pull requests

- Every PR that touches `tellurium_engine.py` or `Tests/brenda_client.py`
  needs new or updated tests, not just a description that it was tested
  locally.
- If you add a dependency, it must appear in `requirements.txt` or
  `requirements-dev.txt` -- `tests/test_dependencies_declared.py` will fail
  the build otherwise, on purpose.
- Run `make test` before opening the PR, not just after CI catches it.
  CI is the backstop, not the first line of defense.

## Code style

No linter is currently enforced (this should probably change once the
backend hire is confirmed and there's a second engineering opinion on
tooling choice). Until then: match the style of the file you're editing.
Docstrings that explain *why*, not just *what*, are valued highly in this
codebase -- see the module docstring in `tellurium_engine.py` for the bar.

## Questions

Open an issue, or if it's about strategic direction rather than a specific
bug, see `Business/ROADMAP.md` for what's already been deliberately
deprioritized and why.

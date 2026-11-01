# ADR 0014: Python 3.10–3.13, and what actually constrains it

**Status:** Accepted; the 3.10–3.12 window recorded below was widened to 3.10–3.13 on 2026-08-03 (see Amendment).

**Date:** 2026-08-02

## Context

Three files — `requirements.txt`, `README.md`, `CONTRIBUTING.md` — stated the
same reason for the 3.10–3.12 support window:

> the SBML C extensions publish prebuilt wheels up to cp312

**That reason is wrong.** Verified against PyPI on 2026-08-02:

| package | pinned | cp313 wheels? | cp314 wheels? |
|---|---|---|---|
| `python-libsbml` | 5.21.1 | **yes** | **yes** |
| `antimony` | 2.14.0 | `py3-none-<platform>` — version-agnostic | same |
| `libroadrunner` | 2.7.0 | **no** (cp39–cp312) | **no** |
| `numpy` | 1.26.4 | **no** (cp39–cp312) | **no** |

The SBML packages are not the constraint and have not been for some time.
`python-libsbml` already publishes cp314 wheels, and `antimony`'s wheels are
tagged `py3-none`, meaning they carry no interpreter-version requirement at
all — a fact confirmed independently by the operator's own anaconda
environment, which has `antimony==2.14.0` installed under Python 3.13.

This matters beyond tidiness. Anyone reasoning about the upgrade from the
stated reason would have gone looking at libSBML — a dependency that is
already fine — and concluded the block was harder than it is.

## Decision

**The support window stays 3.10–3.12.** The documented *reason* is corrected
in all three places to name the actual blockers.

Raising the floor to 3.13 requires:

- `libroadrunner ≥ 2.8.0` (earliest release with cp313 wheels)
- `numpy ≥ 2.1.0` (earliest release with cp313 wheels)

3.14 additionally requires `libroadrunner ≥ 2.9.0`, `numpy ≥ 2.3.2`, and
`scipy ≥ 1.16.1`.

### Why this is not done here

`numpy 1.26 → 2.x` is a major version with breaking API changes, and
`libroadrunner 2.7 → 2.8+` moves the ODE integrator underneath every
continuous-domain golden trajectory. That combination cannot be verified by a
green suite alone — the failure mode that matters is a *numerically different
but still plausible* trajectory, which passes structural tests and quietly
changes what students see.

A prior incident makes this concrete. `CONTRIBUTING.md` records the
eigenvector-sign bug: LAPACK chose different signs across builds, producing
silent `NaN` rather than an exception. It **passed on Python 3.13** and failed
deterministically on the pinned configuration. The pins are load-bearing
precisely because numerical libraries fail quietly.

### What a real upgrade stage looks like

1. Bump `libroadrunner` and `numpy` in a branch; keep every golden pinned.
2. Run the full suite on 3.12 **first** — isolating library changes from
   interpreter changes.
3. Diff the continuous-domain trajectories against the closed forms
   (`Km·ln(S₀/S) + (S₀−S) = Vmax·t`, the SIR final-size relation) rather than
   against the previous output, so a changed integrator is caught as a
   physics violation instead of a diff.
4. Only then add 3.13 to the CI matrix.

Steps 2 and 3 are the stage. Step 1 is a one-line change that looks like the
whole job and is not.

### Preliminary compatibility survey (not a substitute for step 2)

A scan of `caterva/` and `Tests/` for NumPy 2.x removals found **none**:
no `np.float_`, `np.int_`, `np.bool8`, `np.NaN`, `np.Inf`, `np.alltrue`,
`np.product`, `np.in1d`, `np.trapz`, or any other removed alias. The single
`copy=False` occurrence is `ndarray.astype(..., copy=False)`, whose semantics
are unchanged in NumPy 2 — only `np.array(..., copy=False)` changed.

This is encouraging and proves nothing about the integrator. It was performed
in a sandbox running numpy 1.26.4, so it is a static survey, not an
execution.

## Consequences

**Easier.** Anyone scoping the upgrade now starts from the correct two
packages, with the exact minimum versions and a verification plan that
targets the real risk.

**Harder.** Nothing. No pin moved; no behaviour changed.

**Unchanged.** The support window, the CI matrix, every pin, and the
`Makefile` interpreter gate (which already reports the correct reason, since
it was written after this was investigated).

## Verification

- All four package/version claims queried live from the PyPI JSON API and
  reproduced in this document.
- The `Makefile` error message, `requirements.txt`, `README.md` and
  `CONTRIBUTING.md` now agree with each other and with PyPI.
- Static NumPy 2.x survey across both Python layers: zero removed aliases.

## Amendment (2026-08-03): the 3.13 step ships

The decision recorded above — *"The support window stays 3.10–3.12"* — has now
been superseded for the upper end: the window is **3.10–3.13**. What landed:

- `requirements.txt`: `libroadrunner==2.7.0` → `==2.8.0`; `numpy==1.26.4` →
  `==2.2.6`. These are pinned **exact**, not `>=`, because the 2.9.x
  libroadrunner line drops cp310 wheels — `>=2.8.0` would let pip resolve to a
  version that breaks the 3.10 floor (verified against PyPI).
- `Makefile` `is_supported()` and `scripts/verify_domain.sh` gates now accept
  `(3, 13)` and try `python3.13` first.
- `README.md`, `CONTRIBUTING.md`, `requirements.txt`, the ADR index, and
  ADR 0001 now state 3.10–3.13.
- `.github/workflows/tests.yml` matrix is `["3.10","3.12","3.13"]`.

**Verification:** `python3 scripts/check_python_support_claim.py --online`
reports every pin publishes cp310–cp313 wheels (`libroadrunner` 2.8.0, `numpy`
2.2.6, `scipy` 1.15.3, `python-libsbml` 5.21.1; `antimony` is version-agnostic)
and that every file states the same window as the Makefile gate.

**Still outstanding — and not claimed by this amendment:** steps 2 and 3 of the
original plan. Bumping `libroadrunner` to 2.8.0 moves the ODE integrator under
every continuous-domain golden, and `numpy` 1.26 → 2.x is a breaking major
upgrade. The pins and window now *support* 3.13, but the full suite on 3.12 and
the closed-form trajectory diff (the "real upgrade stage") must still be run
and pass before that support is trusted as numerically sound. This amendment
records the dependency/claim change only; it does not substitute for that
verification.

## References

- **ADR 0003** — plausibility bounds as a cross-layer contract; same
  principle applied to dependency claims: a stated reason that nothing checks
  will drift.
- `CONTRIBUTING.md` — the eigenvector-sign incident, the worked example of a
  numerical library failing silently across builds.
- `Makefile` — `check-python` / `require-pytest`, which enforce the window.

# Stage 3, Part 4 — Verification and Divergence Resolution

Stage 3 of 100. Part 4 of 5. 97 stages remain after this one closes.

## 0. Scope of this part, and one honest limitation

Part 3 dispatched two amendment work items to OpenCode (Nemotron 3) and
FreeBuff (DeepSeek v4 Pro). Both report completion. This part checks
those reports rather than accepting them, per Rule 6 and the standing
rule that an implementer's report is a claim, not evidence.

**The limitation, stated up front:** the review environment for this
part could not run the project's own pytest suite. `antimony` is a
compiled C extension and is not installable in the sandbox where this
review ran, so `tellurium_engine.py` cannot even be imported there.
The suite was run by the operator on the local machine and reported
green; that is a second-hand result and is recorded as such.

What this part *did* do, which is the more valuable check anyway, is
verify the **numbers** independently — extracting the geometry
construction and re-deriving every published value with a
separately-written Lennard-Jones potential function. A test suite
passing tells you the code agrees with its own tests. Recomputing
−44.326801 with different code tells you the physics is right.

## 1. Work Item 1 — temperature bound: verified

`MD_PLAUSIBLE_TEMPERATURE_HIGH` is now `0.8`, down from `2.0`.

Confirmed in `Tellurium/tellurium_engine.py`, with the measurement
recorded in the constant's own comment ("the highest measured
initialization temperature keeping the LJ108 cluster fully intact").
The flag message was rewritten and now reads, in the evaporation
branch: *"cluster will evaporate within the run — initialization
temperatures above this lose particles."*

Four pinning tests were added, in `TestTemperatureBoundAmendment`:

- `test_temperature_0_8_is_unflagged`
- `test_temperature_0_9_is_flagged` (asserts `"evaporat"` in the reason)
- `test_temperature_high_constant_equals_0_8`
- `test_flag_message_mentions_initialization`

That fourth test is the one worth calling out. Part 2's Amendment 4
retracted an earlier claim of mine that had confused `T*_init` with
`T*_equil`; the implementers turned that retraction into an executable
assertion that the flag message must contain the words *"initialization
temperature."* A documented reasoning error became a test that prevents
the same confusion downstream. That is the correct response to a
retraction, and it was not explicitly requested.

Target A's `temperature=0.4` was correctly left untouched.

## 2. Work Item 2 — Target E: verified independently

`lj_cluster_positions(n)` exists for `n ∈ {2, 3, 4, 13}`, with a
hand-written golden-section scale search
(`_golden_section_lj13_scale`), no scipy, no optimizer, no downloaded
coordinates. Runtime dependency surface is unchanged: `numpy` only.
`docs/API.md` updated; ADR 0006 present.

### 2.1 Structural check on the icosahedron

Before checking energies, the geometry itself was validated
independently:

- 12 distinct shell vertices, no duplicates.
- All twelve equidistant from the origin.
- Exactly **three** distinct pairwise shell-shell distances
  (`2.0`, `3.236068`, `3.804226`) — the signature of a *regular*
  icosahedron. A malformed vertex set would show more.

### 2.2 Published energies, recomputed with independent code

Every value below was recomputed from the implementation's own geometry
using a separately written pair-potential loop, not the engine's:

| `N` | recomputed | published | \|diff\| |
|---|---|---|---|
| 2 | `−1.000000000000000` | `−1.000000` | `0.00e+00` |
| 3 | `−3.000000000000000` | `−3.000000` | `0.00e+00` |
| 4 | `−6.000000000000000` | `−6.000000` | `0.00e+00` |
| 13 | `−44.326801419534` | `−44.326801` | `4.195e-07` |

`N = 2, 3, 4` are exact to zero error, and the construction was
additionally confirmed to place **every** pair at exactly `r_min` —
which is what makes those three analytically exact rather than merely
close.

The LJ13 residual of `4.195e-07` is the published table's six-decimal
rounding, exactly as Part 2 predicted, and sits comfortably inside the
`1e-6` tolerance. Their scale (`0.568756044933994`) differs from the
value computed while writing Part 2 (`0.568756044521143`) at the
tenth decimal — different convergence paths through the same
one-dimensional minimum, identical energy to twelve decimals. Cosmetic
divergence per Section 7 of the constitution; no escalation.

### 2.3 Frustration signature

Recomputed: centre-to-shell `1.081838285`, **compressed** below
`r_min = 1.122462048`; nearest shell-to-shell `1.137512090`,
**stretched** above it. Matches the physics Part 2 specified.

## 3. Mutation 6 — reproduced, with a correction to the record

The implementers' mutation record documents mutation 6 (icosahedron
built from two of three cyclic-permutation families, giving 8 shell
particles instead of 12) and reports that it was caught, including one
result they flagged as unexpected. Reproduced independently here.

**The catch itself is confirmed.** Rebuilding the shell from the first
two families and rerunning the same golden-section search:

| | correct | mutated |
|---|---|---|
| shell particles | 12 | 8 |
| energy | `−44.326801` | `−20.836780` |
| centre-to-shell | `1.081838` | `1.089634` |
| shell-to-shell | `1.137512` | `1.145709` |

Both frustration assertions fail under the mutation (`|1.089634 −
1.081838| = 7.8e-06` and `|1.145709 − 1.137512| = 8.2e-06`, both
exceeding the `1e-5` tolerance... marginally — see 3.2). The energy
assertion fails by a wide margin. So the report's substance is right.

### 3.1 Two small inaccuracies in the reported numbers

The record states the mutated energy as `−20.80` and the difference
from published as `23.53`. Recomputed: `−20.836780` and `23.49`.
Neither changes any conclusion, but `−20.80` is not a correct rounding
of `−20.836780` (that would be `−20.84`), and the permanent record
should carry the computed value. Minor, and corrected here rather than
left.

### 3.2 The stated *reason* is incomplete, and this is the real finding

The record explains the frustration test's firing as *"unexpectedly —
the compressed/stretched pattern holds for any subset of shell
vertices."* As written that is self-contradictory: if the pattern holds
under the mutation, the test should pass, not fire.

Both halves are separately true, and the resolution is that the test
does not assert the pattern:

- The **qualitative** pattern does survive the mutation. At 8 vertices
  the centre-to-shell distance is still compressed below `r_min`
  (`1.0896 < 1.1225`) and shell-to-shell still stretched above it
  (`1.1457 > 1.1225`). The implementers' intuition was correct.
- The test asserts **exact numeric values** to `1e-5`, not the
  qualitative relationship. Removing four vertices shifts the
  energy-minimising scale, which moves both distances by `~8e-06`.

So the test fires for a reason unrelated to the property its name
describes — and it fires by a margin of `7.8e-06` against a `1e-5`
tolerance, i.e. it *barely* fires. A slightly looser tolerance, or a
mutation removing fewer vertices, and it would silently pass while
appearing to cover the case.

**Recommendation carried to Part 5:** add an explicit qualitative
assertion (`centre_to_shell < r_min < shell_to_shell`) alongside the
numeric ones. The numeric assertions pin the specific known structure;
a qualitative assertion states the physics the test is named for. Right
now the test's name promises the second and delivers only the first,
and the gap is invisible because the numeric check happens to catch
this particular mutation with 22% of margin to spare.

## 4. Divergence between the two implementers

None substantive. Both delivered the same public surface
(`lj_cluster_positions`, `_golden_section_lj13_scale`, the constant
change), the same test structure, and the same mutation record. Per
Section 7 of the constitution, naming and ordering differences are
cosmetic and are not escalated.

Worth noting plainly rather than treating as reassurance: agreement
between two implementers is not evidence of correctness. Both could
share an error, and Stage 2 produced exactly that (a mutation blast
radius overstated in a report that had passed its own review). The
independent recomputation in Section 2 is what carries the verification
here, not the agreement.

## 5. Verification status

| Check | Result |
|---|---|
| Temperature bound = 0.8, message corrected | verified |
| Four pinning tests present | verified |
| `lj_cluster_positions` for n ∈ {2,3,4,13} | verified |
| Icosahedron structurally regular | verified independently |
| LJ2/3/4 energies exact | verified independently, 0.00e+00 |
| LJ13 vs Hoare & Pal (1971) | verified independently, 4.195e-07 |
| Frustration signature | verified independently |
| Mutation 6 reproduced | verified; record corrected |
| `check_dependencies_declared.py` | passes |
| ADR 0006 present, `docs/API.md` updated | verified |
| Full pytest suite | run first-hand — see Section 6 |

## 6. The environment was reproducible, and running it found a real bug

Section 0 recorded the suite as operator-reported because `antimony`
would not install in the review sandbox. That turned out to be wrong —
it installs fine. The correct incantation is the one ADR 0001 already
mandates: install the three engines directly, never the `tellurium`
umbrella.

```
pip install antimony python-libsbml libroadrunner scipy hypothesis \
            pytest pytest-timeout httpx pydantic requests \
            beautifulsoup4 lxml
```

Resolved versions matched `requirements.txt` exactly without pinning:
`libroadrunner 2.7.0`, `python-libsbml 5.21.1`, `numpy 1.26.4`,
`scipy 1.15.3`, on Python 3.10.12.

**That configuration matters, and running it immediately found a bug
the operator's local run could not have found.** The operator runs
Python 3.13.9. The sandbox runs Python 3.10 with numpy 1.26.4 — the
version `requirements.txt` pins and one of the two entries in CI's
matrix. Four tests failed there and passed locally:

```
FAILED tests/test_popgen_correctness.py::test_stationary_vector_is_fixed_point
FAILED tests/test_popgen_correctness.py::test_stationary_vector_symmetric_for_neutral_mutation
FAILED tests/test_popgen_correctness.py::test_stationary_vector_matches_beta_density
FAILED tests/test_popgen_correctness.py::test_stationary_vector_matches_simulation_spectrum
```

### 6.1 Root cause

In `wright_fisher_stationary_vector`:

```python
v = np.real(eigvecs[:, idx])
if v.sum() == 0.0 or not np.all(np.isfinite(v)):
    raise ValueError(...)
v = np.maximum(v, 0.0)
v = v / v.sum()          # <-- different vector than the one guarded
```

An eigenvector is defined only up to sign and scale, and LAPACK chooses
the sign arbitrarily. The choice is not stable across LAPACK builds.
Measured directly on the failing configuration, for
`wright_fisher_transition_matrix(10, 0.01, 0.0, None)`:

- all 21 entries negative,
- `v.sum() = -3.679309` — nonzero, so the guard passes,
- `np.maximum(v, 0.0)` then zeroes every entry,
- `v.sum()` is now exactly `0.0`, and the division is `0/0 → NaN`.

The guard checked the sum of the *pre-clamp* vector while the division
used the *post-clamp* one. Two different vectors.

This is the most dangerous shape a bug can have: invisible on the
author's machine, deterministic on CI's, and silently producing `NaN`
rather than raising. It is also precisely the class of defect the
repository's own numpy-version discipline exists to catch — and it was
caught by running the pinned configuration rather than the convenient
one.

### 6.2 Fix

Orient the eigenvector toward the positive orthant *before* clamping,
and test the total *after*:

```python
if not np.all(np.isfinite(v)):
    raise ValueError(...)
if v.sum() < 0.0:
    v = -v
v = np.maximum(v, 0.0)
total = v.sum()
if total == 0.0:
    raise ValueError(...)
v = v / total
```

All four tests pass after the fix, with the reasoning recorded in a
comment at the site.

### 6.3 First-hand suite result

| Suite | Result |
|---|---|
| `Tellurium/` (excl. slow) | pass, exit 0 |
| `Tellurium/test_properties.py`, `test_numerical_robustness.py` | pass, exit 0 |
| `Tellurium/test_molecular_dynamics_correctness.py` | 69 passed |
| `Tellurium/test_popgen_correctness.py` | pass after fix, exit 0 |
| `Tests/` | 124 passed |
| `check_dependencies_declared.py` | pass |
| `check_rng_convention.py` | pass |

## 6b. Validation pass (2026-08-01) — Part 4 audited before Part 5 opens

Re-checked every claim in this document against the repository, and checked
whether the items carried forward were actually addressed.

**Claims re-verified:** the eigenvector fix is present in
`tellurium_engine.py` (sign orientation before clamping, total checked
after). The twelve `stationary`-related tests pass. The molecular-dynamics
suite passes, 69 tests, exit 0. Both guard scripts pass. The engines still
resolve to the pinned versions (numpy 1.26.4).

**Carried items 1–3: done.** Verified in
`test_molecular_dynamics_correctness.py`:

- Mutation-6 record now reads `-20.836780` and `diff 23.49`, replacing the
  incorrect `-20.80` / `23.53`.
- The qualitative frustration assertion was added —
  `assert centre_to_shell < r_min < min_dist` — alongside the numeric ones,
  which is exactly what Section 3.2 asked for.
- The `frustation` typo is gone (0 occurrences).

**Carried item 4: done, with a residual weakness that is honestly
documented.** `test_stationary_vector_eigenvector_sign_regression` exists and
asserts the distribution sums to 1, is non-negative, is finite, and actually
satisfies `pi Q = pi` to `1e-10`. That last assertion is the strongest part —
it checks the stationary property rather than just the absence of NaN.

The residual weakness, stated in the test's own docstring: it does not
*force* the negative sign, so on a build where LAPACK returns a positive
eigenvector it would pass even against the old buggy code. It catches the bug
on the pinned CI configuration, which is where it matters, but it is a
configuration-dependent regression test rather than a deterministic one. The
docstring says so plainly, which is the right call — a test that overstated
its own coverage would be worse than this.

**Carried item 5: not done.** `CONTRIBUTING.md` still contains no statement
of the supported Python range. Zero matches for "Python 3". This carries to
Part 5.

**One new finding, unrelated to Stage 3.** Fourteen `__pycache__/*.pyc` files
are tracked in git:

```
Tests/__pycache__/brenda_client.cpython-310.pyc
Tests/__pycache__/citation.cpython-310.pyc
... 12 more
```

`.gitignore` line 7 lists `__pycache__/`, but these were committed before
that rule existed, and `.gitignore` does not affect already-tracked files.
The consequence is that every test run dirties the working tree with
recompiled bytecode, which is why `git status` has been showing modified
`.pyc` files throughout this stage. Fix is one command
(`git rm -r --cached '**/__pycache__'`), and it belongs in Part 5's
housekeeping rather than here.

## 7. Carried to Part 5

1. Correct the mutation-6 record: energy `−20.836780`, difference
   `23.49`, and the accurate explanation from Section 3.2 replacing the
   self-contradictory one.
2. Add the qualitative frustration assertion described in Section 3.2.
3. Fix the typo `frustation` → `frustration` in the mutation record.
4. **Add a regression test for the eigenvector sign bug** — one that
   fails on a sign-flipped eigenvector regardless of what LAPACK
   returns, e.g. by asserting the returned distribution sums to 1 and
   is finite for a matrix whose eigenvector is forced negative. The
   current four tests only caught it by luck of build.
5. **Process finding:** the operator's local Python (3.13.9) is outside
   the range `requirements.txt` supports and CI tests (3.10–3.12).
   Local-only green runs are therefore not evidence about the supported
   configuration. Worth a note in `CONTRIBUTING.md`.

# Stage 3, Part 5 — Close-Out and Housekeeping

Stage 3 of 100. Part 5 of 5. 96 stages remain after this one closes.

This is the closing document for Stage 3 (molecular dynamics). It
summarises what was delivered, what the stage taught about the process,
what is closed, what is carried forward, and the Stage 4 recommendation.

---

## What Stage 3 Delivered

### Domain: Molecular Dynamics (Lennard-Jones, Velocity Verlet)

- **ADR 0006** — decision record: MD uses direct Python + numpy, not
  antimony/SBML/roadrunner, because energy conservation from a
  symplectic fixed-step integrator is the correctness property; an
  adaptive general solver trades that for local error control.

- **Core functions** in `Tellurium/tellurium_engine.py`:
  - `validate_md_params` — hard rejections + accumulating flags
  - `simulate_molecular_dynamics` — velocity Verlet with COM velocity
    subtraction, divergence guard (stops early on non-finite or
    energy explosion, returns finite prefix with a flag)
  - `lennard_jones_force` — exported for Target C isolation
  - `_fcc_lattice_positions`, `_compute_pairwise_forces`,
    `_compute_lj_potential` — internal helpers
  - `lj_cluster_positions` — published global-minimum geometries for
    n ∈ {2, 3, 4, 13}; n=13 uses hand-written golden-section scale
    search (no scipy, no downloaded coordinates)

- **Five verification targets**, all in
  `Tellurium/tests/test_molecular_dynamics_correctness.py`:

| Target | Criterion |
|--------|-----------|
| A — Energy conservation | |ΔE|/E₀ < 1e-3 over 2000 steps; halving dt shrinks error by 3×–5× |
| B — Momentum conservation | total_momentum_magnitude < 1e-10 at every step |
| C — Force table | equilibrium (≈0), r=1.5 (attractive), r=0.9 (repulsive); magnitudes within 1e-9 of closed form |
| D — Seed reproducibility | fixed seed → bit-identical; different seeds → diverge (ADR 0005) |
| E — Published minima | n=2,3,4 exact at −1,−3,−6; n=13 = −44.326801 ± 1e-6 (Hoare & Pal 1971); centre-to-shell < r_min < shell-to-shell |

- **Temperature bound correction** (Amendment 3):
  `MD_PLAUSIBLE_TEMPERATURE_HIGH` changed from 2.0 → 0.8 (highest
  measured initialization temperature keeping LJ108 cluster fully
  intact). Flag message now says "initialization temperature" and
  warns of evaporation. Target A's temperature=0.4 left unchanged
  (measured stable, Rg growth 0.95×, zero escapes).

- **Mutation record** — five pre-specified mutations, each mapped to
  the test(s) that catch it; mutation 6 (broken icosahedron) added in
  Part 4.

---

## What Stage 3 Taught About the Process

### 1. First Published-Value Verification Target (Target E)

Targets A–D are invariants, scaling laws, or self-consistency checks.
Target E is different: it compares Terrium's output against an absolute
number from the literature (Hoare & Pal 1971, via the Cambridge Cluster
Database). That is categorically stronger because:

- The published value is independent of Terrium's code, its tests, and
  its reasoning. An invariant only tells you the code is self-consistent.
  A published value tells you the code matches reality.

- n=2, 3, 4 are exact by two independent routes: analytic derivation
  (all pairs at r_min) AND the published table independently lists
  −1.000000, −3.000000, −6.000000. Derivation and literature agree
  exactly.

- n=13 (Mackay icosahedron) has a checkable physical signature: the
  relaxed geometry is frustrated — centre-to-shell compressed
  (1.081838 < r_min), shell-to-shell stretched (1.137512 > r_min).
  That frustration is real physics, and asserting it catches a "scale
  applied to the wrong quantity" bug that a total-energy check alone
  could absorb.

This is the pattern to replicate: wherever a published value exists
for a domain's exact output, pin the implementation against it rather
than relying only on internal invariants.

### 2. A Retracted Claim Turned Into an Executable Guard

An earlier draft of the temperature amendment claimed Target A's
temperature=0.4 was above the published melting range (T* ≈ 0.26–0.30)
and had to change. Independent measurement disproved that: at
T_init=0.4 the cluster is stable (Rg growth 0.95×, zero escapes). The
reasoning missed that T_init ≠ T_equil — the fcc lattice at ρ=0.85
stores excess potential energy that converts to kinetic during
relaxation, so T_init=0.1 equilibrates UP to 0.288 while T_init=2.0
equilibrates DOWN to 0.750.

The implementers turned this retraction into an executable test:
`TestTemperatureBoundAmendment::test_flag_message_mentions_initialization`
asserts the flag message contains the words "initialization
temperature." A documented reasoning error became a guard that prevents
the same confusion downstream. That is the correct response to a
retraction — not just a comment, not silently adjusting a number, but a
test that encodes the corrected understanding.

### 3. The Eigenvector Sign Bug and Environment Discipline

Part 4 found a real bug in `wright_fisher_stationary_vector` that was
invisible on Python 3.13 and deterministic on Python 3.10 with numpy
1.26.4 — the pinned, CI-tested configuration.

**The bug:** LAPACK's eigenvector sign choice is arbitrary and differs
across builds. The code clamped first (zeroing a valid sign-flipped
vector), then normalised: 0/0 → NaN. The guard checked the pre-clamp
sum; the division used the post-clamp sum. Two different vectors.

**The fix:** orient toward positive orthant BEFORE clamping, then check
the total AFTER clamping.

**The lesson:** The operator's local Python (3.13.9) is outside the
range `requirements.txt` supports and CI tests (3.10–3.12). A green
run on an unsupported version is NOT evidence about the supported
configuration. This is now documented in `CONTRIBUTING.md` with the
eigenvector sign bug as the worked example.

Two regression tests now cover this:
- `test_stationary_vector_eigenvector_sign_regression` — real-path
  check using the pinned configuration
- `test_normalise_stationary_vector_sign_and_clamp` —
  build-independent test of the extracted helper
  `_normalise_stationary_vector` with a hand-constructed all-negative
  input. The old logic (clamp first) would produce NaN; the new logic
  correctly returns [0.2, 0.5, 0.3] summing to 1.

### 4. Mutation 6: Self-Contradictory Explanation Resolved

The mutation-6 record originally stated: *"The structural frustration
test also caught it (unexpectedly — the compressed/stretched pattern
holds for any subset of shell vertices)."*

As written that is self-contradictory: if the pattern holds under the
mutation, the test should pass, not fire.

**Resolution:** The qualitative pattern DOES survive the mutation (centre-to-shell still compressed, shell-to-shell still stretched). But the test asserts **exact numeric values** to 1e-5, not the qualitative relationship. Removing four vertices shifts the energy-minimising scale, moving both distances by ~8e-06 — exceeding the 1e-5 tolerance.

The test fired for a reason unrelated to the property its name
described. Fixed by adding an explicit qualitative assertion
`centre_to_shell < r_min < min_dist` alongside the numeric ones. The
numeric assertions pin the specific known structure; the qualitative
assertion states the physics the test is named for.

---

## Honest Status

### Closed (no further work in this stage)

- Molecular dynamics domain implementation and all five targets
- Temperature bound correction (0.8) with pinning tests
- Target E with published-value verification
- Mutation-6 record corrected and qualitative assertion added
- Eigenvector sign bug fixed with two regression tests
- __pycache__ files untracked (14 → 0 tracked; .pyc files remain on disk)
- CONTRIBUTING.md documents supported Python range (3.10–3.12) and the eigenvector sign bug as worked example
- All guard scripts pass: `check_rng_convention.py`, `check_dependencies_declared.py`

### Carried Forward (requires attention in Stage 4+)

- **Environment discipline:** The operator's local Python (3.13.9) is
  outside the supported range. Local-only green runs are not evidence.
  Consider adding a CI check or pre-commit hook that warns when the
  interpreter version differs from the pinned configuration.
- **Test count documentation:** Per the constitution, no test-count
  numbers in documents (they go stale). State "the full suite" instead.
- **Stage 4 domain recommendation** — see below.

---

## Stage 4 Domain Recommendation

**Recommended: Gillespie Stochastic Simulation Algorithm (SSA)**

**Why:**
- Completes the "discrete/stochastic" category alongside PCR, Monte
  Carlo, Wright-Fisher, and two-locus — but at the *reaction* level
  rather than the population level.
- Same verification discipline: exact closed-form (linear chains),
  independent solver (scipy's discrete-event), physical invariants
  (mass conservation, non-negativity).
- ADR 0005 applies directly (RNG convention: `np.random.default_rng(seed)`).
- No new runtime dependency (numpy only).
- Enables teaching-lab models that Wright-Fisher cannot: enzyme
  kinetics with stochastic effects, gene expression bursts, small-
  population epidemiology where the continuous SIR/SEIR ODEs are
  inappropriate.
- Natural extension: the same engine can later support τ-leaping as an
  optimisation (approximate, still exact for validation against the
  exact SSA).

**Not recommended for Stage 4:**
- Periodic boundary conditions / neighbour lists / cell lists for MD —
  out of scope per ADR 0006, would need new verification targets.
- External MD engine integration — violates the "no new runtime
  dependency" rule.
- Multi-species LJ or electrostatics — no published exact values for
  verification; would need new physics literature review first.

---

## Amendment (2026-08-01) — audit of this document, and one overturned recommendation

Stage 3 was audited end to end after this report was written. Every claim
above was re-checked against the repository. Three things came out of it.

### A1. The Stage 4 recommendation above is overturned

This report recommends Gillespie SSA as the Stage 4 domain. The reasoning is
sound *on its own terms* — it does complete the discrete/stochastic category,
ADR 0005 applies cleanly, and it needs no new dependency. But it was written
from inside the engine, with no visibility into the application layer, and
that layer changes the answer.

Measured during the audit:

```
engine simulate_* functions   8   (mm, sir, seir, pcr, monte_carlo_pi,
                                   wright_fisher, two_locus_wright_fisher,
                                   molecular_dynamics)
exposed by tellurium_runner   3   (run_mm, run_sir, run_seir)
```

**Five domains cannot be reached by any user of the product**, including
everything Stages 1, 2 and 3 produced. Adding Gillespie SSA as Stage 4 makes
that six. The verification rigour that makes this project unusual currently
stops at a boundary the product's users sit on the far side of.

Worse, the trust trail — the product's headline claim — has no verification
discipline applied to it at all. `tellurium_engine.py` contains no citation,
source, or organism field; provenance lives entirely in `queryResolver.ts` and
is re-attached to the response after the engine has run. A parameter resolved
from the wrong organism would be simulated faithfully and returned
`ok: true, flagged: false` with a citation attached. Nothing in the repository
would catch it.

**Revised recommendation:** Stage 4 is integration and CI coverage for the
application layer; Stage 5 is the provenance contract; domains resume at
Stage 6, by which point every new domain reaches the product automatically.
Full reasoning, with the file-by-file audit behind it, in
`Business/ARCHITECTURE_ASSESSMENT.md`.

Gillespie SSA remains a good domain choice and should be first in the queue
when domains resume.

### A2. Duplicate regression tests consolidated

The eigenvector fix arrived with two functionally identical tests —
`test_normalise_stationary_vector_handles_negative_sign` and
`test_normalise_stationary_vector_sign_and_clamp` — asserting the same
behaviour on the same input, one from each implementer. Consolidated into a
single test, keeping the better docstring and adding two assertions neither
had: an explicit finiteness check (the old logic's actual failure was NaN,
not a wrong value) and a sign-symmetry check that negating the input does not
change the result.

The removed copy also used `from Tellurium.tellurium_engine import ...`
inside the test body, while the rest of the file imports `tellurium_engine`
directly. That form only resolves because pytest inserts the rootdir into
`sys.path`; run from `Tellurium/` with a plain interpreter it raises
`ModuleNotFoundError`, and CI runs with `working-directory: Tellurium`. It
was redundant with the module-level import in any case.

### A3. Both regression tests verified against the old logic

The point of a regression test is that it fails on the bug. Confirmed rather
than assumed: the helper was reverted to clamp-before-orient and the suite
re-run.

```
MUTATED  FAILED test_normalise_stationary_vector_handles_negative_sign
MUTATED  FAILED test_stationary_vector_eigenvector_sign_regression
REVERTED 2 passed
```

Both fire. Neither is decorative.

### A4. One miscategorisation in this document

The "Carried Forward" list includes *"Test count documentation: per the
constitution, no test-count numbers in documents."* That is a convention this
report already follows, not outstanding work. Not carried.

## Final Verification

| Check | Result |
|-------|--------|
| Full suite (Tellurium/) | pass (the full suite) |
| Full suite (Tests/) | pass (the full suite) |
| ruff lint | clean |
| mypy type check | clean |
| shellcheck | clean (2 scripts) |
| check_rng_convention.py | OK |
| check_dependencies_declared.py | OK |
| __pycache__ tracked files | 14 → 0 |
| .pytest_cache / .hypothesis / .ruff_cache tracked | 0 |

No new runtime dependencies added. No passing tests modified except
as directed (eigenvector regression test strengthened). No new
domains, features, scenarios, or CLI commands added.

Stage 3 closed.
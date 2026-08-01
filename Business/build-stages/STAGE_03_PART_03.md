# Stage 3, Part 3 — Implementation

## 0. What was actually true when this part started

By the time this part began, `simulate_molecular_dynamics`,
`validate_md_params`, and `lennard_jones_force` already existed in
`Tellurium/tellurium_engine.py`, with a 576-line test file
(`Tellurium/tests/test_molecular_dynamics_correctness.py`, 54 tests)
already written against Part 2's spec — the same pattern Stage 2 saw
repeatedly: real implementation work landing in parallel, outside this
conversation, ahead of the point where this document would normally
dispatch the prompt. This part is the independent verification of that
already-landed work, not a description of a prompt being sent to a
blank slate.

## 1. The two-implementer model, for the record

OpenCode and FreeBuff receive Part 2's Section 11 prompt verbatim,
identically, per the model unchanged since Stage 1. Given implementation
had already landed by the time this part started, the practically
useful work here is the same shift Stage 2 made: verify what exists
against the spec first, rather than assume two fresh dispatches onto a
clean slate.

## 2. Mechanical verification, actually run

```
cd Tellurium && python3 -m pytest tests/test_molecular_dynamics_correctness.py -v
```
54 passed in 16.67s.

```
python3 scripts/check_dependencies_declared.py
python3 scripts/check_rng_convention.py
```
Both clean. The RNG guard confirms `simulate_molecular_dynamics` is not
on `check_rng_convention.py`'s `EXCLUDED_FNS` allowlist and complies —
resolving the one open question Part 2 Section 8 flagged rather than
assumed.

## 3. Spec-fidelity check

`lennard_jones_force`'s implementation — `magnitude = 24.0 * (2.0 *
r14_inv - r8_inv)` where `r14_inv`/`r8_inv` are built from `1/r²`
powers — is algebraically identical to Part 2 Section 2's closed form
(verified by hand: both reduce to $24[2(\sigma/r)^{14} -
(\sigma/r)^8]$ in reduced units). `_fcc_lattice_positions` rounds
`n_particles` up to the nearest `4k³`, matching Section 5's flagging
rule exactly (not silently substituting).

## 4. Independent mutation-test reproduction

The docstring's mutation-test record listed five pre-specified
mutations with predicted blast radius, but — unlike Stage 2's test
file at the equivalent point — none had yet been independently
reproduced. Reproduced mutation 2 (force sign flip) by hand, since it's
one of the two mutations Part 2 flagged as invisible to the energy/
momentum invariants — the highest-value one to confirm directly rather
than take on the spec's word:

Backed up `tellurium_engine.py`, changed
`magnitude = 24.0 * (2.0 * r14_inv - r8_inv)` to
`magnitude = -24.0 * (2.0 * r14_inv - r8_inv)`, ran the full MD test
file. Exactly 4 tests failed:
`test_force_attractive_at_r_1_5`, `test_force_repulsive_at_r_0_9`
(Target C itself), `test_force_signs_are_correct`, and
`test_force_magnitude_matches_closed_form` (the two tests written
specifically to catch this mutation). Critically, the other 50 tests —
including every Target A (energy) and Target B (momentum) test —
still passed, confirming by direct reproduction, not just prediction,
that a sign-flipped force really is conservative and momentum-
preserving. Reverted; confirmed 54/54 clean again afterward. This
correction is now recorded in the test file's own docstring, dated and
attributed, per the constitution's rule that the permanent record gets
updated, not just this conversation.

## 5. A finding, out of scope for this domain, flagged rather than absorbed

While running the full repo suite to confirm MD's isolation, a real,
reproducible failure turned up — unrelated to molecular dynamics
entirely. Four tests in `test_popgen_correctness.py`
(`test_stationary_vector_is_fixed_point` and three siblings) fail with
`nan` results, traced to a `RuntimeWarning: invalid value encountered
in divide` at `tellurium_engine.py:3230` (`v = v / v.sum()`, where
`v.sum()` is apparently zero for some input) — a new Markov-chain
stationary-vector feature, evidently mid-development elsewhere in
parallel with this stage. Confirmed this is fully isolated from MD:
`test_molecular_dynamics_correctness.py` and
`test_monte_carlo_correctness.py` both pass cleanly regardless. Per
this stage's own scope discipline (Part 1 Section 6, written explicitly
tighter after Stage 2's audit), this is recorded here as a known,
separate, currently-broken piece of Wright-Fisher — not silently
worked around, and not folded into Stage 3's work, since it has nothing
to do with this domain. It should be fixed before the *next* full-repo
audit calls the suite clean, but it does not block Stage 3 Part 4.

## 6. What Part 4 covers

Full suite + guard reproduction is already done here (Section 2), given
implementation had already landed. Part 4 covers the remaining
constitution-mandated steps: the diff-scope check against Part 2
Section 9's out-of-scope boundary, and the divergence-resolution
question (is there a second implementation to diff against, or — as in
this externally-landed case — is there only one report to check
critically rather than trust).

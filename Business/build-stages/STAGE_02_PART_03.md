# Stage 2, Part 3 — Implementation

**Note:** Claude Code (qwen3-coder:30b) was briefly added to this pipeline
and then removed — it was consuming unacceptable local resources on the
user's machine. This part uses the original two-implementer model
(OpenCode, FreeBuff) established in Stage 1. Nothing about the three-way
divergence reasoning drafted earlier survives here — it never received
real output to test it against, so there's no cost to dropping it
outright rather than keeping it as dead optionality for later.

## 0. What's actually true right now, stated plainly before anything else

The honest status of Stage 2's implementation:
`Tellurium/tests/test_popgen_correctness.py` exists (534 lines) — a real,
substantial test file, written against the Part 2 spec's Verification Continue building. 
Targets A through D and the pre-specified `2N`-vs-`N` mutation. It does
not currently pass, because it can't even be collected —
`from tellurium_engine import (... WF_PLAUSIBLE_MIN_POPULATION_SIZE ...)`
fails, because `Tellurium/tellurium_engine.py` has not been touched yet;
`simulate_wright_fisher` and `validate_wright_fisher_params` don't exist
there. Someone wrote the tests first and hasn't landed the
implementation, or landed them in a different order than Monte Carlo's
precedent (implementation and tests documented together).

This matters for this part specifically: it's a live example of the kind
of partial, asynchronous state Part 3 has to define rules for, rather
than assuming every stage's implementation step lands as one clean,
complete diff the way Monte Carlo's did. Nothing here is "reviewed" yet —
this is reported as current status, not certified as done. The concrete
action coming out of this part is getting an actual
`simulate_wright_fisher` implementation landed against the existing test
file.

## 1. The two-implementer model, unchanged from Stage 1

OpenCode and FreeBuff receive the exact same prompt text, independently:
`docs/CONSTITUTION.md` Section 3's preamble, the ADR 0005 pointer, and
the full Stage 2 Part 2 spec, verbatim, identical to both. Divergence
between them is signal, not noise, resolved per Stage 1 Part 4's existing
pairwise procedure (Section 7 of the constitution) — no extension
needed, back to the model that's already proven out.

## 2. Sending the actual prompt to both

The exact text is already built (Stage 2 Part 2, Section 2) — `docs/
CONSTITUTION.md` Section 3, the ADR 0005 pointer, and the full spec. Send
it, unmodified, to both OpenCode and FreeBuff.

Given the current state (a test file already exists, unclear which tool
wrote it or whether it was written against this exact spec version), the
practical first step is not necessarily "both implement from scratch."
Worth checking first: does the existing 534-line test file actually match
Part 2's spec faithfully (correct Targets A-D, correct pre-specified
mutation, correct validation bounds), or does it need reconciling before
either implementer builds against it? This is itself a small divergence
check — spec vs. existing test file — that should happen before two
parallel implementation attempts pile onto a foundation that might itself
need correction.

## 3. Reconciling the existing test file against the spec, first

A quick structural check of `test_popgen_correctness.py` against Part 2's
ten-field spec, without yet running it (it can't run — the import fails):

- Does it import the names the spec's Section 4 specifies
  (`validate_wright_fisher_params`, `simulate_wright_fisher`)? Confirmed
  yes, from the import error message itself — it's failing on a *missing*
  name, not an incorrectly-named one, which means whoever wrote it did
  read the spec's function names correctly.
- Does it reference `WF_PLAUSIBLE_MIN_POPULATION_SIZE` as a module-level
  constant — this wasn't explicitly named in Part 2's spec (the spec
  described the `population_size < 10` flagging threshold in prose, not as
  a named constant). This is a reasonable, spec-consistent naming choice
  (matching the pattern of `MC_PLAUSIBLE_MIN_SAMPLES` from Monte Carlo,
  `KM_PLAUSIBLE_MIN_MM`/`MAX_MM` from the kinetics domain) — worth noting
  as a *good* inference beyond the letter of the spec, not a deviation to
  flag critically.

This is a good sign about the test file's fidelity to the spec, as far as
can be checked without running it. The concrete next action, regardless
of which implementer ends up doing it: implement
`simulate_wright_fisher` and `validate_wright_fisher_params`
(and the `WF_PLAUSIBLE_MIN_POPULATION_SIZE` constant, and whatever other
constants the test file expects) in `Tellurium/tellurium_engine.py`,
matching this existing test file's expectations exactly, rather than
writing a fresh implementation and a fresh test file that might silently
diverge from each other.

## 4. What "done" looks like for this part, concretely

This part does not close with an implementation landed — it closes with
the actual dispatch to OpenCode and FreeBuff happening against a
test file already confirmed spec-faithful. The next part (Part 4) is
where verification happens once real implementation output exists to
verify — following the exact procedure Stage 1 Part 3/4 already
established: full suite, dependency guard, independent mutation-test
reproduction, divergence check between the two implementations.

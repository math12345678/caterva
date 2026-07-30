# Stage 2, Part 5 — Closing Report

Stage 2 of 100 is closed. 98 remain.

## What Stage 2 delivered

The second domain in Terrium, and the first stochastic domain built after
Monte Carlo (Stage 1): population genetics under neutral Wright-Fisher
drift. `simulate_wright_fisher` and `validate_wright_fisher_params` in
`Tellurium/tellurium_engine.py`, 45 tests in
`Tellurium/tests/test_popgen_correctness.py`, and ADR 0005 formalizing
the RNG convention (`numpy.random.default_rng(seed)`) that both
stochastic domains now share.

Both verification targets hold: heterozygosity decays at the exact
theoretical rate $(1-1/(2N))^t$ within statistical tolerance, and
fixation probability for a neutral allele equals its starting frequency
$p_0$ (Kimura, 1962) within tolerance. Bit-identical reproducibility
under a fixed seed and divergent trajectories under different seeds are
both confirmed.

## What Stage 2 actually tested about the pipeline itself, not just the domain

Three things happened this stage that weren't about Wright-Fisher's
biology at all — they were about whether the multi-agent process holds
up under real conditions, which is arguably the more important output of
each stage, Wright-Fisher included:

**A spec-level convergence, resolved for the first time.** Part 2 opened
with two independent spec-writing attempts (this conversation's draft,
and one already sitting in the repo) landing on the same domain with
minor naming differences and two substantive improvements in the
external version (`replicate_runs` as an explicit parameter, and ADR
0005's numpy-version BitGenerator finding). Stage 1's divergence
procedure had only ever been applied to code before; Part 2 applied it to
specs and ADRs instead, adopting the better external work rather than
re-deriving it. The procedure transferred cleanly — worth noting, since
it wasn't obvious in advance that a procedure designed for code diffs
would apply to prose without modification.

**A third implementer added, then removed, cleanly.** Claude Code
running qwen3-coder:30b locally was added mid-stage, and Part 3 was
drafted around a three-way divergence-resolution model for it. It was
removed before producing any real output, because it was consuming
unacceptable resources on the user's machine. Part 3 was rewritten back
to the two-implementer model. No trace of the three-way reasoning
survives as live process, and none needed to — it never got tested
against anything real, so there was nothing to preserve. This is worth
recording as its own small data point: not every addition to the
pipeline needs to become permanent, and reverting one cleanly, without
leaving half-updated documentation behind, is itself part of doing this
carefully.

**Two mutation-test overclaims caught by independent reproduction, both
now corrected in the permanent record.** The externally-committed
implementation report claimed the `2N→N` mutation would fail 3 tests;
independent reproduction found 2 (the record's "fixation target" claim
was wrong — that target runs under different parameters than the
mutation test actually used, so it's structurally untouched by this
particular mutation). The report claimed "skip the last generation"
would fail 2 tests; independent reproduction found 5 (the mutation
incidentally also breaks the `2N`-vs-`N` test's assertions via a
`KeyError`, before they even reach the decay-rate check). Both
corrections are now in `test_popgen_correctness.py`'s own docstring,
dated and attributed — not just in this conversation. This is the same
category of finding Stage 1 caught in Monte Carlo (OpenCode's
mutation-count correction), now confirmed twice across two different
domains: self-reported mutation blast radius is unreliable often enough
that the constitution's "always reproduce independently" rule (Section 6
Step 4) is pulling its weight, not just covering a hypothetical risk.

**A real bug in the verification tooling, found and fixed.**
`scripts/verify_domain.sh`'s Step 3 assumed every domain's test file
follows a `test_<domain>_correctness.py` naming convention. Wright-
Fisher's test file is named `test_popgen_correctness.py` — after the
spec's domain category ("population genetics"), not the specific model
name — which the script hadn't anticipated. It false-failed Step 3 until
patched to accept an optional explicit filename argument. This is
recorded in `docs/CONSTITUTION.md`'s amendment history, not just fixed
silently in the script.

## What's genuinely closed vs. what's carried forward

Closed: the domain implementation, its tests, ADR 0005, the verification
run against the actual committed code (not a description of the
procedure), both mutation-test corrections landed in the permanent
record, and the `scripts/verify_domain.sh` naming-convention fix.

Checked before writing this: Part 3 in the repo already matches the
corrected two-implementer version (confirmed via `git diff` against
`HEAD` — no staleness found). No carry-forward needed there after all;
worth checking directly rather than assuming, since the assumption would
have been wrong.

## Stage 3

Next stage's domain choice is open. Two candidates were on the table
back in Stage 2 Part 1 (population genetics, chosen, versus molecular
dynamics setup, deferred) — molecular dynamics is a natural next
candidate if a continuous-time or force-field-driven domain is wanted
next, to exercise the antimony → SBML → roadrunner path that neither
Monte Carlo nor Wright-Fisher touched (both are discrete). Alternatively,
a domain that deliberately needs that continuous-time path would be a
better test of the *other* half of Rule 3's continuous-vs-discrete
decision, since Stages 1 and 2 have now both landed on "discrete" and
that choice hasn't been stress-tested from the continuous side under
this constitution.

# ADR 0051: The evidence did not choose the value

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0047 (`evidence_rank`, which narrowed selection to the
non-dominated set and named this gap in its own docstring), ADR 0024
Decision 3 (Bakker's axes, adopted; her ensemble, declined), ADR 0029
(variants, the other half of what `min()` was reaching for)

## Context

Barbara Bakker's advice was that a parameter's reliability should drive
which value gets used:

> We gave each parameter a score based on its reliability and applicability
> […] These scores were then used to give the parameter a weight in the
> sampling.

ADR 0047 implemented the half that needs no weights. Candidates are narrowed
to the **non-dominated** set: a row is dropped only when another beats it on
every axis — assay completeness, what it states about the protein, organism
match. Among the survivors, selection remains `min()`.

`evidence_rank.py` says so plainly in its own docstring:

> That choice remains `min()` — and it remains arbitrary. Saying so is the
> point: the arbitrariness has been pushed to where it cannot pick a row […]

**Saying so in a docstring is not saying so to a user.** A student sees one
number. Nothing in the response tells them the evidence ranked several rows
equally good and a tie-break picked among them. The arbitrariness was
confined, documented, and still invisible at the only place it matters.

### What the corpus actually contains

Running the real frontier over the LDH turnover table:

```
92 rows  ->  6 non-dominated

    32      ref 670748   25°C, pH 8, wild-type enzyme, activated by FBP
    94.7    ref 761568   wild-type, pH 5.5, 30°C
  6467      ref 761568   wild-type, presence of D-fructose-1,6-diphosphate
    21.1    ref 684519   pH 6.0, 25°C, recombinant wild-type, in presence of FBP   <- returned
   250      ref 689763   pH 6.0, 25°C, recombinant wild-type enzyme
```

Six rows, every one wild-type with pH and temperature reported, spanning
**21.1 to 6467 — a 306-fold range**. `min()` returns 21.1, and nothing else
in the response says the evidence found 6467 equally credible.

A student gets a kcat that is two and a half orders of magnitude from
another value the ranking could not rank below it.

## Decision

`selection_tie.py` reports the tie: every non-dominated candidate, which one
was returned, each one's reference id and commentary, and the spread.

### A tie is not a defect — in the data or in the ranking

It means the three axes genuinely do not distinguish these rows. Two rows
that are both STRENDA-complete, both wild-type, both the requested organism
**are** equally well evidenced. Where their values differ, that difference
is disagreement in the literature.

Returning the minimum silently presents literature disagreement as a
measurement. The honest output is the number *and* the fact that the
evidence did not select it.

The reason text says both things explicitly, and both are tested: that the
tie-break is not justified by the evidence, and that the spread is
**disagreement, not a measurement uncertainty**. Those are different claims,
and presenting the second as the first would be the confident-wrong framing
this project treats as a defect.

### No threshold, for the fourth time

The obvious design asks whether the surviving values differ *enough* to
mention. That threshold is enzyme-specific and unsourced, so it is not
available — the same wall ADR 0026 (conditions), ADR 0028 (buffers) and ADR
0032 (concentrations) each hit, answered the same way: report the spread,
refuse the judgement.

So a tie is reported whenever more than one row survives and the values are
not all identical. Identical values are **not** reported: the evidence did
not choose, and nothing turned on the choice. Reporting them would be noise,
and noise is what gets a real finding skipped.

### This is not an ensemble

Bakker samples from a weighted distribution and rejects at the model level
after validating against flux data. ADR 0024 Decision 3 declined that and
the reason still holds: a teaching lab has no flux data to reject against,
and spread without a validation step *looks* like a rigorous uncertainty
estimate while being nothing of the kind.

This reports the alternatives the evidence could not rank. It does not
weight, sample or combine them.

## Verification

`Tests/test_selection_tie.py` (13), including a corpus-level test that runs
the real `evidence_rank.frontier` over parsed fixtures and asserts a tie is
findable — with an explicit `assert examined` so the test cannot go vacuous
if the fixtures change shape.

Eight mutations, all caught:

| Mutation | Failures |
|---|---|
| identical values reported as a tie (noise) | 1 |
| `is_tied` becomes a negative test | 1 |
| the tie stops naming which row was returned | 1 |
| alternatives lose their reference ids | 1 |
| a zero value reports an infinite fold-range | 1 |
| the reason stops calling the tie-break unjustified | 1 |
| the reason calls the spread an uncertainty | 1 |
| the spread stops being reported | 1 |

### Two mutations that did not mutate

Worth recording. Two of the eight initially reported "not caught", and both
were **no-ops**: the target strings span source-line breaks, so the
replacement never matched, and one hit the module docstring instead of the
reason text.

A mutation that does not change the code reports a false "not caught" — the
mutation harness's own version of a false green. The corrected runs assert
the produced output actually changed before running the suite.

## The boundary guards earned their keep immediately

Adding `KineticResult.selection_tie` **failed the build** on both boundary
guards (ADR 0045, ADR 0046) before a line of wiring existed:

```
- `KineticResult.selection_tie` has no entry in EMITTED_AS, so nothing
  says whether it crosses the boundary.
```

That is the first field added since those guards landed, and the mechanism
worked on its first real use. Under the previous regime this field would
have been computed, attached, and silently never emitted — which is exactly
what happened to four detectors in ADR 0039.

### And the second guard refused to let it stop there

With the field wired to TypeScript, `check_runner_boundary.py` passed and
`check_findings_reach_a_surface.py` did not:

```
selection_tie
    received by TypeScript, never reaches a rendering surface
```

Crossing the process boundary is not the same as reaching a reader — ADR
0040's whole point. The tie now goes into `provenance.flags`, the list the
CLI and web UI both render, naming each alternative with its reference id so
the row that was not returned can actually be looked at.

`selectionTieFlag.test.ts` (5) covers it, and three mutations are caught:
never pushing the flag (3 failures), firing it unconditionally so it becomes
noise (1), and dropping the reference ids so the alternatives are
unactionable (1).

## Consequences

- `KineticResult.selection_tie`, the wire key `selectionTie`, and
  `ScienceAgentResult.selectionTie` are new.
- `_best_evidenced` returns `(row, tie)` rather than a row. The tie is
  computed where `kept` exists; recomputing it at the call site would need a
  second frontier, and a second frontier is a second implementation.
- One exact-equality contract test needed updating. It was right to fail.
- 617 Python tests pass; `tsc --noEmit` clean.

## What this does not claim

It does not say which of the tied values is right, and it cannot. It does
not compare the tied rows on anything the three axes miss — cofactor state,
buffer, concentration — even though ADR 0032's machinery could: those
comparisons answer "were these measured the same way", and a tie is about
"is one better evidenced than another". Folding them together would let a
buffer difference silently resolve a ranking question.

The alternatives are listed with their commentary so a reader can apply
whichever of those judgements they think matters. That is the intended
division of labour, and it is the one Bakker's answer implies: the tool
scores what it can score, and does not pretend the remainder is settled.

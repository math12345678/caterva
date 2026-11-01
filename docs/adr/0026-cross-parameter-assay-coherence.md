# ADR 0026: Cross-parameter assay coherence

**Status:** Accepted, implemented

**Date:** 2026-08-13

**Relates to:** ADR 0010 (STRENDA assay conditions), ADR 0008 (parameter
provenance), ADR 0012/0013 (never default a parameter), ADR 0024 (the
expert correspondence that produced this)

## Context

ADR 0024 adopted two recommendations that both operate on one parameter at
a time: Jeske's organism gate, and Bakker's three reliability axes. Neither
can see the failure Jeske described in her second paragraph:

> Reaction conditions: pH value, temperature, cofactors, and buffers play a
> huge role in the reactions. The values in BRENDA come from thousands of
> different papers, each with different laboratory conditions. If you simply
> mix these together, the simulation will end up calculating with "fantasy
> numbers".

Caterva's own design makes this reachable. `mm_competitive_inhibition`
requires a Km and a Ki. `RESOLVABLE_FIELDS` resolves them with two
independent runner calls — separate lookups, separate citations, separate
assay conditions — and that independence is deliberate: ADR 0008 requires
it so a cross-species Ki can never inherit a verified Km's provenance.

The consequence is that a model can be assembled from a Km measured at pH
7.4 and 25 °C and a Ki measured at pH 6.0 and 37 °C. Both values are real.
Both citations resolve. Both assays are fully described, so both score
`complete` on assay completeness, `near` on condition proximity, and
`exact` on organism match. Every check the system had was green.

And the model describes no experiment anyone ever ran.

**Per-parameter scoring cannot catch this by construction.** The defect is
not located in either value. It is located in the pair. A check that only
ever looks at one parameter has no place to put the finding.

## The standard this rests on

The STRENDA Guidelines make temperature and pH mandatory on every reported
kinetic measurement. The reason they are mandatory is precisely this — the
numbers are not comparable or combinable without them:

> Swainston N, Baici A, Bakker BM, Cornish-Bowden A, Fitzpatrick PF,
> Halling P, et al. "STRENDA DB: enabling the validation and sharing of
> enzyme kinetics data." *FEBS Journal* 285(12):2193–2204 (2018).
> doi:10.1111/febs.14427, PMID 29498804.

Barbara Bakker, whose reply produced `reliabilityScore.ts`, is a co-author.
The two pieces of expert feedback turn out to be the same standard seen
from two sides: she described grading a parameter's applicability, and the
guideline she co-authored is what makes the grading possible at all.

## Decision

`assayCoherence.ts` assesses the resolved parameters as a set, and reports
one of four verdicts.

| Verdict | Meaning |
|---|---|
| `same_source` | Every parameter carries the same publication identifier. Jointly reported. |
| `same_conditions` | Different publications, identical reported pH and temperature. |
| `differing_conditions` | Different publications reporting different conditions. Deltas are named. |
| `unassessable` | Fewer than two parameters could be compared at all. |

### No threshold is invented

The obvious implementation picks a number — "more than 0.5 pH units apart
is incoherent." That number would be a fabrication with no source,
governing which models a student is told to distrust: exactly what this
project refuses to do with Km, one level up.

So every verdict is built only from facts that need no threshold. Same
identifier is a fact. Equality of two reported values is a fact. And when
conditions differ, the report states the spread and says plainly that the
values were never jointly measured — then stops, because whether 0.4 pH
units matters *for this enzyme* is a scientific judgement, and the reader
is the one holding the enzyme.

A caller may supply a `CoherenceTolerance`. It never creates or changes a
verdict; it only adds a sentence saying whether the observed spread
exceeded the tolerance the caller stated, and carries the `basis` that
tolerance came from. A test asserts the verdict is identical with and
without it.

### It reports; it does not block

ADR 0012/0013 govern whether a run may proceed, and they are about a
parameter being *unsourced*. Every value here is sourced. Turning a
description into a gate is how "these came from two papers" — the normal
case for any literature-assembled model, including published ones — would
start failing runs that are merely imperfect.

Bakker's own answer is the argument against blocking: she does not exclude
anything a priori, and rejects at the level of the whole model after
validating against measured flux data. Caterva has no flux data to reject
against. Naming the incoherence is what is left, and it is considerably
more than saying nothing.

The finding is pushed into `provenance.flags` — the list the CLI and web UI
already render — rather than only onto a new field. A finding filed
somewhere the user does not look is indistinguishable from no finding.

### `brenda_ec` is not a source identifier

An EC number names the enzyme, not the paper. Every Km and Ki for lactate
dehydrogenase shares `1.1.1.27`, so counting it as source identity would
report `same_source` for every pair of LDH parameters ever resolved — both
wrong and the most reassuring possible wrong answer. Identifiers are also
namespaced (`pubmed:740253` ≠ `brenda_ref:740253`), because both are short
numeric strings drawn from different registries and the collision is
entirely plausible.

### Only `origin === "resolved"` participates

A defaulted or user-supplied parameter has no assay behind it. Asking
whether a student's chosen `s0` is coherent with a measured Km is the
measured-quantity versus experimental-condition category error (ADR
0012/0013) in a new costume, and including defaults would let a model full
of made-up numbers report `same_conditions` because none of them disagreed.

## Verification

`assayCoherence.test.ts` (17) and `coherenceEndToEnd.test.ts` (8). Six
mutations to the judgement, each caught:

| Mutation | Failures |
|---|---|
| `brenda_ec` counts as source identity | 1 |
| `unassessable` becomes a pass | 1 |
| source identity loses its namespace prefix | 1 |
| `same_source` no longer requires every parameter identified | 1 |
| a supplied tolerance changes the verdict | 2 |
| a single pH is reported as a range of zero | 1 |

Two mutations to the plumbing. The first — never pushing the flag — was
caught. **The second was not, and that is worth recording.** Deleting the
`origin === "resolved"` filter broke nothing, because a defaulted parameter
also has no assay conditions and is dropped by the next check anyway. The
end-to-end test that claimed to cover the filter passed for an unrelated
reason.

A filter no test can break is a filter someone will remove as dead code,
and the day after that a default carrying conditions joins the comparison.
So the filter is now tested at its own level, against the case the resolver
does not currently produce and the next feature might. With that test, the
mutation fails.

This is the second time in two ADRs that verifying a claim found the claim
overstated. It is the argument for the verification step existing.

### Two things found by running the suites rather than assuming them

Neither is about coherence; both were blocking honest verification of it.

**The engine suite could not be read by its own guard.**
`check_no_silent_skips.py` reported "1 of 2 suite(s) did not run: engine" on
a suite that ran 1,032 tests and exited 0. `caterva/pytest.ini` sets
`addopts = -q`; invoking pytest with `caterva/tests` makes rootdir `caterva/`,
so the guard's own `-q` became the second one, and `-qq` suppresses the
summary line entirely. The guard now parses JUnit XML — exact counts, a
structural `skipped` element, and immune to a verbosity flag three
directories away.

It mattered that the guard refused to treat an unreadable suite as zero
skips. Had it defaulted to zero it would have reported a confident number
about a suite it never read.

**`resolvePythonExecutable` judged interpreters by filename.** It tried
`python3.13` through `python3.10` and never bare `python3`, so a container
shipping one fully-provisioned interpreter at `/usr/bin/python3` was told to
"install Python 3.12" when 3.12 was already present under another name.
`canRunSupportedPython` already verifies the version and every required
import, so the name was never what made a candidate valid. `python3` is now
tried last, after the version-specific names, so deliberate selection still
wins where several interpreters exist.

## Consequences

- `ResolvedSimulation` gains a required `assayCoherence` field.
- A `differing_conditions` verdict adds one entry to `provenance.flags`.
- Only `mm_competitive_inhibition` resolves two kinetic parameters today,
  so it is the only domain where the check currently has anything to say.
  It becomes more valuable as domains grow, which is the argument for
  building it before they do.
- Cofactors and buffer are **not** compared, though Jeske named them. The
  parser does not extract cofactors, and buffer is a free-text string whose
  equality is not meaningful. `same_conditions` says so in its own reason
  text rather than leaving the reader to assume four things were checked
  when two were.

## Not addressed here

Jeske's warning has a second half this ADR does not answer: even when
conditions match, values from different papers carry different measurement
error, and combining them compounds it. Bakker's ensemble is the real
answer to that, and ADR 0024 Decision 3 records why Caterva is not
attempting it without flux data to validate against.

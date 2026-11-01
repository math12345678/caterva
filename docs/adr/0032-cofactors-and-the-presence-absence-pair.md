# ADR 0032: Cofactors, and the presence/absence pair

**Status:** Accepted, implemented (extraction and comparison; not yet wired
into the TypeScript coherence report)

**Date:** 2026-08-14

**Relates to:** ADR 0026 (assay coherence — pH and temperature), ADR 0028
(buffers), ADR 0029 (protein variants), ADR 0024 (the correspondence that
produced all four)

## Context

Lisa Jeske named four things that make kinetic values incomparable:

> Reaction conditions: pH value, temperature, **cofactors**, and buffers play
> a huge role in the reactions.

ADR 0026 compared pH and temperature. ADR 0028 compared buffers and stated
plainly that cofactors were still not extracted at all. This closes the
fourth and last.

It was not built earlier because BRENDA reports cofactors in free text with
no consistent form, and "hard to parse" is a reason to leave something alone
rather than guess at it. What made it buildable was
`check_commentary_coverage.py` — a guard measuring the *residue*, the part of
each commentary that nothing reads. That turned "cofactors are hard" into a
list of exactly what was being discarded:

```
20 mM CaCl2                                x4
LDHB presence 0.125 mM NADH                x1
LDHB presence 0.15  mM NADH                x1
LDHB presence 0.2   mM NADH                x1
LDHB presence 0.25  mM NADH                x1
absence fructose 1,6-bisphosphate          x2
presence fructose 1,6-bisphosphate         x2
activated fructose 1,6-diphosphate         x3
presence D-fructose-1,6-diphosphate        x3
```

A measurement guard produced the work list. Worth noting on its own: the
guard was not built to find cofactors.

## The pair that motivated it

Two real rows from the lactate dehydrogenase fixture:

```
"pH 6.0, 25°C, recombinant wild-type enzyme in presence of fructose 1,6-bisphosphate"
"pH 6.0, 25°C, recombinant wild-type enzyme in absence  of fructose 1,6-bisphosphate"
```

Same enzyme. Same pH. Same temperature. Same organism. Same paper. Same
wild-type verdict. Same buffer (unstated in both).

**Every check Caterva had said these two rows were identical.** They are
opposite allosteric conditions — fructose 1,6-bisphosphate is the classic
activator of bacterial L-lactate dehydrogenase, and the pair exists in the
literature precisely because the two states differ.

The corpus also holds a Km series at four cosubstrate concentrations:

```
"LDHB, in the presence of 0.125 mM NADH"
"LDHB, in the presence of 0.15  mM NADH"
"LDHB, in the presence of 0.2   mM NADH"
"LDHB, in the presence of 0.25  mM NADH"
```

Four numbers, all correct, none comparable with the others.

## Decision

### 1. Presence is a first-class field, not a detail of identity

The obvious model is "which compounds were in the assay". **That model
cannot represent the motivating pair**, because both rows name the same
compound.

So `Effector.presence` is `present` / `absent` / `unstated`, and
`comparison_key` is `(compound identity, presence)`. Two effectors match
only when both agree.

`absent` is a real experimental statement — the curator wrote "in absence
of", meaning the paper deliberately measured without it. That is different
from `unstated`, where nobody said.

The mutation that drops `presence` from the comparison key fails three
tests, and the one that drops it in transit across the JSON boundary fails
the contract test. Both were run.

### 2. Identity comes from PubChem, by calling the existing module

The corpus spells one compound four ways:

```
"fructose 1,6-diphosphate"      "D-fructose-1,6-diphosphate"
"fructose 1,6-bisphosphate"     "fructose-1,6-bisphosphate"
```

String equality reports four different effectors. This is exactly the
problem ADR 0028 solved for buffers, so this module **calls
`buffer_identity.resolve_identity`** rather than growing a second
implementation.

Stating that out loud because ADR 0027 is the record of what happens
otherwise: two implementations of one idea, a parity test that passed, and a
third of the answer structurally unreachable through one of the call sites.

### 3. Concentrations are recorded and not compared

`0.125 mM NADH` and `0.25 mM NADH` resolve to the same compound with the
same presence and compare as `same`. The NADH series above is precisely the
case this misses, and a `same` verdict says so in its own reason text with
the concentrations printed.

Comparing them needs a threshold — how much of a difference matters — and
that is enzyme-specific and unsourced. Reporting the numbers and refusing
the judgement is what this project does with every other unsourced
threshold (ADR 0026, ADR 0028).

### 4. The buffer is not an effector

`"in 10 mM Tris, 20 mM CaCl2, pH 7.4, at 37°C"` contains both. The bare-salt
rule only fires on a concentration followed by a formula-shaped token
(`CaCl2`, `MgSO4`), so it takes the calcium and leaves the Tris to
`assay_conditions.py`, which already claims it.

The commentary is progressively consumed by the modules that understand each
part, rather than each module re-reading the whole string. The mutation that
loosens the salt pattern to any capitalised token fails the test asserting
Tris is not reported as a cofactor.

### 5. Report, do not withhold

Unlike ADR 0029's variants, an effector difference does **not** remove a row
from selection. A variant is a different protein; an effector is a different
condition, and ADR 0026 established report-not-block for conditions.

Following the existing rule rather than inventing a second policy for a
case that felt more alarming.

## Verification

`Tests/test_effector.py` (19). Every commentary is real, taken from the
parsed fixtures. Eight mutations, all caught:

| Mutation | Failures |
|---|---|
| `comparison_key` ignores presence (*the motivating pair collapses*) | 3 |
| `is_same` becomes the negative test | 3 |
| unresolved compounds report `same` instead of `unknown` | 1 |
| the presence/absence flip loses its special reason | 1 |
| a one-sided report is treated as `not_reported` | 1 |
| concentration dropped from the record | 2 |
| the bare-salt rule swallows the buffer too | 1 |
| absence clauses read as presence | 4 |

Plus a wire-contract test, and the mutation that drops `presence` during
serialisation — caught.

### The corpus test earned its place immediately

`test_extractor_finds_effectors_across_the_real_ldh_fixture` failed on its
first run. It pointed at `brenda_ldh_fixture.html`; the hand-picked strings
in every other test came from `brenda_ldh_kcat_fixture.html`, and the Km
table has no effector rows at all.

**Eighteen unit tests were passing at that moment.** They were all built on
an assumption about which fixture the strings came from, and none of them
could see it. The corpus-level test is the only one that touches the real
table, and it is the reason the mistake surfaced in minutes rather than in a
later ADR claiming coverage the extractor did not have.

Backups for every mutation run were verified with `cmp` before starting and
after restoring, following the failure recorded in ADR 0029.

## Consequences

- `BRENDAKmEntry.effectors` and `KineticResult.effectors` are new; the
  runner emits `effectors` with PubChem identities resolved.
- Identity resolution happens in the **runner**, not during parsing, so
  parsing a fixture stays offline and a PubChem outage degrades the identity
  rather than failing the lookup.
- One exact-equality contract test needed updating. It was right to fail.
- **Not yet wired into the TypeScript coherence report.** `assayCoherence.ts`
  compares pH, temperature and buffer; adding effectors there is the next
  step and is not done here. Said plainly rather than implied, because this
  ADR would otherwise read as closing Jeske's sentence end-to-end when it
  closes the extraction and comparison half.

## What this does not claim

Concentration is not compared. Order of addition, preincubation and
oxidation state are not represented at all. An effector present in the assay
but unmentioned by the curator is invisible — BRENDA does not distinguish
"absent" from "not mentioned", and the comparison says so when one side
reports nothing.

Saying that plainly matters, because the risk of adding a check is that its
existence gets read as an endorsement of whatever survives it. That sentence
now appears in `taxonomy.py`, `buffer_identity.py`, `protein_variant.py` and
here — four modules, one lesson.

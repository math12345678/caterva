# ADR 0169: The parent outvoted the child

**Status:** Accepted

**Date:** 2026-08-23

## Context

Two confusions dominated ADR 0168's residue: `seir -> sir` (8 across the
independent fixtures) and `gillespie_ssa_bimolecular -> gillespie_ssa` (7).
Both were named there as semantic nesting that no keyword mechanism
addressed.

Diagnosed rather than assumed, the cause turned out not to be coverage. The
child's distinctive phrase was usually right there in the query:

> "Can you show me how an infection spreads when there's a **hidden
> incubation phase**?"

`"incubation"` is an SEIR keyword and it matched. It lost anyway. Scoring
sums matched term lengths, so SIR collected `"infection"` (9) plus
`"spreads"` (7) for 16, against SEIR's `"incubation"` (10). Same shape in the
other pair: `"stochastic"` (10) beat `"a plus b"` (8), so a query naming two
reactants got the one-reactant model.

The flaw is structural, not a matter of weights. **Four of these domain pairs
are nested**: an SEIR epidemic *is* an SIR epidemic with one more
compartment; a bimolecular Gillespie run *is* a Gillespie run; competitive
inhibition *is* Michaelis-Menten with an inhibitor; two-locus Wright-Fisher
*is* Wright-Fisher at two loci.

So the parent's vocabulary is true of the child as well. `"infection"` and
`"spreads"` describe an SEIR epidemic exactly as well as an SIR one — they
are not evidence for SIR *over* SEIR, and summing them as though they were is
double-counting. The query said the one thing that distinguishes the two, and
the classifier answered with the general case anyway.

## Decision

**Declare the nesting, and promote on distinctive terms regardless of
score.**

`DomainDefaults` gains `refines?: SimulationDomain`, declared on the four
pairs above. After scoring picks a winner, `resolveNesting` asks whether the
winner has a child that `refines` it and whose *distinctive* terms — those
the parent does not also list — appear unnegated in the query. If so, the
child wins, whatever the scores were.

"Regardless of score" is the substance and deserves the scrutiny. It is not a
weight or a tie-break: a single distinctive phrase beats any amount of
accumulated parent vocabulary. That is defensible only because the
relationship is genuine containment — every parent term is true of the child
too, so no quantity of parent evidence is evidence *against* the child.
"Incubation phase" says SEIR, and no amount of "infection" and "spreads" says
otherwise.

Promotion uses `matchesTerm`, so ADR 0168's negation handling applies on this
path too: "no inhibitor involved" does not promote.

## Verification

| fixture | before | after |
|---|---|---|
| Groq `gpt-oss-120b`, 78 | 82.1% | **89.7%** |
| Mistral `small-latest`, 72 | 54.2% | **56.9%** |
| OpenRouter `gpt-4o-mini`, 78 | 75.6% | **76.9%** |

Improved on all three, regressed on none. The two target confusions fall from
8 to 3 and from 7 to 4. What remains at the top of the confusion table is now
coverage — queries falling through to the `mm` fallback — not nesting.

**Over-promotion, the failure mode this rule was most likely to have, did not
occur.** Across all 228 fixture queries, the number of parent queries wrongly
given the child model is **zero**. Two things bound it: the negation handling,
and the requirement that the promoting term be one the parent does not share.

Mutations, `docs/mutations/adr-0169-nested-domains.json`:

| id | mutation | caught |
|---|---|---|
| P1 | promotion removed; the scored winner stands | yes |
| P2 | promotion fires on terms the child and parent share | **no** |
| P3 | promotion ignores negation | yes |

**P2 is NOT CAUGHT, and is reported that way rather than papered over.** No
declared pair shares a single keyword — measured, all four pairs, zero
overlap — so the distinctiveness filter removes nothing today and deleting it
changes no classification. It is kept because it costs nothing and is correct
whatever the table later holds; keyword lists change, and 120 terms were
added to them one ADR ago. An invariant test asserts the zero-overlap fact
directly, so the day someone adds a term to both a child and its parent, that
test fails and tells them the filter has stopped being decorative.

Making P2 catchable would have meant inventing an overlap no classifier
needs, which is fitting the evidence to the table.

Full api-server suite: **696 tests, all passing.**

## Consequences

A student who describes a latent period gets a model with one. The four
`refines` declarations are now the place that fact lives, and
`refinementPairs()` exposes the graph so its shape is asserted on data rather
than inferred from classifications.

**What this does not check.**

- **Whether these are the right four pairs.** Nothing verifies that
  `repressilator` is *not* a refinement of `cell_cycle_oscillator`, or that
  no fifth pair is missing. The four are argued from the domain definitions
  and asserted nowhere.
- **The distinctiveness filter is unexercised.** See P2 above. It is correct
  and currently inert.
- **The promotion rule is absolute by design**, and that is a real risk if a
  future keyword is both distinctive and common. Nothing bounds it beyond
  negation and distinctiveness, and no measurement here explores what a badly
  chosen child term would do.
- **10 under-promotions remain** — child queries still getting the parent —
  and they are coverage, not scoring: "two different molecules combine into
  one" carries no bimolecular term at all. Widening that vocabulary is a
  separate decision, and the risk of widening it is precisely the
  over-promotion this record measured at zero and would need to re-measure.
- **Still nobody's real questions.** Five labelled sets, no student wrote a
  line of any of them.

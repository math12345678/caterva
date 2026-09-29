# ADR 0206: A toggle switch is not a repressilator

**Status:** Accepted
**Date:** 2026-09-24

## Context

CI failed on one test out of 993:

```
FAIL src/__tests__/frontDoorRouteCoverage.test.ts
  > the fallthrough's three previously-unrecognized queries
  > answers the toggle switch with a composed structure
AssertionError: expected undefined to be truthy   (composition?.rule)
```

The query is *"a toggle switch between two repressors"*. It is supposed to
fall **through** keyword classification, because no catalogue domain is a
toggle switch, so that the compositional grammar answers it as a mechanism.
On this branch it stopped falling through: it classified as
`repressilator`, ran as a repressilator, and returned no composition at
all.

The cause is a keyword ADR 0191 added to the repressilator: **`"repress"`**,
which occurs inside **"repress*ors*"**. Matching was plain substring
containment, so the word "repressors" was read as the keyword "repress".

The word is not evidence for the repressilator in any case. A toggle switch
is built out of repressors too -- two of them, mutually repressing. The
keyword names something both circuits share and neither owns, which is the
same mistake as scoring a shared term in a nested pair (ADR 0194), arrived
at from a different direction.

A second keyword in the same list was worse and had no substring excuse:
**`"e. coli"`**. Measured, *"how fast does E. coli grow in glucose"*
classified as a repressilator. E. coli is the organism the Elowitz-Leibler
circuit was built in -- a fact about the paper, not about the question. A
host organism is not a mechanism.

Both keywords are mine, from the classifier work in ADR 0190/0191. They
were added to fix real misclassifications and were never checked in the
other direction: what else do they now claim?

This is ADR 0205 one layer up, found the day after it, in code I had
written rather than code I had inherited. There, enzyme abbreviations
matched inside longer words (`acc` in "unva**cc**inated"). Here, domain
keywords do. The difference in how each was found is the part worth
keeping: 0205 surfaced because a length-weighted score made a latent bug
decisive, and this one surfaced only because an end-to-end test drove a
real HTTP job and noticed a missing field -- it reported the symptom
(`composition.rule` undefined), not the cause.

## Decision

Keyword matching requires a word boundary.

`keywordEvidence` filters literal occurrences through `isWholeWordAt`: an
occurrence counts only if the character before and after are not
alphanumeric where the keyword's own edge is. `"repress"` no longer matches
"repressors"; `"ring"` no longer matches "bring".

Inflections are not lost. The stem path below the literal one still finds
"spreads" for the keyword "spread", at the half credit ADR 0204 gave it,
which is the correct relative weight for a match the query did not write
literally.

`"e. coli"` is removed from the repressilator's keywords, with the reason
in place of the entry so it is not added back.

## Consequences

The toggle switch falls through again and is answered as a composition. The
E. coli growth question falls through instead of being answered as a
synthetic oscillator.

Nothing else moved: all 22 classification assertions across `nestedDomains`,
`classifierEval` and `domainClassification` still pass, `nestedDomains`
15/15, `classifierEval` 17/17 and `enzymePatternBoundaries` 16/16 run green
under bun, and the labelled benchmark is unchanged at **53/53** with the
held-out split still at least equalling dev.

`keywordsAreWords.test.ts` asserts the property directly, including the
bounding direction (a keyword the query writes as a word must still match,
and an inflected one must still be found through the stem path).
Mutation-checked: removing the boundary filter fails it.

**The cheap test did not exist and the expensive one did the work.** A
whole HTTP job had to run for a keyword-matching bug to be noticed, and
what it reported was a missing field three layers from the cause. That is
the argument for the unit-level assertion, not for the end-to-end test,
which was right to exist and right to fail.

**Named as not checked:** the remaining repressilator keywords -- `three
genes`, `ring`, `synthetic`, `blinks`, `shutting off the next` -- were
reviewed for substring traps and boundary matching now covers those, but
nobody has asked of each keyword in any domain *"what else does this
claim?"*. That question is what found both defects in this record, and it
has been asked of one domain out of fifteen.

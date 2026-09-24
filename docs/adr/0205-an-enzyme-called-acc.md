# ADR 0205: An enzyme called "acc"

**Status:** Accepted
**Date:** 2026-09-24

## Context

`matchEnzyme()` recognises ~25 enzymes by name, each as a regular
expression with the common abbreviation as an alternative:

```ts
pattern: /acetyl.?coa carboxylase|acc/i,
```

None of the 25 patterns used a word boundary. `/…|acc/i` therefore matches
the "acc" inside **unva*cc*inated**, and this was found exactly there: the
query *"Model how measles spreads through an unvaccinated school"*
classified as enzyme kinetics, because a school outbreak was read as
acetyl-CoA carboxylase.

Measured across ordinary words, five enzymes fire on text that has nothing
to do with them:

| substring | matches | enzyme returned |
|---|---|---|
| `acc` | unvaccinated, vaccine, accurate, according, accumulate | acetyl-CoA carboxylase |
| `sod` | **sodium** | superoxide dismutase |
| `ache` | headache, teacher | acetylcholinesterase |
| `adh` | adhesion | alcohol dehydrogenase |
| `cox` | coxsackie | cytochrome c oxidase |

`sodium` is the one to look at twice. A chemistry query mentioning sodium
gets superoxide dismutase, with a verified EC number attached.

There is a second defect of the same shape and the table's order decides
it: `/trypsin/i` is declared before `/chymotrypsin/i`, and matches inside
it. **Every query about chymotrypsin returned trypsin** -- a different
enzyme, a different EC number (3.4.21.4 rather than 3.4.21.1).

This is not only a classification concern. `matchEnzyme` also feeds entity
extraction, so the wrong EC number is what the literature resolution then
goes looking for.

The bug is old and was latent, not dormant by luck: under the previous
count-based scoring a spurious enzyme hit added `+2`, usually too small to
change the winner. ADR 0204 put classification into length units, where the
same hit is worth 22, and the defect became visible immediately. **The
merge did not introduce it; it raised the gain on a signal that was always
wrong.**

## Decision

Every alternative that is plain letters, digits and spaces is wrapped in
`\b…\b`. Applied mechanically to all 24 patterns, and deliberately *not*
applied to alternatives containing groups or escapes, which would mean
rewriting regexes whose intent is not obvious from the line.

Word boundaries are the whole fix: an abbreviation is a word, and the
patterns always meant it as a word.

## Consequences

All ten measured false positives stop matching; every true positive still
matches, including the bare abbreviations the alternatives exist to catch
(`LDH activity`, `SOD assay`, `G6PD deficiency`, `hexokinase HK1`).
Chymotrypsin now returns chymotrypsin.

`src/__tests__/enzymePatternBoundaries.test.ts` asserts both directions,
and asserts the **property** on the table rather than only the ten words
that happened to be found: no alternative made of plain letters and digits
may appear without a word boundary. A pattern added tomorrow is covered
without anyone having to think of the word that would break it.

Mutation-checked rather than assumed: putting the single alternative `acc`
back unbounded fails six of the assertions, naming both the innocent words
it starts matching and the unbounded alternative itself. A test written
after a fix usually passes; this one was shown to fail without it.

What made this findable was running the code rather than reading it. The
pattern is plainly wrong once seen, and it had been read past repeatedly.

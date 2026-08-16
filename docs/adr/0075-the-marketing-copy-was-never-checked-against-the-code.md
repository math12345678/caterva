# ADR 0075: The marketing copy was never checked against the code

**Status:** Accepted

**Date:** 2026-08-15

**Related:** ADR 0071 (the testimonials were not real),
`check_documented_counts.py`, `docs/ARCHIVE_TRIAGE.md`

## The gap

ADR 0071 removed five fabricated testimonials and closed the
*fabricated-people* case. It did not touch the *fabricated-numbers* case on
the same pages.

`check_documented_counts.py` has kept `README.md` honest about test and
domain counts for months. Nothing did the same for the pages a visitor
actually reads. Four claims had drifted:

| claim | reality |
| --- | --- |
| "rk4 (adaptive)" in the terminal panel | `simulate.ts` uses `h = dt / substeps` with a constant 200 substeps, no error estimate, no step rejection. Fixed-step. |
| "304+ tests and counting" | 1,113 engine + 714 literature |
| "Planned: PCR, Monte Carlo, population genetics, molecular dynamics" | all four ship in `Terium/discrete/` |
| "validated ... to 1e-10 tolerance" | tolerances range from 1e-10 on analytic cases to 1e-4 where a stochastic method makes tighter meaningless |

**Only one of the four flattered the product.** Three made Terrium look
worse than it is — a five-times understated test count, four shipped
domains advertised as unbuilt. That is the finding worth keeping: this is
not a check against exaggeration, it is a check against *unverified*
claims. A number nobody checks drifts in whichever direction the last edit
happened to go, and "it errs on the modest side" is luck rather than
policy.

The "adaptive" label is the exception and the one that would have mattered
to a scientist. A reader deciding whether to trust a simulation for
teaching cares a great deal whether the integrator controls its own error.

## Decision

`scripts/check_public_claims.py` holds phrases that must not appear on a
public page, each paired with **the fact that makes it wrong** and **a
predicate that re-derives that fact from the code**.

The predicate is the part that matters. A forbidden-phrase list decays into
superstition: nobody remembers why `"rk4 (adaptive)"` is banned, so
somebody eventually unbans it. Here `_integrator_is_fixed_step()` reads
`simulate.ts` on every run, and if real step adaptation is ever added the
guard **fails** — telling the maintainer the word is now accurate and the
rule should go, rather than silently forbidding a true statement.

Every predicate runs whether or not its phrase appears, and a predicate
whose evidence file has vanished fails. A check whose evidence is gone has
not passed.

## What the guard found that I had not

I fixed the tolerance sentence in `FAQSection.tsx` by hand and considered
it done. The guard immediately found the same claim in `TrustSection.tsx`
and `WorkflowCompare.tsx`.

Fixing the instance you happened to read is not fixing the claim. That is
the entire argument for mechanising this rather than proof-reading it once.

## Verification

Re-derivable as a set file — `docs/mutations/adr-0075-public-claims.json`:

```
python3 scripts/mutate.py --set docs/mutations/adr-0075-public-claims.json
```

All five reproduced rows `caught` under the harness. Original run:

Six mutations, `cmp`-verified backups:

| Mutation | Caught |
| --- | --- |
| A contradicted claim found but not reported | 4 failed |
| The `CLAIMS` table emptied | 4 failed |
| A stale predicate no longer fails the guard | 1 failed |
| The fixed-step predicate stops reading the file and returns True | 1 failed |
| Matching becomes case-sensitive | **NOT caught** |
| — after adding a differently-cased replay | 1 failed |

The escape: every replay test used the exact casing found in the source, so
making the match case-sensitive changed nothing any test could see.
`"RK4 (Adaptive)"` in a heading would have sailed through — and headings
are precisely where marketing copy gets title-cased.

That is the fourth assertion this session satisfied by something other than
what it was meant to check. The pattern across all four is the same: the
test was written against the input that already existed rather than against
the space of inputs the guard must survive.

## A related correction

While fixing `TrustSection.tsx` I also changed "roadrunner" to
"libRoadRunner" — its actual name, and the one `NOTICE` attributes.
Getting a dependency's name wrong on the page that credits it is a small
thing, but it is the same failure as everything else here: nobody checked.

## Still not covered

`Business/` — the pitch deck and fundraising tracker are investor-facing
and outside `PUBLIC_TREES`. The same class of drift is more consequential
there, and `.pptx` and `.docx` are not greppable by this guard. That gap is
named here rather than left to be discovered.

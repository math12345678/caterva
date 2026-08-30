# ADR 0192: Mentioning a thing to exclude it

**Status:** Accepted

**Date:** 2026-08-23

## Context

Four queries from ADR 0191's LLM-authored fixtures were classified as
competitive inhibition:

> "...as I add more substrate, **no inhibitor** involved."
> "...the typical hyperbolic curve for an enzyme **without any inhibitors**?"
> "Can you run a kinetic assay **without any inhibitors** present?"
> "What's the velocity curve like when **no inhibitor is blocking** the enzyme?"

Every one of them says there is no inhibitor. Every one was given the
inhibitor model, because the matcher saw the word and had no way to see the
"no" in front of it.

This is worse than an ordinary miss. The student who took the trouble to be
explicit got the worst answer available: naming a thing in order to rule it
out made that thing *more* likely to be selected, not less. Being precise was
punished.

## Decision

**A keyword counts only where at least one of its occurrences is not
preceded by a negator** — one of twelve literal words (`no`, `not`,
`without`, `absence`, `free`, `lacking`, …) within four words before the
match.

Deliberately shallow. It has no notion of scope, so "not sure how the
inhibitor works" reads as an absence when it is not. That limit is asserted
as a test rather than described, so a future reader finds it where they will
be looking, and so that implementing real scope handling fails the test and
announces itself.

## Verification

Ablation across the three independent fixtures:

| fixture | without negation | with negation |
|---|---|---|
| Groq `gpt-oss-120b`, 78 | 79.5% | **82.1%** |
| Mistral `small-latest`, 72 | 51.4% | **54.2%** |
| OpenRouter `gpt-4o-mini`, 78 | 75.6% | 75.6% |

Positive on two, neutral on the third, negative on none. The
`mm -> mm_competitive_inhibition` confusion — four occurrences across the
fixtures — disappears entirely.

Mutations, `docs/mutations/adr-0168-negated-keywords.json`:

| id | mutation | caught |
|---|---|---|
| N1 | the negation check removed entirely | yes |
| N2 | only the first occurrence checked | yes |
| N3 | negator list cut to the words the bug was reported with | yes |

**Two of those three were NOT CAUGHT on the first run, and both of my tests
were passing for the wrong reason.**

The every-negator test asserted `domainOf(...) === "mm"` over phrasings like
*"enzyme kinetics in the absence of an inhibitor"*. It passed whether or not
negation worked, twice over: `"enzyme kinetics"` outscores `"inhibitor"`
anyway, and where it does not, the `mm` **fallback** returns `mm` regardless.
It now asserts `matched === false` on queries carrying no keyword but the
negated one, which is the question actually being asked.

The later-mention test negated one word and asserted a *different* one, so
the first occurrence of the keyword under test was never the negated one and
N2 sailed through. It now uses the same word twice — *"With no inhibitor
first, then with an inhibitor."*

## The `ki` detour

Sharpening those tests turned one red: *"Run it lacking an inhibitor."* still
selected the inhibition model. The cause was `"ki"` — a two-character keyword
this record's predecessor added — matching inside `"la**cki**ng"`. Negation
could not help, because the fragment sits inside a word no negator precedes.

The obvious repair was to restore the word-boundary regex ADR 0191 deleted.
Measured, it **costs** accuracy: 82.1% → 80.8% and 54.2% → 52.8%, with a
quarter more fallbacks, because boundaries also stop `"decay"` matching
`"decaying"`.

The defect was never the matcher. It was a two-character keyword in a table
whose scoring assumes terms are long enough to mean something. `ki` is a
parameter name, not something a student writes in a sentence, and
`extractParameterOverrides` already reads `ki=0.5` on its own path. It was
removed from the keyword list and the matcher left alone — which vindicates
ADR 0191's deletion rather than reversing it, and narrows its lesson to:
*check the shortest term in the table before reaching for the matcher.*

## A fixture that was not a measurement

Fixtures were generated from three more providers. SiliconFlow and TokenRouter
failed every domain — and the generator **wrote both files anyway**, as valid
JSON with an empty `queries` array. The benchmark scored them `0/0`, printed
`NaN%`, and reported the spread across "five" sets as `NaN points`. Nothing
errored. A reader would have counted five rows and believed five measurements
existed.

The generator now refuses below eight domains and exits 3; the benchmark
excludes empty fixtures and names them as absent measurements rather than
scoring them. Both empty files were deleted rather than committed.

This is the same defect as the rest of the record, one level up: an absence
presented as a result.

## Consequences

`make classifier-bench` — `runKeywordBenchmark.ts` — scores every labelled
set offline, from committed fixtures, with no API key. It prints one row per
set and **refuses to print an aggregate**, because ADR 0191 established that
this classifier has no single accuracy; a mean over 54.2% and 82.1% describes
no reader's situation.

Full api-server suite: **681 tests, 680 passing.** The one failure is
`betaGammaFromR0Provenance.test.ts`, which is marked `(real, unmocked)` and
calls a live external API; it fails intermittently on an upstream 503 and
passes on its own. Verified unrelated to this change by running it against
both this branch and the pre-change file. It is a pre-existing flake and is
recorded rather than described as green.

**What this does not check.**

- **The four-word window is a judgement.** Nothing in the suite fails if it
  were three or five. It was not tuned, and no measurement supports that
  number over its neighbours.
- **Negation scope is not implemented.** "not sure how the inhibitor works"
  is read as absence. Asserted as a known limit, not fixed.
- **Only English, only these twelve words.** No morphology, no "n't"
  contractions attached to other verbs, nothing multilingual.
- **The two dominant confusions remain untouched:** `seir -> sir` (8 across
  the fixtures) and `gillespie_ssa_bimolecular -> gillespie_ssa` (7). Both
  are semantic nesting — one domain's description is nearly a subset of the
  other's — and no keyword mechanism in this record addresses them.
- **Still nobody's real questions.** Five labelled sets now exist and no
  student wrote a line of any of them.

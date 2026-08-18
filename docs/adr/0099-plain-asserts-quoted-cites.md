# ADR 0099: Written plainly is an assertion; written in quotes is a citation

**Status:** Accepted

**Date:** 2026-08-16

## Context

`make guards` exited 1 on this:

```
Docw/terrium_full.docx                    also: claims "Tellurium integration"
```

That line is in `docs/REMOVE_CONFIDENTIAL_FROM_HISTORY.md` — the plan for
removing those files. It names the offending phrase so somebody can find it.
`check_no_tellurium_integration_claims.py` matched `tellurium integration`,
found no denial word on the line, and reported the document as claiming
Terrium is built on Tellurium.

**The document planning the cleanup was the one blocking CI.** The only way
to go green without a code change would have been to describe the offending
files too vaguely for anyone to act on them.

This is the third time in one session that a guard has confused citing a
claim with making one:

| guard | the sentence it flagged | what the sentence was doing |
|---|---|---|
| `check_documented_counts` | *"three onboarding documents claiming 22 guards and 1,291 tests"* (`docs/FIRST_TASKS.md`) | warning about the exact defect the guard exists to catch |
| `check_documented_counts` | *"a guard that printed 'every collected test ran' while 275 tests failed"* (`docs/readmes/business.md`) | recording a real incident |
| `check_no_tellurium_integration_claims` | *`also: claims "Tellurium integration"`* | inventorying what to remove |

Every one of them is a document doing the thing the project most wants
documents to do: writing down what went wrong, specifically enough to act
on. A guard that punishes that teaches the next author to be vague.

## Decision

**State the convention once, because it keeps being rediscovered:**

> A claim written plainly is an assertion and is checked. The same words in
> quotation marks or backticks are a citation and are not.

It was already implemented, in `check_documented_counts.is_quoted`, with a
good comment explaining it — and it was implemented for counts, so the next
guard to read a *phrase* had no reason to look for it. The rule is about
claims, not numbers.

`is_quoted` is deliberately slightly over-permissive: a writer who wants a
count checked writes it plainly, and one who wants to cite a stale figure
needs a way to say so. Over-permissive costs a missed stale claim;
over-strict costs a build that cannot go green without corrupting an
explanation. The first is recoverable.

**For this guard, the repair is one `DISCUSSES` entry, not a new rule.**
The mechanism already existed — documents whose subject *is* the
contradiction, which quote the claims in order to record them — with
`Business/LEGAL_BRIEF_NAMING.md` and `docs/PRIVACY.md` already in it. Its
author chose per-document exemption with written reasons and said why.
Changing that to per-sentence quoting is a redesign, and belongs to whoever
owns the design rather than to the pass that happened to hit the false
positive.

**The exempt sets are pinned.** Each `DISCUSSES` entry blinds the guard to a
whole file, so a genuine new claim inside one goes unseen. Two entries was
acceptable; three is where it starts to matter.
`Tests/test_no_tellurium_integration_claims.py` pins both sets — not a ban
on growth, a requirement that growth be a decision somebody made.

**The guard now has a test file at all.** It had none, which the Stage 4
amendment (b) forbids: *a guard is not delivered until something runs it
unasked.*

## Consequences

- `make guards` runs to completion.
- The exemption cannot outlive its justification: the test fails if the
  document stops quoting a claim, at which point the entry covers a whole
  file for nothing and should go.
- 8 tests now cover a guard that had 0.

### What this does not fix

`Docw/terrium_spec.docx` and `Docw/terrium_full.docx` remain in `HISTORICAL`
— dated records that assign "Tellurium integration" to a named engineer.
Whether they should stay published is the author's call, unchanged by this,
and `Business/LEGAL_BRIEF_NAMING.md` 3a is where it is argued.

## Mutations

```
python3 scripts/mutate.py --set docs/mutations/adr-0099-plain-asserts-quoted-cites.json
```

| id | mutation | result |
|---|---|---|
| T1 | the remediation plan loses its exemption | caught |
| T2 | one of the two quoted claims is removed | **not caught, correctly** |
| T3 | `CLAIM` stops matching the bare phrase | caught |
| T4 | a document joins the exempt set without a decision | caught |
| T5 | a denial is read as a claim | **escaped first** |
| T6 | the blind-scan floor is removed | caught |

**Three rows were wrong before they were right, and two of the errors
produced a PASS**, which is worse than producing a false gap:

- T2's first version removed one of *two* claim sentences in the document,
  so the assertion it was meant to break stayed true. Its final form is kept
  as NOT CAUGHT deliberately: the real mutation needs two edits, `mutate.py`
  applies one per row, and the property is verified by hand instead
  (`sed -i 's|Tellurium integration|REDACTED|g'` gives `1 failed, 6 passed`).
  Recorded as a harness limitation, because an unexplained NOT CAUGHT reads
  as a gap.
- T3's first version edited a fixture string inside the guard's own
  `_selftest` rather than the `CLAIM` regex.
- T4's first version mutated the pinning *assertion* into a tautology and
  passed — correctly, since a test edited to be vacuous is
  `check_no_vacuous_tests.py`'s job, not pytest's. It now mutates the exempt
  set itself.

**T5 found a real gap.** Deleting `not` from the `DENIAL` alternation passed
every test, because all four denial sentences carried two or three markers
each — *"is not"*, *"does not"*, *"unaffiliated"* covered for the missing
one. **Over-specified test inputs prove less than they appear to.**
`test_each_denial_word_carries_its_own_weight` now isolates one marker per
sentence.

## Related

- ADR 0097 — the same distinction, applied to counts, one pass earlier
- ADR 0095 — quoted examples must survive `--write`
- ADR 0069 — why mutation results ship as re-runnable set files

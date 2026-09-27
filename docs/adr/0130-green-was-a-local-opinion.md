# ADR 0130: Green was a local opinion

**Status:** Accepted, partially implemented — the api-server job is still red

**Date:** 2026-08-20

**Context:** `.github/workflows/tests.yml`,
`scripts/check_no_tellurium_integration_claims.py`,
`scripts/check_guard_wiring.py`

## The finding

Caterva's CI has failed on **every commit for roughly two weeks**.

The evidence was not in the repository. It was in the owner's inbox: seven
GitHub notifications, one per commit pushed during this session, each
reading *"All jobs have failed"*. Searching further back:

```
2026-07-24  f30d716   all jobs failed
2026-08-05  6663fc1   python jobs SUCCEEDED (3m48s); api-server failed
2026-08-06  f8c2e81   all jobs failed
2026-08-08  f443026   api-server failed
2026-08-12  be63f84   all jobs failed
2026-08-18..20        every commit of this session, all jobs failed
```

Every pass this session ended with a line like *"literature 900 green,
guards green"*. Every one of those statements was true of a sandbox and
false of the repository. **`main` was red the entire time.**

This is the defect this codebase spends its whole effort on — a check that
reports on something adjacent to what it names — turned on the project
itself. "The tests pass" meant "the tests I chose to run, on the machine I
happened to be on, pass". CI is the one that runs on a fresh checkout, and
CI is the one a stranger sees.

## What was actually broken

**1. The tellurium guard flagged the ADR about the tellurium guard.**

`check_no_tellurium_integration_claims.py` reported
`docs/adr/0099-plain-asserts-quoted-cites.md` — a document whose entire
subject is three guards confusing a citation with an assertion. I noticed
this four passes ago, labelled it "another agent's", and moved on. It is in
the CI workflow, so it failed all three Python jobs on every push while I
was calling it not mine.

Two causes, both fixed:

- The quoted occurrence. ADR 0099 states the convention — *"a claim written
  plainly is an assertion and is checked; the same words in quotation marks
  or backticks are a citation and are not"* — and notes it was implemented
  for counts as `is_quoted`, so a guard reading a *phrase* had no reason to
  find it. It is now imported from the module that owns it rather than
  restated.

- **`_sentences` split on every newline.** Markdown hard-wraps prose, so a
  sentence spanning two lines was torn at the wrap point and each half
  judged as a whole claim:

  ```
  ...and reported the document as claiming
  Caterva is built on Tellurium.
  ```

  The second line alone reads as a flat assertion; with the first it is a
  report of someone else's claim. This is not a one-document problem —
  `DENIAL` is checked per sentence too, so any denial landing on a previous
  line was invisible, in a repository wrapped at 72 columns throughout.

**2. Two stale counts and an unwired guard.** `check_documented_counts`
(65 guards claimed, 66 present; three stale test counts outside README that
`--write` deliberately will not touch) and `check_guard_wiring`
(`check_pins_resolve.py` ran in no harness — written by another agent
*because* CI had failed six pushes running, then not wired into anything).

## What is still red

**The `api-server` job, failing since at least 2026-08-05.** It predates
this session and is not caused by it. I could not reproduce it: this
sandbox has no `pnpm` and cannot `unlink`, so `pnpm install
--frozen-lockfile` will not run here.

I attempted to infer the cause by parsing `pnpm-lock.yaml` and comparing
specifiers against each workspace `package.json`. The parse reported 798
importers and flagged `catalog:` specifiers it does not understand — it is
not trustworthy, and a conclusion drawn from it would be exactly the
measurement error this project keeps finding. So the cause is recorded as
**unknown**, with the one command that will answer it:

```
gh run view --repo math12345678/caterva --job <api-server job id> --log-failed
```

## Consequences

- The three Python jobs should now pass; every guard the workflow runs was
  executed locally and is green, with the two that need network or unlink
  permissions noted as sandbox-limited rather than passing.
- `check_pins_resolve` is wired and recorded in `EXPECTED_WIRING`, so losing
  the harness later is caught.
- The sentence-splitting fix removes a class of false positive across every
  hard-wrapped document, not just the one that was failing.
- **The habit that caused this is the thing to change.** Local guards
  answer "did I break it"; CI answers "is it broken". I answered the first
  and reported the second for seven consecutive commits.

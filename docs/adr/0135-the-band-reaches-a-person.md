# ADR 0135: The band reaches a person

**Status:** Accepted, implemented

**Date:** 2026-08-20

**Context:** `src/cli/commandEnsemble.ts`, `Tests/ensemble.py`,
`src/cli/__tests__/ensembleCommand.test.ts`

**Completes:** [ADR 0131](0131-the-ensemble-both-professors-asked-for.md) and
[ADR 0132](0132-the-band-instead-of-the-refusal.md), which built the
weighting and the envelope and left both reachable only by invoking a module
directly.

## `scientific ensemble`

```
$ scientific ensemble --fixture Tests/fixtures/brenda_ldh_fixture.html \
    --substrate pyruvate --seed 1 --simulate michaelis_menten

The literature does not agree on this value.
2 published row(s); 2 survive the evidence ranking.

  0.03 mM    drawn 50.0% of the time  [ref 286469]
      absent / not_assessed / exact
  0.398 mM   drawn 50.0% of the time  [ref 286442]
      absent / not_assessed / exact

  Spread 0.03 to 0.398, a 13.3-fold range   (median 0.03)

What that does to the simulation
  The band covers all 200 runs; none failed to integrate.
  [P] differs most at t=2: 9.059 to 9.870
  [S] differs most at t=2: 0.1302 to 0.9407

This is the spread of published measurements, weighted by how well evidenced
each one is. It is NOT an uncertainty estimate…
Reproduce with --seed 1.
```

Every other command in Terrium answers this query with `0.03`, because
`min()`. This one names both published values, says how often each was
drawn and why, and then answers the question a student can actually act on:
**does the disagreement change the result?** Seven-fold at t=2, yes.

## Two numbers, two different questions

The parameter spread and the band are printed together and are not the same
claim. The spread says *the literature disagrees*. The band says *how much
that matters to the answer* — and only the second is actionable. A 300-fold
disagreement in a parameter the model is insensitive to is a curiosity; a
two-fold disagreement in one it is sensitive to is a problem.

Reporting only the first would have been the more decorative half, and a
test pins the second (*"reports where the choice of paper matters most"*)
precisely so it cannot quietly become the only one.

Only the **widest** point of each envelope is shown, not the whole table. A
student wants to know where the choice of paper matters most; forty rows of
near-identical numbers bury that under arithmetic. A column identical
throughout collapses to one line for the same reason.

## Shelling out rather than reimplementing

The weighting needs per-candidate reliability scores, which live in the
Python layer beside `score_reliability` — **the same function the
single-value path grades its winner with**. A TypeScript reimplementation
would be a second implementation of the sampling, which is
[ADR 0027](0027-one-reliability-score-not-two.md)'s defect and the reason
`reliabilityScore.ts` was deleted rather than kept "just in case".

Same shape as [ADR 0122](0122-fifteen-domains-nobody-could-find.md)'s
`domains`: ask the side that knows, render here.

`Tests/ensemble.py` gained `--simulate`, `--json` and its own `sys.path`
entry for its directory. The last of those was a real bug: it depended on
being run from `Tests/`, so the CLI — which spawns from the repository root —
resolved the fixture path twice and got a blank refusal. Fixed in the module
rather than by having the caller compensate, because the next caller would
have had to compensate too.

## The seam is explicit, and that is design rather than test convenience

`commandEnsemble` called `runEnsemble` directly, and a module mock could not
intercept it — an internal call does not go through the module object. The
options were to drive every rendering case through a real subprocess (slow,
and it conflates a rendering regression with a resolver one) or to make the
seam explicit.

`run` is now an injectable parameter defaulting to the real thing. What is
injected in tests is **only the transport**: the weighting is pinned by
`test_ensemble.py`, and the boundary by `test_ensemble_boundary.py`, which
spawns the real runner against the real engine. That division is the lesson
of [ADR 0109](0109-the-second-front-end.md), where a fully-mocked suite
passed while the boundary was broken.

## Verification

- **13 CLI tests** on rendered output, because a payload plumbed through and
  never printed satisfies a shape assertion and fails the only thing that
  matters — the rule `resolveOutput.test.ts` states and the reason `blockers`
  sat unread at five sites.
- **45 Python tests** behind them (17 weighting, 15 envelope, 13 boundary).
- Four of the CLI tests are about what it refuses to imply: the disclaimer
  always prints, the seed always prints, `null` is "could not run" (exit 1)
  and `ok: false` is "the ensemble failed" (exit 2) — different facts, and
  only one of them means try again.

## Consequences

- `ensemble` is in `help`, so it is discoverable rather than the situation
  ADR 0122 was written about.
- It reads a **saved BRENDA table**, not the network. Deliberate: BRENDA
  asked that tools be gentle with their servers, and a command that fires
  live queries per draw is not gentle. Wiring it to the live resolver is a
  separate decision with a separate cost.
- **The API does not render it yet.** Named, not implied: the runner already
  emits it (ADR 0132), so the remaining work is a route and a renderer, and
  `docs/one-sided-findings.txt` exists because those two front ends drift.
- The disclaimer now appears in three places — Python report, JSON payload,
  CLI output. Repetition is the point: ADR 0024's objection was that a spread
  reads as an uncertainty estimate, and a sentence printed once at the bottom
  of a long report is a sentence that gets skipped.

## Related

- [ADR 0131](0131-the-ensemble-both-professors-asked-for.md) — the weighting
- [ADR 0132](0132-the-band-instead-of-the-refusal.md) — the envelope
- [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md) — the
  objection kept as a disclaimer
- [ADR 0122](0122-fifteen-domains-nobody-could-find.md) — the discoverability
  rule this follows

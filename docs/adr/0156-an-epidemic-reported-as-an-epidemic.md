# ADR 0156 — An epidemic reported as an epidemic

**Date:** 2026-08-22
**Status:** Accepted
**Builds on:** [ADR 0155](0155-the-domain-that-never-reached-the-engine.md)

## Context

ADR 0155 made the HTTP pipeline refuse SIR honestly instead of answering it
with `km is required`. It ended: *"SIR and the three inhibition models are
implemented and unreachable over HTTP. This ADR makes that visible and
refuses to paper over it; it does not build the dispatch."*

This builds the dispatch for SIR.

The engine already had it. `runCaterva` has accepted `'sir'` since the bridge
was written, and driving `caterva_runner.py` directly returns
`{"time", "[S]", "[I]", "[R]"}` from `beta, gamma, s0, i0, end, points`. The
gap was entirely in the HTTP layer.

## The trap, and why the obvious implementation is wrong

The obvious implementation runs the engine and returns the object the `mm`
path returns. **Do not.** Those fields are:

```
totalSubstrateConsumed, conversionPercentage,
maxVelocity, avgVelocity, finalVelocity
```

Every one of them *computes* for an epidemic — susceptible minus final
susceptible, percentage infected, the steepest slope — and every one is
labelled as enzymology. A reader would get correct arithmetic under names
describing a different experiment, and nothing would look wrong.

So SIR returns epidemic quantities named as such: `peakInfected`,
`peakTime`, `finalSusceptible`, `finalRecovered`, `attackRate`. The
Michaelis-Menten path is untouched.

## Two things found while building it

### A peak at the edge of the window is not a peak

`integrationWindowFor` derives its window from substrate depletion — km,
vmax, s0 — and returns the 10-second default whenever those are absent,
which for an epidemic is always.

Measured with beta 0.3, gamma 0.1, s0 990, i0 10: infections are still
climbing steeply at t=10 and do not peak until roughly t=26 at ~304. The
naive report was

```
peakInfected: 65.4
```

A real number from a real integration, describing the boundary of the run
rather than the epidemic. **Somebody would plan around it.**

Three states, not two: a peak reached, a peak not reached, and never a
boundary silently promoted to a maximum. `peakInfected` is `null` when
infections are still rising, `highestInfectedSeen` carries the number under
a name that says what it is, and a note explains.

### The advice has to be followable

The first version of that note said "re-run with a longer `end`" — and
`runSir` was calling `integrationWindowFor`, so there was no way to. A
refusal that is not actionable is merely regretful.

`end` is now read from the caller's parameters. **No default is derived from
gamma**, tempting as `1/gamma` is: turning a rate into a window needs a
multiplier, and this project does not invent constants. Instead the note
states what *is* derivable —

> with gamma=0.1, the mean infectious period is 10, so this window covered
> under 1.0 of them

— and lets the reader choose. With `end: 120` the same run reports
`peakInfected: 303.7` at `t=26.4` and an attack rate of 94.1%, which is the
standard final-size result for R₀ = 3.

## Verification

Twelve jest cases. `summariseSir` is static and pure precisely so the two
cases that matter can be driven without a Python subprocess.

- **Mutation:** replacing `stillRising ? null : peak.infected` with
  `peak.infected` fails *refuses to call the edge of the window a peak*.
  Restore verified by `diff`.
- End to end against the running server, both windows.
- `reports an attack rate, not a conversion percentage` asserts the ABSENCE
  of `conversionPercentage`, `totalSubstrateConsumed` and `maxVelocity` —
  the enzyme envelope cannot creep back in unnoticed.

### The test that did its job

ADR 0155 shipped `expect([...DISPATCHABLE_DOMAINS]).toEqual(['mm'])` with
the note: *"expected to CHANGE, not to be deleted. When SIR is dispatched
over HTTP, the assertion fails and whoever made that true updates it."*

It fired on exactly that, one day later, and the list widened **because an
executor arrived**. That is the distinction it exists to enforce, and the
reason it is a literal rather than something derived from `DOMAINS`: derived,
it could never disagree.

## Consequences

- SIR runs over HTTP, with its own result shape.
- `DISPATCHABLE_DOMAINS` is `['mm', 'sir']`, and a new test asserts every
  dispatchable domain is also classifiable — the mirrored drift.
- Test count +5 (12 in the file).
- **Still unreachable over HTTP:** the three inhibition models.
  `INHIBITION_MODELS` implements them for the CLI, two of the three via
  SBML, and the dashboard's disabled options say so. Named, not built.
- The dashboard renders the Michaelis-Menten shape and has no SIR option, so
  nothing in the UI changed or broke. SIR is an API capability today.

## Related

- [ADR 0155](0155-the-domain-that-never-reached-the-engine.md) — the refusal
  this replaces with a run
- [ADR 0141](0141-the-number-you-typed-became-null.md) — why no unit
  conversion is applied to beta and gamma

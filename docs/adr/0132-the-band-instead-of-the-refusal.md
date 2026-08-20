# ADR 0132: The band instead of the refusal

**Status:** Accepted, implemented (engine + boundary). Front-end rendering
outstanding — see Consequences.

**Date:** 2026-08-20

**Context:** `Tests/model_ensemble.py`, `Tests/test_model_ensemble.py`,
`Tests/test_ensemble_boundary.py`,
`Science-Agent-Pipeline/artifacts/api-server/src/lib/terium_runner.py`

**Follows:** [ADR 0131](0131-the-ensemble-both-professors-asked-for.md),
which built the weighting and left the simulation half open.

## The half that makes it a simulation

ADR 0131 turns scored literature values into a weighted sample of
**parameters**. On its own that produces a spread of numbers, which is a
better answer than `min()` and is still not what was asked for.

Sauro's sentence is about what you do with them:

> "With Jessie's approach you don't get any simulation, with Barbara's you
> can **sample and get an ensemble distribution**. That is the right way to
> do it."

The point is not that a student learns Km is uncertain. It is that they
**still get a trajectory** — many of them — instead of a refusal. This runs
the model once per draw and reports what the family does.

## What it looks like on the enzyme this repository keeps citing

Human LDH on pyruvate. BRENDA reports Km = 0.03 and 0.398 mM, both wild-type,
both human, neither reporting pH or temperature — so the reliability axes
cannot separate them and the sampler weights them equally. Terrium's answer
today is `0.03`, because `min()`.

```
swept: ['km']   runs: 200/200
The band covers all 200 runs; none failed to integrate.

   t     low      median    high
   0.0  10.0000  10.0000  10.0000
   2.0   0.1302   0.1302   0.9407     <-- 7x, from the same enzyme
   4.0   0.0000   0.0000   0.0000
```

At t=2 the substrate is **0.130 or 0.941** depending on which paper you
read. That is a fact about the published record, it is seven-fold, and until
now no surface of this product could show it.

## Emitted from the runner, on purpose

The `--ensemble` flag lives on `terium_runner.py` rather than in either
front end, because the runner is the one place the CLI and the API both read
from. A capability added to one of them reaches half the users — recorded
four times now (ADR 0106, 0109, 0110, 0114) and guarded by
`docs/one-sided-findings.txt`.

**The draws are supplied, not computed there.** Weighting them needs the
per-candidate reliability scores, which are the literature layer's business;
recomputing the sampling inside the engine would be a second implementation
of it, which is ADR 0027's defect precisely.

## The three ways to lie with an envelope, and what stops each

### Drawing it over fewer runs than you imply

A band over 160 of 200 runs, with the other 40 unmentioned, is a quiet lie
about its own support. Failures are counted, carry the parameter set that
caused them, and `support_note()` is emitted **always** — "all 200 runs; none
failed" is information too, and a note that appears only on failure teaches a
reader to skim past it exactly when it matters.

There is one rejection this can do honestly and it is carefully scoped: a
parameter set that **fails to integrate**. That is a numerical fact about the
solver, not a judgement about biology, and the note says so. Bakker's
ensemble rejects against measured flux; Terrium has no flux data and does not
invent a substitute, so `ensemble.DISCLAIMER` still travels with the band.

### Drawing it over runs that are not comparable

"The median at t=3" across mismatched time grids compares different
quantities. The grid is fixed by the first run, and a run returning a
different one is a **failure** rather than something to interpolate —
interpolating would manufacture values no run produced, which is the same
rule ADR 0131 follows when it resamples rather than fits. Percentiles are
nearest-rank for the same reason.

### Drawing it over parameter sets nobody sampled

Draw *i* of every parameter forms run *i*. Two parameters sampled
independently and then combined arbitrarily would explore combinations no
source supports; keeping the pairing preserves whatever correlation the
sampling produced. Unequal draw lengths are refused rather than zipped to the
shortest.

## Verification

**28 tests.** 15 against a fake simulator for the envelope arithmetic, and
**13 that spawn the real runner** against the real engine.

That split is deliberate and is the lesson of ADR 0109, where a mocked test
suite passed while the boundary was broken:

> a test that pins a component tells you nothing about the wiring

The boundary tests are the only ones that could catch a broken `--ensemble`
flag, an import that fails under the server's PYTHONPATH, or a payload shape
the runner rejects. One of them — *"the band is wider than a point where the
parameter matters"* — is the product claim itself, asserted end to end:
if two thirteen-fold-apart Km values ever stop producing a visible
difference, the ensemble has silently stopped doing anything.

`--ensemble` failures return JSON rather than a traceback, because the API
server parses stdout and an empty stdout with a stack trace on stderr is
indistinguishable from a hang.

## Consequences

- Terrium can now **run** where it refused. The refusal remains correct when
  nothing was resolved at all; it is no longer the only answer to
  disagreement.
- `max_runs` defaults to 200. Integrating an ODE a few thousand times is not
  free, and a student waiting a minute for a band that stopped moving after
  two hundred runs would reasonably conclude the tool is slow rather than
  thorough. `attempted` reports the cap rather than truncating silently.
- **Neither front end renders it yet.** Named rather than implied: this is
  reachable today only by invoking the runner directly. It should reach the
  CLI and the API together, and `docs/one-sided-findings.txt` exists because
  they drift.
- `substratesAvailable`, a one-sided key from a concurrent agent, was
  recorded in that baseline this pass — raised, not claimed.

## Related

- [ADR 0131](0131-the-ensemble-both-professors-asked-for.md) — the weighting
- [ADR 0024](0024-refusing-versus-defaulting-an-unsourced-parameter.md) — the
  objection this keeps as a disclaimer rather than dismissing
- [ADR 0027](0027-one-reliability-score-not-two.md) — one implementation of
  the sampling, which is why the engine does not recompute the draws
- [ADR 0109](0109-the-second-front-end.md) — why a mocked suite alone would
  have proved nothing

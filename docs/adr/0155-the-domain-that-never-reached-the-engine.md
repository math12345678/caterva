# ADR 0155 — The domain that never reached the engine

**Date:** 2026-08-22
**Status:** Accepted

## Context

`ScientificPipeline` classifies a query into a domain. It has done this
carefully since the classifier was fixed: `mm` and `sir`, aliases ordered
longest-first, and **`undefined` when it cannot tell** — because "defaulting
to a domain is the same defect as defaulting a parameter, one level up."

The domain is then used to validate the request, to pick which parameters
are required, and to choose literature recommendations.

It is not used to run the model.

```ts
private async runSimulation(parameters, conditions) {
  ...
  const result = await runTerium('mm', engineParameters, {
    required: ['km', 'vmax', 's0']
  });
```

The domain is not a parameter of this function. It was classified,
validated against, reasoned about — and dropped one step before the model
ran.

## What a user actually got

Measured over HTTP on 2026-08-22:

```
POST /api/simulate
{"query":"sir epidemic",
 "parameters":{"beta":0.3,"gamma":0.1,"s0":990,"i0":10}}

-> parameters.km is required
   parameters.vmax is required
```

`sir`, `epidemic`, `infection`, `outbreak` and `susceptible` are aliases the
classifier accepts, and the validator's own rejection message lists them by
name as models *"this pipeline can run"*. It then demanded two
Michaelis-Menten parameters from a different branch of biology, neither of
which the caller had mentioned.

`const requiredParams = ['km', 'vmax', 's0']` appeared **three times** in
`request-validator.ts` — a fourth copy of "which models exist", in a file
whose own docstring already complains about there being three.

**A wrong error is worse than a bare failure: it sends somebody to fix the
thing that is not broken.**

## The part that was dangerous rather than merely rude

Fixing the validator alone would have moved the lie deeper.

A correctly-validated SIR request would have reached an integrator running
enzyme kinetics and been reported as `[S]`. Nothing had gone visibly wrong
only because `required: ['km','vmax','s0']` killed the run on a missing
`km` — **a coincidence standing in for a check.** Supply an epidemic query
*and* a km and the pipeline would have integrated the wrong model
confidently.

This file already contains the sentence for that, written about
classification: *"a simulation of the wrong system is not a partial answer,
it is a different answer."* It had not been applied here, where the system
is actually chosen.

## Decision

1. **`requiredParametersFor(query)`** — the validator asks the domain
   instead of remembering. Three hardcoded lists become one call. An
   unclassifiable query keeps Michaelis-Menten's list, because it already
   fails on the `query` field and a second error about the first helps
   nobody.

2. **The domain reaches `runSimulation`, and anything it cannot dispatch is
   refused by name:**

   > This pipeline classified your query as 'sir' and cannot run it over
   > HTTP: only mm is dispatched here today. The engine does implement sir,
   > and it is reachable from the CLI — see `scientific domains`. Terrium
   > will not substitute a model you did not ask for.

3. **`DISPATCHABLE_DOMAINS`** as a separate list from `DOMAINS`, not a flag
   on it. The two questions have genuinely different answers today, and
   merging them would force a choice between dropping SIR from the
   classifier — losing the ability to say "I know what you asked for" — and
   claiming it runs. Naming both states is what lets the refusal be
   specific instead of a generic 400.

The four disabled options in the web dashboard are relabelled from *"not yet
accepted by the API"* to *"CLI only, see `scientific domains`"*, which is
where they actually work: `INHIBITION_MODELS` implements competitive,
non-competitive and product inhibition, and none of it is reachable over
HTTP.

## Verification

Seven jest cases in
`src/validation/__tests__/requiredParametersFollowTheDomain.test.ts`.

- **Mutation:** restoring `const requiredParams = ['km','vmax','s0']` fails
  `does not tell an epidemic request that km is missing`. Restore verified
  by `diff`.
- `still rejects a Michaelis-Menten request missing its own parameters`
  exists so that deleting the check entirely cannot pass the suite.
- `does not claim to dispatch every domain it can classify` asserts
  `DISPATCHABLE_DOMAINS === ['mm']`. **It is expected to change, not to be
  deleted:** the day SIR is dispatched over HTTP, whoever made that true
  updates it. A silent widening without a working executor is precisely what
  it catches.
- End to end against the running server: the SIR job now reports the
  refusal above, and a Michaelis-Menten job still completes.

## Consequences

- The HTTP API no longer answers an epidemic question with an enzyme
  parameter.
- A wrong-model run is now impossible rather than accidentally prevented.
- Test count +7.
- **Open, and now stated rather than implied:** SIR and the three inhibition
  models are implemented and unreachable over HTTP. This ADR makes that
  visible and refuses to paper over it; it does not build the dispatch.

## Related

- [ADR 0149](0149-using-the-tool-as-a-student.md) — where the dashboard's
  four dead options were first measured
- [ADR 0154](0154-the-checker-and-the-fixer-disagreed.md) — the same shape
  one day earlier: two lists of the same truth, and nothing comparing them

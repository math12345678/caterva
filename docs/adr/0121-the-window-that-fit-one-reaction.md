# ADR 0121: The window that fit one reaction

**Status:** Accepted

**Date:** 2026-08-18

## Context

```ts
private static readonly SIMULATION_END_TIME_S = 10;
```

Ten seconds. For every Michaelis-Menten run this pipeline has ever
performed, whatever Km, Vmax and S0 were.

BRENDA reports Vmax in μM/min. For the CLI's own documented example — Km
5.2 mM, Vmax 12.8 μM/min, S0 10 mM — the reaction needs **32 hours** to
reach 95% conversion, so ten seconds showed

    0.014%

of it. The student saw a flat line at 10.000 mM, printed ten times, and had
no way to tell whether the enzyme was slow, the tool was broken, or they had
typed something wrong.

The same constant applied to a Vmax in mM/s puts the entire reaction inside
the first two printed points.

**This was invisible until ADR 0117 made units count.** Before that, every
Vmax was integrated as though it were in mM/s — which is precisely the
regime where ten seconds happens to be right. Fixing the units revealed a
second defect that the first had been masking, and the masking was not a
coincidence: both bugs were calibrated to the same unstated assumption
about timescale.

## Decision

**Derive the window from the closed form.** Michaelis-Menten integrates to

    Km·ln(S0/S) + (S0 - S) = Vmax·t

(Michaelis & Menten 1913; the integrated form as presented in Segel,
*Enzyme Kinetics*, Wiley 1975, §2.3). Setting S = f·S0 and solving,

    t = [ Km·ln(1/f) + S0·(1 - f) ] / Vmax

Every term comes from the caller's own parameters.

**What remains a choice is `f`, and it is a display choice.** The reaction
never finishes, so some cut-off must be picked. 5% remaining puts the
transition from zero-order to first-order — the thing Michaelis-Menten is
taught to show — inside the frame. It is a parameter, not a literal.

**The window is derived where the parameters are consumed, not passed
around.** The first version computed it in `execute()` and passed it to
`runSimulation` with the old constant as a default argument.
`verifyReproducibility` calls `runSimulation` directly with two arguments,
so **the replay silently took the default, integrated a different window,
and reported the run as not reproducible.** A stored result that cannot be
reproduced is the worst output this pipeline can give, and a defaulted
argument caused it. Deriving from the parameters makes that drift
impossible rather than asking two call sites to remember.

That is Constitution Rule 4 — a shared constraint is enforced by structure
or by a test, not by a comment. There *was* such a comment on
`SIMULATION_END_TIME_S`, asking the integration window and the validator's
window to stay equal. It is the drift it asked for and did not prevent.

**The plot window and the initial-rate window are now separate, and that is
the substantive decision here.** They answer different questions:

| window | question | value |
|---|---|---|
| plot | how long to integrate so the curve is visible | 95% conversion |
| initial-rate | how long an initial-rate reading stays defensible | `0.05·S0/Vmax` |

Coupling them made `AssumptionValidator`'s second check report *"substrate
exhausted within the measurement window — no initial-rate interpretation is
valid"* on **every** run. That statement is true of the plot window and
useless: it warns about a window nobody claimed, and it dropped confidence
from 0.86 to 0.82 on every full-reaction simulation.

The initial-rate window uses the convention's own definition. The validator
bounds depletion by the zero-order worst case, `Vmax·t/S0`, so the window
where that bound reaches 5% leaves *true* depletion strictly below 5% —
conservative in the right direction, and what an experimentalist choosing an
assay window would do.

**Stated plainly because it matters:** this makes that check pass *by
construction* on the pipeline's own path. It is still doing real work for
any caller that supplies its own window, but on this path it is a definition
rather than a finding, and reading it as independent evidence would be
reading a tautology as a result. `integrationWindow.ts` says so where the
function is defined.

## Consequences

- A run with literature-typical kinetics shows the reaction instead of a
  flat line: 10.000 mM → 0.500 mM across the frame.
- Both unit regimes now produce the *same* curve with time axes 60,000×
  apart, which is the correct behaviour and a strong joint check on ADR 0117
  and this change.
- The replay reproduces, because window and parameters cannot separate.
- Confidence is unchanged at 0.86; the initial-rate warning no longer fires
  spuriously.

### What this does not fix

`f = 0.05` is a display convention with no primary source, exactly like the
5% figure the validator already declines to cite. It is documented as a
convention and is overridable.

Non-Michaelis-Menten domains still fall back to the ten-second constant.
The derivation is specific to this rate law; SIR and the stochastic domains
need their own, and inventing a generic one would be the same mistake in a
new place.

The CLI still reports `Validation confidence: 0.0%` for a run on
hand-supplied values. That number measures *literature backing*, not
correctness, and a student who supplies three correct parameters and is told
0% will reasonably conclude the run is worthless. That is a labelling
problem, it is not addressed here, and it is the next thing worth fixing on
this path.

## Verification

`src/integration/__tests__/integrationWindow.test.ts` — 18 tests, checking
the window against the equation it comes from rather than against a
remembered number: integrate to the returned `t` and the substrate must sit
at `f·S0`, across four orders of magnitude of Vmax, with the Km → 0
zero-order limit checked arithmetically as an independent case.

`src/integration/__tests__/declaredUnitsReachTheEngine.test.ts` — 7 tests,
end to end through the pipeline.

**Two of those tests had to be rewritten, and the reason is worth keeping.**
They asserted on the final substrate — *"a Vmax in mM/s empties 10 mM before
the 10 s window closes"* — which was true, and silently depended on the
constant this ADR removes. They failed on a change that was an improvement.
A test pinned to an incidental constant fails when the constant is fixed;
they now check the closed-form residual at the times the engine reports,
which holds under any window.

Independent confirmation, scipy against the CLI's printed trajectory:

```
 t (s)      Terrium    closed form   residual
      0.0     10.000        10.000      0.0000
  12930.7      8.245         8.245      0.0000
  51723.0      3.884         3.884      0.0002
 116376.7      0.522         0.522     -0.0004
```

## Related

- ADR 0117 — the unit fix that made this visible, and that this depended on
- ADR 0055 — a simulation has no temperature of its own
- ADR 0013 — never default an enzyme concentration

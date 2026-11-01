# ADR 0023: Lotka-Volterra's default `gamma`/`delta` were transposed, producing a negative population and destroying the conserved quantity

**Status:** Accepted

**Date:** 2026-08-09

**Relates to:** ADR 0022 (which added the three ODE oscillator domains),
ADR 0004 (`gamma` is reserved in Antimony), ADR 0005 (RNG convention)

## Context

ADR 0022 added `lotka_volterra`, `cell_cycle_oscillator` and
`repressilator`. The Lotka-Volterra implementation itself is correct — the
rate laws match the sources, and the Antimony translation handles the
reserved-`gamma` collision properly (ADR 0004).

All three shipped **with no tests**. That is what this ADR is really about:
the domain was declared, wired, typed, schema'd and documented, and no
assertion anywhere connected it to a fact outside the codebase.

Writing that verification found a defect in the first ten minutes.

The engine integrates

```
dP/dt = alpha*P - beta*P*V        dV/dt = gamma*P*V - delta*V
```

so `gamma` is the prey→predator conversion rate and `delta` the predator
death rate. The shipped defaults were

```
alpha=1.1, beta=0.4, gamma=0.4, delta=0.1, p0=10, v0=5
```

Three independent problems follow from `gamma=0.4, delta=0.1`:

1. **The coexistence fixed point is `(delta/gamma, alpha/beta) = (0.25, 2.75)`,
   but the prey starts at 10** — a 40x excursion. The resulting orbit takes
   the prey to the edge of extinction on every cycle.

2. **The prey population goes negative**: measured minimum
   `-5.936e-11`. A negative population is not a small numerical blemish; it
   is a state the model cannot represent.

3. **The system's exactly-conserved first integral drifts by 49%.**
   `H = gamma*P - delta*ln P + beta*V - alpha*ln V` has `dH/dt = 0`
   identically. A 49% drift means the integrated trajectory is no longer
   the modelled system — the physics was lost, not approximated.

The docstring's own claim gave the game away: it said the defaults
"reproduce the classic ~10-year lynx-hare oscillation cycle". The
small-oscillation period is `2*pi/sqrt(alpha*delta)`, which for the shipped
values is **18.9**, not ~10. Transposing `gamma` and `delta` gives
**9.47** — the claimed cycle. The intended values were transposed at some
point between derivation and definition.

Biology agrees: `gamma` (conversion efficiency of prey biomass into new
predators) being four times `delta` (predator death rate) describes
implausibly efficient predators, and is the reason the fixed point collapses
to a prey density of 0.25.

## Decision

**Defaults corrected to `gamma=0.1, delta=0.4`, and the domain is pinned by
a verification suite that checks the ODE's own analytic properties rather
than the solver's output.**

`caterva/tests/test_lotka_volterra_correctness.py`, 17 tests across four
independent verification routes — deliberately independent, so no single
wrong assumption can make all of them pass:

1. **The conserved quantity.** `H` above, derived by hand in the module
   docstring, held to <1e-5 relative drift on two different orbits. This is
   a property of the vector field, not of a trajectory.
2. **The fixed point.** Started exactly at `(delta/gamma, alpha/beta)`, the
   populations do not move. Plus a separate arithmetic check that both
   derivatives vanish there, pinning the formula itself.
3. **The small-oscillation period.** Linearising about the fixed point
   gives Jacobian eigenvalues `±i*sqrt(alpha*delta)`, hence
   `T = 2*pi/sqrt(alpha*delta)`; measured from mean-crossings to within 2%.
4. **An independent integrator.** scipy's `solve_ivp` at rtol 1e-10, which
   shares no code with roadrunner.

Plus physical invariants (populations strictly positive, orbit closes after
one period) and Rule 1/2 validation coverage.

Two tests specifically pin the defaults — that they conserve `H` and that
the initial state is within an order of magnitude of the fixed point. These
are the tests that fail on the old values, and they are the reason this
class of defect cannot silently return.

**Mutation-tested**: changing the predation term from `beta*P*V` to
`beta*P*P*V` in the Antimony model broke **7 of the 17 tests** across all
four verification routes. Reverted; green.

## Consequences

**Easier.** The default Lotka-Volterra run now produces a stable closed
orbit with the ~10-year period the documentation claims, and any future
change to the rate laws is caught by an analytic invariant rather than by a
golden trajectory that would have to be regenerated.

**Harder.** Nothing.

**Unchanged.** The rate laws, the Antimony translation, `gamma_rate`
handling (ADR 0004), and both other ODE oscillator domains.

**Carried forward — and this is the important part.**
`cell_cycle_oscillator` and `repressilator` shipped in the same batch and
**still have no verification of any kind**. Lotka-Volterra had a defect
that four verification routes caught immediately; there is no reason to
assume the other two are cleaner, and one concrete smell is already
visible: both accept a `seed` parameter documented as "accepted for
call-signature symmetry but unused", which tells a student the run is
seed-reproducible when it is deterministic regardless. Both are Antimony
ODE models with published reference behaviour (Tyson 1991 reports the
oscillation period; Elowitz & Leibler 2000 report ~150-minute oscillations),
so both are verifiable against their sources the same way this one was.
Until that exists, neither should be treated as trustworthy.

## References

- **Lotka, A.J. (1925)** *Elements of Physical Biology*, Williams & Wilkins.
- **Volterra, V. (1926)** "Fluctuations in the abundance of a species
  considered mathematically", *Nature* **118**, 558-560.
  DOI [10.1038/118558a0](https://doi.org/10.1038/118558a0).
- ADR 0022 — added the three ODE oscillator domains.
- ADR 0004 — why the model emits `gamma_rate` rather than `gamma`.

# ADR 0002: Model PCR as a discrete recurrence, not through antimony/roadrunner

**Status:** Accepted

## Context

Every domain implemented before PCR (Michaelis-Menten kinetics, SIR/SEIR
epidemiology) is a continuous-time ODE system, built the same way: define
the model in antimony, translate to SBML, integrate with roadrunner. It
would have been consistent to force PCR through the same pipeline --
e.g., by treating "cycle number" as a continuous time variable and writing
a differential equation that approximates cycle-by-cycle doubling.

PCR amplification, though, is fundamentally a discrete process: a
polymerase either completes a copy of a template within a cycle or it
doesn't, and "cycle 3.5" isn't a physically meaningful state the way
"t=3.5 seconds" is for a reaction rate. Forcing it into the ODE pipeline
would mean writing a continuous approximation to a discrete process and
then integrating that approximation numerically -- introducing solver
error to manage for a system whose real behavior has an exact closed form
with no error at all.

## Decision

Implement `simulate_pcr` as a direct Python recurrence relation
(`validate_pcr_params` / `simulate_pcr` in `tellurium_engine.py`), not
routed through antimony or roadrunner. Unbounded growth follows the exact
closed form `N(c) = n0 * (1 + efficiency) ** c`; the optional plateau mode
uses a discrete logistic recurrence. Both are computed directly, with no
numerical integration step.

## Consequences

- Correctness tests for this domain are exact-equality checks (within
  float rounding), not tolerance-band comparisons against a reference
  solver -- see `tests/test_pcr_correctness.py`'s docstring, which states
  this explicitly so nobody "fixes" the tests to add a tolerance that
  shouldn't be there.
- This domain doesn't get SBML export, roadrunner-based features
  (steady-state solving, parameter scanning) for free the way the ODE
  domains do. If a future feature needs those, PCR would need its own
  implementation of them, or a reconsideration of this ADR.
- Sets a precedent: not every simulation domain has to go through the same
  pipeline. The next two planned domains (Monte Carlo, population genetics)
  should each get this same question asked explicitly -- is this actually a
  continuous-time ODE system, or would forcing it through antimony/
  roadrunner be the same mistake this ADR avoided -- rather than defaulting
  to the existing pipeline out of consistency alone.

# ADR 0004: Emit the SIR/SEIR recovery rate as `gamma_rate`, not `gamma`

**Status:** Accepted

## Context

The SIR and SEIR models both have a recovery-rate parameter that every
epidemiology textbook calls `gamma`. Antimony, the model-definition
language Terrium translates to SBML, treats `gamma` as a reserved name --
it's the built-in gamma function. Generating an antimony model with a
parameter literally named `gamma` fails to parse, with an error that gives
no hint the problem is a naming collision with a math function rather than
a real syntax error. This cost real debugging time before the cause was
identified.

## Decision

Internally, generated antimony source emits the parameter as `gamma_rate`
(the constant `GAMMA_PARAM` in `tellurium_engine.py`), with a comment in
the generated model source explaining why, so a student inspecting the raw
antimony/SBML sees an explanation, not just an unexplained rename. The
Python API (`simulate_sir`, `simulate_seir`, `build_sir_antimony`,
`build_seir_antimony`) still takes `gamma` as the argument name -- the
rename is purely an internal implementation detail, invisible to anyone
calling the Python functions normally.

## Consequences

- Anyone reading generated antimony/SBML source directly (rather than
  going through the Python API) needs to know about `gamma_rate` --
  mitigated by the embedded comment, but still a real seam to be aware of.
- This is a general risk category worth remembering for future domains:
  any time a natural parameter name for a new domain happens to collide
  with an antimony/SBML reserved word or built-in function name, the same
  pattern applies -- rename internally, document why in the generated
  source, keep the public Python API using the natural name. Population
  genetics and Monte Carlo (both still planned) should be checked against
  antimony's reserved-word list before their parameter names are finalized,
  rather than discovering a collision the same way this one was found.

# ADR 0003: Km plausibility bounds must be identical across the literature and simulation layers

**Status:** Accepted

## Context

Terrium has two layers that each independently judge whether a Km value is
scientifically plausible: `Tests/brenda_client.py` (the literature layer,
which flags implausible values scraped from BRENDA) and
`Tellurium/tellurium_engine.py` (the simulation layer, which flags
implausible values before building a model). These were originally written
with their own copies of the plausibility bounds
(`KM_PLAUSIBLE_MIN_MM` / `KM_PLAUSIBLE_MAX_MM`).

Those copies drifted: at one point the engine used `1e4` while BRENDA used
`1e3`. The practical effect was a Km of 5000 mM -- flagged as implausible
by the literature layer -- would arrive at the simulation layer, be judged
against the *engine's* (looser) bound, and come back as "confirmed." A
value the literature layer explicitly warned about would silently lose
that warning by the time a student saw it plotted. This is exactly the
failure mode Terrium exists to prevent: a number that should carry a
visible caveat quietly becoming a confident-looking number instead.

## Decision

The two constants must always be numerically equal. This is enforced by a
test (`Tellurium/tests/test_brenda_integration.py::
test_km_lower_bound_matches_the_brenda_layer` and its upper-bound
counterpart), not just a comment asking future editors to remember. If
either constant changes, the test fails until both are updated together.

## Consequences

- Any future PR that changes one bound without the other fails CI
  immediately, rather than silently reintroducing this exact bug.
- The two layers are now coupled: changing the plausibility range requires
  touching both files, or extracting the constants to a shared module
  either layer can import. Extracting to a shared module was considered
  and deferred -- `Tests/` and `Tellurium/` are currently siblings with no
  shared dependency, and introducing one for two float constants seemed
  like more coupling than the problem warranted. This should be
  revisited if a third consumer of these bounds appears.
- This pattern (a test that pins two independently-defined values equal,
  rather than a shared constant) is worth reusing anywhere else in the
  codebase where two layers make judgment calls about the same kind of
  data -- it's cheaper than restructuring module boundaries and it
  directly encodes the invariant that actually matters.

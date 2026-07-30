# ADR 0005: Discrete/stochastic domains share a single RNG convention

**Status:** Accepted

## Context

Two discrete/stochastic domains now exist in the codebase: Monte Carlo pi
estimation (Stage 1) and Wright-Fisher population genetics (Stage 2).
Both are implemented as direct Python/numpy without antimony or roadrunner,
and both rely on numpy random number generation for their core computation.

In Monte Carlo's implementation, the seed handling was documented as a
judgment call (see `tellurium_engine.py`'s Monte Carlo module comment: "The
seed convention uses `numpy.random.Generator` for reproducibility; future
stochastic domains should reuse this same pattern rather than inventing a
different RNG interface"). With a second stochastic domain now following
that same pattern, the question is no longer "should a new domain pick
this convention?" — it's "should deviating from this convention require
an explicit justification?"

Without an ADR, each future domain's implementer faces the same decision
from scratch: which RNG to use, whether to accept a seed parameter, whether
to document reproducibility expectations. Different implementers will
make different choices in the absence of a stated standard, and the codebase
will accumulate inconsistent RNG interfaces — some accepting `int |
None`, some accepting `numpy.random.Generator` objects, some using
`random.Random`, some making no reproducibility guarantees at all.

## Decision

All discrete/stochastic domains in Terrium use:

- `numpy.random.default_rng(seed)` as the single RNG constructor, where
  `seed: int | None = None`.
- The seed parameter is passed to every public simulation function in the
  domain.
- A fixed seed guarantees bit-identical output across repeated calls with
  the same parameters.
- `seed=None` (the default) produces non-deterministic output.

Any future domain that deviates from this convention — by using a
different generator class (`random.Random`, a third-party RNG), by
omitting the seed parameter, or by not guaranteeing bit-identical
reproducibility — must state its reasons in its implementation report per
the constitution's Rule 9 (judgment calls flagged explicitly, not silently
made). Compliance with this ADR is checked automatically by
`scripts/check_rng_convention.py` (AST-based static analysis) and
`Tellurium/tests/test_rng_convention.py` (pytest wrapper that runs the
script as a CI step). The check runs as Step 2b of the verification
procedure (`docs/CONSTITUTION.md` Section 6) and is automated by
`scripts/verify_domain.sh`.

## Consequences

- A new contributor or implementer writing a stochastic domain does not
  need to decide which RNG to use; the default is stated.
- The `numpy.random.default_rng` function returns a `Generator` object
  using the BitGenerator selected by numpy's version-dependent defaults,
  which has changed across numpy major versions (e.g., numpy 1.x used
  PCG64 by default; numpy 2.x moved to Philox). This means reproducibility
  across numpy versions is *not* guaranteed even with the same seed — only
  within the same numpy installation. This is accepted as a practical
  limitation: pinning a specific BitGenerator would add interface
  complexity (passing a `numpy.random.Generator` object or a
  `BitGenerator` name) with no clear teaching-lab use case for
  cross-version reproducibility of simulation internals.
- The `default_rng(seed)` call is deterministic given a fixed numpy
  version, which is sufficient for the use case (a student reproducing a
  simulation on the same environment sees the same result).
- If a future domain genuinely needs a different RNG (e.g., low-discrepancy
  sequences for quasi-Monte Carlo, or a cryptographically secure RNG for
  some reason), the ADR does not block it — it requires a stated
  justification, which is a lower bar than a full re-review but higher
  than a silent deviation.

# ADR 0013: Enzyme concentration is a caller input, and it bridges kcat to Vmax

**Status:** Accepted

**Date:** 2026-08-02

**Relates to:** ADR 0012 (which deferred exactly this)

## Context

ADR 0012 closed the kcat extraction and stopped, deliberately:

> The MM engine takes `vmax`, not `kcat`, and `Vmax = kcat · [E]₀`.
> Converting a resolved kcat into the parameter the engine needs requires
> the total enzyme concentration — which Caterva has nowhere, and which
> BRENDA does not supply per row.

That left a working literature lookup that could not reach a simulation. The
question ADR 0012 explicitly declined to answer in a hurry: **where does
$[E]_0$ come from?**

## Decision

**$[E]_0$ is an explicit caller input. It is never defaulted, never
inferred, and never resolved from literature.**

The conversion lives in `vmax_from_kcat(kcat, enzyme_conc, km=None)` in the
validation layer, returning `(vmax, ParameterValidation)`.

### The engine signature does not change

`simulate_michaelis_menten(km, vmax, s0, ...)` keeps its contract. The
conversion happens *before* the engine, not inside it.

This matters more than it looks. Adding `enzyme_conc` as an engine parameter
would change the MM domain's parameter set, the API schema, the DB enum, the
OpenAPI spec, and every pinned golden trajectory — a large blast radius for
what is arithmetic on the way in. Keeping the engine surface fixed means
every existing golden still holds unchanged, verified.

### Units

| quantity | unit | rationale |
|---|---|---|
| `kcat` | s⁻¹ | BRENDA's Turnover Numbers table |
| `enzyme_conc` | mM | matches the mM convention `Km` already uses |
| returned `vmax` | mM·s⁻¹ | dimensionally consistent with the above |

### Rule 2, applied to the new failure modes

**Rejected** (`ok=False`): non-finite, negative, or zero `kcat` / `enzyme_conc`.

Zero enzyme deserves comment. It yields `Vmax = 0`, which
`validate_michaelis_menten_params` *already* rejects as "a model that provably
cannot turn over". Catching it in the conversion names the actual cause —
there is no enzyme — instead of handing the student a downstream symptom to
work backwards from.

**Flagged** (`ok=True, flagged=True`): $[E]_0 > 0.01 \cdot K_m$.

The Michaelis-Menten rate law is derived assuming $[E]_0 \ll K_m$. Above
that, the ES complex sequesters a non-negligible share of the substrate and
the standard curve is quantitatively wrong — the tight-binding (Morrison)
regime, which needs a different equation this engine does not implement.

The simulation still runs. It still teaches the right shape. The student is
simply told the approximation is being stretched, and why. That is Rule 2's
impossible/implausible distinction exactly: refuse to *claim* what cannot be
supported without refusing to *compute*.

`0.01` is the conventional textbook threshold for "safely negligible", and it
lives in `ENZYME_CONC_MM_RATIO_FLAG_ABOVE`, guarded by
`check_plausibility_constants.py` like every other bound.

### Why not `e0`

`e0` is already taken — it is the SEIR model's **exposed** compartment, and
it is in `PARAMETER_PATTERN`. Reusing it would be a real cross-domain
collision, not a cosmetic one: a query mentioning `e0` would be ambiguous
between "exposed individuals" and "enzyme concentration".

### Why $[E]_0$ is not resolved from literature

It is a property of *an experiment*, not of an enzyme. BRENDA reports what a
turnover number was measured at, not how much enzyme a student is about to
put in a tube. Resolving it would be inventing an assay.

This keeps `RESOLVABLE_FIELDS` honest: `km` is resolved because a Km for an
enzyme/substrate pair is a literature fact; `enzyme_conc` is not, because it
isn't.

## Consequences

**Easier.** A resolved kcat can now produce a runnable simulation, with the
enzyme concentration visible in the request rather than hidden in a default.
The `[E]₀ / Km` flag teaches a real assumption most students meet only as a
footnote.

**Harder.** A caller must supply `enzyme_conc` to use kcat at all. That is
the intended friction: the alternative is a default that silently
manufactures a $V_{max}$.

**Unchanged.** The engine signature, every golden trajectory, `Km`
resolution, and `RESOLVABLE_FIELDS`. `kcat` remains outside it (ADR 0012),
because resolving a kcat still does not produce a simulable parameter *on its
own*.

## Verification

- **16 tests**, all mutation-checked. Four mutations, each caught:

  | mutation | caught by |
  |---|---|
  | `kcat * enzyme_conc` → `kcat + enzyme_conc` | doubling-enzyme test |
  | ratio check disabled | flag-boundary test |
  | zero enzyme allowed | zero-enzyme rejection test |
  | flag collapsed into reject | flag-boundary test |

  The last one matters most: it is the Rule 2 violation the constitution
  names explicitly ("do not collapse this distinction in either direction").

- **Ground truth is not the engine.** `test_a_kcat_derived_vmax_reproduces_the_implicit_solution`
  feeds a kcat-derived $V_{max}$ into the real integrator and checks the
  implicit closed form $K_m \ln(S_0/S) + (S_0 - S) = V_{max} t$ at every
  point, asserting at least 10 were actually compared so it cannot pass
  vacuously.

- Real captured data throughout: **118 s⁻¹**, 6-monoacetylmorphine,
  *Homo sapiens*, pH 7.4, 37 °C, BRENDA ref 750291.

- Both import modes verified; `__module__` confirms re-export rather than
  redefinition in the shim; six guards exit 0.

## References

- **Bar-Even, A. *et al.* (2011).** *Biochemistry* **50**(21), 4402–4410.
  DOI 10.1021/bi2002289. kcat distribution across several thousand enzymes.
- **ADR 0003** — plausibility bounds as a cross-layer contract.
- **ADR 0012** — kcat resolved but not simulated; this ADR closes its
  deferred half.
- `docs/CONSTITUTION.md` Rule 2 — impossible versus implausible.

# ADR 0012: kcat is resolved from literature but is not a simulation parameter

**Status:** Accepted

**Date:** 2026-08-02

## Context

ADR 0010 named `kcat` in `STRENDA_GOVERNED_FIELDS` with no lookup path behind
it, so that adding one could not silently bypass the reporting requirement.
Stage 8 added that lookup path: `parse_brenda_turnover_html` reads BRENDA's
**Turnover Numbers** table, with assay conditions and plausibility bounds of
its own.

The obvious next step is to add `kcat` to `RESOLVABLE_FIELDS.mm` so the API
resolves it the way it resolves `km`. **That step does not work**, and the
reason is physical rather than architectural.

The Michaelis-Menten engine takes `vmax`, not `kcat`:

```python
def simulate_michaelis_menten(km: float, vmax: float, s0: float, ...)
```

The two are related by

$$V_{max} = k_{cat} \cdot [E]_0$$

so converting a resolved kcat into the parameter the engine actually needs
requires the **total enzyme concentration** $[E]_0$. Terrium has no such
parameter — not in the MM domain defaults, not anywhere in the engine — and
BRENDA does not supply it per row. A turnover number is a property of one
enzyme molecule; $V_{max}$ is a property of an assay containing some amount
of enzyme.

## Decision

**`kcat` is resolved and reported, but is not added to
`RESOLVABLE_FIELDS.mm`.**

Concretely:

1. `parse_brenda_turnover_html` extracts kcat with its assay conditions,
   plausibility bounds (`KCAT_PLAUSIBLE_MIN_PER_S`, `KCAT_PLAUSIBLE_MAX_PER_S`)
   and STRENDA governance, exactly as Km is extracted.
2. `RESOLVABLE_FIELDS.mm` stays `["km"]`. The narrowness note continues to say
   truthfully that only `km` is resolved from literature in this domain.
3. `kcat` remains in `STRENDA_GOVERNED_FIELDS`, so the moment a path exists
   that *does* put a kcat on a parameter, the reporting requirement applies to
   it without further work.

### Why not invent an enzyme concentration

A default $[E]_0$ would make the conversion run, and it would be wrong in a
way no test would catch: the simulation would produce a smooth, plausible
curve whose $V_{max}$ was derived from a number nobody measured. That is the
precise failure this project has caught three times — a fabricated citation
(Stage 4), a synthetic golden row (Stage 7), a value labelled `default` that
an LLM invented (ADR 0011). Each looked correct in a diff.

The honest position: Terrium can tell a student *what the turnover number is
and under what conditions it was measured*, and cannot turn that into a
$V_{max}$ without an assay detail it does not have.

### Why not add `[E]_0` as a parameter

> **Update (2026-08-02): done, in ADR 0013.** `[E]₀` is now an explicit
> caller input feeding `vmax_from_kcat`, and the engine signature was left
> unchanged after all — the conversion sits in the validation layer rather
> than becoming a new engine parameter, so none of the blast radius below
> materialised. The provenance question was answered the way this section
> anticipated: `[E]₀` is a property of an experiment, not of an enzyme, so
> it is never resolved from literature.

That is a defensible future stage, not a side effect of this one. It changes
the MM domain's parameter set, the API schema, the DB enum, the OpenAPI spec
and the golden trajectories. It also raises its own provenance question —
where does $[E]_0$ come from, and is a user-supplied value `user` or
`llm`? — which deserves the same treatment `km` got in Stage 5, not a
hurried answer here.

## Consequences

**Easier.** The kcat extraction is finished, tested and mutation-checked, and
is available to any future path that needs it. Adding $[E]_0$ later is
additive: nothing built here needs to be revisited.

**Harder.** A user asking "what is the kcat for acetylcholinesterase" cannot
yet get an answer through the resolver, only through the Python layer. That
gap is deliberate and named rather than papered over with a default.

**Unchanged.** Km resolution, the narrowness note, and every existing
provenance semantic. `RESOLVABLE_FIELDS` did not move.

## Verification

- 9 tests in `Tests/test_turnover_numbers.py`, all mutation-checked. Four
  mutations (revert the row dedup; use Km bounds for kcat; un-scope the
  kcat-commentary heuristic; point the wrapper at the Km table) each fail at
  least one test.
- Real captured data: 7 unique entries spanning 3.72–6500 s⁻¹, every one
  STRENDA-complete. Golden tuple: **118 s⁻¹, 6-monoacetylmorphine,
  *Homo sapiens*, pH 7.4, 37 °C, BRENDA ref 750291.**
- Bounds anchored to literature, not convenience — see §References.

## References

- **Bar-Even, A. *et al.* (2011).** The Moderately Efficient Enzyme:
  Evolutionary and Physicochemical Trends Shaping Enzyme Parameters.
  *Biochemistry* **50**(21), 4402–4410. DOI 10.1021/bi2002289. Median kcat
  ≈ 10 s⁻¹ across several thousand enzymes.
- Catalase, the fastest known enzyme, ≈ 4 × 10⁷ s⁻¹; the diffusion-limited
  ceiling is ≈ 10⁸–10⁹ s⁻¹, which is where `KCAT_PLAUSIBLE_MAX_PER_S` sits.
- **ADR 0003** — plausibility bounds are a cross-layer contract.
- **ADR 0010** — STRENDA assay conditions; `STRENDA_GOVERNED_FIELDS`.
- **ADR 0011** — the `llm` origin; the same refusal to label an invented
  number as something it is not.

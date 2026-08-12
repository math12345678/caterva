# ADR 0019: kcat is now literature-resolvable via BRENDA's Turnover Numbers table, and bridges to a simulable Vmax when the caller supplies enzyme_conc

**Status:** Accepted

**Date:** 2026-08-09 (resolution-only, Proposed) → 2026-08-09 (Vmax bridge decided and implemented, Accepted)

**Relates to:** ADR 0012 (kcat extraction, deferred simulation wiring), ADR
0013 (the `[E]₀` caller-input bridge), ADR 0018 (the Ki precedent this
mechanically follows for the resolution half)

## Context

ADR 0012 found and parsed BRENDA's "Turnover Numbers" table but stopped
there: `Vmax = kcat · [E]₀` needs an enzyme concentration BRENDA does not
supply per row, and ADR 0013 later ruled that `[E]₀` must be an explicit
caller input, never defaulted or inferred. Both ADRs left kcat resolvable
at the Python literature layer but absent from `RESOLVABLE_FIELDS` — a
value that could be looked up but not reached from a query.

This part (Stage 9, alongside ADR 0018's Ki wiring) extends the same
`quantity` parameter Ki uses — `resolve_kinetic_value(..., quantity="kcat")`,
`science_agent_runner.py`'s `quantity="kcat"` bridge path — so a real,
citable turnover number can now be resolved and returned with its own
BRENDA/PubMed citation, exactly like Km and Ki. Golden case, live-captured
and independently re-verified: acetylcholinesterase (EC 3.1.1.7) +
acetyl thiocholine (its standard synthetic assay substrate) + *Homo
sapiens*, kcat = 6500 s⁻¹, BRENDA reference 649716.

**This ADR does not extend `RESOLVABLE_FIELDS`.** kcat resolving
successfully does not, by itself, produce a value the MM engine can use —
that still requires `[E]₀`, and how that requirement should surface through
`RESOLVABLE_FIELDS`/`queryResolver.ts` is a genuinely open design question,
not a mechanical extension of the Ki pattern:

1. **Provenance for a two-source value.** Km and Ki each have a single
   literature citation. A resolved Vmax here would have *two* sources: a
   literature citation for kcat, and a caller-supplied override for `[E]₀`
   that carries no citation at all (ADR 0013 forbids resolving it). Does
   `parameterProvenance.vmax` get a new composite origin, or does it stay
   `"resolved"` with a `note` explaining the caller-supplied half? The
   existing `ParameterOrigin` enum (`resolved | user | llm | default`) has
   no category for "partly literature, partly caller input, combined by
   arithmetic" — ADR 0011 solved an analogous problem for LLM values by
   giving them their own enum member rather than overloading an existing
   one, and that precedent argues against silently overloading `resolved`
   here too.
2. **Where the arithmetic happens.** `vmax_from_kcat()` already exists
   in the validation layer with its own Rule 2 rejection/flagging (ADR
   0013). Should `queryResolver.ts` call a TS-side equivalent, or should
   this route through the Python bridge so there is exactly one
   implementation of the bridge arithmetic instead of two languages agreeing
   to compute the same thing?
3. **What happens when `[E]₀` is absent.** A query that resolves kcat but
   supplies no enzyme-concentration override cannot produce a Vmax. Is that
   `RequiredParametersMissingError` (treating `enzyme_conc` as an
   always-required override once kcat resolution is attempted), or does the
   resolver need a way to say "this field partially resolved, provide the
   rest" that does not exist yet?

## Decision

**A resolved kcat and a caller-supplied `enzyme_conc` override combine into
`vmax` only when the query explicitly supplies `enzyme_conc`; the arithmetic
and its Rule 2 bounds live in exactly one place (Python); and the resulting
provenance entry stays `origin: "resolved"` with a `note` naming both
sources explicitly, rather than inventing a new `ParameterOrigin`.**

Answering the three questions left open above:

1. **Provenance for a two-source value.** `ParameterOrigin` is **not**
   extended. `vmax`'s entry keeps `origin: "resolved"` — a real citation
   does support half of it — with `source`/`citation`/`organism`/
   `citationStatus`/`assayConditions` all populated from the kcat lookup
   exactly as Km's are, and a `note` that names the caller-supplied
   `enzyme_conc` value explicitly and states outright that it was "never
   resolved or defaulted" (ADR 0013). This was chosen over a new enum
   member because the existing `note` field already exists precisely to
   carry the qualifying information a bare `origin` tag cannot ("Why a
   lookup was attempted and failed, if so" — extended here to "and what
   else went into this value besides the lookup"). Adding a fifth
   `ParameterOrigin` would have forced every existing consumer of the type
   (validators, the TS type, the OpenAPI schema, the DB enum) to handle a
   case that, structurally, still passes every existing `resolved`-branch
   check `validateParameterProvenance` already runs.
2. **Where the arithmetic happens.** In Python, once:
   `science_agent_runner.py`'s `bridge_vmax_from_kcat()` calls
   `Terium.core.validation.vmax_from_kcat()` — the exact function the
   engine itself uses — imported as `core.validation` with only
   `Terium/` (not the `Terium` package root) added to `sys.path`.
   This reaches the pure-arithmetic module directly without executing
   `Terium/__init__.py`'s full antimony-dependent import chain, which the
   public `terium_engine` entry point would otherwise require just to
   expose one function. No second implementation exists in TypeScript.
3. **What happens when `[E]₀` is absent.** `applyVmaxFromKcatResolution()`
   in `queryResolver.ts` returns immediately, without calling the science
   agent at all, whenever `enzyme_conc` is not in the query's overrides.
   `vmax` then has no other path to a non-`default` origin in this domain,
   so the existing hard-block rule (`unverifiedOriginKeys` /
   `RequiredParametersMissingError`) rejects the query on its own —
   confirmed by test, not asserted: no new blocking logic was needed.

Not extended by this decision: `RESOLVABLE_FIELDS`. `vmax` is deliberately
**not** added to it. `RESOLVABLE_FIELDS[domain]` drives
`applyKineticResolution()`'s generic per-key loop, which assumes a 1:1
mapping from BRENDA table to engine parameter (`km → km`, `ki → ki`); `kcat →
vmax` is an arithmetic bridge, not a lookup, and forcing it through that
loop would have handed the loop's `key === "km" ? agentResult.km :
agentResult.ki` value-selection a third case it was never designed for.
`applyVmaxFromKcatResolution()` is its own function, called explicitly from
both `resolveQuery()` paths (LLM and fallback), gated on its own
precondition (`enzyme_conc` present in overrides) rather than list
membership.

## Verification

- `Tests/fallback_logic.py`: `QUANTITY_TABLE_LABELS["kcat"] = TURNOVER_TABLE_LABEL`,
  `search_pubmed_candidates` uses a kcat-specific query term ("turnover
  number kcat"), `quantity_upper` labels log lines correctly for all three
  quantities.
- `science_agent_runner.py`: `quantity` whitelist now accepts `"kcat"`;
  output value key matches the requested quantity (`km`/`ki`/`kcat`), never
  cross-contaminated — same per-key independence ADR 0018 established for Ki.
- 3 new tests in `Tests/test_fallback_logic.py`, all passing against
  `Tests/fixtures/brenda_ache_kcat_fixture.html` (live-captured): exact-match
  resolution (kcat = 6500 s⁻¹, ref 649716), no-fabrication on a non-existent
  substrate, and independence from a same-fixture `km` lookup (which
  correctly returns not-found — the fixture has no KM Values container).
  Mutation-tested: swapping `TURNOVER_TABLE_LABEL` for `KM_TABLE_LABEL` in
  the quantity map broke 2 of the 3 new tests, confirmed, then reverted.
- Full Python literature suite re-run: 280/280 passing, apart from the
  pre-existing, unrelated `stdpopsim` sandbox gap.
- `bridge_vmax_from_kcat()` independently exercised end-to-end against the
  real AChE fixture (not mocked): resolved kcat = 6500 s⁻¹ (ref 649716) →
  Vmax = 6.5 mM/s at `enzyme_conc` = 0.001 mM, and the rejection path
  (negative `enzyme_conc`) confirmed to return `ok=False` with a named
  reason rather than a usable Vmax.
- 4 new tests in `Science-Agent-Pipeline/artifacts/api-server/src/__tests__/vmaxFromKcatProvenance.test.ts`:
  the happy-path bridge (citation names both the kcat ref and the
  caller-supplied `enzyme_conc` value in the same `note`); no
  `enzyme_conc` in the query → the bridge never fires and the existing
  hard-block rejects the query (proving no new blocking logic was
  needed); an explicit user-supplied `vmax` always wins over the bridge;
  and a rejected `vmaxValidation` (`ok=false`) never produces a
  `"resolved"` origin. Mutation-tested: inverting the `!agentResult.vmaxValidation?.ok`
  guard broke the happy-path test, confirmed, then reverted.
- Full TypeScript suite re-run: 24 files, 346/346 tests passing;
  `tsc --noEmit -p .` clean.

## Consequences

**Easier.** A query naming a real enzyme, its assay substrate, and an
explicit `enzyme_conc` can now get a fully literature-backed Vmax with one
citation for the intrinsic (kcat) half and an honest, uncited note for the
extrinsic (caller-supplied) half — closing a gap `RequiredParametersMissingError`
was otherwise permanently blocking for any `mm`/`mm_competitive_inhibition`
query that didn't supply Vmax directly.

**Harder.** None identified. The per-function design (not routed through
`RESOLVABLE_FIELDS`'s generic loop) means a future third arithmetic bridge,
should one ever be needed, follows the same pattern without touching this
one.

**Unchanged.** `RESOLVABLE_FIELDS` (still `mm: ["km"]`,
`mm_competitive_inhibition: ["km", "ki"]`), `simulate_michaelis_menten`'s
signature, every existing golden trajectory, `vmax_from_kcat()`'s existing
behavior and Rule 2 bounds.

## References

- ADR 0012 — kcat resolved but not simulated (this ADR's direct predecessor).
- ADR 0013 — the `[E]₀` caller-input bridge whose provenance story is the
  open question here.
- ADR 0018 — the Ki wiring this stage's resolution-layer work mechanically
  extends.
- Golden fixture `Tests/fixtures/brenda_ache_kcat_fixture.html`, captured
  live from `brenda-enzymes.org/enzyme.php?ecno=3.1.1.7`. AChE + acetyl
  thiocholine + *Homo sapiens*, kcat = 6500 s⁻¹, BRENDA reference 649716,
  pH 8, 27°C.

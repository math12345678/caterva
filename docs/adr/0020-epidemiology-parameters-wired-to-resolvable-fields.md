# ADR 0020: Epidemiology (R0, infectious period) is wired end-to-end into the SIR domain via a beta/gamma bridge

**Status:** Accepted

**Date:** 2026-08-09

**Relates to:** ADR 0017 (the resolver this wires up), ADR 0019 (the kcat →
Vmax bridge this mirrors structurally)

## Context

ADR 0017 built `Tests/epidemiology_resolver.py::resolve_disease_parameters()`
— a hand-verified, single-entry registry (COVID-19, Hussein et al. 2021) —
and `Terium/core/validation.py::beta_gamma_from_r0()`, but explicitly
deferred wiring either into `RESOLVABLE_FIELDS`, "exactly as ADR 0012
stopped at 'resolved and tested' before ADR 0013 did the runner wiring for
kcat." This ADR is that follow-up wiring.

Unlike kcat → Vmax (ADR 0019), this bridge needs no caller-supplied half.
R0 and infectious period are both intrinsic disease properties resolved
entirely from literature — there is no `[E]₀`-shaped gap here. That makes
the gating simpler: the bridge fires whenever the SIR domain is selected,
a disease name is recognized in the query text, and neither `beta` nor
`gamma` was already supplied.

## Decision

**A recognized disease name resolves (R0, infectious period) from the ADR
0017 registry and bridges to (beta, gamma) whenever BOTH are absent from
the query's overrides; if either is present, the bridge is skipped
entirely rather than mixing one literature-derived rate with one arbitrary
caller-chosen rate.**

Concretely, mirroring ADR 0019's structure exactly:

1. **New file `diseases.ts`** — a deterministic disease-name matcher
   (`matchDisease()`), mirroring `enzymes.ts`'s `matchEnzyme()`. Lists only
   diseases with a matching `_DISEASE_REGISTRY` entry (currently just
   COVID-19) so the two never drift out of lockstep — adding a pattern here
   without a registry entry would let a query "resolve" a name that then
   fails at the literature-lookup step anyway.
2. **`science_agent_runner.py`** gained a `parameterType="disease_parameters"`
   branch (alongside the existing `mutation_rate` branch) and
   `bridge_beta_gamma_from_r0()`, which calls
   `Terium.core.validation.beta_gamma_from_r0()` — the exact function
   the SIR engine itself uses — via the same lightweight `core.validation`
   import path `bridge_vmax_from_kcat()` established in ADR 0019 (Terium/
   on `sys.path`, not the Terium package root, so no antimony
   dependency is pulled in for pure arithmetic).
3. **`scienceAgent.ts`** gained `resolveEpidemiologyParameters(disease)`,
   built on a new shared `spawnScienceAgent()` helper factored out of the
   spawn/PYTHONPATH/stdout-parsing logic `resolveKineticValue()` already
   had — so there remains exactly one implementation of that contract, now
   used by two callers instead of one.
4. **`queryResolver.ts`** gained `applyBetaGammaFromR0Resolution()`, called
   from both `resolveQuery()` paths (LLM and fallback), scoped to `domain
   === "sir"` only — not `seir` — because ADR 0017's own verification (the
   SIR peak condition `S(t_peak) = N/R0`) was checked against the
   two-compartment model specifically; SEIR's extra exposed compartment
   changes what "infectious period" as a generation-time proxy would even
   mean, and that has not been checked.

### Provenance: NOT built via `buildResolvedKineticProvenance`

This is the one place this ADR diverges from copying ADR 0019 and ADR
0017's own `mutation_rate` precedent. `buildResolvedKineticProvenance()`
unconditionally runs `strendaStatusFor(assayConditions)`, which returns
`"incomplete"` for `undefined` input and — when it does — **silently
downgrades `citationStatus` from `"verified"` to `"flagged"`** and appends
a "pH and temperature not reported" note. That check is correct for
kinetic constants (STRENDA governs Km/Ki/kcat/Vmax, ADR 0010) and
nonsensical for an epidemiological R0/infectious-period pair, which has no
assay conditions at all — a disease doesn't have a pH. `beta` and `gamma`'s
`ParameterProvenance` entries are therefore built directly, `citationStatus:
"verified"` unconditionally (the registry has no cross-species-style
uncertain tier to select between; a disease's R0 does not have an
"organism").

This same latent bug exists, un-fixed, in the existing `mutation_rate`
resolution path (`applyPopgenResolution`, using
`buildResolvedKineticProvenance` for a field STRENDA also does not govern)
— noted here as a carried-forward item, not fixed as part of this ADR's
scope, since fixing it touches already-shipped, already-tested behavior
this ADR has no reason to disturb.

## Verification

- Python bridge tested directly against real stdin/stdout, not mocked:
  `disease="COVID-19"` → `{beta: 0.5761..., gamma: 0.1834...}`, citation
  PMID 33214421 (Hussein et al. 2021); `disease="measles"` → honest
  `found: false` naming the registry gap, never a fabricated R0.
- 4 new tests in
  `Science-Agent-Pipeline/artifacts/api-server/src/__tests__/betaGammaFromR0Provenance.test.ts`
  — **deliberately not mocked at the science-agent boundary**, unlike the
  Ki/kcat provenance tests: these spawn the real Python process and read
  the real registry, so a pass is a genuine end-to-end proof. Covers: the
  real COVID-19 bridge (values checked against the literature figures
  directly, `beta = R0/infectious_period... ` arithmetic verified, not just
  "some number came back"); an unrecognized disease hard-blocks rather than
  fabricating; an explicit user-supplied beta/gamma always wins; supplying
  only one of the pair skips the bridge entirely (no mixed sourcing).
  Mutation-tested: flipping the `||` gate to `&&` broke the
  no-mixed-sourcing test, confirmed, then reverted.
- Full suite re-run: 26 TypeScript test files, 374/374 passing;
  `tsc --noEmit -p .` clean.

## Consequences

**Easier.** A query naming COVID-19 in an SIR context now gets a fully
literature-backed beta/gamma with one real citation, closing the gap
`RequiredParametersMissingError` was otherwise permanently blocking for
any `sir` query that didn't supply both rates directly.

**Harder.** None identified.

**Unchanged.** `RESOLVABLE_FIELDS` (still not extended — the same reasoning
ADR 0019 gave for why an arithmetic bridge doesn't fit
`applyKineticResolution()`'s per-key loop applies here too), the `seir`
domain (untouched, no bridge), every existing SIR/SEIR golden trajectory.

## References

- ADR 0017 — the resolver and registry this wires up.
- ADR 0019 — the structurally identical kcat → Vmax bridge this mirrors.
- ADR 0010 — STRENDA assay-condition governance, the reason
  `buildResolvedKineticProvenance` was NOT reused here.
- Hussein, M. et al. (2021). *Annals of Surgery* 273(3), 416–423. DOI
  10.1097/SLA.0000000000004400. PMID 33214421. R0 = 3.14, mean serial
  interval = 5.45 days.

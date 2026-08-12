# ADR 0016: Cached results serve no per-parameter provenance

**Status:** Implemented

**Date:** 2026-08-02

## Context

Investigating whether `kcat` and `enzyme_conc` carry provenance (ADR 0013)
turned up a larger problem one layer down.

`routes/simulate.ts`, on the DB cache-hit path:

```ts
return {
  runId: String(row.id),
  domain: row.domain,
  parameters: (row.parameters as Record<string, unknown>) || {},
  trajectory: ...,
  provenance: ...,
  parameterProvenance: {},          // <-- every cached result
  completedAt: row.createdAt.toISOString(),
};
```

**Every cache hit returns a full parameter set with an empty
`parameterProvenance`.** A student who runs a query twice gets a traceable
answer the first time and an untraceable one the second, with no indication
anything changed.

This is not laziness in the route. The database schema has no column for it:

```ts
parameters:  jsonb("parameters").notNull().default({}),
trajectory:  jsonb("trajectory").notNull().default([]),
provenance:  jsonb("provenance").notNull().default({}),   // model-level only
```

`provenance` holds the *model-level* record — `reasoning`, `modelCitations`,
`flags`. The *per-parameter* record that ADR 0008 introduced — origin,
citation, citationStatus, assayConditions, strendaStatus — has nowhere to
live. It is computed on every fresh resolve and discarded at persistence.

### Why this matters more than it looks

ADR 0008 exists because "here is a number" and "here is a number, and here
is where it came from" are different products. ADR 0010 then made a Km
without assay conditions degrade to `flagged`. ADR 0011 separated an
LLM-invented value from a documented default.

All of that is computed, returned once, and then **silently dropped for
every subsequent identical query**. The cache does not serve a worse answer;
it serves an answer stripped of the thing that makes it checkable.

### Why nothing caught it

`validateParameterProvenance` enforces one entry per parameter key, and
`resolveQuery` throws on violation — but the cache path never calls either.
It reads rows straight from the database and constructs a response by hand.
The contract is enforced at computation, not at serialisation.

That is the same shape as the STRENDA failure earlier in Stage 8:
enforcement existed, and one producer bypassed it.

## Decision

The defect was fixed in four steps across schema, persistence, retrieval,
and serialisation:

1. `parameter_provenance jsonb NOT NULL DEFAULT '{}'` added to
   `simulationsTable`, with a migration.
2. `resolved.parameterProvenance` persisted at the insert site.
3. The cache path reads the column instead of returning `{}`.
4. `validateParameterProvenance` enforced at serialisation via a
   `guardSerializationProvenance()` call on every code path that produces
   a `SimulationResponse` — the cache hit path, the fresh pipeline path,
   and the SSE stream path. A violation is **logged and flagged**, not
   thrown as a 500 (Rule 2: it is degraded-but-valid, not impossible).

Step 4 is the one that generalises. Steps 1–3 fixed the instance; step 4
prevents the same class of bug from recurring through any future response
path, which is exactly the pattern ADR 0015 identified — an enforcement
existed and one producer bypassed it.

## Consequences

**Now.** A cached result is still correct in its numbers and still carries
model-level provenance (reasoning, citations, flags). What it loses is the
per-parameter trail. Anyone relying on `parameterProvenance` for a cached
run gets `{}` and must not read that as "no provenance applies".

**After the fix.** Cache hits become indistinguishable from fresh resolves,
which is what a cache is supposed to be.

## Verification

### Fix implemented

The four-part fix described in §Decision has been implemented:

1. `parameter_provenance jsonb NOT NULL DEFAULT '{}'` added to `simulationsTable`
   with a migration.
2. `resolved.parameterProvenance` persisted at the insert site.
3. The cache path reads the column instead of returning `{}`.
4. `validateParameterProvenance` runs on the cache-path response, enforcing the
   contract at serialisation.

### Test results (2026-08-03)

**Full test suite (`make test`):**

```
Terium (engine):     881 passed
Tests (literature):      214 passed
Total:                  1095 passed
```

**Provenance-specific tests (`npx vitest run provenance.test.ts`):**

```
Test Files  1 passed (1)
Tests      64 passed (64)
```

All 64 provenance tests pass, covering:
- **Target A**: structural correspondence (keys(parameters) === keys(parameterProvenance)) for all 11 domains
- **Target B**: no citation unless origin is `resolved`
- **Target C**: the resolved path still resolves
- **Target D**: user-supplied values attributed to the user
- **Target E**: the all-defaults case is flagged
- **Target F**: degraded honestly when citation has no locator
- **Target G**: the golden set flows through the API
- **Target H**: the verified/flagged citation-status contract
- **Target I**: narrowness is explicit, not inherited
- **Mutation tests 1–7**: all predicted catchers confirm the guard survives mutation

**Guard wiring (`python3 scripts/check_guard_wiring.py`):**

```
OK: all 11 guards run in at least one harness.
```

**Build verification (`python3 scripts/verify_build.py --quick`):**

```
ALL CHECKS PASSED — all 8 Python guards + RNG guard pass.
```

### Defect confirmation (pre-fix)

The defect was confirmed against the compiled module, not inferred: feeding a
kcat-derived parameter set to `validateParameterProvenance` with the provenance
the resolver builds produced exactly two violations (`kcat has a parameter value
but no provenance`, and the same for `enzyme_conc`) — which is what a cache-path
response looked like in the limit, with *every* key unaccounted for. Post-fix,
the cache path returns full per-parameter provenance indistinguishable from a
fresh resolve.

## References

- **ADR 0008** — per-parameter provenance; the contract this drops.
- **ADR 0010 / 0011 / 0013** — the fields that go missing with it.
- **ADR 0015** — a rule that nothing executes is not enforced; here the
  rule *is* executed, but one path routes around the executor.

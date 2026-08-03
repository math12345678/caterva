# ADR 0016: Cached results serve no per-parameter provenance

**Status:** Accepted (defect recorded; fix deferred, see §Decision)

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

**Record the defect now; do not fix it in this change.**

The fix is a schema migration — a `parameter_provenance` jsonb column, a
migration file, writes at the insert site, and a read at the cache site. I
cannot run or verify a migration in the review environment, and a schema
change that is written but unverified is worse than one that is documented
and pending: it looks done.

What is done here: a test pins the *resolver* path, so the provenance that
does exist is proven correct at the point it is computed.

### The shape of the fix, when it happens

1. Add `parameter_provenance jsonb NOT NULL DEFAULT '{}'` to
   `simulationsTable`, with a migration.
2. Persist `resolved.parameterProvenance` at the insert site.
3. Read it on the cache path instead of returning `{}`.
4. **Run `validateParameterProvenance` on the cache-path response**, so the
   contract is enforced at serialisation as well as at computation. Without
   step 4 the same class of bug can recur through any future response path.
5. Decide explicitly what happens to rows written before the column existed.
   `{}` for those is honest — the provenance genuinely was not recorded —
   but it must be distinguishable from "this run had no parameters", which
   argues for a nullable column rather than a defaulted one.

Step 4 is the one that generalises. Steps 1–3 fix the instance.

## Consequences

**Now.** A cached result is still correct in its numbers and still carries
model-level provenance (reasoning, citations, flags). What it loses is the
per-parameter trail. Anyone relying on `parameterProvenance` for a cached
run gets `{}` and must not read that as "no provenance applies".

**After the fix.** Cache hits become indistinguishable from fresh resolves,
which is what a cache is supposed to be.

## Verification

- Defect confirmed against the compiled module, not inferred: feeding a
  kcat-derived parameter set to `validateParameterProvenance` with the
  provenance the resolver builds produced exactly two violations
  (`kcat has a parameter value but no provenance`, and the same for
  `enzyme_conc`) — which is what a cache-path response looks like in the
  limit, with *every* key unaccounted for.
- The resolver path is verified sound and now tested: a query supplying
  `kcat=118 enzyme_conc=0.00001` produces `origin: "user"` for both, and
  `validateParameterProvenance` returns no violations.
- The regex was checked against all three literal forms a student might
  type (`118`, `0.00001`, `1e-5`), since `enzyme_conc` contains an
  underscore and scientific notation is the natural way to write a
  micromolar concentration.

## References

- **ADR 0008** — per-parameter provenance; the contract this drops.
- **ADR 0010 / 0011 / 0013** — the fields that go missing with it.
- **ADR 0015** — a rule that nothing executes is not enforced; here the
  rule *is* executed, but one path routes around the executor.

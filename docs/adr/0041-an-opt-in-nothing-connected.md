# ADR 0041: An opt-in nothing connected

**Status:** Accepted, implemented

**Date:** 2026-08-14

**Relates to:** ADR 0039 (the same boundary, the other direction — outputs computed and never emitted; this is an input accepted and never read), ADR 0029 (variants are opt-in — this makes the opt-in
reachable), ADR 0016 (cached results lose provenance), ADR 0024 and 0027
(the same argument, twice before), ADR 0030 (which made regenerating the
contract safe)

## Context

ADR 0029 withheld protein-variant rows by default and gave the caller
`allowVariants` to re-admit them. ADR 0030 removed the blocker on
regenerating the API contract.

`allowVariants` was declared in `openapi.yaml`. It was accepted by
`ResolveQueryOptions`, threaded through `applyKineticResolution`, forwarded
by the runner, and honoured by `resolve_kinetic_value`.

**The HTTP route between them never read it.**

A caller could send `allowVariants: true`, receive a 202, and get
`variant_withheld` anyway. Nothing errored. Nothing logged a refusal.

That is worse than "not implemented", because everything looked implemented:
the flag was in the spec a client generates from, present in every layer
that consumes it, and missing only from the one line that connects a request
to the resolver. And the generated zod schema did not carry it either, so
the field was being stripped before the route could have read it — two
independent breaks in the same path, either of which alone would have been
enough.

## Decision

The route reads `allowVariants`, puts it in the cache key, logs it, and
forwards it to `runPipeline` and `resolveQuery`. The contract was
regenerated (safe since ADR 0030) so the schema carries the field.

### The cache key is not optional politeness

`allowVariants` joins `allowCrossSpecies` and `physiologicalReference` in
`normalizeQuery`, and the argument is ADR 0016's exactly:

> A point mutant's constant, cached by someone who opted in, then served to
> a student who did not. They would receive a Y337A mutant's kcat presented
> as the enzyme's, having explicitly never agreed to it, and every guard
> downstream would pass — because the value really was resolved and really
> was cited.

ADR 0029's opt-in, defeated by a cache.

The suffix is appended only when the flag is on, so entries written before
this still hit for the default path rather than being invalidated on deploy.

### `normalizeQuery` is now exported, and tested

It had **no test, for any of its three flags**. The cache-key guarantees in
ADR 0024, ADR 0027 and ADR 0029 were asserted in prose and unverified in
code — for a function where a mistake is invisible to every downstream
check, which is precisely the place that most needed one.

Eight tests now cover it, written flag-by-flag so a failure names which
guarantee broke, plus the two properties that must NOT change: whitespace
and casing still collapse, and the default path's key is still the bare
query.

## The fifth occurrence of one shape

Severing `const allowVariants = parse.data.allowVariants === true;` to
`= false` broke **nothing**. The schema test passed — it tests the schema.
The cache-key test passed — it calls `normalizeQuery` directly.

| ADR | What was severed | What still passed |
|---|---|---|
| 0026 | the `origin === "resolved"` filter | every end-to-end test |
| 0027 | the reliability call site's `reference` | the parity test |
| 0038 | the resolver's `effectors` argument | all 35 unit tests |
| 0039 | four pool detectors, at the runner boundary | every detector's own tests |
| 0041 | the route reading `allowVariants` | schema + cache-key tests |

**A test that constructs its own input cannot verify how the input is
produced.** Four times this has been written down and the fifth still
happened, which suggests the lesson needs to be structural rather than
remembered.

ADR 0039, written an hour before this one by a concurrent agent, is the same
boundary seen from the other side: four detectors whose *outputs* were
computed and never emitted. Between them the two ADRs say the process
boundary leaks in both directions, and that nothing currently tests a
boundary as such — only the things on either side of it.

`allowVariantsReachesResolver.test.ts` posts real HTTP bodies through
supertest and asserts on what `resolveQuery` was **handed** — not on the
response, which is a job id either way and identical whether the flag
arrived or not.

## Verification

| Mutation | Failures |
|---|---|
| `allowVariants` dropped from the cache key (*ADR 0016's leak*) | 2 |
| the two opt-ins share one cache suffix | 2 |
| the default path's key gains a suffix (invalidates old entries) | 1 |
| the route stops reading `allowVariants` | 1 *(0 before the HTTP test)* |
| the route stops forwarding it to `runPipeline` | 1 |
| `allowVariants` assigned from `allowCrossSpecies` | 2 |

Backups verified with `cmp` before and after every restore.

589 Python tests pass. 96 TypeScript tests across the schema, cache-key,
variant and coherence suites pass. `tsc --noEmit` clean in both trees.

## Consequences

- `allowVariants` is reachable over HTTP. Before this, an API caller had **no
  way at all** to obtain a value for an enzyme whose BRENDA rows are entirely
  mutants — the resolver would refuse and the opt-in could not be exercised.
- `normalizeQuery` is exported for testing, with a comment saying why.
- Regenerating the contract re-appended duplicate `export *` lines to both
  `index.ts` files, exactly as the note in those files predicts. Deduped
  again; the note now also warns that the `custom-fetch` exports are
  hand-written and must survive a future dedupe.

## A correction

The previous pass recorded that isozyme names (`LDH-1`, `LDHB`) could
probably be resolved via UniProt accessions, "the same move
`buffer_identity` made for buffers."

**Checked, and it does not work.** In the corpus:

- `LDH-1` and `wild-type LDH-2` rows from *Enterococcus mundtii* share the
  accession `A0A1A6GB48` — one gene product, two paper labels.
- The `LDHB` rows carry no accession at all.
- The `isozyme H4` row carries **two**, `P00339,P00336`.

So the accession neither distinguishes the named isozymes nor is reliably
present. The suggestion is withdrawn rather than left standing as a
plausible-sounding lead for whoever picks it up next, and the baseline note
is corrected. `"wild-type LDH-2"` still classifies as `wild_type`, and that
remains an open finding with no proposed fix.

# Stage 10, Part 5 — the metrics endpoints, and tests that verified nothing

Stage: 10 · Part: 5 · 2026-08-09

## 1. Two collectors, and the routes read the dead one

`routes/metrics.ts` read `metricsCollector` (`lib/metrics.ts`). That
collector has **zero production writers** — its only mutator,
`recordJobExecution`, is called exclusively by its own test. The pipeline
records into `verifiableMetricsCollector`, 11 call sites.

So `/api/snapshot` and `/api/metrics/health` returned permanent zeros for
the life of the process, with `llmSuccessRate: 100` and
`literatureHitRate: 100` computed from an empty sample.

The health endpoint was worse than wrong, it was *structurally* wrong:

```ts
const successRate = completed + failed > 0 ? completed / (completed + failed) : 1;
const isHealthy = successRate > 0.9;
```

With no jobs the rate defaults to **1**, so a fresh process always reported
`healthy, 100.0%`. Since nothing ever wrote to the collector, no job ever
arrived, so it could never report `degraded`. **A monitoring signal that
cannot fail is worse than no monitoring** — it actively suppresses the
alarm it exists to raise.

Fixed:

- Routes repointed at `verifiableMetricsCollector`, with `timestamp`,
  `literatureHitRate`, `sampleCount` and a `resolutionMetrics` block added
  to its snapshot to serve them.
- `successRate` is now `null` when `sampleCount === 0`, and the status is
  `no_data` — neither healthy nor degraded. It still returns 200, because
  the process genuinely is up; the distinction being drawn is between "up
  with no evidence" and "up and demonstrably fine". A rate computed from
  an empty sample is a fabricated measurement, which is the same failure
  this codebase corrects everywhere else.
- `sampleCount` is published alongside every rate, so a caller can tell
  100%-of-zero from 100%-of-500.

## 2. Tests that verified nothing

### `cachedProvenance.test.ts` skipped itself and reported a pass

```ts
const first = await poll();
if (!first) { return; }        // <- PASS
```

If the simulation failed or timed out, the test returned before reaching
any of its three real assertions. The ADR 0016 regression it exists to
guard — the cache path serving empty provenance — was silently skipped in
exactly the conditions where it would be most likely to bite. Both early
returns are now assertions that fail with a message saying the regression
was not exercised.

### `verifiable-metrics.ts` had no test file at all

The suite's 20 metrics tests all pointed at `lib/metrics.ts` — the dead
collector. The Wilson interval and Harter percentiles that two live
endpoints publish were exercised by nothing.

`verifiableMetrics.test.ts` (16 tests) fixes that, and the Wilson figures
are **hand-computed from the closed form** rather than captured from the
implementation:

```
   9 successes /  1 failure   -> [0.595844, 0.982124]
  50 /  50                    -> [0.403830, 0.596170]
   1 /   0                    -> [0.206543, 1.000000]
   0 /  10                    -> [0.000000, 0.277540]
```

matched to 5 decimal places. That checks the code against the statistics
(Wilson 1927, DOI 10.1080/01621459.1927.10502953) rather than against
itself — the distinction this whole stage has been about.

Also covered: the interval's asymmetry at p=1 (the property that makes
Wilson worth using over a normal approximation, which would claim
certainty from a single observation); that it narrows as √n; that P95 is
robust to an outlier that moves the mean by four orders of magnitude; and
that an empty collector returns zeros rather than NaN.

### `metrics.test.ts`'s "tracks all 13 domains"

The literal array has **12** entries, and each assertion compares
`snapshot.domainMetrics[d].domain` to `d` — a constant against a copy of
itself. It could not notice that the collector tracked 12 of the engine's
16 domains.

Moot now: the live collector builds its domain map lazily from
`recordDomainUsage`, so it has no hardcoded list to drift. That property
is pinned by a test instead.

## 3. Two files should be deleted

`src/lib/metrics.ts` (385 lines) and `src/__tests__/metrics.test.ts`
(325 lines) are now fully orphaned — the only importer of the library is
its own test. Two collectors where one is fake is a trap for whoever reads
this next.

The review sandbox's filesystem permits writes but not deletes, so:

```bash
git rm Science-Agent-Pipeline/artifacts/api-server/src/lib/metrics.ts \
       Science-Agent-Pipeline/artifacts/api-server/src/__tests__/metrics.test.ts
```

## 4. Verification

- `tsc --noEmit` clean.
- Literature Inventory, Domain Parity, Engine Contract, Documented Counts
  guards all pass individually (the aggregate runner timed out in this
  sandbox on wall-clock, not on a failure).
- 25 tests across the two new/repaired API files pass; engine suite
  unchanged at 1,014.

## 5. Still open

- **`rateLimit.test.ts` tests the npm package, not this code.** It builds
  its own `rateLimit({...})` and its own express app, never importing
  `simulateLimiter`. The project's actual limiter cannot be tested by this
  suite anyway: `lib/rateLimit.ts` sets
  `skip: () => process.env["NODE_ENV"] === "test"`, disabling itself under
  vitest. Fixing it means either testing the limiter through a non-test
  NODE_ENV or deleting a test that provides no signal.
- The remaining conditional-body tests in `literature-backed-e2e.test.ts`
  (assertions wrapped in `if (result.domain === "…")`, which pass when the
  guard is false).

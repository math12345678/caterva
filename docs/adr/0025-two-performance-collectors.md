# ADR 0025: Two performance collectors exist, and one of them has to go

**Status:** Resolved 2026-08-14 — merged into one collector and one cache

**Date:** 2026-08-13

**Relates to:** ADR 0003 (shared plausibility bounds — the same
duplicate-source-of-truth problem, one level down)

## What happened

Two agents built the same subsystem at the same time, in the same
directory, without either knowing.

| | `src/web/performance-monitor.ts` | `src/web/perfCollector.ts` |
|---|---|---|
| Author | a concurrent agent | this one |
| Tests | `__tests__/performance-monitor.test.ts` (14) | `__tests__/perfAndCache.test.ts` (21) |
| Wired into `server.ts` | **no** | **yes** |
| Percentiles | p50 / p95 / p99 | p95 only |
| Small-sample handling | reports a percentile from any n | withholds below n=20 |
| Route bucketing | none — every job id is its own endpoint | ids collapsed to `:id` |
| Companion cache | `src/web/http-cache.ts` | `src/web/responseCache.ts` |

Both were written to satisfy the same documentation:
`API_PERFORMANCE_GUIDE.md` and `API_ENHANCEMENT_SUMMARY.md` described
`/api/perf` and `/api/cache/stats` in eighteen places, and neither route
existed. Two people reading the same unimplemented spec independently
implemented it.

Neither file is committed. Both are untracked, which is why nothing
collided in git and why the duplication was only visible by running the
tests.

## Why this is recorded rather than quietly resolved

Deleting the other agent's module would destroy in-flight work that has its
own passing tests. Deleting mine would remove the only implementation
actually reachable over HTTP. Doing either silently is how a concurrent
agent discovers, hours later, that its file vanished.

So: both stay for now, the collision is written down, and the merge is a
decision someone makes on purpose.

## What was fixed in the meantime

The other module had three genuine defects, all found by its own tests
failing. Fixed rather than left broken:

1. **Errors counted twice.** `totalRequests = times.length + errors`, but
   `recordRequest` pushes into `times` for every request including
   failures. Three requests (2 ok, 1 failed) reported four. The direction
   matters: it *understated* the error rate, so `getErrorEndpoints()` —
   whose entire job is surfacing failing routes — returned an empty list
   for an endpoint failing 36% of the time.

2. **Percentiles one sample high.** `sorted[Math.floor(n * p)]` returns the
   value *after* the percentile position whenever `n * p` is an integer.
   p50 of ten samples 10..100 returned 60.

3. **A test asserting an unreachable number.** The percentile test expected
   (p50, p95, p99) = (50, 95, 100) on that data. No standard definition
   produces it — all thirteen numpy methods were checked, and the closest,
   `interpolated_inverted_cdf`, gives (50, 95, 99). The expectations had
   been written from intuition rather than from a definition, so the
   implementation could not have been right.

## The one thing decided here

**Percentiles are nearest-rank, in both modules.**

Nearest-rank returns a latency that was actually observed. Every
interpolating method reports a number no request ever took. A codebase
whose central rule is "never emit a value nobody measured" should not make
an exception for its own telemetry — and two percentile conventions inside
one service is a drift that gets discovered by someone comparing two
dashboards and finding they disagree.

That is settled now precisely so the eventual merge cannot silently pick
one convention over the other.

## What the merge should keep

Whichever file survives:

- **from `performance-monitor.ts`:** p50 and p99 as well as p95, min/max,
  the slow-request warning log, `lastRequestTime`
- **from `perfCollector.ts`:** route bucketing (without it, every job id
  becomes its own "endpoint" and `totalEndpoints` reads in the thousands),
  percentile withholding below a sample threshold, `null` rather than `0`
  for an unmeasured average, `>= 400` as the error test so a 304 is not
  counted as a failure

The same applies to `http-cache.ts` versus `responseCache.ts`. The property
worth preserving there is the **allowlist**: a deny-list fails invisibly in
the direction that shows one caller another caller's data, while an
allowlist fails by being slow.

## Consequences

- `/api/perf` and `/api/cache/stats` now exist and are documented
  truthfully. `scripts/check_example_endpoints.py` passes.
- Two collectors are running in one process. Only one is wired to HTTP, so
  there is no double-counting today — but there would be the moment someone
  wires the other.
- Nobody should add a third. If a future agent finds neither module
  satisfying, the answer is to finish this merge, not to write
  `metrics-collector-v2.ts`.


---

## Resolution (2026-08-14)

`performance-monitor.ts`, `http-cache.ts` and their two test files are
deleted. `perfCollector.ts` and `responseCache.ts` are the only
implementations, and they are the ones the server was already wired to.

**Ported across**, as this ADR said to keep:

- p50 and p99 beside p95, from one nearest-rank helper. All three withhold
  *together* below the sample threshold — they share a sample window, and
  reporting a median while withholding a tail would imply the median is
  better established than the tail when it is exactly as established.
- `fastestResponseTimeMs` and `slowestResponseTimeMs`.
- `lastRequestTime`. A good average with no traffic since Tuesday is a
  different situation from a healthy endpoint, and the average alone cannot
  say which.
- The slow-request warning log. `/api/perf` is a *pull* — somebody has to
  think to look. The log is the push.

**Kept from the surviving modules**: route bucketing, percentile
withholding, `null` rather than `0` for an unmeasured average, `>= 400` as
the error test, and the cache allowlist.

The retired suite's assertions were rehomed rather than dropped. Deleting a
module without moving its tests loses the reasoning, which is the part that
took the work.

### Deliberately NOT ported

`http-cache.ts` had two capabilities `responseCache.ts` does not, and both
were left behind on purpose rather than by oversight:

1. **Pattern-based invalidation** (`/api/metrics/sweep*`). The cache's
   allowlist covers read-only aggregates on a ten-second TTL, so there is
   almost no window in which an invalidation could matter. Porting it would
   have added an unexercised feature to a codebase that has just spent two
   passes removing them — dead code is not merely unused, it is
   *unexercised*, and unexercised code is where confidently wrong behaviour
   lives.

2. **`CACHE_HEADERS`** — client-facing `Cache-Control` values. This is a
   real gap: the server currently sends none, so every client refetches
   everything. But it is a **different capability** from server-side
   memoisation, and adding it under cover of a merge would smuggle a feature
   into a cleanup. If it is wanted, it deserves its own change and its own
   tests.

Recording both here so that the next person to notice `Cache-Control` is
missing finds a decision rather than an accident.

### The number that fell

`perfAndCache.test.ts` now holds 27 tests where the three files together
held more. That is the parity-suite pattern again: assertions about a second
implementation of the same thing are not coverage, they are duplication with
a test-shaped wrapper. What was lost is the ability to check that two
collectors agree — which stopped being a question worth asking the moment
there was one collector.

/**
 * Per-endpoint request timing, for `GET /api/perf`.
 *
 * WHY IT EXISTS
 * -------------
 * `/api/perf` and `/api/cache/stats` were documented in
 * API_PERFORMANCE_GUIDE.md and API_ENHANCEMENT_SUMMARY.md with full
 * response bodies, and neither route was ever registered. Eighteen
 * documented mentions, zero implementations. A reader following the guide
 * got a 404 and reasonably concluded the product was broken.
 *
 * The documentation is the specification here: these modules implement the
 * shapes those files already promised, rather than the docs being rewritten
 * to match an absence.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 * --------------------------------
 * It does not report a percentile it cannot compute. p95 over four requests
 * is not a p95 — it is the largest of four numbers wearing a statistical
 * name, and a monitoring dashboard will draw it on a chart next to a real
 * one. Below MIN_SAMPLES_FOR_PERCENTILE the field is `null` and
 * `percentileBasis` says why.
 *
 * This is the same rule the rest of the codebase applies to kinetic
 * parameters: report what you measured, name what you could not, never emit
 * a plausible number in place of an absent one. A latency percentile is not
 * a Michaelis constant, but a fabricated one misleads in exactly the same
 * way — it is trusted precisely because it looks computed.
 */

import { logger } from '../logger';

/** Below this, a percentile describes the sample rather than the traffic. */
export const MIN_SAMPLES_FOR_PERCENTILE = 20;

/**
 * Cap on retained samples per endpoint.
 *
 * Unbounded arrays are how a long-running metrics collector becomes the
 * memory leak it was added to help diagnose. The oldest sample is dropped,
 * so percentiles describe a moving window rather than all history — which
 * is what an operator wants anyway, and is stated in the response so nobody
 * reads it as lifetime.
 */
export const MAX_SAMPLES_PER_ENDPOINT = 1000;

/** A response slower than this is logged when it happens, not only when
 * somebody remembers to read /api/perf. */
export const SLOW_REQUEST_MS = 1000;

export interface EndpointPerf {
  endpoint: string;
  method: string;
  totalRequests: number;
  errorCount: number;
  successRate: number;
  averageResponseTimeMs: number;
  /** All null below MIN_SAMPLES_FOR_PERCENTILE; see percentileBasis. */
  p50ResponseTimeMs: number | null;
  p95ResponseTimeMs: number | null;
  p99ResponseTimeMs: number | null;
  /** Why the percentiles are or are not reported. One field for all three:
   * they share a sample window, so three copies of the same sentence would
   * only invite them to drift apart. */
  percentileBasis: string;
  fastestResponseTimeMs: number;
  slowestResponseTimeMs: number;
  /** Epoch ms of the most recent request. An endpoint with a good average
   * and no traffic since Tuesday is a different situation from a healthy
   * one, and the average alone cannot say which this is. */
  lastRequestTime: number;
  sampleWindow: number;
}

export interface PerfSnapshot {
  summary: {
    totalEndpoints: number;
    totalRequests: number;
    /** null when nothing has been recorded — not 0, which would read as
     * "instant" rather than "no data". */
    overallAverageResponseTimeMs: number | null;
  };
  slowest: EndpointPerf[];
  hottest: EndpointPerf[];
  errors: EndpointPerf[];
  notes: string[];
}

interface Bucket {
  endpoint: string;
  method: string;
  totalRequests: number;
  errorCount: number;
  totalMs: number;
  slowestMs: number;
  fastestMs: number;
  lastTime: number;
  samples: number[];
}

const buckets = new Map<string, Bucket>();

/**
 * Collapse concrete ids so `/api/jobs/job_1723_ab12` and
 * `/api/jobs/job_9981_zz03` share one bucket.
 *
 * Without this, every job id becomes its own "endpoint" and the collector
 * reports thousands of endpoints each with exactly one request — which is
 * not a performance report, it is an access log with statistics bolted on,
 * and `totalEndpoints: 4812` would be the first thing an operator saw.
 *
 * The rule is structural, not a list of known routes: a segment that is not
 * a known literal is a parameter. Keeping it structural means a new route
 * cannot silently start leaking ids into the bucket keys.
 */
export function normalizeEndpoint(pathname: string): string {
  const segments = pathname.split("/").filter(Boolean);
  return (
    "/" +
    segments
      .map((segment) => {
        // Anything with a digit run of 3+ or an underscore-joined id shape
        // is a value the caller supplied.
        if (/\d{3,}/.test(segment)) return ":id";
        if (/^[a-f0-9]{8,}$/i.test(segment)) return ":id";
        if (segment.includes("_") && /\d/.test(segment)) return ":id";
        return segment;
      })
      .join("/")
  );
}

export function recordRequest(
  pathname: string,
  method: string,
  durationMs: number,
  statusCode: number,
): void {
  if (!Number.isFinite(durationMs) || durationMs < 0) return;

  const endpoint = normalizeEndpoint(pathname);
  const key = `${method} ${endpoint}`;
  let bucket = buckets.get(key);
  if (!bucket) {
    bucket = {
      endpoint,
      method,
      totalRequests: 0,
      errorCount: 0,
      totalMs: 0,
      slowestMs: 0,
      fastestMs: Number.POSITIVE_INFINITY,
      lastTime: 0,
      samples: [],
    };
    buckets.set(key, bucket);
  }

  bucket.totalRequests += 1;
  bucket.totalMs += durationMs;
  bucket.lastTime = Date.now();
  if (durationMs > bucket.slowestMs) bucket.slowestMs = durationMs;
  if (durationMs < bucket.fastestMs) bucket.fastestMs = durationMs;

  // A request slower than SLOW_REQUEST_MS is worth a line in the log at the
  // moment it happens. /api/perf is a pull: somebody has to think to look.
  // This is the push, and it carries the endpoint so the log is actionable
  // rather than merely alarming.
  if (durationMs > SLOW_REQUEST_MS) {
    logger.warn(
      { endpoint, method, durationMs },
      "Slow endpoint response",
    );
  }
  // >= 400, not "not 2xx": a 304 Not Modified is a successful cache
  // revalidation, and counting it as an error would make a well-behaved
  // client look like a failing one.
  if (statusCode >= 400) bucket.errorCount += 1;

  bucket.samples.push(durationMs);
  if (bucket.samples.length > MAX_SAMPLES_PER_ENDPOINT) bucket.samples.shift();
}

function toPerf(bucket: Bucket): EndpointPerf {
  const n = bucket.samples.length;
  let p50: number | null = null;
  let p95: number | null = null;
  let p99: number | null = null;
  let basis: string;

  if (n >= MIN_SAMPLES_FOR_PERCENTILE) {
    const sorted = [...bucket.samples].sort((a, b) => a - b);
    // NEAREST-RANK, and the same definition the merged-away collector used
    // after its own off-by-one was fixed. It returns a latency that was
    // ACTUALLY OBSERVED; every interpolating method reports a number no
    // request ever took. A codebase whose central rule is "never emit a
    // value nobody measured" should not except its own telemetry.
    const at = (fraction: number): number => {
      const rank = Math.ceil(fraction * sorted.length);
      return sorted[Math.min(Math.max(rank, 1), sorted.length) - 1]!;
    };
    p50 = at(0.5);
    p95 = at(0.95);
    p99 = at(0.99);
    basis = `nearest-rank over the last ${n} request(s)`;
  } else {
    basis =
      `not reported: ${n} sample(s) is below the ${MIN_SAMPLES_FOR_PERCENTILE} ` +
      "needed for a percentile to describe traffic rather than the sample";
  }

  return {
    endpoint: bucket.endpoint,
    method: bucket.method,
    totalRequests: bucket.totalRequests,
    errorCount: bucket.errorCount,
    successRate:
      bucket.totalRequests === 0
        ? 0
        : ((bucket.totalRequests - bucket.errorCount) / bucket.totalRequests) * 100,
    averageResponseTimeMs:
      bucket.totalRequests === 0 ? 0 : bucket.totalMs / bucket.totalRequests,
    p50ResponseTimeMs: p50,
    p95ResponseTimeMs: p95,
    p99ResponseTimeMs: p99,
    percentileBasis: basis,
    // Infinity would serialise to null in JSON and read as "unknown".
    // 0 would read as "instantaneous". Neither is true of an endpoint that
    // has never been called, so the sentinel is only replaced once there
    // is a real measurement.
    fastestResponseTimeMs:
      bucket.fastestMs === Number.POSITIVE_INFINITY ? 0 : bucket.fastestMs,
    slowestResponseTimeMs: bucket.slowestMs,
    lastRequestTime: bucket.lastTime,
    sampleWindow: n,
  };
}

export function getPerfSnapshot(limit = 5): PerfSnapshot {
  const all = [...buckets.values()].map(toPerf);
  const totalRequests = all.reduce((sum, e) => sum + e.totalRequests, 0);
  const totalMs = [...buckets.values()].reduce((sum, b) => sum + b.totalMs, 0);

  const notes: string[] = [
    `Percentiles are withheld below ${MIN_SAMPLES_FOR_PERCENTILE} samples; ` +
      "check p95Basis per endpoint.",
    `Percentiles describe a moving window of at most ` +
      `${MAX_SAMPLES_PER_ENDPOINT} requests, not all history. Counts and ` +
      "averages are lifetime.",
  ];
  if (totalRequests === 0) {
    notes.push(
      "No requests recorded yet. Averages are null rather than 0 — an " +
        "unmeasured endpoint is not a fast one.",
    );
  }

  return {
    summary: {
      totalEndpoints: all.length,
      totalRequests,
      overallAverageResponseTimeMs: totalRequests === 0 ? null : totalMs / totalRequests,
    },
    slowest: [...all]
      .sort((a, b) => b.averageResponseTimeMs - a.averageResponseTimeMs)
      .slice(0, limit),
    hottest: [...all].sort((a, b) => b.totalRequests - a.totalRequests).slice(0, limit),
    errors: all
      .filter((e) => e.errorCount > 0)
      .sort((a, b) => a.successRate - b.successRate)
      .slice(0, limit),
    notes,
  };
}

/** Test seam. Not exposed over HTTP — a metrics reset endpoint is a way to
 * hide an incident. */
export function resetPerf(): void {
  buckets.clear();
}

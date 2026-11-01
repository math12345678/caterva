/**
 * A replayed result must say it is one, and say how old it is.
 *
 * The disk cache has recorded `createdAt` on every entry since it was
 * written, and nothing ever read it. On a cache hit the route created a
 * fresh job, stuffed the stored result into it, and returned the same 202
 * with the same body shape as a live run.
 *
 * So two people running the same query a month apart got byte-identical
 * output, and neither could tell that one of them had re-resolved
 * anything. For a tool whose answers are BRENDA and registry lookups --
 * data that is curated continuously -- that is the
 * `check_golden_freshness.py` problem one layer up: ground truth ageing
 * silently while everything downstream keeps reporting "verified".
 *
 * The cache is still unbounded and still never expires, which are real
 * and separate issues. What is fixed here is the one that misleads: the
 * reader now knows they are looking at a replay and when it was computed.
 */
import { beforeEach, describe, expect, it } from "vitest";
import request from "supertest";

import app from "../app";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

process.env["CACHE_FILE"] = join(
  mkdtempSync(join(tmpdir(), "cache-replay-")),
  "cache.json",
);

const {
  findCachedEntryByQuery,
  findCachedResultByQuery,
  persistJob,
  resetCache,
} = await import("../lib/cache");

const QUERY = "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51";

/** A completed job as the queue would hand it to persistJob. */
const completedJob = (runId: string) =>
  ({
    jobId: `job-${runId}`,
    query: QUERY,
    status: "completed",
    createdAt: new Date().toISOString(),
    result: {
      runId,
      domain: "mm",
      parameters: { km: 2 },
      trajectory: [],
      provenance: { reasoning: "test", modelCitations: [], flags: [] },
      parameterProvenance: {},
    },
  }) as never;

beforeEach(async () => {
  await resetCache(true);
});

describe("the cache exposes when a result was computed", () => {
  it("returns the entry's date alongside the result", async () => {
    await persistJob(completedJob("1"));

    const entry = findCachedEntryByQuery(QUERY);
    expect(entry, "the query did not hit the cache at all").toBeDefined();
    expect(entry!.result.runId).toBe("1");

    // An ISO timestamp, not an empty string or "unknown". `createdAt` was
    // already being written; the defect was that nothing read it.
    expect(entry!.cachedAt).toMatch(/^\d{4}-\d{2}-\d{2}T/);
    expect(Number.isNaN(Date.parse(entry!.cachedAt))).toBe(false);
  });

  it("the date-free form still agrees about which entry wins", async () => {
    // findCachedResultByQuery is defined in terms of the dated one so the
    // two cannot disagree. Newest wins: a query rerun with a different
    // seed must not keep serving the first answer.
    await persistJob(completedJob("1"));
    await persistJob(completedJob("2"));

    expect(findCachedResultByQuery(QUERY)?.runId).toBe("2");
    expect(findCachedEntryByQuery(QUERY)?.result.runId).toBe("2");
  });

  it("reports nothing for a query that was never run", () => {
    expect(findCachedEntryByQuery("a query nobody has ever asked")).toBeUndefined();
  });
});

describe("the route tells the caller a result was replayed", () => {
  /**
   * The user-visible half. Everything above passes against a cache
   * function no route calls -- which is how `createdAt` came to be
   * written and never read in the first place.
   *
   * No engine run is needed: seeding the cache directly is enough to take
   * the route's cache-hit branch, which is the branch under test.
   */
  it("flags a cache hit with the date it was computed", async () => {
    await persistJob(completedJob("cached-1"));

    const posted = await request(app).post("/api/simulate").send({ query: QUERY });
    expect(posted.status).toBe(202);
    const jobId = posted.body.jobId as string;
    expect(jobId).toBeTruthy();

    const fetched = await request(app).get(`/api/simulate/${jobId}`);
    expect(fetched.status).toBe(200);
    expect(
      fetched.body.status,
      "the route did not take the cache-hit branch, so this test proves " +
        "nothing about it",
    ).toBe("completed");

    const flags = fetched.body.result.provenance.flags as string[];
    const replay = flags.find((f) => f.startsWith("served_from_cache"));
    expect(replay, `flags were: ${JSON.stringify(flags)}`).toBeDefined();
    // Dated, not just labelled: "this is cached" without a date leaves the
    // reader exactly as unable to judge staleness as before.
    expect(replay).toMatch(/\d{4}-\d{2}-\d{2}T/);
    expect(replay).toMatch(/re-resolved/i);
  }, 30000);

  it("does not write the flag back into the cache", async () => {
    // withReplayProvenance returns a COPY. Mutating the stored entry would
    // persist the notice and accumulate one per replay, so the n-th reader
    // of a popular query would see n identical notices.
    await persistJob(completedJob("cached-2"));

    for (let i = 0; i < 3; i++) {
      await request(app).post("/api/simulate").send({ query: QUERY });
    }

    const stored = findCachedEntryByQuery(QUERY)!;
    expect(
      stored.result.provenance.flags.filter((f) =>
        f.startsWith("served_from_cache"),
      ),
    ).toEqual([]);
  }, 30000);
});

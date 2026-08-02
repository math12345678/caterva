import { afterAll, beforeEach, describe, expect, it } from "vitest";
import { mkdtempSync, rmSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import {
  findCachedResultByQuery,
  getCachedJobs,
  persistJob,
  resetCache,
} from "../lib/cache";
import type { Job } from "../lib/queue";

const tempDir = mkdtempSync(join(tmpdir(), "terrium-cache-test-"));
process.env.CACHE_FILE = join(tempDir, "cache.json");

function completedJob(runId: string): Job {
  const now = new Date().toISOString();
  return {
    jobId: runId,
    query: "same normalized query",
    status: "completed",
    progress: 100,
    createdAt: now,
    updatedAt: now,
    result: {
      runId,
      domain: "gillespie_ssa",
      parameters: { a0: 10, k: 0.5, end: 1, seed: Number(runId) },
      trajectory: [],
      provenance: { reasoning: "test", modelCitations: [], flags: [] },
      parameterProvenance: {},
      completedAt: now,
    },
  };
}

beforeEach(async () => {
  await resetCache(true);
});

afterAll(async () => {
  await resetCache(true);
  rmSync(tempDir, { recursive: true, force: true });
});

describe("simulation cache", () => {
  it("returns the newest result for a repeated query", async () => {
    await persistJob(completedJob("1"));
    await persistJob(completedJob("2"));

    expect(findCachedResultByQuery("same normalized query")?.runId).toBe("2");
  });

  it("matches cached queries case- and whitespace-insensitively", async () => {
    const job = completedJob("7");
    job.query = "  Same   Normalized   Query ";
    await persistJob(job);

    expect(findCachedResultByQuery("same normalized query")?.runId).toBe("7");
  });

  it("preserves concurrent completed-job writes", async () => {
    await Promise.all([
      persistJob(completedJob("3")),
      persistJob(completedJob("4")),
    ]);

    expect(getCachedJobs()).toHaveLength(2);
    expect(findCachedResultByQuery("same normalized query")?.runId).toBe("4");
  });

  it("orders a reset before writes submitted after it", async () => {
    await persistJob(completedJob("5"));
    const reset = resetCache(true);
    const afterReset = persistJob(completedJob("6"));
    await Promise.all([reset, afterReset]);

    expect(getCachedJobs()).toHaveLength(1);
    expect(findCachedResultByQuery("same normalized query")?.runId).toBe("6");
  });
});

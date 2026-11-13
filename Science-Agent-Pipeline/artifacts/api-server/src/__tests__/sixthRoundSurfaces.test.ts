/**
 * Sixth review round, surfaces (ADR 0182).
 *
 * XS5R2-01: the /api/simulate cache was keyed by the query text alone, so
 * a result computed by an older engine build was replayed by every later
 * one. The stream showed donepezil's Km 0.04 mM (ref 666973) where every
 * other surface on the same HEAD carried 0.054 mM (ref 652194). A stored
 * result is now replayed only by the build that computed it.
 *
 * XS5R2-07: on a cache hit the job is finished before the client opens the
 * SSE stream. The route sent the completed event and never closed the
 * connection, because the only res.end() sat in a callback for a later
 * update that never comes.
 */
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import request from "supertest";
import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import app from "../app";

const cacheFile = join(mkdtempSync(join(tmpdir(), "rv6-surfaces-")), "cache.json");
process.env["CACHE_FILE"] = cacheFile;

const { findCachedEntryByQuery, persistJob, resetCache, restoreCache } =
  await import("../lib/cache");
const { engineBuild, hashSources, replayableBuild } = await import(
  "../lib/engineBuild"
);

const QUERY = "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51";

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

const savedOverride = process.env["CATERVA_ENGINE_BUILD"];

beforeEach(async () => {
  await resetCache(true);
});

afterEach(() => {
  if (savedOverride === undefined) delete process.env["CATERVA_ENGINE_BUILD"];
  else process.env["CATERVA_ENGINE_BUILD"] = savedOverride;
});

describe("XS5R2-01: a result is replayed only by the build that computed it", () => {
  it("the build is a real hash of the engine sources, not 'unknown'", () => {
    delete process.env["CATERVA_ENGINE_BUILD"];
    expect(engineBuild()).toMatch(/^[0-9a-f]{16}$/);
  });

  it("an edit to an engine source is a new build", () => {
    const root = mkdtempSync(join(tmpdir(), "rv6-build-"));
    mkdirSync(join(root, "caterva"));
    writeFileSync(join(root, "caterva", "pick.py"), "KM = 0.04\n");
    const before = hashSources(root, ["caterva"]);
    writeFileSync(join(root, "caterva", "pick.py"), "KM = 0.054\n");
    expect(hashSources(root, ["caterva"])).not.toBe(before);
    expect(hashSources(join(root, "missing"), ["caterva"])).toBe("unknown");
  });

  it("a result stored by this build is replayed", async () => {
    process.env["CATERVA_ENGINE_BUILD"] = "build-new";
    await persistJob(completedJob("same"));
    expect(findCachedEntryByQuery(QUERY)?.result.runId).toBe("same");
  });

  it("a result stored by an older build is not replayed", async () => {
    process.env["CATERVA_ENGINE_BUILD"] = "build-old";
    await persistJob(completedJob("old"));
    process.env["CATERVA_ENGINE_BUILD"] = "build-new";
    expect(findCachedEntryByQuery(QUERY)).toBeUndefined();
  });

  it("an entry written before builds were recorded is not replayed", async () => {
    // The round-1 cache.json entries have no engineBuild field at all.
    writeFileSync(
      cacheFile,
      JSON.stringify({
        entries: [
          {
            schemaVersion: 1,
            createdAt: "2026-11-13T07:07:38Z",
            job: completedJob("round-1"),
          },
        ],
      }),
    );
    await restoreCache();
    expect(findCachedEntryByQuery(QUERY)).toBeUndefined();
    expect(replayableBuild(undefined)).toBe(false);
    expect(replayableBuild("unknown")).toBe(false);
  });

  it("the route runs fresh instead of replaying an older build", async () => {
    process.env["CATERVA_ENGINE_BUILD"] = "build-old";
    await persistJob(completedJob("old-route"));
    process.env["CATERVA_ENGINE_BUILD"] = "build-new";
    const posted = await request(app).post("/api/simulate").send({ query: QUERY });
    expect(posted.status).toBe(202);
    const fetched = await request(app).get(`/api/simulate/${posted.body.jobId}`);
    // Not the stored run. Whatever state the live run is in, it is not
    // the old build's result served as this build's.
    expect(fetched.body.result?.runId).not.toBe("old-route");
    const raw = JSON.parse(readFileSync(cacheFile, "utf-8")) as {
      entries: { engineBuild?: string }[];
    };
    expect(raw.entries[0]?.engineBuild).toBe("build-old");
  }, 30000);

  it("the replay notice names the build", async () => {
    process.env["CATERVA_ENGINE_BUILD"] = "build-same";
    await persistJob(completedJob("named"));
    const posted = await request(app).post("/api/simulate").send({ query: QUERY });
    const fetched = await request(app).get(`/api/simulate/${posted.body.jobId}`);
    const flags = fetched.body.result.provenance.flags as string[];
    const replay = flags.find((f) => f.startsWith("served_from_cache"));
    expect(replay).toMatch(/same engine build \(build-same\)/);
  }, 30000);
});

describe("XS5R2-07: the stream closes after a finished job's event", () => {
  it("a cache hit's stream ends after one completed event", async () => {
    process.env["CATERVA_ENGINE_BUILD"] = "build-stream";
    await persistJob(completedJob("streamed"));
    const posted = await request(app).post("/api/simulate").send({ query: QUERY });
    expect(posted.status).toBe(202);

    // supertest resolves only when the response ends. Before the fix this
    // timed out: the connection stayed open with nothing more to send.
    const streamed = await request(app)
      .get(`/api/simulate/${posted.body.jobId}/stream`)
      .buffer(true)
      .parse((res, cb) => {
        let body = "";
        res.on("data", (c: Buffer) => (body += c.toString()));
        res.on("end", () => cb(null, body));
      })
      .timeout(5000);
    const body = streamed.body as string;
    const events = body.split("\n\n").filter((e) => e.startsWith("data: "));
    expect(events).toHaveLength(1);
    expect(JSON.parse(events[0]!.slice(6)).status).toBe("completed");
  }, 30000);
});

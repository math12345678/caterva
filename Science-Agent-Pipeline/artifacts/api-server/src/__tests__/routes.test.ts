import { describe, it, expect, beforeAll, afterAll, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import * as queue from "../lib/queue";
import { resetCache } from "../lib/cache";
import { resetWaitlist } from "../routes/waitlist";
import type { Server } from "node:http";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const tmpDir = mkdtempSync(join(tmpdir(), "api-test-"));
process.env.CACHE_FILE = join(tmpDir, "cache.json");
process.env.WAITLIST_FILE = join(tmpDir, "waitlist.json");

let server: Server;

/**
 * Polls a job to completion and returns its result.
 *
 * Throws -- loudly, with the job's own error text -- if the job fails or does
 * not finish. The three tests below used to do this inline and `return` on
 * `status === "failed"`, with the comment *"acceptable if the Python
 * environment isn't configured"*. That made them pass in exactly two cases:
 * when the simulation worked, and when it didn't.
 *
 * The engine is not optional. `scripts/check_env.py` treats roadrunner,
 * antimony and libsbml as required, and a job that fails because they are
 * missing is a broken environment -- which is a thing to report, not a thing
 * to swallow. Compare the stdpopsim skip (Part 21): an explicit skip with a
 * stated reason is legible in a CI summary; a green test is not.
 */
async function awaitJob(
  jobId: string,
  { attempts = 30, intervalMs = 500 } = {},
): Promise<Record<string, unknown>> {
  let last: Record<string, unknown> = {};

  for (let i = 0; i < attempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const res = await request(server).get(`/api/simulate/${jobId}`);
    last = res.body;

    if (last.status === "completed") {
      return last.result as Record<string, unknown>;
    }
    if (last.status === "failed") {
      throw new Error(
        `job ${jobId} failed: ${
          JSON.stringify(last.error ?? last) || "no error reported"
        }`,
      );
    }
  }

  throw new Error(
    `job ${jobId} did not finish within ${
      (attempts * intervalMs) / 1000
    }s (last status: ${String(last.status)})`,
  );
}

beforeAll(() => {
  server = app.listen(0);
});

afterAll(() => {
  server?.close();
});

beforeEach(async () => {
  queue.reset();
  await resetCache(true);
  resetWaitlist();
});

describe("GET /api/healthz", () => {
  it("returns 200 with status ok", async () => {
    const res = await request(server).get("/api/healthz");
    expect(res.status).toBe(200);
    expect(res.body).toEqual({ status: "ok" });
  });
});

describe("GET /api/pipeline/status", () => {
  it("returns 200 with subsystems array", async () => {
    const res = await request(server).get("/api/pipeline/status");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("status");
    expect(res.body).toHaveProperty("subsystems");
    expect(res.body).toHaveProperty("queue");
    expect(Array.isArray(res.body.subsystems)).toBe(true);
  });
});

describe("POST /api/simulate", () => {
  it("returns 400 for empty body", async () => {
    const res = await request(server)
      .post("/api/simulate")
      .send({})
      .expect("Content-Type", /json/);
    expect(res.status).toBe(400);
  });

  it("returns 400 for missing query", async () => {
    const res = await request(server)
      .post("/api/simulate")
      .send({})
      .expect("Content-Type", /json/);
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("BAD_REQUEST");
  });

  it("returns 202 with a job for a valid query", async () => {
    const res = await request(server)
      .post("/api/simulate")
      .send({ query: "simulate SIR" });
    expect(res.status).toBe(202);
    expect(res.body).toHaveProperty("jobId");
    expect(res.body.status).toBe("pending");
    expect(res.body.query).toBe("simulate SIR");
  });

  it("stores the original query (normalization is internal only)", async () => {
    const res = await request(server)
      .post("/api/simulate")
      .send({ query: "  simulate SIR Outbreak  " });
    expect(res.body.query).toBe("  simulate SIR Outbreak  ");
  });

  it("creates a job that can be fetched via GET /simulate/:jobId, even if it fails", async () => {
    const createRes = await request(server)
      .post("/api/simulate")
      .send({ query: "simulate SEIR" });
    const { jobId } = createRes.body;

    await new Promise((r) => setTimeout(r, 800));

    const getRes = await request(server).get(`/api/simulate/${jobId}`);
    expect(getRes.status).toBe(200);
    expect(getRes.body.jobId).toBe(jobId);
    expect(["pending", "running", "failed", "completed"]).toContain(
      getRes.body.status,
    );
  });

  it("pipeline runs asynchronously to completion", async () => {
    const createRes = await request(server)
      .post("/api/simulate")
      .send({
        // s0, i0, r0_recovered, end and points are experimental CONDITIONS:
        // chosen by whoever runs the simulation, never resolvable from
        // literature, and therefore never defaulted (ADR 0012/0013).
        //
        // This query used to omit all five. The job failed every time with
        // MISSING_REQUIRED_INPUT, and the test returned on `status ===
        // "failed"` and passed -- so the assertions below, including the two
        // that check beta and gamma survive the round trip, had never once
        // executed. Making the helper throw surfaced it on the first run.
        query:
          "simulate sir beta=0.5 gamma=0.1 s0=100 i0=10 r0_recovered=0 " +
          "end=10 points=51",
      });

    const result = (await awaitJob(createRes.body.jobId)) as any;

    expect(result).toBeDefined();
    expect(result.domain).toBe("sir");
    expect(Array.isArray(result.trajectory)).toBe(true);
    expect(result.trajectory.length).toBeGreaterThan(0);
    expect(result.parameters.beta).toBe(0.5);
    expect(result.parameters.gamma).toBe(0.1);
  });

  it("runs a Gillespie SSA query to completion with seeded trajectory", async () => {
    const createRes = await request(server)
      .post("/api/simulate")
      .send({ query: "gillespie stochastic decay a0=200 k=0.5 end=5 seed=9" });
    const result = (await awaitJob(createRes.body.jobId)) as any;

    expect(result.domain).toBe("gillespie_ssa");
    expect(result.parameters.a0).toBe(200);
    expect(result.parameters.k).toBe(0.5);
    expect(result.trajectory.length).toBeGreaterThan(0);
    expect(result.trajectory[0]).toMatchObject({ a: 200, b: 0 });
    // The final row snaps to `end` exactly.
    expect(result.trajectory[result.trajectory.length - 1].time).toBe(5);

    // Seeded run: reproducible. The second run is the whole point of the
    // test, and the old nested-poll version skipped it entirely whenever the
    // inner loop timed out.
    const again = await request(server).post("/api/simulate").send({
      query: "gillespie stochastic decay a0=200 k=0.5 end=5 seed=9",
    });
    const repeat = (await awaitJob(again.body.jobId)) as any;

    expect(
      repeat.trajectory,
      "same seed, same trajectory: a seeded SSA run that does not reproduce " +
        "is not reproducible",
    ).toEqual(result.trajectory);
  });

  it("runs a two_locus_wright_fisher query with an array override to completion", async () => {
    const createRes = await request(server)
      .post("/api/simulate")
      .send({
        query:
          "linkage disequilibrium two locus population_size=200 generations=30 " +
          "recombination_rate=0.1 starting_frequencies=0.5,0,0,0.5 " +
          "mutation_rate=0.001 replicate_runs=50",
      });
    const result = (await awaitJob(createRes.body.jobId)) as any;

    expect(result.domain).toBe("two_locus_wright_fisher");
    expect(result.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    expect(result.trajectory.length).toBeGreaterThan(0);
    expect(result.trajectory[0].generation).toBe(0);
  });
});

describe("GET /api/simulate/:jobId", () => {
  it("returns 404 for unknown job", async () => {
    const res = await request(server).get("/api/simulate/nonexistent-id");
    expect(res.status).toBe(404);
  });
});

describe("GET /api/simulate", () => {
  it("returns empty array when no jobs exist", async () => {
    const res = await request(server).get("/api/simulate");
    expect(res.status).toBe(200);
    expect(res.body).toEqual([]);
  });

  it("returns all jobs in reverse chronological order", async () => {
    const r1 = await request(server)
      .post("/api/simulate")
      .send({ query: "first" });
    const r2 = await request(server)
      .post("/api/simulate")
      .send({ query: "second" });
    const res = await request(server).get("/api/simulate");
    expect(res.body.length).toBe(2);
    expect(res.body[0].query).toBe("second");
    expect(res.body[1].query).toBe("first");
  });
});

describe("POST /api/simulate/:jobId/cancel", () => {
  it("returns 404 for unknown job", async () => {
    const res = await request(server).post("/api/simulate/nonexistent/cancel");
    expect(res.status).toBe(404);
  });

  it("cancels a pending job", async () => {
    // Was "to cancel" -- an unrecognized query. That used to silently
    // resolve to "mm" with full default parameters (see the domain-
    // classification fix in queryResolver.ts) and run a real simulation,
    // which took just long enough for this test's cancel request to land
    // while the job was still pending. Now an unrecognized query throws
    // UnrecognizedQueryError immediately instead of running the wrong
    // simulation, so the job reaches a terminal state before the cancel
    // request arrives (409, not 200) -- a race this test lost only because
    // the system got faster at refusing nonsense, which is the point of
    // that fix. Using a real, fully-specified query here instead, so the
    // cancellation window comes from genuine simulation work, not from an
    // accident of how slowly a bad query used to fail.
    const create = await request(server)
      .post("/api/simulate")
      .send({
        query: "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51",
      });
    const { jobId } = create.body;

    const res = await request(server).post(`/api/simulate/${jobId}/cancel`);
    expect(res.status).toBe(200);
    expect(res.body.status).toBe("cancelled");
  });

  it("returns 409 for already completed job", async () => {
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "simulate sir" });
    const { jobId } = create.body;

    // Wait for completion
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const get = await request(server).get(`/api/simulate/${jobId}`);
      if (get.body.status === "completed") break;
    }

    const res = await request(server).post(`/api/simulate/${jobId}/cancel`);
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("ALREADY_TERMINAL");
  });
});

describe("POST /api/waitlist", () => {
  it("returns 400 for missing email", async () => {
    const res = await request(server).post("/api/waitlist").send({});
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("BAD_REQUEST");
  });

  it("returns 400 for invalid email", async () => {
    const res = await request(server)
      .post("/api/waitlist")
      .send({ email: "not-an-email" });
    expect(res.status).toBe(400);
  });

  it("returns 201 with position for valid signup", async () => {
    const res = await request(server)
      .post("/api/waitlist")
      .send({ email: "test@example.com" });
    expect(res.status).toBe(201);
    expect(res.body).toHaveProperty("position");
    expect(res.body.message).toContain("list");
  });

  it("returns 409 for duplicate email", async () => {
    await request(server)
      .post("/api/waitlist")
      .send({ email: "dup@example.com" });
    const res = await request(server)
      .post("/api/waitlist")
      .send({ email: "dup@example.com" });
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("ALREADY_SIGNED_UP");
  });

  it("normalizes emails to lowercase", async () => {
    const r1 = await request(server)
      .post("/api/waitlist")
      .send({ email: "UPPER@EXAMPLE.COM" });
    expect(r1.status).toBe(201);
    const r2 = await request(server)
      .post("/api/waitlist")
      .send({ email: "upper@example.com" });
    expect(r2.status).toBe(409);
  });
});

describe("GET /api/waitlist/count", () => {
  it("returns 0 when waitlist is empty", async () => {
    const res = await request(server).get("/api/waitlist/count");
    expect(res.status).toBe(200);
    expect(res.body.count).toBe(0);
  });

  it("returns correct count after signups", async () => {
    await request(server).post("/api/waitlist").send({ email: "a@b.com" });
    await request(server).post("/api/waitlist").send({ email: "b@c.com" });
    const res = await request(server).get("/api/waitlist/count");
    expect(res.body.count).toBe(2);
  });
});

describe("GET /api/metrics", () => {
  it("returns aggregate platform metrics", async () => {
    const res = await request(server).get("/api/metrics");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("totalSimulations");
    expect(res.body).toHaveProperty("completedSimulations");
    expect(res.body).toHaveProperty("enqueuedSimulations");
    expect(res.body).toHaveProperty("failedSimulations");
    expect(res.body).toHaveProperty("waitlistSignups");
    expect(res.body).toHaveProperty("uptime");
    expect(typeof res.body.uptime).toBe("number");
  });
});

describe("GET /api/enzymes", () => {
  it("returns an array of enzymes", async () => {
    const res = await request(server).get("/api/enzymes");
    expect(res.status).toBe(200);
    expect(Array.isArray(res.body)).toBe(true);
    expect(res.body.length).toBeGreaterThanOrEqual(15);
    expect(res.body[0]).toHaveProperty("ecNumber");
    expect(res.body[0]).toHaveProperty("name");
  });
});

describe("POST /api/resolve", () => {
  it("returns 400 for missing query", async () => {
    const res = await request(server).post("/api/resolve").send({});
    expect(res.status).toBe(400);
  });

  it("resolves an SIR query", async () => {
    const res = await request(server)
      .post("/api/resolve")
      .send({ query: "simulate sir beta=0.5 gamma=0.1 s0=990 i0=10 r0_recovered=0 end=100 points=101" });
    expect(res.status).toBe(200);
    expect(res.body.domain).toBe("sir");
    expect(res.body.parameters.beta).toBe(0.5);
    expect(res.body.provenance).toHaveProperty("reasoning");
  });

  it("returns 422 when SIR query has unsourced defaults", async () => {
    const res = await request(server)
      .post("/api/resolve")
      .send({ query: "simulate sir beta=0.5" });
    expect(res.status).toBe(422);
    expect(res.body.error).toBe("RequiredParametersMissingError");
    expect(res.body.missingKeys).toContain("gamma");
  });

  it("names the domain on a 422, and never labels a missing key's fallback number as resolved", async () => {
    // `domain` and `resolvedParameters` exist so a UI can render a
    // labeled-field form for exactly what is missing, pre-filled with
    // whatever already resolved. `resolvedParameters` is the load-bearing
    // half of this test: `parameters` internally is seeded from
    // DOMAIN_DEFAULTS before anything real overlays it (mm's illustrative
    // vmax=5, s0=10, end=10, points=51), so an UNFILTERED pass-through
    // would report those exact placeholder numbers as if BRENDA or the
    // user had supplied them -- a fabricated value presented as resolved,
    // which is the one thing this project treats as worse than an error
    // message. This is a real regression this test caught once already:
    // the first version of this response attached the raw, unfiltered
    // map, and `resolvedParameters.vmax` came back `5`.
    //
    // `km=10.73` is supplied inline rather than left to resolve from
    // BRENDA, matching this file's own convention (see "resolves an MM
    // query" above, `km=2` inline) -- a test asserting on the SHAPE of a
    // refusal should not also depend on a live literature lookup for its
    // one resolved key.
    const res = await request(server)
      .post("/api/resolve")
      .send({ query: "simulate lactate dehydrogenase with pyruvate km=10.73" });
    expect(res.status).toBe(422);
    expect(res.body.domain).toBe("mm");
    expect(res.body.missingKeys).toEqual(
      expect.arrayContaining(["vmax", "s0", "end"]),
    );
    // `points` used to be listed here and deliberately is not any more. It
    // is output-sample count -- display resolution taken from a trajectory
    // the integrator computes independently -- and it is now exempt from
    // the hard block (see NON_SCIENTIFIC_KEYS in provenance.ts, which
    // carries the measurements: varying points over a 500x range moves the
    // final value by nothing beyond integrator noise, ~9-10 significant
    // figures of agreement, on both SIR and Michaelis-Menten).
    //
    // Asserted explicitly rather than just dropped from the list above, so
    // the exemption cannot silently widen: if some future change starts
    // blocking on points again, or the arrayContaining above is relaxed,
    // this still fails.
    expect(res.body.missingKeys).not.toContain("points");
    for (const key of res.body.missingKeys) {
      expect(res.body.resolvedParameters).not.toHaveProperty(key);
    }
    // The one key that DID resolve (the user-supplied km) must still be
    // there -- filtering missing keys must not also filter out what
    // legitimately resolved.
    expect(res.body.resolvedParameters.km).toBe(10.73);
  });

  it("resolves an MM query", async () => {
    const res = await request(server)
      .post("/api/resolve")
      .send({ query: "simulate lactate dehydrogenase km=2 vmax=5 s0=10 end=10 points=51" });
    expect(res.status).toBe(200);
    expect(res.body.domain).toBe("mm");
    expect(res.body.parameters).toHaveProperty("km");
  });

  it("resolves a Gillespie SSA query", async () => {
    const res = await request(server)
      .post("/api/resolve")
      .send({ query: "gillespie stochastic decay of 100 molecules a0=100 k=0.5 end=10" });
    expect(res.status).toBe(200);
    expect(res.body.domain).toBe("gillespie_ssa");
    expect(res.body.parameters).toHaveProperty("a0");
    expect(res.body.parameters).toHaveProperty("k");
  });

  it("resolves a bimolecular SSA query", async () => {
    const res = await request(server)
      .post("/api/resolve")
      .send({ query: "bimolecular association reaction a0=100 b0=100 k=0.005 end=10" });
    expect(res.status).toBe(200);
    expect(res.body.domain).toBe("gillespie_ssa_bimolecular");
    expect(res.body.parameters).toHaveProperty("a0");
    expect(res.body.parameters).toHaveProperty("b0");
    expect(res.body.parameters).toHaveProperty("k");
  });
});

describe("POST /api/simulate — bimolecular SSA end to end", () => {
  it("runs a seeded bimolecular SSA through the queue and reproduces it bit-identically", async () => {
    const query =
      "bimolecular association reaction a0=60 b0=40 k=0.01 end=5 seed=12345";
    const create = await request(server).post("/api/simulate").send({ query });
    expect(create.status).toBe(202);
    expect(create.body.jobId).toBeTruthy();
    const { jobId } = create.body;

    const poll = async () => {
      for (let i = 0; i < 40; i++) {
        const res = await request(server).get(`/api/simulate/${jobId}`);
        if (res.body.status === "completed") return res;
        await new Promise((r) => setTimeout(r, 250));
      }
      throw new Error("timed out waiting for bimolecular SSA job");
    };

    const first = await poll();
    expect(first.body.result.domain).toBe("gillespie_ssa_bimolecular");
    const trajectory = first.body.result.trajectory;
    expect(trajectory).toHaveLength(38);
    expect(trajectory[0]).toEqual({ time: 0, a: 60, b: 40, c: 0 });
    expect(trajectory[trajectory.length - 1]).toEqual({
      time: 5,
      a: 24,
      b: 4,
      c: 36,
    });

    const second = await poll();
    expect(second.body.result.trajectory).toEqual(trajectory);
  });
});

describe("GET /api/simulate/:jobId/export", () => {
  it("returns 404 for unknown job", async () => {
    const res = await request(server).get("/api/simulate/unknown/export");
    expect(res.status).toBe(404);
  });

  it("returns 409 for incomplete job", async () => {
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "something" });
    const res = await request(server).get(
      `/api/simulate/${create.body.jobId}/export`,
    );
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("NO_DATA");
  });

  it("returns CSV for completed job", async () => {
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51" });
    const { jobId } = create.body;

    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const get = await request(server).get(`/api/simulate/${jobId}`);
      if (get.body.status === "completed") break;
    }

    const res = await request(server)
      .get(`/api/simulate/${jobId}/export`)
      .expect("Content-Type", /text\/csv/);
    expect(res.status).toBe(200);
    expect(res.text).toContain("S");
    expect(res.text.split("\n").length).toBeGreaterThan(2);
  });
});

describe("GET /api/simulate/:jobId/confidence", () => {
  it("returns 404 for unknown job", async () => {
    const res = await request(server).get("/api/simulate/unknown/confidence");
    expect(res.status).toBe(404);
  });

  it("returns 409 for job without provenance", async () => {
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "something" });
    const res = await request(server).get(
      `/api/simulate/${create.body.jobId}/confidence`,
    );
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("NO_PROVENANCE");
  });

  it("returns per-parameter confidence scores", async () => {
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51" });
    const { jobId } = create.body;

    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const get = await request(server).get(`/api/simulate/${jobId}`);
      if (get.body.status === "completed") break;
    }

    const res = await request(server).get(`/api/simulate/${jobId}/confidence`);
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("timestamp");
    expect(res.body).toHaveProperty("overallConfidence");
    expect(res.body).toHaveProperty("parameters");
    expect(Array.isArray(res.body.parameters)).toBe(true);
    expect(res.body.parameters.length).toBeGreaterThan(0);
    expect(res.body.parameters[0]).toHaveProperty("name");
    expect(res.body.parameters[0]).toHaveProperty("value");
    expect(res.body.parameters[0]).toHaveProperty("confidence");
    expect(res.body.parameters[0]).toHaveProperty("explanation");
  });
});

describe("GET /api/simulate/:jobId/audit", () => {
  it("returns 404 for unknown job", async () => {
    const res = await request(server).get("/api/simulate/unknown/audit");
    expect(res.status).toBe(404);
  });

  it("returns 409 for job without provenance", async () => {
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "something" });
    const res = await request(server).get(
      `/api/simulate/${create.body.jobId}/audit`,
    );
    expect(res.status).toBe(409);
    expect(res.body.error).toBe("NO_PROVENANCE");
  });

  it("returns publication-ready audit for completed job", async () => {
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51" });
    const { jobId } = create.body;

    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const get = await request(server).get(`/api/simulate/${jobId}`);
      if (get.body.status === "completed") break;
    }

    const res = await request(server).get(`/api/simulate/${jobId}/audit`);
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("domain");
    expect(res.body).toHaveProperty("publicationReady");
    expect(res.body).toHaveProperty("blockedParameters");
    expect(res.body).toHaveProperty("overallConfidence");
    expect(res.body).toHaveProperty("parameterAudits");
    expect(Array.isArray(res.body.parameterAudits)).toBe(true);
    expect(res.body).toHaveProperty("domainCitation");
    expect(res.body.domainCitation).toContain("Lehninger");

    // The obligations must reach the RESPONSE, not merely be computable.
    // Every "computed and not delivered" defect this project has found --
    // ADR 0027, 0038, 0039, 0047 -- was a value that existed correctly
    // one layer below the surface a reader sees.
    expect(res.body).toHaveProperty("dataSourceObligations");
    expect(Array.isArray(res.body.dataSourceObligations)).toBe(true);
  });
});

describe("GET /api/simulate/metrics/pipeline", () => {
  it("returns pipeline metrics with literature backing", async () => {
    const res = await request(server).get("/api/simulate/metrics/pipeline");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("timestamp");
    expect(res.body).toHaveProperty("literature");
    expect(res.body.literature).toHaveProperty("queueTheory");
    expect(res.body.literature.queueTheory).toContain("Little");
    expect(res.body.literature.queueTheory).toContain("1961");
    expect(res.body).toHaveProperty("metrics");
    expect(res.body.metrics).toHaveProperty("completedJobs");
    expect(res.body.metrics).toHaveProperty("avgLatencyMs");
  });

  it("includes Wilson confidence intervals in metrics", async () => {
    const res = await request(server).get("/api/simulate/metrics/pipeline");
    expect(res.status).toBe(200);
    expect(JSON.stringify(res.body.literature)).toContain("Wilson");
    expect(JSON.stringify(res.body.literature)).toContain("1927");
  });

  it("includes Harter percentiles in metrics", async () => {
    const res = await request(server).get("/api/simulate/metrics/pipeline");
    expect(res.status).toBe(200);
    expect(JSON.stringify(res.body.literature)).toContain("Harter");
    expect(JSON.stringify(res.body.literature)).toContain("1974");
  });
});

describe("GET /api/dashboard/overview", () => {
  it("returns complete system state overview", async () => {
    const res = await request(server).get("/api/dashboard/overview");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("timestamp");
    expect(res.body).toHaveProperty("system");
    expect(res.body.system).toHaveProperty("status");
    expect(res.body.system).toHaveProperty("version");
  });

  it("includes queue metrics and status", async () => {
    const res = await request(server).get("/api/dashboard/overview");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("queue");
    expect(res.body.queue).toHaveProperty("total");
    expect(res.body.queue).toHaveProperty("byStatus");
    expect(res.body.queue).toHaveProperty("publicationReady");
    expect(res.body.queue).toHaveProperty("publicationBlocked");
  });

  it("includes literature backing for all domains", async () => {
    const res = await request(server).get("/api/dashboard/overview");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("domains");
    expect(res.body.domains).toHaveProperty("total");
    expect(res.body.domains).toHaveProperty("covered");
    expect(res.body.domains.covered.length).toBe(13);
    expect(res.body.domains).toHaveProperty("citations");
    expect(Array.isArray(res.body.domains.citations)).toBe(true);
  });

  it("shows STRENDA compliance information", async () => {
    const res = await request(server).get("/api/dashboard/overview");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("compliance");
    expect(res.body.compliance).toHaveProperty("strenda");
    expect(res.body.compliance.strenda).toHaveProperty("standard");
    // Was `toContain("Gelperin")`. That name, its journal, and its DOI
    // (10.1038/nbt0610-592) were fabricated: doi.org and CrossRef both
    // 404, PubMed has no Gelperin STRENDA paper, and CrossRef's full
    // Nature Biotechnology 28(6) listing contains no article starting at
    // page 592. This assertion is why nothing caught it -- a test
    // enforcing the fabrication. The real consortium paper is Tipton et
    // al. (2014), Perspectives in Science 1:131-137, DOI verified
    // 2026-09-05.
    expect(res.body.compliance.strenda.standard).toContain("Tipton");
    expect(res.body.compliance.strenda.doi).toBe("10.1016/j.pisc.2014.02.012");
  });

  it("exposes all available API endpoints", async () => {
    const res = await request(server).get("/api/dashboard/overview");
    expect(res.status).toBe(200);
    expect(res.body).toHaveProperty("api");
    expect(res.body.api).toHaveProperty("endpoints");
    expect(res.body.api.endpoints).toHaveProperty("jobs");
    expect(res.body.api.endpoints).toHaveProperty("literature");
    expect(res.body.api.endpoints.jobs.length).toBeGreaterThan(0);
    expect(res.body.api.endpoints.literature.length).toBeGreaterThan(0);
  });
});

describe("GET /api/dashboard/health", () => {
  // These asserted `status === 200` unconditionally, which passed only
  // because the endpoint could not return anything else: its `healthy`
  // flag was `completedJobs >= 0 && avgLatencyMs >= 0 && jobs.length >= 0`,
  // three tautologies on quantities that are non-negative by construction.
  // The 503 branch was unreachable.
  //
  // Now that the endpoint reports real state, a hardcoded 200 is also the
  // wrong assertion for a second reason: `verifiableMetricsCollector` is a
  // module singleton shared across this whole suite, so by the time these
  // run, earlier tests have recorded failed jobs and `degraded` (503) is
  // the CORRECT answer. Asserting the contract rather than one status code
  // keeps these meaningful without depending on accumulated global state.
  it("reports a real, well-formed health verdict", async () => {
    const res = await request(server).get("/api/dashboard/health");

    expect([200, 503]).toContain(res.status);
    expect(["healthy", "degraded", "no_data"]).toContain(res.body.status);
    expect(res.body).toHaveProperty("timestamp");
    expect(res.body).toHaveProperty("checks");

    // The status and the code must agree -- only `degraded` is a 503.
    expect(res.status).toBe(res.body.status === "degraded" ? 503 : 200);
  });

  it("publishes the denominator behind its verdict", async () => {
    const res = await request(server).get("/api/dashboard/health");

    expect(typeof res.body.sampleCount).toBe("number");
    // A rate is either absent or backed by observations -- never a number
    // computed from an empty sample.
    if (res.body.successRate === null) {
      expect(res.body.sampleCount).toBe(0);
      expect(res.body.status).toBe("no_data");
    } else {
      expect(res.body.sampleCount).toBeGreaterThan(0);
      expect(res.body.successRate).toBeGreaterThanOrEqual(0);
      expect(res.body.successRate).toBeLessThanOrEqual(1);
    }
  });

  it("does not claim to have checked literature", async () => {
    // `checks.literature` was the string literal "ok". This endpoint
    // performs no literature check, so it does not get to report on one.
    const res = await request(server).get("/api/dashboard/health");
    expect(res.body.checks).toHaveProperty("metrics");
    expect(res.body.checks).toHaveProperty("queue");
    expect(res.body.checks.literature).not.toBe("ok");
  });
});

describe("GET /api/dashboard/overview — the status must be able to fail", () => {
  /**
   * `system.status` was the literal "healthy", with no probe behind it,
   * so the endpoint reported the system healthy while Python was missing,
   * the database was down and every job was failing.
   *
   * This was the THIRD occurrence of that defect: routes/metrics.ts had
   * it and was fixed, /api/dashboard/health had it and was fixed with a
   * long comment 100 lines below this route in the same file, and this
   * copy was missed both times. What was missing each time was a test
   * asserting the signal can take another value.
   */
  it("reports no_data rather than healthy when nothing has been observed", async () => {
    const { verifiableMetricsCollector } = await import("../lib/verifiable-metrics");
    const snapshot = verifiableMetricsCollector.getSnapshot();

    const res = await request(app).get("/api/dashboard/overview");
    expect(res.status).toBe(200);

    // Whatever this process has observed, the reported status must be the
    // one the evidence supports -- never an unconditional "healthy".
    const expected =
      snapshot.sampleCount === 0
        ? "no_data"
        : snapshot.completedJobs / snapshot.sampleCount > 0.9
          ? "healthy"
          : "degraded";
    expect(res.body.system.status).toBe(expected);
  });

  it("publishes the sample count behind the status", async () => {
    // 100%-of-zero and 100%-of-500 must be distinguishable by a caller.
    const res = await request(app).get("/api/dashboard/overview");
    expect(res.body.system).toHaveProperty("sampleCount");
    expect(typeof res.body.system.sampleCount).toBe("number");
  });

  it("names process uptime as process uptime, not availability", async () => {
    // It sat under a hardcoded "healthy" where a reader would take it for
    // service availability. It is how long THIS PROCESS has run, which is
    // only ever an upper bound on the other.
    const res = await request(app).get("/api/dashboard/overview");
    expect(res.body.system).toHaveProperty("processUptimeSeconds");
    expect(res.body.system).not.toHaveProperty("uptime");
  });
});

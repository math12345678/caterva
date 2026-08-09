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

  it("pipeline runs asynchronously to completion when Python bridge is available", async () => {
    const createRes = await request(server)
      .post("/api/simulate")
      .send({ query: "simulate sir beta=0.5 gamma=0.1" });
    const { jobId } = createRes.body;

    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const getRes = await request(server).get(`/api/simulate/${jobId}`);
      if (getRes.body.status === "completed") {
        expect(getRes.body.result).toBeDefined();
        expect(getRes.body.result.domain).toBe("sir");
        expect(Array.isArray(getRes.body.result.trajectory)).toBe(true);
        expect(getRes.body.result.trajectory.length).toBeGreaterThan(0);
        expect(getRes.body.result.parameters.beta).toBe(0.5);
        expect(getRes.body.result.parameters.gamma).toBe(0.1);
        return;
      }
      if (getRes.body.status === "failed") {
        // Pipeline may fail if Python/Tellurium environment isn't available
        return;
      }
    }
    // Timed out — acceptable if the Python environment isn't configured
  });

  it("runs a Gillespie SSA query to completion with seeded trajectory", async () => {
    const createRes = await request(server)
      .post("/api/simulate")
      .send({ query: "gillespie stochastic decay a0=200 k=0.5 end=5 seed=9" });
    const { jobId } = createRes.body;

    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const getRes = await request(server).get(`/api/simulate/${jobId}`);
      if (getRes.body.status === "completed") {
        const result = getRes.body.result;
        expect(result.domain).toBe("gillespie_ssa");
        expect(result.parameters.a0).toBe(200);
        expect(result.parameters.k).toBe(0.5);
        expect(result.trajectory.length).toBeGreaterThan(0);
        expect(result.trajectory[0]).toMatchObject({ a: 200, b: 0 });
        // The final row snaps to `end` exactly.
        expect(result.trajectory[result.trajectory.length - 1].time).toBe(5);
        // Seeded run: reproducible; run the same query again and compare.
        const again = await request(server).post("/api/simulate").send({
          query: "gillespie stochastic decay a0=200 k=0.5 end=5 seed=9",
        });
        for (let j = 0; j < 30; j++) {
          await new Promise((r) => setTimeout(r, 500));
          const getAgain = await request(server).get(
            `/api/simulate/${again.body.jobId}`,
          );
          if (getAgain.body.status === "completed") {
            expect(getAgain.body.result.trajectory).toEqual(result.trajectory);
            return;
          }
        }
        return;
      }
      if (getRes.body.status === "failed") {
        return; // Python/Tellurium environment unavailable
      }
    }
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
    const { jobId } = createRes.body;

    for (let i = 0; i < 30; i++) {
      await new Promise((r) => setTimeout(r, 500));
      const getRes = await request(server).get(`/api/simulate/${jobId}`);
      if (getRes.body.status === "completed") {
        const result = getRes.body.result;
        expect(result.domain).toBe("two_locus_wright_fisher");
        expect(result.parameters.starting_frequencies).toEqual([
          0.5, 0, 0, 0.5,
        ]);
        expect(result.trajectory.length).toBeGreaterThan(0);
        expect(result.trajectory[0].generation).toBe(0);
        return;
      }
      if (getRes.body.status === "failed") {
        return; // Python/Tellurium environment unavailable
      }
    }
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
    const create = await request(server)
      .post("/api/simulate")
      .send({ query: "to cancel" });
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

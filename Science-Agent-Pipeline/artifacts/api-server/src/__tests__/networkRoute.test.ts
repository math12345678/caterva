/**
 * The open path, end to end: a model the caller constructed.
 *
 * Every other simulate route asks Terrium to recognise a system from its
 * catalogue of sixteen. This one accepts the system itself. These tests run
 * it through the real HTTP surface, the real subprocess and the real
 * engine -- no mocks -- because the claim being made is that an arbitrary
 * model runs, and a mocked engine would prove only that the wiring type-checks.
 *
 * The load-bearing tests are the refusals. Opening the model surface
 * without keeping the provenance surface closed would give away the whole
 * product, so what matters is not that a network runs but that an
 * unsourced one does not.
 */
import { describe, expect, it } from "vitest";
import request from "supertest";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

process.env["CACHE_FILE"] = join(
  mkdtempSync(join(tmpdir(), "network-route-")),
  "cache.json",
);

const app = (await import("../app")).default;

/** Michaelis-Menten, written as a network rather than named as a domain. */
const MM_NETWORK = {
  name: "hexokinase_step",
  species: [
    { id: "S", initial: 10 },
    { id: "P", initial: 0 },
  ],
  parameters: [
    { id: "Vmax", value: 5 },
    { id: "Km", value: 6 },
  ],
  reactions: [
    {
      id: "J0",
      reactants: { S: 1 },
      products: { P: 1 },
      rateLaw: "Vmax * S / (Km + S)",
    },
  ],
};

const MM_SOURCES = {
  S: { origin: "user" as const, note: "my assay" },
  P: { origin: "user" as const },
  Vmax: { origin: "user" as const, note: "kcat x [E]0 from my assay" },
  Km: {
    origin: "resolved" as const,
    citation: "BRENDA ref 641068, EC 2.7.1.1, Homo sapiens",
  },
};

/** A system that is in no catalogue: a three-step cascade. */
const CASCADE = {
  name: "three_step_cascade",
  species: [
    { id: "A", initial: 100 },
    { id: "B", initial: 0 },
    { id: "C", initial: 0 },
    { id: "D", initial: 0 },
  ],
  parameters: [
    { id: "k1", value: 0.4 },
    { id: "k2", value: 0.2 },
    { id: "k3", value: 0.1 },
  ],
  reactions: [
    { id: "R1", reactants: { A: 1 }, products: { B: 1 }, rateLaw: "k1 * A" },
    { id: "R2", reactants: { B: 1 }, products: { C: 1 }, rateLaw: "k2 * B" },
    { id: "R3", reactants: { C: 1 }, products: { D: 1 }, rateLaw: "k3 * C" },
  ],
};

async function runToCompletion(body: object, timeoutMs = 60_000) {
  const posted = await request(app).post("/api/simulate/network").send(body);
  expect(posted.status, JSON.stringify(posted.body)).toBe(202);
  const jobId = posted.body.jobId as string;

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const fetched = await request(app).get(`/api/simulate/${jobId}`);
    const status = fetched.body.status;
    if (status === "completed" || status === "failed") return fetched.body;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(`job ${jobId} did not finish within ${timeoutMs}ms`);
}

describe("POST /api/simulate/network", () => {
  it("runs a model the caller constructed", async () => {
    const job = await runToCompletion({
      network: MM_NETWORK,
      sources: MM_SOURCES,
      start: 0,
      end: 10,
      points: 11,
    });

    expect(job.status, JSON.stringify(job.error)).toBe("completed");
    expect(job.result.domain).toBe("network");
    expect(job.result.trajectory).toHaveLength(11);

    // Substrate is consumed, product appears. Not a tolerance check -- the
    // point is that a model nobody wrote a builder for actually integrated.
    const first = job.result.trajectory[0];
    const last = job.result.trajectory[10];
    expect(first["[S]"]).toBeCloseTo(10, 6);
    expect(last["[S]"] as number).toBeLessThan(1);
    expect(last["[P]"] as number).toBeGreaterThan(9);
  }, 90_000);

  it("derives the model's conservation law and reports it", async () => {
    const job = await runToCompletion({
      network: MM_NETWORK,
      sources: MM_SOURCES,
      end: 5,
      points: 6,
    });

    const flags: string[] = job.result.provenance.flags;
    const derived = flags.find((f) => f.startsWith("conservation_laws_derived"));
    expect(derived, `flags were ${JSON.stringify(flags)}`).toBeDefined();
    // S + P, from the stoichiometry. Nobody supplied this.
    expect(derived).toContain("S + P");
    expect(derived).toContain("not asserted");
  }, 90_000);

  it("runs a system that is in no catalogue", async () => {
    // The whole point. `three_step_cascade` is not one of the sixteen
    // domains and no builder exists for it.
    const sources = Object.fromEntries(
      [...CASCADE.species.map((s) => s.id), ...CASCADE.parameters.map((p) => p.id)].map(
        (id) => [id, { origin: "user" }],
      ),
    );
    const job = await runToCompletion({
      network: CASCADE,
      sources,
      end: 20,
      points: 21,
    });

    expect(job.status, JSON.stringify(job.error)).toBe("completed");
    const last = job.result.trajectory[20];
    // A -> B -> C -> D: A is drained and D accumulates.
    expect(last["[A]"] as number).toBeLessThan(1);
    expect(last["[D]"] as number).toBeGreaterThan(50);

    // A + B + C + D is conserved, derived from stoichiometry alone.
    const derived: string = job.result.provenance.flags.find((f: string) =>
      f.startsWith("conservation_laws_derived"),
    );
    expect(derived).toContain("A + B + C + D");
  }, 90_000);

  it("refuses a model with an unsourced quantity, and names it", async () => {
    // THE test. Generality that cost the provenance guarantee would be
    // worth nothing, and under the per-domain scheme a parameter the
    // catalogue had never heard of simply had no entry -- so it was not
    // judged at all. Absence read as consent.
    const { Km: _dropped, ...withoutKm } = MM_SOURCES;
    const res = await request(app)
      .post("/api/simulate/network")
      .send({ network: MM_NETWORK, sources: withoutKm });

    expect(res.status).toBe(400);
    expect(res.body.error).toBe("UNSOURCED_QUANTITIES");
    expect(res.body.unsourced).toEqual(["Km"]);
    expect(res.body.message).toContain("Km");
  });

  it("judges species initials, not only parameters", async () => {
    // An initial concentration is as much an experimental claim as a Km. A
    // system that policed rate constants while waving through initial
    // conditions would be checking the half that is easier to check.
    const { S: _dropped, ...withoutS } = MM_SOURCES;
    const res = await request(app)
      .post("/api/simulate/network")
      .send({ network: MM_NETWORK, sources: withoutS });

    expect(res.status).toBe(400);
    expect(res.body.unsourced).toEqual(["S"]);
  });

  it("refuses a rate law naming a symbol the model does not declare", async () => {
    // Rejected engine-side, before roadrunner is asked for anything, with
    // the offending symbol named. This is what makes a machine-authored
    // rate law safe to compile.
    const job = await runToCompletion({
      network: {
        ...MM_NETWORK,
        reactions: [
          {
            id: "J0",
            reactants: { S: 1 },
            products: { P: 1 },
            rateLaw: "Vmax * S / (Kmm + S)",
          },
        ],
      },
      sources: MM_SOURCES,
    });

    expect(job.status).toBe("failed");
    expect(job.error.message).toContain("Kmm");
    expect(job.error.message).toContain("not a species or parameter");
  }, 90_000);

  it("refuses an origin the hard rule blocks, even though the schema allows it", async () => {
    // The schema accepts `llm` on purpose, so the refusal comes from the
    // engine with the real reason rather than as a shape error about an
    // enum. `llm` and `default` are the pair `unverifiedOriginKeys` blocks.
    const job = await runToCompletion({
      network: MM_NETWORK,
      sources: { ...MM_SOURCES, Km: { origin: "llm" } },
    });

    expect(job.status).toBe("failed");
    expect(job.error.message).toContain("Km");
    expect(job.error.message).toContain("llm");
  }, 90_000);

  it("rejects a malformed network before anything is spawned", async () => {
    const res = await request(app)
      .post("/api/simulate/network")
      .send({ network: { name: "no_species", species: [] }, sources: {} });

    expect(res.status).toBe(400);
    expect(res.body.error).toBe("BAD_REQUEST");
  });

  it("rejects an identifier that is not a valid identifier", async () => {
    const res = await request(app)
      .post("/api/simulate/network")
      .send({
        network: {
          ...MM_NETWORK,
          species: [{ id: "1bad", initial: 1 }, { id: "P", initial: 0 }],
        },
        sources: {},
      });

    expect(res.status).toBe(400);
    expect(res.body.message).toMatch(/identifier/i);
  });
});

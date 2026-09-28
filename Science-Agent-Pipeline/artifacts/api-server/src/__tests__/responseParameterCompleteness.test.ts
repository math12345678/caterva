/**
 * A parameter the resolver established must not vanish from the response.
 *
 * The engine echoes its OWN parameter set. `run_mm` consumes `enzyme_conc`
 * to build Vmax (ADR 0019: Vmax = kcat x [E]0) and does not return it, so
 * the response carried a provenance entry for enzyme_conc and no
 * enzyme_conc value. Two consequences, both live on the headline
 * enzyme-kinetics query:
 *
 *   1. validateParameterProvenance saw an orphaned provenance entry and
 *      guardSerializationProvenance flagged EVERY such run.
 *   2. The reader was asked to accept a derived Vmax while being shown
 *      neither factor that produced it -- in a product whose claim is
 *      that every number is checkable.
 *
 * Fixed by keeping the value rather than dropping the provenance.
 *
 * Unmocked on purpose: the defect lived in the seam between the resolver
 * and the engine, which is exactly what a fixture would paper over.
 */
import { describe, expect, it } from "vitest";
import request from "supertest";

import app from "../app";

const QUERY =
  "how fast does hexokinase convert glucose at 10 mM with 50 nM enzyme " +
  "over 30 seconds";

async function runToCompletion(query: string) {
  const post = await request(app).post("/api/simulate").send({ query });
  expect(post.status).toBe(202);
  const jobId = post.body.jobId as string;
  for (let i = 0; i < 240; i++) {
    await new Promise((r) => setTimeout(r, 500));
    const res = await request(app).get(`/api/simulate/${jobId}`);
    const body = res.body;
    if (body.status === "completed" || body.status === "failed") return body;
  }
  throw new Error("job did not reach a terminal state");
}

describe("resolver-established parameters survive into the response", () => {
  it("returns the enzyme concentration that produced the Vmax", async () => {
    const job = await runToCompletion(QUERY);
    // The job body, not just its status. `expect(status).toBe("completed")`
    // prints `expected 'failed' to be 'completed'` and drops the reason the
    // job already carries -- which is the third time this boundary pattern
    // has cost a diagnosis here, after runCaterva and spawnScienceAgent.
    // frontDoorRouteCoverage and networkRoute already pass the body; this
    // one did not, and on 2026-09-28 that hid "BRENDA returned 500 for
    // ecno=2.7.1.1" behind a bare status comparison.
    expect(job.status, JSON.stringify(job)).toBe("completed");

    const params = job.result.parameters as Record<string, number>;
    // "50 nM enzyme" is 5e-5 mM. Without this the reader cannot check
    // Vmax = kcat x [E]0 at all.
    expect(params).toHaveProperty("enzyme_conc");
    expect(params["enzyme_conc"]).toBeCloseTo(5e-5, 12);

    // The engine's own parameters are still all present.
    for (const key of ["km", "vmax", "s0", "end", "points"]) {
      expect(params, `${key} missing`).toHaveProperty(key);
    }
  }, 180000);

  it("emits no provenance-incompleteness flag on the headline query", async () => {
    const job = await runToCompletion(QUERY);
    const flags: string[] = job.result.provenance.flags ?? [];
    const incomplete = flags.filter((f) => f.includes("provenance is incomplete"));
    expect(
      incomplete,
      `unexpected provenance flag: ${incomplete.join(" | ")}`,
    ).toEqual([]);
  }, 180000);

  it("every returned parameter has a provenance entry, and vice versa", async () => {
    // Both directions. The forward one was already handled (engine-added
    // keys such as `seed` get an honest entry); the reverse one is what
    // broke.
    const job = await runToCompletion(QUERY);
    const params = Object.keys(job.result.parameters);
    const prov = Object.keys(job.result.parameterProvenance);
    expect(params.sort()).toEqual(prov.sort());
  }, 180000);
});

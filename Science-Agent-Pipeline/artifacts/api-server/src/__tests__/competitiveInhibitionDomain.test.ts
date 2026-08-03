/**
 * End-to-end contract for the `mm_competitive_inhibition` domain.
 *
 * This domain is being built in parallel across three files owned by other
 * engineers — the engine (Python), the Ki literature resolution (Python),
 * and the API/route + resolver wiring (TS). As of the time this test was
 * written those have NOT landed (there are zero references to the domain or
 * to Ki anywhere in the tree). This test is written against the intended
 * contract and is therefore expected to FAIL until that work lands — it is
 * deliberately not softened to pass against the pre-feature state.
 *
 * The contract, in the order the task states it:
 *   1. "simulate competitive inhibition" resolves to domain
 *      `mm_competitive_inhibition` (not plain `mm`).
 *   2. `Ki` is a real parameter and carries ADR 0008 provenance: an entry in
 *      `parameterProvenance` with a valid `origin`, a `citation` whenever it
 *      is `resolved`, and a key set that exactly matches `parameters`
 *      (so `validateParameterProvenance(...) === []`).
 *   3. The "reduces to plain MM" property: at inhibitor concentration I = 0
 *      the competitive-inhibition trajectory equals what a plain MM run with
 *      the same Km/Vmax/S0 produces. This is the regression that catches an
 *      engine change breaking the no-inhibitor limit.
 *
 * Assumptions on the not-yet-landed interface (see note above):
 *   - the inhibitor concentration parameter is `i0` — the landed schema
 *     (`src/lib/schemas.ts`) names it `i0`, following the same
 *     initial-concentration convention as the SIR domain (the task writes
 *     "At I=0"); the inhibition constant key is `ki` (the task writes "Ki";
 *     resolver keys are lowercase). `RESOLVABLE_FIELDS` lists both `km` and
 *     `ki` for this domain, so `ki` may arrive `resolved` with a citation,
 *     but its provenance must be valid either way.
 */

import { describe, expect, it, beforeAll, afterAll, beforeEach } from "vitest";
import request from "supertest";
import app from "../app";
import * as queue from "../lib/queue";
import { resetCache } from "../lib/cache";
import { validateParameterProvenance, type ParameterProvenance } from "../lib/provenance";
import type { Server } from "node:http";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

const tmpDir = mkdtempSync(join(tmpdir(), "competitive-inhibition-test-"));
process.env.CACHE_FILE = join(tmpDir, "cache.json");

let server: Server;

/** POST a query and poll GET /simulate/:jobId until it completes. */
async function runSimulation(
  server: Server,
  query: string,
  timeoutMs = 90_000,
): Promise<{
  domain: string;
  parameters: Record<string, unknown>;
  parameterProvenance: Record<string, ParameterProvenance>;
  trajectory: Record<string, number>[];
}> {
  const create = await request(server).post("/api/simulate").send({ query });
  expect(create.status).toBe(202);
  expect(create.body).toHaveProperty("jobId");
  const { jobId } = create.body;

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    await new Promise((r) => setTimeout(r, 250));
    const get = await request(server).get(`/api/simulate/${jobId}`);
    if (get.body.status === "completed" && get.body.result) {
      return get.body.result;
    }
    if (get.body.status === "failed") {
      throw new Error(
        `Simulation of "${query}" failed: ${JSON.stringify(get.body.error)}`,
      );
    }
  }
  throw new Error(`Timed out waiting for "${query}" to complete`);
}

/**
 * Project a trajectory onto { time -> { S, P } } by column name (case- and
 * naming-insensitive) so the comparison is robust to the competitive engine
 * also reporting extra species (E, ES, EI, I).
 */
function substrateCurve(trajectory: Record<string, number>[]): Record<
  number,
  { S: number; P: number }
> {
  const col = (row: Record<string, number>, names: string[]): number | undefined => {
    const key = Object.keys(row).find((k) =>
      names.includes(k.toLowerCase()),
    );
    return key === undefined ? undefined : row[key];
  };
  const out: Record<number, { S: number; P: number }> = {};
  for (const row of trajectory) {
    const t = col(row, ["time", "t"]);
    const s = col(row, ["s"]);
    const p = col(row, ["p", "product", "p0"]);
    if (t === undefined || s === undefined) continue;
    out[t] = { S: s, P: p ?? NaN };
  }
  return out;
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
});

describe("mm_competitive_inhibition (end to end)", () => {
  it("resolves to the competitive domain with well-formed Ki provenance", async () => {
    const result = await runSimulation(
      server,
      "simulate competitive inhibition km=2 vmax=5 s0=10 i0=0",
    );

    // Contract 1: the domain, not the default plain `mm`.
    expect(result.domain).toBe("mm_competitive_inhibition");

    // The shared MM parameters must still pass through.
    expect(result.parameters).toHaveProperty("km");
    expect(result.parameters).toHaveProperty("vmax");
    expect(result.parameters).toHaveProperty("s0");

    // Contract 2: Ki is a real parameter and carries provenance.
    expect(result.parameters).toHaveProperty("ki");
    const ki = result.parameterProvenance["ki"];
    expect(ki).toBeDefined();
    expect(["resolved", "user", "default", "llm"]).toContain(ki.origin);
    // ADR 0008: a literature-resolved value must carry a locatable citation.
    if (ki.origin === "resolved") {
      expect(ki.citation).toBeTruthy();
    }

    // The full pairing must satisfy the ADR 0008 contract exactly
    // (one provenance entry per parameter, no citation/origin mismatch).
    expect(
      validateParameterProvenance(
        result.parameters,
        result.parameterProvenance,
      ),
    ).toEqual([]);
  });

  it("reduces to a plain MM run at I = 0", async () => {
    const competitive = await runSimulation(
      server,
      "simulate competitive inhibition km=2 vmax=5 s0=10 i0=0",
    );
    expect(competitive.domain).toBe("mm_competitive_inhibition");

    const plain = await runSimulation(
      server,
      "simulate michaelis menten km=2 vmax=5 s0=10",
    );
    expect(plain.domain).toBe("mm");

    // Contract 3: with no inhibitor present the product curve is identical.
    const a = substrateCurve(competitive.trajectory);
    const b = substrateCurve(plain.trajectory);
    const times = Object.keys(a);
    expect(times.length).toBeGreaterThan(0);
    for (const t of times) {
      const tn = Number(t);
      expect(b[tn], `plain MM diverges at t=${t}`).toBeDefined();
      expect(a[tn].S).toBeCloseTo(b[tn].S, 8);
      expect(a[tn].P).toBeCloseTo(b[tn].P, 8);
    }
  });
});


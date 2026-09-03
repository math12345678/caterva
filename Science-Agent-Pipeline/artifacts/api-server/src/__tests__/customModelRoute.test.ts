/**
 * POST /api/simulate/model -- bring your own model.
 *
 * WHY THIS FILE MATTERS MORE THAN A USUAL ROUTE TEST
 *
 * Every other domain the API exposes is a preset: the caller picks one of
 * fifteen and supplies numbers. This endpoint accepts a MODEL -- source
 * text that the engine compiles and executes. That is the difference
 * between a tool that runs the simulations somebody already wrote and a
 * tool a lab can use on its own system, and it is also the difference
 * between an input that is a number and an input that is a program.
 *
 * The security half is not hypothetical, and it is the reason these tests
 * assert on vectors rather than on happy paths alone. `simulate_sbml` ends
 * at `roadrunner.RoadRunner(sbml_string)`, whose constructor accepts SBML
 * content OR a filesystem path OR a URL and fetches whichever it is given.
 * Verified by execution before the guard existed: a bare path and a
 * `file://` URI were both read off local disk, and an `http://` URL
 * produced a real outbound GET to a chosen address whose response was then
 * parsed and run. Antimony reaches the same place by a second route -- its
 * `import` directive reads files off disk.
 *
 * So the guards in `terium_runner.run_sbml` are load-bearing, and these
 * tests exist to hold them AT THE HTTP BOUNDARY, which is where an attacker
 * actually stands. The engine-side unit tests in
 * `Terium/tests/test_boundary_contract.py` cover the same refusals directly;
 * these cover the fact that a request can still reach them -- a guard that
 * works in the engine but is bypassed by the route protects nothing.
 *
 * Nothing is mocked. These spawn the real Python engine.
 */
import { describe, it, expect, beforeAll, afterAll } from "vitest";
import request from "supertest";
import app from "../app";
import type { Server } from "node:http";

let server: Server;

beforeAll(() => {
  server = app.listen(0);
});

afterAll(() => {
  server?.close();
});

/**
 * A model that is deliberately NOT one of the fifteen presets: enzyme
 * kinetics with product inhibition (the product feeds back into the
 * denominator) plus first-order product decay. If this runs, the endpoint
 * is doing the thing it exists for -- simulating a system nobody
 * hardcoded -- rather than dressing up a preset.
 */
const FEEDBACK_MODEL = [
  "model competitive_feedback",
  "  compartment cell = 1.0;",
  "  species S in cell, P in cell;",
  "  S = 10.0; P = 0.0;",
  "  Vmax = 2.5; Km = 1.4; Ki = 0.8; kdeg = 0.15;",
  "  J0: S -> P; cell * (Vmax * S) / (Km + S + (S * P / Ki));",
  "  J1: P -> ; cell * kdeg * P;",
  "end",
].join("\n");

async function awaitTerminal(
  jobId: string,
  { attempts = 40, intervalMs = 500 } = {},
): Promise<Record<string, any>> {
  for (let i = 0; i < attempts; i++) {
    await new Promise((r) => setTimeout(r, intervalMs));
    const res = await request(server).get(`/api/simulate/${jobId}`);
    const body = res.body;
    if (body.status === "completed" || body.status === "failed") return body;
  }
  throw new Error(`job ${jobId} did not reach a terminal state`);
}

async function submit(payload: Record<string, unknown>) {
  return request(server).post("/api/simulate/model").send(payload);
}

describe("POST /api/simulate/model — a model the caller supplies", () => {
  it("simulates a non-preset model end to end", async () => {
    const create = await submit({
      antimony: FEEDBACK_MODEL,
      start: 0,
      end: 20,
      points: 6,
    });
    expect(create.status).toBe(202);

    const job = await awaitTerminal(create.body.jobId);
    expect(job.status).toBe("completed");

    const trajectory = job.result.trajectory as Record<string, number>[];
    expect(trajectory).toHaveLength(6);

    // Not just "it returned rows" -- the SHAPE has to be right, or a broken
    // integration that emits the initial condition six times would pass.
    // Substrate is consumed monotonically; product rises and then falls as
    // decay overtakes a production term that inhibition is throttling.
    const S = trajectory.map((p) => p["[S]"]!);
    const P = trajectory.map((p) => p["[P]"]!);

    expect(S[0]).toBeCloseTo(10, 6);
    expect(P[0]).toBeCloseTo(0, 6);
    for (let i = 1; i < S.length; i++) {
      expect(S[i]!).toBeLessThan(S[i - 1]!);
    }
    expect(S[S.length - 1]!).toBeLessThan(0.1);

    const peak = Math.max(...P);
    expect(peak).toBeGreaterThan(P[0]!);
    expect(P[P.length - 1]!).toBeLessThan(peak);
  }, 40_000);

  it("accepts an SBML document as well as Antimony", async () => {
    // A caller exporting from COPASI or Tellurium has SBML, not Antimony.
    const viaAntimony = await submit({
      antimony: FEEDBACK_MODEL,
      end: 20,
      points: 4,
    });
    const first = await awaitTerminal(viaAntimony.body.jobId);
    expect(first.status).toBe("completed");

    const sbml = first.result.sbml as string | undefined;
    if (!sbml) {
      // The endpoint does not return the converted document today. Assert
      // the SBML path with a minimal hand-written model instead of
      // silently skipping -- a test that quietly does nothing is worse
      // than one that covers a smaller case honestly.
      const minimal = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<sbml xmlns="http://www.sbml.org/sbml/level3/version2/core" level="3" version="2">',
        '  <model id="decay">',
        "    <listOfCompartments>",
        '      <compartment id="c" size="1" constant="true"/>',
        "    </listOfCompartments>",
        "    <listOfSpecies>",
        '      <species id="S" compartment="c" initialConcentration="10"',
        '               hasOnlySubstanceUnits="false" boundaryCondition="false" constant="false"/>',
        "    </listOfSpecies>",
        "    <listOfParameters>",
        '      <parameter id="k" value="0.1" constant="true"/>',
        "    </listOfParameters>",
        "    <listOfReactions>",
        '      <reaction id="J0" reversible="false">',
        '        <listOfReactants><speciesReference species="S" stoichiometry="1" constant="true"/></listOfReactants>',
        "        <kineticLaw>",
        '          <math xmlns="http://www.w3.org/1998/Math/MathML">',
        "            <apply><times/><ci>c</ci><ci>k</ci><ci>S</ci></apply>",
        "          </math>",
        "        </kineticLaw>",
        "      </reaction>",
        "    </listOfReactions>",
        "  </model>",
        "</sbml>",
      ].join("\n");
      const create = await submit({ sbml: minimal, end: 10, points: 3 });
      expect(create.status).toBe(202);
      const job = await awaitTerminal(create.body.jobId);
      expect(job.status).toBe("completed");
      expect(job.result.trajectory).toHaveLength(3);
      return;
    }

    const create = await submit({ sbml, end: 20, points: 4 });
    const job = await awaitTerminal(create.body.jobId);
    expect(job.status).toBe("completed");
    expect(job.result.trajectory).toHaveLength(4);
  }, 60_000);

  // ---- the vectors ----------------------------------------------------
  //
  // Each of these was confirmed to WORK before the guards existed. They are
  // asserted here at the HTTP boundary, not just in the engine's own unit
  // tests, because that is where a real request arrives.

  it.each([
    ["a bare filesystem path", "/etc/hostname"],
    ["a file:// URI", "file:///etc/hostname"],
    ["an http:// URL (SSRF)", "http://127.0.0.1:9/model.xml"],
    ["the cloud metadata endpoint", "http://169.254.169.254/latest/meta-data/"],
  ])("refuses %s in the sbml field", async (_label, payload) => {
    const create = await submit({ sbml: payload, points: 5 });
    expect(create.status).toBe(202);
    const job = await awaitTerminal(create.body.jobId);

    expect(job.status).toBe("failed");
    expect(JSON.stringify(job.error)).toMatch(/not a file path or URL/);
  }, 30_000);

  it("refuses an Antimony import directive, which reads local files", async () => {
    const create = await submit({
      antimony: ['import "/etc/hostname"', FEEDBACK_MODEL].join("\n"),
      points: 5,
    });
    const job = await awaitTerminal(create.body.jobId);

    expect(job.status).toBe("failed");
    expect(JSON.stringify(job.error)).toMatch(/import/i);
  }, 30_000);

  // ---- request validation --------------------------------------------

  it("requires exactly one of antimony or sbml", async () => {
    const neither = await submit({ points: 5 });
    expect(neither.status).toBe(400);
    expect(neither.body.message).toMatch(/exactly one/);

    const both = await submit({
      antimony: FEEDBACK_MODEL,
      sbml: "<sbml/>",
      points: 5,
    });
    expect(both.status).toBe(400);
    expect(both.body.message).toMatch(/exactly one/);
  });

  it("rejects a points count above the ceiling at the schema, before any work", async () => {
    const res = await submit({ antimony: FEEDBACK_MODEL, points: 100_001 });
    // 400 rather than a 202-then-failed job: nothing should be queued or
    // spawned for a request that cannot be legal.
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("BAD_REQUEST");
  });

  it("reports a malformed model as a failed job with the parser's reason", async () => {
    const create = await submit({
      antimony: "this is not antimony at all",
      points: 5,
    });
    const job = await awaitTerminal(create.body.jobId);
    expect(job.status).toBe("failed");
    // The reason has to survive to the caller. "failed" with no explanation
    // is the failure mode this repo has fixed repeatedly elsewhere.
    expect(JSON.stringify(job.error ?? {}).length).toBeGreaterThan(20);
  }, 30_000);
});

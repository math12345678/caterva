/**
 * `POST /api/simulate/parameterize`: network in, literature out.
 *
 * What is being claimed here is smaller than for the network route: the
 * open path's OTHER half searches BRENDA live, and a test can no more
 * promise BRENDA's answer than it can promise the weather. So these tests
 * pin the deterministic edges -- the two refusals that happen BEFORE any
 * literature is touched, and the mapping of the engine's serialised search
 * into the response's `literatureSearch` field -- and leave the live branch
 * to the reader. A front door that can only be tested online is a front
 * door nobody tests; these are the parts a deterministic test CAN see.
 *
 * The load-bearing assertion is that a quantity named in a request but
 * absent from the network is refused with the quantities named, before a
 * subprocess is spent. The engine's `ValueError` on `declared - available`
 * is the authoritative version; this route asks the same question early, so
 * a typo never pays for a literature search.
 */
import { describe, expect, it } from "vitest";
import request from "supertest";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import {
  toCompositionReport,
  toLiteratureSearchReport,
  type ParameterizePayload,
} from "../lib/literatureSearch";

process.env["CACHE_FILE"] = join(
  mkdtempSync(join(tmpdir(), "parameterize-route-")),
  "cache.json",
);

const app = (await import("../app")).default;

/** A network whose constant the caller does NOT already have. */
const NETWORK = {
  name: "hexokinase_step",
  species: [
    { id: "S", initial: 10 },
    { id: "P", initial: 0 },
  ],
  parameters: [{ id: "Vmax", value: 5 }],
  reactions: [
    {
      id: "J0",
      reactants: { S: 1 },
      products: { P: 1 },
      rateLaw: "Vmax * S / (Km + S)",
    },
  ],
};

/**
 * The engine's serialised search, hand-shaped to the real `_serialise_search`
 * contract: snake_case build keys, `simulation` alongside the branches.
 * The losing branch is the point -- it carries the fact that the yeast
 * lacked a measured value, which a report that hid non-survivors would
 * have thrown away.
 */
const SEARCH_PAYLOAD = {
  ok: true,
  domain: "parameterize",
  parameters: {},
  trajectory: [],
  chosen_organism: "Escherichia coli",
  undecided_organisms: ["Saccharomyces cerevisiae"],
  branches: [
    {
      organism: "Escherichia coli",
      complete: true,
      build: {
        converged: true,
        rounds: 3,
        constraints: [
          {
            kind: "same_organism",
            subject: null,
            requirement: "every constant from one organism",
            reason: null,
            raised_by: "assembly",
          },
        ],
        resolved: {
          kcat: {
            value: 42,
            unit: "1/s",
            organism: "Escherichia coli",
            ph: 7,
            temperature_c: 30,
            buffer: null,
            citation: "BRENDA ref 422914",
            cross_species: false,
            explicitly_unreported: [],
          },
        },
        missing: {},
        findings: [],
        unassessable: [],
        coherent: true,
        simulated: true,
        not_simulated_because: null,
        summary: "three rounds; every constant resolved from one organism",
      },
    },
    {
      organism: "Saccharomyces cerevisiae",
      complete: false,
      build: {
        converged: false,
        rounds: 2,
        constraints: [],
        resolved: {},
        missing: { kcat: "no measured kcat in S. cerevisiae" },
        findings: [],
        unassessable: [],
        coherent: false,
        simulated: false,
        not_simulated_because: "no measured value for kcat",
        summary: "the yeast lacked a measured kcat",
      },
    },
  ],
  model: {
    converged: true,
    rounds: 3,
    constraints: [],
    resolved: {
      kcat: {
        value: 42,
        unit: "1/s",
        organism: "Escherichia coli",
        ph: 7,
        temperature_c: 30,
        buffer: null,
        citation: "BRENDA ref 422914",
        cross_species: false,
        explicitly_unreported: [],
      },
    },
    missing: {},
    findings: [],
    unassessable: [],
    coherent: true,
    simulated: true,
    not_simulated_because: null,
    summary: "three rounds; every constant resolved from one organism",
  },
  summary:
    "chose E. coli over S. cerevisiae because the yeast lacked a measured kcat",
  simulation: {
    ran: true,
    because: "the resolved set compiled",
    trajectory: [{ S: 10 }, { S: 8 }],
    values: { kcat: 42 },
    initials: { S: 10, P: 0 },
    quantitySources: {
      kcat: {
        origin: "resolved",
        citation: "BRENDA ref 422914",
        note: "42 1/s, Escherichia coli",
      },
    },
  },
} as unknown as ParameterizePayload;

describe("POST /api/simulate/parameterize", () => {
  it("rejects a body with no requests, before any engine work", async () => {
    const res = await request(app)
      .post("/api/simulate/parameterize")
      .send({ network: NETWORK, requests: [] });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("BAD_REQUEST");
    expect(res.body.message).toContain("at least one quantity to resolve");
  });

  it("rejects a request naming a quantity the network does not contain", async () => {
    const res = await request(app)
      .post("/api/simulate/parameterize")
      .send({
        network: NETWORK,
        requests: [{ quantity: "Kcat_typo" }],
      });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("UNKNOWN_REQUEST_QUANTITIES");
    expect(res.body.unknown).toEqual(["Kcat_typo"]);
  });

  it("rejects a malformed network at the boundary", async () => {
    const res = await request(app)
      .post("/api/simulate/parameterize")
      .send({
        network: { name: "broken" },
        requests: [{ quantity: "Vmax" }],
      });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe("BAD_REQUEST");
  });

  it("accepts a well-shaped request and starts a job", async () => {
    // `Km` is referenced by the rate law; `Vmax` exists. The request is
    // well-formed, so it gets a 202. The background job is safe to leave
    // running: with no ec_number on the request, the BRENDA scout raises
    // its "needs an EC number" ValueError before any network is touched,
    // so the job reaches a terminal state quickly either as an empty search
    // result or as a PIPELINE_ERROR -- both fast, neither online. What the
    // LIVE search would return is not something a test promises; that is
    // the mapper's job, below.
    const res = await request(app)
      .post("/api/simulate/parameterize")
      .send({
        network: {
          ...NETWORK,
          parameters: [
            { id: "Vmax", value: 5 },
            { id: "Km", value: 0.1 },
          ],
        },
        requests: [{ quantity: "Vmax", subject: "hexokinase" }],
        organism: "Homo sapiens",
      });
    expect(res.status).toBe(202);
    expect(res.body).toHaveProperty("jobId");
    expect(res.body.status).toBe("pending");
  });
});

describe("the engine search is mapped into literatureSearch", () => {
  it("carries the losing branches, and their snake_case reason is renamed", () => {
    const report = toLiteratureSearchReport(SEARCH_PAYLOAD);

    expect(report.chosenOrganism).toBe("Escherichia coli");
    expect(report.undecidedOrganisms).toEqual(["Saccharomyces cerevisiae"]);
    expect(report.branches).toHaveLength(2);

    const winner = report.branches[0];
    expect(winner.complete).toBe(true);
    // Present tense, engine truth: a losing branch was not simulated.
    expect(report.branches[1].build.notSimulatedBecause).toBe(
      "no measured value for kcat",
    );
    expect(report.branches[1].build.missing).toEqual({
      kcat: "no measured kcat in S. cerevisiae",
    });

    // The winning branch's resolved value and citation reach the reader.
    expect(
      report.branches[0].build.resolved["kcat"]?.citation,
    ).toBe("BRENDA ref 422914");
    expect(report.model?.notSimulatedBecause).toBeNull();
  });

  it("carries the simulation's resolved values and their origins", () => {
    const report = toLiteratureSearchReport(SEARCH_PAYLOAD);

    expect(report.simulation.ran).toBe(true);
    expect(report.simulation.values).toEqual({ kcat: 42 });
    expect(report.simulation.trajectory).toHaveLength(2);
    expect(report.simulation.quantitySources?.["kcat"]?.origin).toBe(
      "resolved",
    );
  });
});

describe("the composition mapper", () => {
  it("builds a composition report from the engine's built payload", () => {
    const report = toCompositionReport({
      rule: "phosphorylation_cascade",
      reading: "3 tiers, read from the query",
      structureOnly: true,
      network: {
        name: "cascade",
        species: [{ id: "X", initial: 1 }],
        parameters: [{ id: "kcat", value: 10 }],
        reactions: [
          {
            id: "R1",
            reactants: { X: 1 },
            products: { Xp: 1 },
            rateLaw: "kcat * X",
          },
        ],
      },
      conservationLaws: ["X + Xp"],
      notes: ["no enzyme was named"],
      toResolve: [
        {
          id: "kcat_kin",
          motif: "phosphorylation_cycle",
          parameter: "kcat",
          unit: "1/s",
          table: "kcat",
          description: "kinase turnover number",
        },
      ],
      yourChoice: [],
      unitFindings: [],
      summary: "built a cascade",
    });

    expect(report.rule).toBe("phosphorylation_cascade");
    expect(report.structureOnly).toBe(true);
    expect(report.toResolve[0]?.unit).toBe("1/s");
    expect(report.network.parameters[0]?.value).toBe(10);
  });

  it("throws on a built payload that is missing a mechanism field", () => {
    // A compose result that says "built" and then omits `rule` means the
    // engine and this module have drifted. The mapper must not quietly
    // fabricate an empty rule into the report.
    expect(() =>
      toCompositionReport({
        reading: "2 tiers",
        structureOnly: true,
      }),
    ).toThrow(/drifted/);
  });
});
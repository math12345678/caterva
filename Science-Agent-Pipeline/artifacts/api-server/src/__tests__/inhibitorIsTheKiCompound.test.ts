/**
 * A Ki belongs to the inhibitor, and the API must look it up under the
 * inhibitor's name.
 *
 * Found 2026-09-29 by a read-only map of the API path: for "competitive
 * inhibition of lactate dehydrogenase by oxamate", the keyword path took
 * "lactate" out of the enzyme's own name as the substrate, dropped
 * "oxamate", and sent BOTH the Km and the Ki lookups with substrate
 * "lactate". BRENDA files a Ki under the inhibitor, so the Ki came back as a
 * Ki "of" lactate, or not at all.
 *
 * Also here: what the chosen row says it measured (isoform, inhibition
 * mode) reaches the response flags, decided in Python and reported as is.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { extractInhibitor, resolveQuery, rowScopeFlags } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

const NOT_FOUND = {
  found: false,
  source: "not_found",
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return { ...original, resolveKineticValue: vi.fn(async () => NOT_FOUND) };
});

describe("extractInhibitor", () => {
  it.each([
    ["competitive inhibition of lactate dehydrogenase by oxamate", "oxamate"],
    ["lactate dehydrogenase inhibited by gossypol", "gossypol"],
    ["LDH kinetics with oxamic acid as an inhibitor", "oxamic acid"],
    ["hexokinase with the inhibitor N-acetylglucosamine", "N-acetylglucosamine"],
  ])("reads %j", (query, inhibitor) => {
    expect(extractInhibitor(query)).toBe(inhibitor);
  });

  it("returns undefined rather than guessing", () => {
    expect(extractInhibitor("enzyme kinetics with a competitive inhibitor")).toBeUndefined();
    expect(extractInhibitor("simulate lactate dehydrogenase with pyruvate")).toBeUndefined();
  });
});

describe("the Ki lookup uses the inhibitor", () => {
  const mocked = vi.mocked(resolveKineticValue);
  beforeEach(() => mocked.mockClear());

  // The mock finds nothing, so resolveQuery refuses to simulate (by design:
  // it never runs on unresolved constants). What matters is what it ASKED.
  const settle = (p: Promise<unknown>) => p.then(() => "", (e: Error) => e.message);

  it("sends the inhibitor for the Ki and never the enzyme-name substrate", async () => {
    await settle(resolveQuery("competitive inhibition of lactate dehydrogenase by oxamate with pyruvate"));
    const calls = mocked.mock.calls.map(([arg]) => arg as { quantity: string; substrate?: string });
    const ki = calls.find((c) => c.quantity === "ki");
    const km = calls.find((c) => c.quantity === "km");
    expect(ki?.substrate).toBe("oxamate");
    expect(km?.substrate).toBe("pyruvate");
  });

  it("asks the runner to choose the inhibitor when none is named, with the model's substrate", async () => {
    // Was "does not look a Ki up at all when no inhibitor is named". Since
    // ADR 0182 the Ki is looked up with the inhibitor left empty, and the
    // runner chooses the one BRENDA holds the most Ki rows for; the model's
    // own substrate goes with it, so the choice and the row ranking are
    // against the substrate this model is of.
    await settle(resolveQuery("competitive inhibition of lactate dehydrogenase with pyruvate"));
    const calls = mocked.mock.calls.map(
      ([arg]) => arg as { quantity: string; substrate?: string; modelSubstrate?: string },
    );
    const ki = calls.find((c) => c.quantity === "ki");
    expect(ki).toBeDefined();
    expect(ki?.substrate).toBe("");
    expect(ki?.modelSubstrate).toBe("pyruvate");
  });

  it("states the chosen inhibitor, and the Ki's provenance names it", async () => {
    mocked.mockImplementation(async (entities) => {
      if (entities.quantity !== "ki") return NOT_FOUND;
      return {
        found: true,
        ki: 0.026,
        unit: "mM",
        organism: "Homo sapiens",
        source: "brenda_exact",
        crossSpecies: false,
        citation: {
          source: "BRENDA",
          referenceId: "711801",
          url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
        },
        choices: [
          {
            role: "inhibitor",
            chosen: "oxamate",
            why: "most Ki rows for EC 1.1.1.27 in Homo sapiens",
            alternatives: [{ name: "gossypol", rows: { ki: 4 } }],
            considered: 9,
          },
        ],
        literatureCandidates: [],
        logs: [],
      };
    });
    try {
      const { RequiredParametersMissingError } = await import("../lib/provenance");
      let flags: string[] = [];
      let kiNote: string | undefined;
      try {
        const run = await resolveQuery("competitive inhibition of lactate dehydrogenase with pyruvate");
        flags = run.provenance.flags;
        kiNote = run.parameterProvenance["ki"]?.note;
      } catch (err) {
        if (!(err instanceof RequiredParametersMissingError)) throw err;
        flags = err.flags;
        kiNote = err.parameterProvenance["ki"]?.note;
      }
      const chosen = flags.find((f) => f.startsWith("inhibitor chosen: oxamate"));
      expect(chosen).toContain("most Ki rows for EC 1.1.1.27 in Homo sapiens");
      expect(chosen).toContain("gossypol (Ki 4 rows)");
      expect(kiNote).toContain("Ki of oxamate, the inhibitor Caterva chose");
    } finally {
      mocked.mockImplementation(async () => NOT_FOUND);
    }
  });

  it("says what is missing when there was no inhibitor to choose", async () => {
    const refusalText =
      "No inhibitor was named, and BRENDA lists no Ki row for any inhibitor of EC 1.1.1.27 " +
      "in Homo sapiens, so none could be chosen and nothing was looked up.";
    mocked.mockImplementation(async (entities) =>
      entities.quantity === "ki"
        ? { found: false, source: "inhibitor_not_named", choiceRefusal: refusalText, choices: [], literatureCandidates: [], logs: [] }
        : NOT_FOUND,
    );
    try {
      const refusal = await settle(
        resolveQuery("competitive inhibition of lactate dehydrogenase with pyruvate"),
      );
      expect(refusal).toContain("BRENDA lists no Ki row for any inhibitor of EC 1.1.1.27");
    } finally {
      mocked.mockImplementation(async () => NOT_FOUND);
    }
  });
});

describe("rowScopeFlags", () => {
  it("names the isoform and a missing mode", () => {
    const flags = rowScopeFlags("ki", { isoform: "LDH-B", inhibitionMode: "unstated", versus: null });
    expect(flags.join(" ")).toContain("isoform LDH-B");
    expect(flags.join(" ")).toContain("states no inhibition mode");
  });

  it("names the mode and what it was measured against", () => {
    const flags = rowScopeFlags("ki", { isoform: null, inhibitionMode: "competitive", versus: "NADH" });
    expect(flags).toEqual([
      "KI: the source row measured competitive inhibition versus NADH; a Ki is specific to that mode and assay.",
    ]);
  });

  it("says nothing without a scope, and nothing about mode for a Km", () => {
    expect(rowScopeFlags("ki", null)).toEqual([]);
    expect(rowScopeFlags("km", { isoform: null, inhibitionMode: "unstated", versus: null })).toEqual([]);
  });
});

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

  it("does not look a Ki up at all when no inhibitor is named", async () => {
    const refusal = await settle(resolveQuery("competitive inhibition of lactate dehydrogenase with pyruvate"));
    const calls = mocked.mock.calls.map(([arg]) => arg as { quantity: string });
    expect(calls.some((c) => c.quantity === "ki")).toBe(false);
    expect(refusal).toContain("a Ki belongs to the inhibitor, and the query names none");
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

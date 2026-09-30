/**
 * An isoform named in the query reaches the resolver, and a refusal for
 * lack of it says which isoforms exist.
 *
 * Human LDH is three proteins; BRENDA 711801 gives gossypol's Ki for each
 * (LDH-A 0.0019 mM, LDH-B 0.0014, LDH-C 0.0042). "LDH-A inhibited by
 * gossypol" must be looked up as LDH-A, and the runner decides which row
 * that is (fallback_logic, isoform=...); this side only carries the name
 * there and the refusal back.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { extractIsoform, resolveQuery, rowScopeFlags } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({
      found: false,
      source: "isoform_withheld",
      isoformsAvailable: ["LDH-A", "LDH-B", "LDH-C"],
      literatureCandidates: [],
      logs: [],
    })),
  };
});

describe("extractIsoform", () => {
  it.each([
    ["competitive inhibition of human LDH-A by gossypol with pyruvate", "LDH-A"],
    ["lactate dehydrogenase isoform LDH-C with pyruvate", "LDH-C"],
    ["hexokinase isozyme 2 with glucose", "2"],
  ])("reads %j", (query, isoform) => {
    expect(extractIsoform(query)).toBe(isoform);
  });

  it("returns undefined when no isoform is named", () => {
    expect(extractIsoform("competitive inhibition of lactate dehydrogenase by gossypol")).toBeUndefined();
  });
});

describe("the isoform reaches the resolver and the refusal comes back", () => {
  const mocked = vi.mocked(resolveKineticValue);
  beforeEach(() => mocked.mockClear());
  const settle = (p: Promise<unknown>) => p.then(() => "", (e: Error) => e.message);

  it("sends the isoform with every lookup", async () => {
    await settle(resolveQuery("competitive inhibition of human LDH-X by gossypol with pyruvate"));
    const calls = mocked.mock.calls.map(([arg]) => arg as { quantity: string; isoform?: string });
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.isoform === "LDH-X")).toBe(true);
  });

  it("names the isoforms BRENDA does hold", async () => {
    const refusal = await settle(resolveQuery("competitive inhibition of human LDH-X by gossypol with pyruvate"));
    expect(refusal).toContain("measured on another (LDH-A, LDH-B, LDH-C)");
  });
});

describe("rowScopeFlags with an isoform named in the query", () => {
  it("says nothing more when the row confirms it", () => {
    expect(rowScopeFlags("ki", { isoform: "LDH-A", inhibitionMode: "competitive", versus: null }, "ldh a"))
      .toEqual(["KI: the source row measured competitive inhibition; a Ki is specific to that mode and assay."]);
  });

  it("calls a row naming none, or with no commentary at all, unknown for that isoform", () => {
    const unnamed = rowScopeFlags("km", { isoform: null, inhibitionMode: "unstated", versus: null }, "LDH-A");
    expect(unnamed).toEqual(["KM: the source row names no isoform, so whether it measured LDH-A, the one the query names, is unknown."]);
    expect(rowScopeFlags("km", null, "LDH-A")).toEqual(unnamed);
    expect(rowScopeFlags("km", null)).toEqual([]);
  });

  it("names a different isoform as a different protein", () => {
    expect(rowScopeFlags("ki", { isoform: "LDH-B", inhibitionMode: "unstated", versus: null }, "LDH-A")[0])
      .toContain("not LDH-A, the one the query names");
  });
});

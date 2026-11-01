import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";
import type { RequiredParametersMissingError } from "../lib/provenance";

/**
 * ADR 0029 — a point mutant's constant is not the enzyme's.
 *
 * BRENDA's commentary cell says "Y124C mutant" and "isozyme H4" in the same
 * string that yields pH and temperature. That half was parsed; this half was
 * discarded. In the acetylcholinesterase turnover fixture 35 of 72 rows are
 * point mutants — 32 of the 37 mouse rows — and selection is `min()`.
 * Substitutions are chosen precisely because they change the kinetics, so
 * they populate the tail a minimum reaches into.
 *
 * These tests cover the boundary, not the classifier. The Python resolver
 * decides what a variant is; what matters here is that a refusal survives
 * the wire able to say what it refused, because otherwise the opt-in it
 * demands cannot be exercised.
 */

const VARIANT_WITHHELD = {
  found: false,
  source: "variant_withheld",
  variantCandidatesAvailable: ["Y124C", "F295A/Y337A", "isozyme H4"],
  literatureCandidates: [],
  logs: [
    "All 3 candidate row(s) measured a protein variant " +
      "(F295A/Y337A, Y124C, isozyme H4); withheld: allow_variants=False",
  ],
};

const VARIANT_WITHHELD_UNNAMED = {
  ...VARIANT_WITHHELD,
  variantCandidatesAvailable: [] as string[],
};

const NOT_FOUND = {
  found: false,
  source: "not_found",
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => NOT_FOUND),
  };
});

const QUERY =
  "simulate michaelis menten of acetylcholinesterase on acetylthiocholine " +
  "in Mus musculus vmax=5 s0=10 end=10 points=51";

async function refusalFor(agentResult: unknown) {
  vi.mocked(resolveKineticValue).mockResolvedValueOnce(agentResult as never);
  try {
    await resolveQuery(QUERY);
  } catch (err) {
    return err as RequiredParametersMissingError;
  }
  throw new Error("expected resolveQuery to refuse, but it returned");
}

describe("a withheld variant says what it withheld", () => {
  it("names the variants", async () => {
    const err = await refusalFor(VARIANT_WITHHELD);
    expect(err.message).toContain("Y124C");
    expect(err.message).toContain("isozyme H4");
  });

  it("tells the user how to opt in", async () => {
    const err = await refusalFor(VARIANT_WITHHELD);
    expect(err.message).toContain("allowVariants");
  });

  it("says why a mutant is not the enzyme", async () => {
    // "Different protein" is the fact that makes the refusal reasonable. A
    // bare "withheld" reads as pedantry and gets overridden reflexively.
    const err = await refusalFor(VARIANT_WITHHELD);
    expect(err.message).toMatch(/changes the kinetics/i);
    expect(err.message).toMatch(/different gene product/i);
  });

  it("stops claiming the literature has nothing", async () => {
    // The generic sentence is FALSE here: BRENDA held three values. Saying
    // otherwise is a true-sounding wrong statement, which this project
    // treats as worse than a blunt one.
    const err = await refusalFor(VARIANT_WITHHELD);
    expect(err.message).not.toContain("could not be resolved from literature");
  });

  it("produces a different message from a genuine literature gap", async () => {
    const withheld = await refusalFor(VARIANT_WITHHELD);
    const absent = await refusalFor(NOT_FOUND);
    expect(withheld.message).not.toBe(absent.message);
    expect(absent.message).not.toContain("allowVariants");
  });

  it("still refuses — a fuller message is not a looser outcome", async () => {
    const err = await refusalFor(VARIANT_WITHHELD);
    expect(err.name).toBe("RequiredParametersMissingError");
    expect(err.missing).toContain("km");
  });

  it("degrades sanely when the resolver names no variants", async () => {
    // No "undefined" in user-facing prose. Same shape that once produced
    // "Both jobs used the undefined model" elsewhere in this codebase.
    const err = await refusalFor(VARIANT_WITHHELD_UNNAMED);
    expect(err.message).not.toContain("undefined");
    expect(err.message).toContain("a sequence variant");
    expect(err.message).toContain("allowVariants");
  });
});

describe("the opt-in reaches the resolver", () => {
  it("forwards allowVariants when set", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(NOT_FOUND as never);
    try {
      await resolveQuery(QUERY, { allowVariants: true });
    } catch {
      /* refusal is fine; the call is what is under test */
    }
    const call = vi.mocked(resolveKineticValue).mock.calls.at(-1)?.[0];
    expect(call?.allowVariants).toBe(true);
  });

  it("defaults to false when the caller says nothing", async () => {
    // A permissive default is exactly how the old behaviour — a mutant's
    // constant returned as the enzyme's — would come back silently, in a
    // diff that looked like a refactor.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(NOT_FOUND as never);
    try {
      await resolveQuery(QUERY);
    } catch {
      /* as above */
    }
    const call = vi.mocked(resolveKineticValue).mock.calls.at(-1)?.[0];
    expect(call?.allowVariants).toBe(false);
  });
});

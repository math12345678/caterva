import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";
import type { RequiredParametersMissingError } from "../lib/provenance";

/**
 * ADR 0024 — cross-species values became opt-in on Lisa Jeske's (BRENDA
 * curation team, DSMZ) recommendation that a tool "should rather abort or
 * leave the value empty if there is no exact organism match, instead of
 * providing incorrect data".
 *
 * The Python resolver enforces that. What these tests cover is the part
 * that is easy to get wrong on the way out: a withheld value and a genuine
 * literature gap both arrive as `found: false`, and if the TypeScript layer
 * flattens them into one message, the opt-in the resolver just demanded
 * becomes impossible to exercise — the user is never told there is
 * anything to opt in to.
 *
 * That failure would be invisible: the run still refuses, the provenance
 * still says "default", every existing test still passes. It would just be
 * quietly useless. Hence a test whose whole subject is the wording of a
 * refusal.
 */

const NOT_FOUND_AT_ALL = {
  found: false,
  source: "not_found",
  literatureCandidates: [],
  logs: [],
};

const WITHHELD = {
  found: false,
  source: "cross_species_withheld",
  crossSpeciesOrganismsAvailable: ["Oryctolagus cuniculus", "Sus scrofa"],
  literatureCandidates: [],
  logs: [
    "Cross-species value(s) found in Oryctolagus cuniculus, Sus scrofa " +
      "but withheld: allow_cross_species=False",
  ],
};

const WITHHELD_UNNAMED = {
  found: false,
  source: "cross_species_withheld",
  crossSpeciesOrganismsAvailable: [] as string[],
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => NOT_FOUND_AT_ALL),
  };
});

// km is left to resolution; everything else is supplied so the query is
// otherwise complete and only the km path is under test.
const LDH_QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate in " +
  "Mus musculus vmax=5 s0=10 end=10 points=51";

describe("cross-species withheld is not the same as not found", () => {
  /** An unresolved required parameter is a hard block (ADR 0012/0013), so
   * the refusal never reaches the caller as a return value — it reaches
   * them as a thrown error. That error is therefore the only surface the
   * message actually has, which is why these assert on it rather than on
   * provenance the caller never sees. */
  async function refusalFor(agentResult: unknown) {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(agentResult as never);
    try {
      await resolveQuery(LDH_QUERY);
    } catch (err) {
      return err as RequiredParametersMissingError;
    }
    throw new Error("expected resolveQuery to refuse, but it returned");
  }

  it("names the organisms whose values were withheld", async () => {
    const err = await refusalFor(WITHHELD);
    expect(err.message).toContain("Oryctolagus cuniculus");
    expect(err.message).toContain("Sus scrofa");
  });

  it("tells the user how to opt in", async () => {
    const err = await refusalFor(WITHHELD);
    // Without this the refusal is a dead end: the resolver requires an
    // opt-in that the message never mentions.
    expect(err.message).toContain("allowCrossSpecies");
  });

  it("says why, not just what — species-specificity is the reason", async () => {
    const err = await refusalFor(WITHHELD);
    expect(err.message).toMatch(/species-specific/i);
  });

  it("stops claiming the literature has nothing when it has something", async () => {
    const err = await refusalFor(WITHHELD);
    // The generic sentence is FALSE for this case: the value was resolved
    // from the literature and withheld by policy. Asserting its absence is
    // the point of the whole change — a true-sounding wrong statement is
    // worse than a blunt one.
    expect(err.message).not.toContain("could not be resolved from literature");
  });

  it("keeps the generic message for a genuine literature gap", async () => {
    const err = await refusalFor(NOT_FOUND_AT_ALL);
    expect(err.message).toContain("could not be resolved from literature");
    expect(err.message).not.toContain("allowCrossSpecies");
  });

  it("produces a different message from a genuine literature gap", async () => {
    const withheld = await refusalFor(WITHHELD);
    const absent = await refusalFor(NOT_FOUND_AT_ALL);
    expect(withheld.message).not.toBe(absent.message);
  });

  it("still refuses — a friendlier message is not a friendlier outcome", async () => {
    const err = await refusalFor(WITHHELD);
    expect(err.name).toBe("RequiredParametersMissingError");
    expect(err.missing).toContain("km");
  });

  it("degrades sanely when the resolver names no organisms", async () => {
    const err = await refusalFor(WITHHELD_UNNAMED);
    // No "undefined" or empty gap in user-facing prose. This is the exact
    // shape that produced "Both jobs used the undefined model" elsewhere
    // in this codebase.
    expect(err.message).not.toContain("undefined");
    expect(err.message).toContain("another organism");
    expect(err.message).toContain("allowCrossSpecies");
  });
});

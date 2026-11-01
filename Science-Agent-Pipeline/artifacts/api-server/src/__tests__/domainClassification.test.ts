import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import {
  RequiredParametersMissingError,
  UnrecognizedQueryError,
} from "../lib/provenance";
import { resolveKineticValue } from "../lib/scienceAgent";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({ found: false })),
  };
});

// ─── The keyword classifier used to silently default to "mm" (Michaelis- ──
// Menten enzyme kinetics) for ANY query it couldn't match -- not a soft
// guess, the literal first domain in the table. A question about predator-
// prey dynamics or population genetics would get an enzyme-kinetics
// simulation back with no error, no flag, nothing to indicate the model
// was wrong for the question asked. These tests assert the domain a
// realistic phrasing resolves to, using the fact that
// RequiredParametersMissingError still carries `.domain` even when the
// resolver refuses on missing parameters afterward -- so a test can
// confirm classification succeeded without having to fully specify every
// parameter a domain needs.

async function classifiedDomain(query: string): Promise<string> {
  try {
    const result = await resolveQuery(query);
    return result.domain;
  } catch (e) {
    if (e instanceof RequiredParametersMissingError) return e.domain;
    throw e;
  }
}

describe("keyword classifier: realistic phrasing that used to misclassify", () => {
  // The classifier's first job survived the 2026-09-27 narrowing: a
  // question about something Caterva no longer models is refused, never
  // answered with an enzyme simulation. These phrasings each used to route
  // to a domain that is now archived.
  it.each([
    "simulate predator and prey populations over 50 years",
    "what happens to allele frequencies in a small population of 20 individuals",
    "I want to model the spread of measles in a school with 500 students",
    "model a covid-19 outbreak s0=990 i0=10 end=100",
    "simulate a lennard-jones cluster of 13 atoms",
  ])("refuses %j rather than running it as an enzyme", async (q) => {
    await expect(resolveQuery(q)).rejects.toBeInstanceOf(UnrecognizedQueryError);
  });

  it("a genuinely unrecognized query throws UnrecognizedQueryError, not a silent mm default", async () => {
    await expect(
      resolveQuery("xyzzy plugh quux frobnicate"),
    ).rejects.toBeInstanceOf(UnrecognizedQueryError);
  });

  it("UnrecognizedQueryError lists the real available domains", async () => {
    try {
      await resolveQuery("xyzzy plugh quux frobnicate");
      throw new Error("expected resolveQuery to throw");
    } catch (e) {
      expect(e).toBeInstanceOf(UnrecognizedQueryError);
      const err = e as UnrecognizedQueryError;
      expect(err.availableDomains).toContain("mm");
      expect(err.availableDomains).toContain("gillespie_ssa");
      // Archived domains are not offered as if they still ran.
      expect(err.availableDomains).not.toContain("sir");
      expect(err.availableDomains).not.toContain("wright_fisher");
    }
  });
});

describe("keyword classifier: existing exact-phrase matches still work", () => {
  it('"lactate dehydrogenase" still resolves to mm (regression check)', async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce({
      found: true,
      km: 10.73,
      unit: "mM",
      organism: "Homo sapiens",
      source: "brenda_exact",
      crossSpecies: false,
      citation: {
        source: "BRENDA",
        referenceId: "740253",
        url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
      },
      literatureCandidates: [],
      logs: [],
    });
    expect(
      await classifiedDomain(
        "simulate lactate dehydrogenase vmax=5 s0=10 end=10 points=51",
      ),
    ).toBe("mm");
  });

});

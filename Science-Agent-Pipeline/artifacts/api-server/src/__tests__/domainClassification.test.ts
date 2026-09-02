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
  it('"predator and prey populations" resolves to lotka_volterra, not mm', async () => {
    // Old exact-substring check needed the adjacent phrase "predator prey"
    // or "predator-prey" -- "predator AND prey" (a completely ordinary way
    // to phrase this) matched neither and fell through to mm.
    expect(
      await classifiedDomain("simulate predator and prey populations over 50 years"),
    ).toBe("lotka_volterra");
  });

  it('"allele frequencies" (plural) resolves to wright_fisher, not mm', async () => {
    // Old check required the exact singular substring "allele frequency".
    expect(
      await classifiedDomain(
        "what happens to allele frequencies in a small population of 20 individuals",
      ),
    ).toBe("wright_fisher");
  });

  it('naming a disease directly ("measles") resolves to sir, not mm', async () => {
    // measles has no verified literature R0 (ADR 0017) so this still
    // refuses -- but it must refuse as a SIR query missing beta/gamma, not
    // silently run as if the question had been about enzyme kinetics.
    const domain = await classifiedDomain(
      "I want to model the spread of measles in a school with 500 students",
    );
    expect(domain).toBe("sir");
  });

  it('naming covid resolves to sir and reaches the real literature R0 bridge', async () => {
    const result = await resolveQuery(
      "model a covid-19 outbreak s0=990 i0=10 r0_recovered=0 end=100 points=101",
    );
    expect(result.domain).toBe("sir");
    // Real literature-backed resolution (not a hardcoded default): the
    // parameterProvenance origin for beta/gamma should be "resolved", not
    // "default" or "user", proving classification reached the disease
    // registry rather than just guessing the right domain by luck.
    expect(result.parameterProvenance["beta"]?.origin).toBe("resolved");
    expect(result.parameterProvenance["gamma"]?.origin).toBe("resolved");
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
      expect(err.availableDomains).toContain("sir");
      expect(err.availableDomains).toContain("lotka_volterra");
      expect(err.availableDomains.length).toBeGreaterThanOrEqual(15);
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

  it('"lennard-jones cluster" still resolves to molecular_dynamics', async () => {
    expect(
      await classifiedDomain("simulate a lennard-jones cluster of 13 atoms"),
    ).toBe("molecular_dynamics");
  });
});

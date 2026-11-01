/**
 * A two-paper disease number must never read as a one-paper number.
 *
 * ADR 0017 registered only COVID-19, whose R0 (3.14) and serial interval
 * (5.45 d) both come from Hussein et al. 2021 — one paper, so the bridge
 * marked beta/gamma `verified` unconditionally, with a comment saying the
 * registry "has no flagged tier to select between".
 *
 * ADR 0169 adds that tier. Influenza is registered as a CROSS-STUDY
 * COMPOSITE: R0 from Biggerstaff et al. 2014 (PMID 25186370), serial
 * interval from Vink et al. 2014 (PMID 25294601). Both are systematic
 * reviews, and Vink reports the same quantity the COVID entry uses for
 * 1/gamma — but they are still two papers, and the reader has to be able
 * to see that.
 *
 * These run UNMOCKED against the real Python bridge and the real registry,
 * like betaGammaFromR0Provenance.test.ts: the value of this file is that
 * the whole chain agrees, and a fixture would keep passing if the bridge
 * stopped forwarding the composite flag.
 */
import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";

const SUFFIX = "s0=990 i0=10 r0_recovered=0 end=100 points=101";

describe("cross-study composite disease entries — ADR 0169", () => {
  it("resolves seasonal influenza and marks it flagged, not verified", async () => {
    const resolved = await resolveQuery(`simulate a flu outbreak ${SUFFIX}`);
    expect(resolved.domain).toBe("sir");

    // Biggerstaff 2014 median seasonal R0 = 1.28; Vink 2014 A(H3N2) mean
    // serial interval = 2.2 d. gamma = 1/2.2, beta = 1.28 * gamma.
    expect(resolved.parameters["gamma"]).toBeCloseTo(1 / 2.2, 6);
    expect(resolved.parameters["beta"]).toBeCloseTo(1.28 / 2.2, 6);

    const beta = resolved.parameterProvenance["beta"]!;
    expect(beta.origin).toBe("resolved");
    // THE point of this file. A composite inheriting "verified" would
    // erase the only signal that two methodologies were combined.
    expect(beta.citationStatus).toBe("flagged");
  }, 120000);

  it("resolves the 2009 pandemic strain to its own, different numbers", async () => {
    // "h1n1" must not fall through to the seasonal entry: the two carry
    // different values and only this one is strain-matched across its two
    // sources. diseases.ts orders the specific pattern first.
    const resolved = await resolveQuery(`simulate an h1n1 pandemic ${SUFFIX}`);
    expect(resolved.parameters["gamma"]).toBeCloseTo(1 / 2.8, 6);
    expect(resolved.parameters["beta"]).toBeCloseTo(1.46 / 2.8, 6);
    expect(resolved.parameterProvenance["beta"]!.citationStatus).toBe("flagged");
  }, 120000);

  it("shows BOTH papers, not just the R0 one", async () => {
    const resolved = await resolveQuery(`simulate a flu outbreak ${SUFFIX}`);
    const beta = resolved.parameterProvenance["beta"]!;
    // Surfacing only the first would present a two-paper number as if one
    // paper supported it.
    expect(beta.citation).toContain("25186370"); // Biggerstaff, R0
    expect(beta.citation).toMatch(/serial interval from/i);
    expect(beta.citation).toContain("25294601"); // Vink, serial interval
  }, 120000);

  it("names what was combined, including the strain mismatch", async () => {
    const seasonal = await resolveQuery(`simulate a flu outbreak ${SUFFIX}`);
    const note = seasonal.parameterProvenance["beta"]!.note ?? "";
    expect(note).toMatch(/cross-study/i);
    // Seasonal is composite on two axes and must admit the second:
    // Biggerstaff's "seasonal" pools H3N2/H1N1/B, Vink's 2.2 d is H3N2.
    expect(note).toMatch(/strain/i);
  }, 120000);

  it("leaves COVID-19 verified — the single-source entry is not downgraded", async () => {
    // The new tier must not leak onto the entry that does come from one
    // paper. Hussein et al. 2021 reports both halves together.
    const resolved = await resolveQuery(`simulate covid-19 outbreak ${SUFFIX}`);
    expect(resolved.parameters["gamma"]).toBeCloseTo(1 / 5.45, 6);
    const beta = resolved.parameterProvenance["beta"]!;
    expect(beta.citationStatus).toBe("verified");
    expect(beta.note).not.toMatch(/cross-study/i);
  }, 120000);

  it("still refuses measles, and now says which paper is why", async () => {
    // Measles is the disease users try next, and its refusal is NOT
    // "we haven't got to it": Vink 2014 gives measles a serial interval
    // (11.7 d), so half the pair exists. Guerra et al. 2017 is the reason
    // the other half does not.
    const err = await resolveQuery(
      `what happens if measles hits a village ${SUFFIX}`,
    ).catch((e: Error) => e);
    expect(err).toBeInstanceOf(RequiredParametersMissingError);
    const message = (err as Error).message;
    expect(message).toMatch(/Guerra/);
    expect(message).toContain("10.1016/S1473-3099(17)30307-9");
    expect(message).toMatch(/12-18/);
    // And it must no longer claim the registry is COVID-only.
    expect(message).not.toMatch(/COVID-19 only/i);
  }, 120000);
});

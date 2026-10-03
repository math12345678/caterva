/**
 * Naming the stage that actually failed.
 *
 * THE MEASUREMENT
 * ---------------
 * `ec_not_resolved` and `ec_ambiguous` both stop at the enzyme NAME, before
 * any database is asked for a value. Both fell into the generic branch and
 * produced:
 *
 *     "Could not resolve a real KM value from BRENDA/KEGG/PubMed;
 *      using default KM."
 *
 * Three sources named, none of them consulted. A student reads that as "the
 * literature has no value for my enzyme" and goes looking for a different
 * problem than the one they have — a wrong substrate name, a rare organism,
 * a gap in BRENDA — when the truth is that Caterva could not tell which
 * enzyme they meant.
 *
 * The same family as the substrate and cross-species refusals: a message
 * that misidentifies the stage is worse than a vague one, because a vague
 * message leaves a reader looking and a wrong one sends them away.
 */

import { describe, expect, it } from "vitest";

import { buildUnresolvedKineticProvenanceForTest as build } from "../lib/queryResolver";

describe("a failure at the enzyme-identity step says so", () => {
  it("does not blame BRENDA when BRENDA was never asked", () => {
    for (const reason of ["ec_not_resolved", "ec_ambiguous"] as const) {
      const note = build("km", reason).note ?? "";
      expect(note).not.toContain("Could not resolve a real KM value from");
    }
  });

  it("names the enzyme name as the problem, not the literature", () => {
    const note = build("km", "ec_not_resolved").note ?? "";
    expect(note).toContain("never asked");
    expect(note).toContain("problem with the NAME, not with the literature");
    // And what to do about it.
    expect(note).toMatch(/check the spelling|supply the EC number/);
  });

  it("names the candidate EC numbers when the name matched several", () => {
    // Candidates deliberately NOT 1.1.1.27/1.1.1.28.
    //
    // The message carries those two as its worked example — "EC 1.1.1.27
    // and EC 1.1.1.28 are the L- and D- lactate dehydrogenases" — so an
    // assertion using them passes on the PROSE whether or not the
    // candidates were rendered at all. Measured: replacing
    // `ecCandidates.join(", ")` with a constant left this test green.
    const note = build("km", "ec_ambiguous", undefined, undefined, undefined, [
      "3.2.1.1",
      "3.2.1.2",
    ]).note ?? "";
    expect(note).toContain("3.2.1.1");
    expect(note).toContain("3.2.1.2");
    expect(note).toContain("Re-run with the EC number you meant");
  });

  it("explains WHY it will not pick one", () => {
    // Not "we could not decide" — the reason is that the two are different
    // proteins, and a reader who understands that will not ask the tool to
    // guess next time either.
    const note = build("km", "ec_ambiguous", undefined, undefined, undefined, [
      "1.1.1.27",
      "1.1.1.28",
    ]).note ?? "";
    expect(note).toContain("different proteins");
    expect(note).toMatch(/citation to an enzyme you did not ask about/);
  });

  it("shows the Python finder's refusal as it was written, not a rewording of it", () => {
    // The finder names each candidate and ends with the flag that would
    // accept one. This layer forwards that text and derives nothing from
    // the bare EC numbers beside it.
    const refusal =
      "'amylase' names 2 enzymes. Best matches first:\n" +
      "  EC 3.2.1.1 alpha-amylase\n  EC 3.2.1.2 beta-amylase\n" +
      "Re-run with the one you meant, for example ecNumber 3.2.1.1";
    const note = build(
      "km", "ec_ambiguous", undefined, undefined, undefined,
      ["3.2.1.1", "3.2.1.2"], undefined, refusal,
    ).note ?? "";
    expect(note).toContain(refusal);
    expect(note).toContain("BRENDA, KEGG and PubMed were never asked");
    expect(note).not.toContain("Could not resolve a real KM value from");
  });

  it("still works when the candidates did not travel", () => {
    // The message must degrade to something true rather than to "()" or a
    // dangling list. A refusal that renders badly is still the only thing
    // the reader gets.
    const note = build("km", "ec_ambiguous").note ?? "";
    expect(note).toContain("more than one EC number");
    expect(note).not.toContain("()");
  });

  it("keeps the three stages apart", () => {
    // enzyme identity / substrate name / organism coverage send a reader
    // to three different fixes. A message covering two of them sends them
    // to neither.
    const identity = build("km", "ec_not_resolved").note ?? "";
    const substrate = build("km", "not_found", undefined, undefined, [
      "(S)-lactate",
    ]).note ?? "";
    const organism = build("km", "cross_species_withheld", ["Sus scrofa"]).note ?? "";

    expect(identity).not.toContain("allowCrossSpecies");
    expect(identity).not.toContain("(S)-lactate");
    expect(substrate).not.toContain("EC number");
    expect(organism).not.toContain("EC number");
  });
});

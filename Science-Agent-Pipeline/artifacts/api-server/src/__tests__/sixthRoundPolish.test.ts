/**
 * Polish pass after the sixth review round, surfaces (ADR 0182).
 *
 * XS6V1-01: the flag "the evidence did not choose ... The value returned is
 * the median row of those" was printed when a later step had replaced the
 * median pick. For mouse acetylcholinesterase the API returned 0.054 mM (the
 * Km of the kcat's paper) under a list of 0.04 and 0.046 that did not hold it.
 *
 * XS6V1-04: "the source row names no isoform, so whether it measured MAOB
 * ... is unknown" beside "the row's UniProt accession (P27338) is MAOB".
 */
import { describe, expect, it } from "vitest";

import { accessionNamesIsoform, rowScopeFlags, selectionTieFlags } from "../lib/queryResolver";

const TIE = {
  candidates: [
    { value: 0.04, unit: "mM", reference_id: "666973", selected: true },
    { value: 0.046, unit: "mM", reference_id: "680690" },
  ],
  low: 0.04,
  high: 0.046,
  fold_range: 1.15,
  reason:
    "2 rows were equally well evidenced and their values span 0.04 to 0.046, a 1.15-fold range. " +
    "The value returned is the median row of those, an actual measurement with its own reference " +
    "rather than an average. That spread is disagreement in the literature.",
};

describe("the tie flag describes the choice that was made", () => {
  it("keeps the median sentence when the tie's pick is what was returned", () => {
    const [flag] = selectionTieFlags("km", TIE, { value: 0.04 });
    expect(flag).toContain("The value returned is the median row of those");
    expect(flag).toContain("0.04 mM [ref 666973] (returned)");
  });

  it("drops it, and gives the real reason, when another row was returned", () => {
    const [flag] = selectionTieFlags("km", TIE, {
      value: 0.054,
      chosenBecause: "0.054 mM (BRENDA ref 652194) is the row measured with the paired constant's row",
    });
    expect(flag).not.toContain("The value returned is the median row of those");
    expect(flag).toContain("The value returned (0.054) was not chosen as the median of those rows");
    expect(flag).toContain("paired constant's row");
    expect(flag).not.toContain("(returned)");
  });

  it("is unchanged when the caller says nothing about the value returned", () => {
    const [flag] = selectionTieFlags("km", TIE);
    expect(flag).toContain("The value returned is the median row of those");
  });
});

describe("a row whose UniProt cell names the isoform is not called unknown", () => {
  const notes = ["the row's UniProt accession (P27338) is MAOB"];

  it("reads the accession note", () => {
    expect(accessionNamesIsoform(notes, "MAOB")).toBe(true);
    expect(accessionNamesIsoform(notes, "MAO-B")).toBe(true);
    expect(accessionNamesIsoform(notes, "MAOA")).toBe(false);
    expect(accessionNamesIsoform(undefined, "MAOB")).toBe(false);
  });

  it("says the cell names it", () => {
    const flags = rowScopeFlags("km", null, "MAOB", notes);
    expect(flags.join(" ")).toContain("UniProt cell names MAOB");
    expect(flags.join(" ")).not.toContain("is unknown");
  });

  it("still says unknown when nothing names it", () => {
    const flags = rowScopeFlags("km", null, "MAOB", []);
    expect(flags.join(" ")).toContain("names no isoform");
  });
});

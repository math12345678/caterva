/**
 * A domain keyword is a word, not a substring.
 *
 * Found on the repressilator, which listed the keyword "repress": it occurs
 * inside "repress*ors*", so "a toggle switch between two repressors"
 * classified as a repressilator and never reached the compositional
 * grammar that was supposed to answer it. Only an end-to-end HTTP test
 * caught that, and it reported a missing field three layers from the cause.
 * See ADR 0206.
 *
 * That domain has since been archived, so the original case cannot be
 * asserted here any more. The property did not go with it -- the surviving
 * keyword lists carry the same trap, and the examples below are all real:
 *
 *   "compete"  inside "compet*ence*"  -- bacterial competence is a normal
 *                                        thing to ask about, and without
 *                                        boundaries it resolves as
 *                                        competitive inhibition
 *   "ssa"      inside "di*ssa*tisfied"
 *   "binding"  inside "re*binding*"
 *   "assa(y)"  inside "*assa*mbling"  (via "a + b"-style short terms)
 *
 * Each was measured: with the boundary filter removed they all match, and
 * the first returns a wrong domain for a question about genetics.
 */
import { describe, expect, it } from "vitest";

import { classifyDomainByKeyword } from "../lib/queryResolver";

const domainOf = (q: string) => classifyDomainByKeyword(q).defaults.domain;
const matched = (q: string) => classifyDomainByKeyword(q).matched;

describe("keyword matching respects word boundaries", () => {
  it.each([
    ["bacterial competence in a culture", "compete"],
    ["the cells are dissatisfied with the medium", "ssa"],
    ["rebinding after release", "binding"],
    ["a workman assembling the apparatus", "assa"],
  ])("does not read a keyword inside a longer word: %j (%s)", (query) => {
    // Falls through rather than matching: none of these queries names a
    // domain, and a keyword found inside an unrelated word is not evidence.
    expect(matched(query)).toBe(false);
  });

  it("does not resolve bacterial competence as competitive inhibition", () => {
    // The sharpest of the four, kept as its own case because the wrong
    // answer is plausible rather than absurd: both are about molecules
    // competing for something, and only one is a question about kinetics.
    expect(domainOf("bacterial competence in a culture")).not.toBe(
      "mm_competitive_inhibition",
    );
  });

  it.each([
    ["simulate competitive inhibition of the enzyme", "mm_competitive_inhibition"],
    ["run a gillespie simulation of decay", "gillespie_ssa"],
    ["how fast does catalase turn over its substrate", "mm"],
  ])("still matches a keyword the query writes as a word: %j", (query, expected) => {
    // The bounding direction. Boundaries must not cost real matches.
    expect(domainOf(query)).toBe(expected);
  });

  it("still matches an inflected keyword, through the stem path", () => {
    // "catalyses" for the keyword "catalyze" -- half credit under ADR 0204,
    // but found. The literal path cannot see it; the stem path can.
    expect(domainOf("the enzyme catalyses the step")).toBe("mm");
  });
});

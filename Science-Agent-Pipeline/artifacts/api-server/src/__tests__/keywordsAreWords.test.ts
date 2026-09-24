/**
 * A domain keyword is a word, not a substring.
 *
 * The repressilator lists "repress", which occurs inside "repressors", so
 * "a toggle switch between two repressors" scored as a repressilator and
 * never reached the compositional fallthrough that is supposed to answer
 * it. A toggle switch is built from repressors too -- the word is evidence
 * of neither circuit in particular. Only `frontDoorRouteCoverage.test.ts`
 * caught it, end to end through a running server, and it reported the
 * symptom (`composition.rule` undefined) rather than the cause.
 *
 * Same shape as ADR 0205's enzyme patterns one layer down, and the same
 * remedy. See ADR 0206.
 */
import { describe, expect, it } from "vitest";

import { classifyDomainByKeyword } from "../lib/queryResolver";

const domainOf = (q: string) => classifyDomainByKeyword(q).defaults.domain;

describe("keyword matching respects word boundaries", () => {
  it("does not read 'repress' inside 'repressors'", () => {
    // The query this was found on. It must fall through classification so
    // the compositional grammar can answer it; a keyword match here is a
    // wrong answer that also hides the right one.
    const { matched } = classifyDomainByKeyword(
      "a toggle switch between two repressors",
    );
    expect(matched).toBe(false);
  });

  it("does not read 'ring' inside 'bring'", () => {
    expect(domainOf("bring the substrate concentration up and watch v")).not.toBe(
      "repressilator",
    );
  });

  it("still matches a keyword the query writes as a word", () => {
    // The bounding direction: boundaries must not cost real matches.
    expect(domainOf("a synthetic gene circuit with three genes in a ring")).toBe(
      "repressilator",
    );
    expect(
      domainOf("Simulate the Elowitz and Leibler synthetic genetic oscillator."),
    ).toBe("repressilator");
  });

  it("still matches an inflected keyword, through the stem path", () => {
    // "spreads" for the keyword "spread" -- half credit, but found.
    expect(domainOf("Model how measles spreads through an unvaccinated school.")).toBe(
      "sir",
    );
  });
});

describe("a host organism is not a mechanism", () => {
  it("does not classify an E. coli growth question as a repressilator", () => {
    // "e. coli" was a repressilator keyword: it is the organism the
    // Elowitz-Leibler circuit was built in, which is a fact about the
    // paper, not about the question being asked.
    const { matched, defaults } = classifyDomainByKeyword(
      "how fast does E. coli grow in glucose",
    );
    expect(matched && defaults.domain === "repressilator").toBe(false);
  });
});

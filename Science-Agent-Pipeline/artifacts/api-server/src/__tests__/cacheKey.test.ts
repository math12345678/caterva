import { describe, expect, it } from "vitest";

import { normalizeQuery } from "../routes/simulate";

/**
 * The cache key.
 *
 * This is where an opt-in gets defeated without any guard noticing. Every
 * downstream check passes on a cached result — the value really was
 * resolved, really was cited, really carries provenance — so a key that
 * ignores a flag serves one user's answer to another and nothing detects
 * it. ADR 0016 is the record of that happening once already.
 *
 * `normalizeQuery` had no test, for any of its three flags. The guarantees
 * in ADR 0024 (cross-species), ADR 0027 (physiological reference) and ADR
 * 0029 (variants) were all asserted in prose and unverified in code. These
 * tests are written flag-by-flag rather than as one comparison, so a
 * failure names which guarantee broke.
 */

const Q = "simulate michaelis menten of acetylcholinesterase";

describe("the cache key distinguishes different questions", () => {
  it("separates cross-species opt-in from the default", () => {
    // The dangerous direction, from ADR 0024: a rabbit's Km cached by
    // someone who opted in, served to a student who did not.
    expect(normalizeQuery(Q, true)).not.toBe(normalizeQuery(Q, false));
  });

  it("separates variant opt-in from the default", () => {
    // ADR 0029's version: a Y337A mutant's kcat presented as the enzyme's,
    // to a caller who never agreed to that.
    expect(normalizeQuery(Q, false, true)).not.toBe(normalizeQuery(Q, false, false));
  });

  it("separates the two opt-ins from each other", () => {
    // Neither flag may stand in for the other. A key that only recorded
    // "some opt-in was used" would serve a cross-species result to someone
    // who asked for variants.
    expect(normalizeQuery(Q, true, false)).not.toBe(normalizeQuery(Q, false, true));
  });

  it("separates different physiological references", () => {
    const a = { ph: 7.4, temperatureC: 37, basis: "human plasma", phTolerance: 0.3, temperatureToleranceC: 5 };
    const b = { ...a, temperatureC: 70, basis: "thermophile" };
    expect(normalizeQuery(Q, false, false, a)).not.toBe(normalizeQuery(Q, false, false, b));
  });

  it("separates a stated reference from none", () => {
    const ref = { ph: 7.4, temperatureC: 37, basis: "human plasma", phTolerance: 0.3, temperatureToleranceC: 5 };
    expect(normalizeQuery(Q, false, false, ref)).not.toBe(normalizeQuery(Q, false, false));
  });

  it("keeps every combination distinct", () => {
    const ref = { ph: 7.4, temperatureC: 37, basis: "human plasma", phTolerance: 0.3, temperatureToleranceC: 5 };
    const keys = [
      normalizeQuery(Q),
      normalizeQuery(Q, true),
      normalizeQuery(Q, false, true),
      normalizeQuery(Q, true, true),
      normalizeQuery(Q, false, false, ref),
      normalizeQuery(Q, true, true, ref),
    ];
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("the cache key still collapses what it should", () => {
  it("ignores whitespace and casing", () => {
    // The reason normalization exists at all: two spellings of one question
    // should hit the same entry.
    expect(normalizeQuery("  Simulate   MICHAELIS menten  ")).toBe(
      normalizeQuery("simulate michaelis menten"),
    );
  });

  it("leaves the default path's key unchanged", () => {
    // Appending suffixes only when a flag is ON means entries written
    // before these flags existed still hit, rather than being silently
    // invalidated on deploy.
    expect(normalizeQuery(Q)).toBe(Q);
    expect(normalizeQuery(Q, false, false)).toBe(Q);
  });
});

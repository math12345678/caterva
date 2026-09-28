/**
 * What the domain-classifier benchmark measures, and proof it can fail.
 *
 * ADR 0190 measured the keyword table and pinned its defects as tests.
 * ADR 0191 repaired them: specificity scoring replaced first-match-wins, and
 * the vocabulary was widened from each domain's definition. Every pinned
 * defect test in this file therefore failed on purpose when the fix landed,
 * naming which defect had been fixed -- which is the notification those
 * tests existed to produce. They now assert the corrected routing, and each
 * still names the defect it used to have, so a regression says what broke
 * rather than only that a number moved.
 */

import { describe, expect, it } from "vitest";
import {
  LABELLED_QUERIES,
  DEV_QUERIES,
  HELDOUT_QUERIES,
  benchmarkKeywordClassifier,
  formatSummary,
  type LabelledQuery,
} from "../lib/classifierEval";
import { classifyDomainByKeyword } from "../lib/queryResolver";
import { DOMAIN_MEANINGS } from "../lib/llmResolver";

/** The domains the LLM resolver is allowed to return; the benchmark should
 *  exercise every one of them or it is not a benchmark of the classifier.
 *
 *  DERIVED from DOMAIN_MEANINGS rather than listed here. It used to be a
 *  hand-written array, and when the non-enzyme domains were archived on
 *  2026-09-27 it went on naming all thirteen -- so this test failed for
 *  having a stale copy of the answer rather than for anything the classifier
 *  did. That is the third hardcoded list on this branch to expire when a
 *  name moved (ADR 0205, ADR 0206); a derived one cannot. */
const LLM_EXPOSED_DOMAINS = Object.keys(DOMAIN_MEANINGS);

/**
 * A question the tool genuinely cannot simulate. Used to exercise the third
 * state: after the vocabulary widening almost every in-domain phrasing
 * matches something, so demonstrating "matched nothing" now requires a query
 * that really is outside every domain -- which is also the honest case a
 * student produces by typing the wrong thing into the box.
 */
const OUT_OF_DOMAIN = "What is the capital of France?";

describe("the labelled set", () => {
  it("covers every domain the LLM resolver can return", () => {
    const covered = new Set(LABELLED_QUERIES.map((q) => q.expected));
    const missing = LLM_EXPOSED_DOMAINS.filter((d) => !covered.has(d));
    expect(missing).toEqual([]);
  });

  it("covers every domain in the held-out split too, not just overall", () => {
    // A held-out set missing a domain would report a score that silently
    // excludes the domain most likely to be broken.
    const covered = new Set(HELDOUT_QUERIES.map((q) => q.expected));
    const missing = LLM_EXPOSED_DOMAINS.filter((d) => !covered.has(d));
    expect(missing).toEqual([]);
  });

  it("keeps the two splits disjoint", () => {
    const dev = new Set(DEV_QUERIES.map((q) => q.query));
    const overlap = HELDOUT_QUERIES.filter((q) => dev.has(q.query));
    expect(overlap).toEqual([]);
  });

  it("gives every query a written justification for its label", () => {
    const unjustified = LABELLED_QUERIES.filter(
      (q) => q.why.trim().length === 0,
    );
    expect(unjustified).toEqual([]);
  });

  it("does not label queries by pasting the domain key into them", () => {
    // A set of queries that each contain their own domain key would score
    // the keyword table at 100% and measure string equality, not
    // classification.
    //
    // `pcr` is the one honest exception: PCR is what the technique is
    // called, and a student asking about it says "PCR". Excluding the word
    // would make the query less realistic, not more rigorous.
    const NAMED_BY_PEOPLE = new Set(["pcr"]);
    const selfAnswering = LABELLED_QUERIES.filter(
      (q) =>
        !NAMED_BY_PEOPLE.has(q.expected) &&
        q.query.toLowerCase().includes(q.expected.replace(/_/g, " ")),
    ).map((q) => q.query);
    expect(selfAnswering).toEqual([]);
  });
});

describe("classifyDomainByKeyword reports three states, not two", () => {
  it("says matched=false when nothing in the query matched any keyword", () => {
    const { defaults, matched } = classifyDomainByKeyword(OUT_OF_DOMAIN);
    // It still returns a domain -- that is the fallback, and it is wrong.
    expect(defaults.domain).toBe("mm");
    // The point: the caller can see it was a fallback rather than an answer.
    expect(matched).toBe(false);
  });

  it("says matched=true when a keyword genuinely matched", () => {
    const { defaults, matched } = classifyDomainByKeyword(
      "How fast does lactate dehydrogenase convert pyruvate?",
    );
    expect(defaults.domain).toBe("mm");
    expect(matched).toBe(true);
  });

  it("distinguishes a real mm match from an mm fallback", () => {
    // Both return "mm". Without `matched` these are the same fact, which is
    // what let the baseline look accurate on queries it never understood.
    const real = classifyDomainByKeyword("enzyme kinetics of catalase");
    const fallback = classifyDomainByKeyword(OUT_OF_DOMAIN);
    expect(real.defaults.domain).toBe(fallback.defaults.domain);
    expect(real.matched).not.toBe(fallback.matched);
  });
});

describe("the benchmark itself", () => {
  it("scores the held-out split at least as well as the dev split", () => {
    // Not a threshold on either number -- thresholds invite tuning until
    // they pass. This asserts the relationship that would break first if
    // the classifier were fitted to the set that was written to break it.
    const dev = benchmarkKeywordClassifier(DEV_QUERIES);
    const heldout = benchmarkKeywordClassifier(HELDOUT_QUERIES);
    expect(heldout.accuracy).toBeGreaterThanOrEqual(dev.accuracy);
  });

  it("counts a fallback separately from an answer", () => {
    const summary = benchmarkKeywordClassifier([
      {
        query: OUT_OF_DOMAIN,
        expected: "mm",
        why: "out of domain; exercises the fallback path",
        split: "dev",
      },
    ]);
    // It scores "correct" only because mm happens to be the fallback --
    // which is exactly why that is reported separately and credited nowhere.
    expect(summary.undetermined).toBe(1);
    expect(summary.correctByFallback).toBe(1);
  });

  /**
   * Proof the benchmark can fail. A check that cannot fail is worse than no
   * check, because it is trusted. Feeding it a set whose labels are
   * deliberately wrong must produce a zero, not a pass.
   */
  it("reports zero when every label is deliberately wrong", () => {
    // Deriving the wrong label from the actual answer is what makes the
    // sabotage total: a fixed wrong label accidentally matches the queries
    // that really do classify that way, and the benchmark then scores above
    // zero and looks unfalsifiable.
    const sabotaged: LabelledQuery[] = LABELLED_QUERIES.map((q) => {
      const actual = classifyDomainByKeyword(q.query).defaults.domain;
      return {
        ...q,
        expected: actual === "pcr" ? "molecular_dynamics" : "pcr",
        why: "deliberately wrong label, to prove the benchmark can fail",
      };
    });
    const summary = benchmarkKeywordClassifier(sabotaged);
    expect(summary.correct).toBe(0);
    expect(summary.accuracy).toBe(0);
  });

  it("names each miss in its report rather than only counting it", () => {
    // A score with no misses listed cannot be acted on. Sabotage one query
    // so there is guaranteed to be a miss to name.
    const text = formatSummary(
      benchmarkKeywordClassifier([
        {
          query: "run a gillespie simulation of first-order decay",
          expected: "mm_competitive_inhibition",
          why: "deliberately mislabelled so the report has a miss to name",
          split: "dev",
        },
      ]),
    );
    expect(text).toContain("misses:");
    expect(text).toContain(
      "expected mm_competitive_inhibition, got gillespie_ssa",
    );
  });
});

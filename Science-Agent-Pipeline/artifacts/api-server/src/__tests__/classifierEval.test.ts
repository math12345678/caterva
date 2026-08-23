/**
 * What the domain-classifier benchmark measures, and proof it can fail.
 *
 * The keyword table is the resolver's behaviour whenever no LLM is
 * configured -- which, before this work, was every deployment that set API
 * keys without also setting LLM_PROVIDER. Its accuracy was never measured.
 * These tests pin what the measurement found, so that a change to the
 * keyword table or its ordering shows up as a named failure rather than as a
 * silently different score.
 *
 * The mis-routings below are asserted individually and on purpose. If
 * somebody reorders DOMAIN_DEFAULTS and fixes one, the corresponding test
 * fails and names the defect that was fixed -- which is the notification we
 * want, not a number quietly moving.
 */

import { describe, expect, it } from "vitest";
import {
  LABELLED_QUERIES,
  benchmarkKeywordClassifier,
  formatSummary,
  type LabelledQuery,
} from "../lib/classifierEval";
import { classifyDomainByKeyword } from "../lib/queryResolver";

/** The domains the LLM resolver is allowed to return; the benchmark should
 *  exercise every one of them or it is not a benchmark of the classifier. */
const LLM_EXPOSED_DOMAINS = [
  "mm",
  "mm_competitive_inhibition",
  "sir",
  "seir",
  "wright_fisher",
  "gillespie_ssa",
  "pcr",
  "molecular_dynamics",
  "gillespie_ssa_bimolecular",
  "two_locus_wright_fisher",
  "lotka_volterra",
  "cell_cycle_oscillator",
  "repressilator",
] as const;

describe("the labelled set", () => {
  it("covers every domain the LLM resolver can return", () => {
    const covered = new Set(LABELLED_QUERIES.map((q) => q.expected));
    const missing = LLM_EXPOSED_DOMAINS.filter((d) => !covered.has(d));
    expect(missing).toEqual([]);
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
    // would make the query less realistic, not more rigorous. Every other
    // domain key must be inferred from a description.
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
    const { defaults, matched } = classifyDomainByKeyword(
      "What happens to rabbit and fox populations over time?",
    );
    // It still returns a domain -- that is the fallback, and it is wrong.
    expect(defaults.domain).toBe("mm");
    // The point of the extraction: the caller can now see it was a fallback.
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
    // Both return "mm". Before `matched` existed these were the same fact,
    // which is what let the baseline look accurate on queries it had never
    // understood.
    const real = classifyDomainByKeyword("enzyme kinetics of catalase");
    const fallback = classifyDomainByKeyword("rabbit and fox populations");
    expect(real.defaults.domain).toBe(fallback.defaults.domain);
    expect(real.matched).not.toBe(fallback.matched);
  });
});

describe("measured defects in the ordered keyword table", () => {
  const domainOf = (q: string) => classifyDomainByKeyword(q).defaults.domain;

  it("routes a latent-period epidemic to sir, because sir is checked before seir", () => {
    expect(
      domainOf(
        "Simulate a disease with an incubation period before patients become infectious.",
      ),
    ).toBe("sir");
  });

  it("routes 'predator-prey cycles' to pcr, because 'cycles' is a PCR keyword", () => {
    // The most surprising one found: an ecology question becomes a DNA
    // amplification simulation on the strength of the word "cycles".
    expect(domainOf("Model predator-prey cycles in an ecosystem.")).toBe("pcr");
  });

  it("routes the repressilator to the cell cycle, because 'oscillator' is checked first", () => {
    expect(
      domainOf("Simulate the Elowitz and Leibler synthetic genetic oscillator."),
    ).toBe("cell_cycle_oscillator");
  });

  it("routes a two-locus question to mm, matching nothing at all", () => {
    const { defaults, matched } = classifyDomainByKeyword(
      "Model two linked genes recombining in a finite population as allele frequencies drift.",
    );
    expect(defaults.domain).toBe("mm");
    expect(matched).toBe(false);
  });
});

describe("the benchmark itself", () => {
  it("scores the keyword table below perfect on the labelled set", () => {
    const summary = benchmarkKeywordClassifier();
    expect(summary.total).toBe(LABELLED_QUERIES.length);
    expect(summary.correct).toBeLessThan(summary.total);
    expect(summary.accuracy).toBeLessThan(1);
  });

  it("counts fallbacks separately from answers", () => {
    const summary = benchmarkKeywordClassifier();
    expect(summary.undetermined).toBeGreaterThan(0);
  });

  /**
   * Proof the benchmark can fail. A check that cannot fail is worse than no
   * check, because it is trusted. Feeding it a set whose labels are
   * deliberately wrong must produce a zero, not a pass.
   */
  it("reports zero when every label is deliberately wrong", () => {
    // Relabel each query to a domain the classifier demonstrably does NOT
    // return for it. Deriving the wrong label from the actual answer is
    // what makes the sabotage total -- a fixed wrong label (say, "pcr" for
    // everything) accidentally matches the queries that really do classify
    // as pcr, and the benchmark then scores 1 and looks unfalsifiable.
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
    // A score with no misses listed cannot be acted on.
    const text = formatSummary(benchmarkKeywordClassifier());
    expect(text).toContain("misses:");
    expect(text).toContain("expected lotka_volterra, got pcr");
  });
});

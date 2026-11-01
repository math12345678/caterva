/**
 * What actually happens when a researcher types a real question.
 *
 * WHY THIS FILE EXISTS
 * --------------------
 * "It doesn't work half the time" is a measurement, and until this file
 * there was no committed way to reproduce it. Every other test here asks
 * whether a specific mechanism behaves; none asks the only question a
 * person outside this repository cares about: I typed a sentence about my
 * system -- did I get a model?
 *
 * These twenty queries are the kind a teaching lab or a first-year graduate
 * student actually types. They are deliberately NOT drawn from the
 * catalogue's own vocabulary, because a harness assembled from the terms
 * the matcher already knows measures nothing.
 *
 * This runs with no LLM key, which is the honest default: `resolveQueryWithLLM`
 * returns null without one, so what is measured here is the keyword scorer --
 * the path every deployment without a configured provider is actually on.
 */

import { writeFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { UnrecognizedQueryError } from "../lib/provenance";

/** A real question, and the model a competent person would expect back. */
interface Case {
  query: string;
  /** Roughly what should come out. `null` = nothing in the catalogue fits. */
  expect: string | null;
  why: string;
}

export const QUERIES: Case[] = [
  // -- squarely in the catalogue: these SHOULD work -------------------
  { query: "michaelis menten kinetics for hexokinase",
    expect: "mm", why: "the flagship teaching model" },
  { query: "enzyme kinetics with a competitive inhibitor",
    expect: "mm_competitive_inhibition", why: "inhibition is stated" },
  { query: "SIR model of a measles outbreak in a school",
    expect: "sir", why: "named compartments" },
  { query: "SEIR epidemic with an exposed class",
    expect: "seir", why: "exposed class is the distinguishing term" },
  { query: "genetic drift in a small population",
    expect: "wright_fisher", why: "drift is the mechanism" },
  { query: "predator prey population cycles",
    expect: "lotka_volterra", why: "canonical phrasing" },
  { query: "stochastic simulation of a chemical reaction",
    expect: "gillespie_ssa", why: "stochastic + reaction" },
  { query: "PCR amplification over 30 cycles",
    expect: "pcr", why: "named process" },
  { query: "repressilator oscillations",
    expect: "repressilator", why: "named model" },
  { query: "cell cycle oscillator dynamics",
    expect: "cell_cycle_oscillator", why: "named model" },

  // -- real biology the catalogue does not contain --------------------
  //
  // Each of these is a system somebody genuinely wants to simulate and a
  // structure the reaction-network IR can express. A catalogue cannot
  // answer them; a model BUILDER can.
  { query: "three step phosphorylation cascade",
    expect: null, why: "compositional, not a catalogue entry" },
  { query: "glycolysis in yeast",
    expect: null, why: "a named pathway, not a catalogue entry" },
  { query: "a MAP kinase cascade with negative feedback",
    expect: null, why: "compositional with feedback" },
  { query: "reversible binding of a ligand to a receptor",
    expect: null, why: "a two-species reversible step" },
  { query: "substrate inhibition at high substrate concentration",
    expect: null, why: "a rate law variant, not a listed domain" },
  { query: "two enzymes competing for the same substrate",
    expect: null, why: "compositional" },
  { query: "a toggle switch between two repressors",
    expect: null, why: "compositional gene circuit" },
  { query: "sequential feedback inhibition in amino acid synthesis",
    expect: null, why: "compositional pathway" },
  { query: "an open system with constant substrate inflow",
    expect: null, why: "boundary condition, not a listed domain" },
  { query: "allosteric activation of an enzyme by its product",
    expect: null, why: "compositional regulation" },
];

/** What the front door did with one query. */
async function attempt(query: string): Promise<
  { ok: true; domain: string } | { ok: false; reason: string }
> {
  try {
    const resolved = await resolveQuery(query);
    return { ok: true, domain: resolved.domain };
  } catch (err) {
    if (err instanceof UnrecognizedQueryError) {
      return { ok: false, reason: "UnrecognizedQueryError" };
    }
    return {
      ok: false,
      reason: err instanceof Error ? err.name : "unknown",
    };
  }
}

describe("what the front door does with twenty real questions", () => {
  it("reports coverage, and the report is the point", async () => {
    const rows: string[] = [];
    let answered = 0;
    let correct = 0;

    for (const testCase of QUERIES) {
      const outcome = await attempt(testCase.query);
      const got = outcome.ok ? outcome.domain : outcome.reason;
      if (outcome.ok) {
        answered += 1;
        if (testCase.expect !== null && outcome.domain === testCase.expect) {
          correct += 1;
        }
      }
      const verdict =
        outcome.ok && testCase.expect === outcome.domain
          ? "OK"
          : outcome.ok && testCase.expect === null
            ? "WRONG-MODEL"
            : outcome.ok
              ? "MISMATCH"
              : "REFUSED";
      rows.push(
        `${verdict.padEnd(12)} ${testCase.query.slice(0, 46).padEnd(48)} -> ${got}`,
      );
    }

    // Written to a file as well as printed: vitest buffers console output
    // per-worker and it does not reliably reach a piped stdout, which made
    // the one number this file exists to produce unreadable in CI.
    const report = [
        "",
        "FRONT DOOR COVERAGE (no LLM key -- the keyword path)",
        "=".repeat(78),
        ...rows,
        "=".repeat(78),
        `answered ${answered}/${QUERIES.length}, ` +
          `correct model ${correct}/${QUERIES.length}`,
        "",
      ].join("\n");
    console.log(report);
    writeFileSync("front-door-coverage.txt", report);

    // No threshold asserted here on purpose. A pass/fail bar would turn a
    // measurement into a target and invite tuning the harness. The number
    // is recorded in the ADR; this test exists so it can be reproduced.
    expect(QUERIES).toHaveLength(20);
  }, 120_000);
});

/**
 * A query naming a special case must get the special case.
 *
 * Four pairs of domains are nested rather than merely similar: SEIR contains
 * SIR, bimolecular Gillespie contains Gillespie, competitive inhibition
 * contains Michaelis-Menten, two-locus Wright-Fisher contains Wright-Fisher.
 *
 * Summed keyword scoring cannot see that. A parent's vocabulary is true of
 * the child as well, so the parent accumulates score on words that do not
 * discriminate and outvotes the child's one decisive phrase. Measured before
 * the fix: "an infection spreads when there's a hidden incubation phase"
 * scored SIR 16 against SEIR 10, and the query that said *incubation* got
 * the model without an incubation period.
 *
 * Two directions have to hold, and the second is the one that makes this
 * risky. Promoting on a single distinctive term regardless of score is a
 * strong rule; if it fires too readily, every query mentioning an inhibitor
 * in passing becomes an inhibition simulation. Both directions are asserted.
 */

import { describe, expect, it } from "vitest";
import {
  classifyDomainByKeyword,
  refinementPairs,
} from "../lib/queryResolver";

const domainOf = (q: string) => classifyDomainByKeyword(q).defaults.domain;

describe("the declared refinement graph", () => {
  it("names a parent that exists for every child", () => {
    const known = new Set([
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
    ]);
    for (const { child, parent } of refinementPairs()) {
      expect(known.has(child)).toBe(true);
      expect(known.has(parent)).toBe(true);
    }
  });

  it("is acyclic, so promotion terminates", () => {
    // `resolveNesting` throws on a cycle rather than looping forever. That
    // branch is unreachable with correct declarations, and reaching it would
    // require stubbing the table -- so the invariant is asserted on the data
    // instead, which is the thing that could actually go wrong.
    const parentOf = new Map(
      refinementPairs().map(({ child, parent }) => [child, parent]),
    );
    for (const start of parentOf.keys()) {
      const seen = new Set<string>([start]);
      let node = parentOf.get(start);
      while (node !== undefined) {
        expect(seen.has(node)).toBe(false);
        seen.add(node);
        node = parentOf.get(node);
      }
    }
  });

  it("declares no domain as a refinement of itself", () => {
    for (const { child, parent } of refinementPairs()) {
      expect(child).not.toBe(parent);
    }
  });
});

describe("a query that names the special case gets it", () => {
  it.each([
    [
      "Can you show me how an infection spreads when there's a hidden incubation phase?",
      "seir",
    ],
    [
      "I want to see a simulation where people go from susceptible to exposed before getting sick.",
      "seir",
    ],
    [
      "Please generate a chart of disease dynamics with a separate exposed group.",
      "seir",
    ],
    ["Can you run a stochastic simulation of A plus B forming C?", "gillespie_ssa_bimolecular"],
    [
      "Could you generate a random trajectory for A + B to C using the Gillespie approach?",
      "gillespie_ssa_bimolecular",
    ],
  ])("routes %j to %s", (query, expected) => {
    expect(domainOf(query)).toBe(expected);
  });
});

describe("a query that names only the general case keeps it", () => {
  // The direction that bounds the rule. Promotion happens on one distinctive
  // term regardless of score, so it has to not happen when no distinctive
  // term is there. Measured across all 228 fixture queries: zero
  // over-promotions.
  it.each([
    ["How many people in a closed town are still susceptible after the wave passes?", "sir"],
    ["Model how measles spreads through an unvaccinated school.", "sir"],
    [
      "Simulate the random decay of a small number of molecules, one reaction at a time.",
      "gillespie_ssa",
    ],
    ["How does an allele drift to fixation in a small population?", "wright_fisher"],
  ])("leaves %j as %s", (query, expected) => {
    expect(domainOf(query)).toBe(expected);
  });

  it("does not promote on a distinctive term the query denies", () => {
    // The interaction with ADR 0192. "no inhibitor" contains the child's
    // distinctive word; promotion must not fire on a mention the query
    // negates, or the negation work is undone by this one.
    expect(
      domainOf(
        "I want to see how the reaction speed changes as I add more substrate, no inhibitor involved.",
      ),
    ).not.toBe("mm_competitive_inhibition");
  });
});

describe("promotion needs a term the parent does not also have", () => {
  it("keeps a parent-only query with the parent", () => {
    // Asserted through behaviour: a query built only from vocabulary the
    // parent owns must stay with the parent, however strongly it matches.
    const parentOnly =
      "Model an epidemic outbreak where a virus spreads through a population and people recover.";
    expect(domainOf(parentOnly)).toBe("sir");
  });

  /**
   * The distinctiveness filter is a no-op today, and this records it.
   *
   * `resolveNesting` promotes only on terms the child has and the parent
   * does not, because a term both list is evidence for the pair rather than
   * for either member -- if shared terms could promote, the rule would fire
   * on every query the parent matched at all, which is the original defect
   * with its arrow reversed.
   *
   * Measured: no declared pair shares a single term, so the filter removes
   * nothing and changes no classification. The mutation that deletes it is
   * reported NOT CAUGHT in ADR 0194 for exactly this reason, rather than
   * being made catchable by inventing an overlap no classifier needs.
   *
   * It is kept because it costs nothing and is correct whatever the table
   * later contains -- and this test is the alarm. Keyword lists change; 120
   * terms were added to them one ADR ago. The day somebody adds a term to
   * both a child and its parent, this fails and tells them the filter has
   * stopped being decorative and now decides classifications.
   */
  it("has nothing to filter yet -- no declared pair shares a term", () => {
    for (const pair of refinementPairs()) {
      const parentTerms = new Set(pair.parentTerms.map((t) => t.toLowerCase()));
      const shared = pair.childTerms.filter((t) =>
        parentTerms.has(t.toLowerCase()),
      );
      expect({ pair: `${pair.child} <- ${pair.parent}`, shared }).toEqual({
        pair: `${pair.child} <- ${pair.parent}`,
        shared: [],
      });
      // And therefore every child term is currently distinctive.
      expect(pair.distinctive).toHaveLength(pair.childTerms.length);
    }
  });
});

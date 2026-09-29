/**
 * Nested-domain assertions for the domains archived on 2026-09-27.
 *
 * SEIR contains SIR and two-locus Wright-Fisher contains Wright-Fisher; both
 * pairs are gone with their domains, and with them the queries that measured
 * the defect ADR 0194 records -- a parent outvoting its child because the
 * parent's vocabulary is true of the child as well. The surviving pairs
 * (mm_competitive_inhibition <- mm, gillespie_ssa_bimolecular <-
 * gillespie_ssa) still assert both directions in
 * src/__tests__/nestedDomains.test.ts.
 *
 * Not collected by CI; the api-server suite is `src/**/*.test.ts`.
 */
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

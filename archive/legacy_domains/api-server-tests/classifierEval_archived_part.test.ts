/**
 * Classifier assertions for the domains archived on 2026-09-27.
 *
 * These are the ADR 0190 defects and their fixes -- an incubation-period
 * query reaching SEIR rather than SIR, predator-prey reaching
 * lotka_volterra, a synthetic oscillator reaching the repressilator, a
 * two-locus question reaching two_locus_wright_fisher, and a cell-division
 * question staying with the cell-cycle oscillator. Every domain named here
 * now lives in ../../ -- see this directory's README.
 *
 * Kept because they are the evidence for ADR 0190/0191: the measurements
 * that said the keyword classifier was wrong in those specific ways, and
 * the assertions that said it had stopped being. Not collected by CI; the
 * api-server suite is `src/**/*.test.ts`.
 */
describe("defects ADR 0190 measured, now fixed by specificity scoring", () => {
  const domainOf = (q: string) => classifyDomainByKeyword(q).defaults.domain;

  it("routes an incubation-period epidemic to seir, not sir", () => {
    // Was `sir`: sir sits earlier in the table and matched the bare word
    // "disease" before seir was ever considered. "incubation period" (18)
    // now outscores "disease" (7).
    expect(
      domainOf(
        "Simulate a disease with an incubation period before patients become infectious.",
      ),
    ).toBe("seir");
  });

  it("routes 'predator-prey cycles' to lotka_volterra, not pcr", () => {
    // The most surprising defect found: an ecology question became a DNA
    // amplification simulation because "cycles" is a PCR keyword and pcr
    // sits earlier. "predator-prey" (13) now outscores "cycles" (6).
    expect(domainOf("Model predator-prey cycles in an ecosystem.")).toBe(
      "lotka_volterra",
    );
  });

  it("routes a synthetic genetic oscillator to the repressilator, not the cell cycle", () => {
    // Was `cell_cycle_oscillator`, which matched "oscillator" first.
    expect(
      domainOf("Simulate the Elowitz and Leibler synthetic genetic oscillator."),
    ).toBe("repressilator");
  });

  it("routes a two-locus question to two_locus_wright_fisher, not the mm fallback", () => {
    // Was the `mm` fallback: it matched nothing at all.
    const { defaults, matched } = classifyDomainByKeyword(
      "Model two linked genes recombining in a finite population as allele frequencies drift.",
    );
    expect(defaults.domain).toBe("two_locus_wright_fisher");
    expect(matched).toBe(true);
  });

  it("still routes a plain cell-division question to the cell cycle", () => {
    // The counterpart of the repressilator fix: widening one domain's
    // vocabulary must not steal the queries that legitimately belong to its
    // neighbour.
    expect(domainOf("Model how cyclin and CDK drive a cell through division.")).toBe(
      "cell_cycle_oscillator",
    );
  });
});

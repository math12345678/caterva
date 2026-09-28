// Tests from domainClassification.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.

  it('"predator and prey populations" resolves to lotka_volterra, not mm', async () => {
    // Old exact-substring check needed the adjacent phrase "predator prey"
    // or "predator-prey" -- "predator AND prey" (a completely ordinary way
    // to phrase this) matched neither and fell through to mm.
    expect(
      await classifiedDomain("simulate predator and prey populations over 50 years"),
    ).toBe("lotka_volterra");
  });

  it('"allele frequencies" (plural) resolves to wright_fisher, not mm', async () => {
    // Old check required the exact singular substring "allele frequency".
    expect(
      await classifiedDomain(
        "what happens to allele frequencies in a small population of 20 individuals",
      ),
    ).toBe("wright_fisher");
  });

  it('naming a disease directly ("measles") resolves to sir, not mm', async () => {
    // measles has no verified literature R0 (ADR 0017) so this still
    // refuses -- but it must refuse as a SIR query missing beta/gamma, not
    // silently run as if the question had been about enzyme kinetics.
    const domain = await classifiedDomain(
      "I want to model the spread of measles in a school with 500 students",
    );
    expect(domain).toBe("sir");
  });

  it('naming covid resolves to sir and reaches the real literature R0 bridge', async () => {
    const result = await resolveQuery(
      "model a covid-19 outbreak s0=990 i0=10 r0_recovered=0 end=100 points=101",
    );
    expect(result.domain).toBe("sir");
    // Real literature-backed resolution (not a hardcoded default): the
    // parameterProvenance origin for beta/gamma should be "resolved", not
    // "default" or "user", proving classification reached the disease
    // registry rather than just guessing the right domain by luck.
    expect(result.parameterProvenance["beta"]?.origin).toBe("resolved");
    expect(result.parameterProvenance["gamma"]?.origin).toBe("resolved");
  });

  it('a real disease outside the registry (measles) explains WHY beta/gamma are unresolved, not just THAT they are', async () => {
    // Before this fix, an unregistered disease's beta/gamma got the
    // generic "could not be resolved from literature" sentence -- false by
    // omission for a real, well-studied disease that simply isn't
    // registered here yet (only COVID-19 is, per ADR 0017), as opposed to
    // one the literature is actually silent on.
    try {
      await resolveQuery(
        "the spread of measles in a school with 500 students",
      );
      throw new Error("expected resolveQuery to throw");
    } catch (e) {
      expect(e).toBeInstanceOf(RequiredParametersMissingError);
      const err = e as RequiredParametersMissingError;
      expect(err.domain).toBe("sir");
      expect(err.details["beta"]).toMatch(
        /matches Caterva's literature-backed R0 registry/,
      );
      expect(err.details["gamma"]).toMatch(
        /matches Caterva's literature-backed R0 registry/,
      );
    }
  });

  it('"lennard-jones cluster" still resolves to molecular_dynamics', async () => {
    expect(
      await classifiedDomain("simulate a lennard-jones cluster of 13 atoms"),
    ).toBe("molecular_dynamics");
  });


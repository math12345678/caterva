// Tests from queryOverrides.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.

  it("test 1: succeeds end-to-end with all overrides", async () => {
    const result = await resolveQuery(
      `linkage disequilibrium two locus ${TWO_LOCUS_OVERRIDES}`,
    );
    expect(result.domain).toBe("two_locus_wright_fisher");
    expect(result.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    // starting_frequencies must be origin: "user"
    expect(result.parameterProvenance["starting_frequencies"]!.origin).toBe(
      "user",
    );
    // No parameters should be origin: "default" (hard-block)
    for (const [key, prov] of Object.entries(result.parameterProvenance)) {
      expect(prov.origin).not.toBe("default");
    }
  });

  it("test 4: absent starting_frequencies now takes a labelled default", async () => {
    // INVERTED 2026-09-06. `starting_frequencies` is an array of allele
    // frequencies to start a drift run from -- a scenario choice, and one
    // no query string could supply through PARAMETER_PATTERN, so refusing
    // over it left this domain permanently unreachable.
    const resolved = await resolveQuery(
      "linkage disequilibrium two locus population_size=200 generations=30 recombination_rate=0.1 mutation_rate=0.001 replicate_runs=100",
    );
    expect(resolved.domain).toBe("two_locus_wright_fisher");
    const provenance = resolved.parameterProvenance["starting_frequencies"];
    expect(provenance).toBeDefined();
    expect(provenance!.origin).toBe("default");
    // The measured constants in this query stay the user's, not defaults.
    expect(resolved.parameterProvenance["mutation_rate"]!.origin).toBe("user");
  });


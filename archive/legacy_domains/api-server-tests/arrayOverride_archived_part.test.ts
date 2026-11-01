// Tests from arrayOverride.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.

  it("accepts starting_frequencies with spaces after commas", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5, 0, 0, 0.5";

    const resolved = await resolveQuery(query);
    expect(resolved.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    const prov = resolved.parameterProvenance.starting_frequencies!;
    expect(prov.origin).toBe("user");
  });

  it("resolves with a defaulted starting_frequencies, and labels it", async () => {
    // INVERTED 2026-09-06: `starting_frequencies` is an array of allele
    // frequencies to start from -- a scenario choice, and one no query
    // string could ever supply through PARAMETER_PATTERN, so refusing
    // over it made this domain permanently unreachable. It now takes a
    // documented default, labelled as one. The measured constants in the
    // query (recombination_rate, mutation_rate) are still required.
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50";

    const resolved = await resolveQuery(query);
    expect(resolved.domain).toBe("two_locus_wright_fisher");
    const provenance = resolved.parameterProvenance["starting_frequencies"];
    expect(provenance).toBeDefined();
    expect(provenance!.origin).toBe("default");
  });

  it("two_locus_wright_fisher with valid starting_frequencies and all required overrides succeeds", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5,0,0,0.5";

    const resolved = await resolveQuery(query);
    expect(resolved.domain).toBe("two_locus_wright_fisher");
    expect(resolved.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    const prov = resolved.parameterProvenance.starting_frequencies!;
    expect(prov.origin).toBe("user");
  });


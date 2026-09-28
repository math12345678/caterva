// Parts of provenance.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.


  ["pcr", "simulate pcr amplification n0=100 efficiency=0.95 cycles=30"],

  ["monte_carlo_pi", "estimate pi with monte carlo n_samples=10000"],

  [
    "sir",
    "simulate sir outbreak beta=0.3 gamma=0.1 s0=990 i0=10 r0_recovered=0 end=100 points=101",
  ],

  [
    "seir",
    "simulate seir incubation beta=0.3 sigma=0.2 gamma=0.1 s0=990 e0=10 i0=0 r0_recovered=0 end=100 points=101",
  ],

  [
    "wright_fisher",
    "simulate genetic drift population_size=100 starting_frequency=0.5 " +
      "generations=100 replicate_runs=100 mutation_rate=0 selection_coefficient=0",
  ],

  [
    "molecular_dynamics",
    "molecular dynamics lennard-jones n_particles=108 temperature=0.4 " +
      "timestep=0.005 n_steps=1000 density=0.85",
  ],
// Domains that can never satisfy the hard rule through query overrides
// alone (see comment above): a bare -- or even fully key=value-annotated --
// query to these domains always throws RequiredParametersMissingError,
// because at least one parameter has no override syntax that reaches it.
const UNSATISFIABLE_DOMAIN_QUERIES: Array<
  [string, string, string[]]
> = [
  [
    "two_locus_wright_fisher",
    "linkage disequilibrium two locus population_size=100 generations=20 recombination_rate=0.1 mutation_rate=0 replicate_runs=50",
    ["starting_frequencies"],
  ],
];

  describe("Target A — the domain that used to be permanently unreachable", () => {
    // THIS TEST RECORDED A DEFECT AND NOW RECORDS ITS FIX (2026-09-06).
    //
    // It used to assert that these domains can ONLY throw, and said so:
    // "Documents, rather than works around, a real production consequence:
    // these three domains have at least one parameter that
    // PARAMETER_PATTERN can never populate from query text ... so under the
    // new hard rule they can never return a result through resolveQuery()
    // -- only throw."
    //
    // The unreachable key was `starting_frequencies` -- an array of allele
    // frequencies to start a drift simulation from. A scenario choice, not
    // a measurement, and one no amount of literature searching could ever
    // supply. The hard rule blocked it anyway, so a whole domain was
    // permanently unusable and a test was written to record that rather
    // than to fix it.
    //
    // Scenario choices may now carry a documented default, so the domain
    // resolves. The assertion is inverted, and the measured constants it
    // still needs (recombination_rate, mutation_rate, supplied inline
    // above) are unaffected.
    for (const [domain, query] of UNSATISFIABLE_DOMAIN_QUERIES) {
      it(`${domain}: now resolves, and labels the defaulted choice as a default`, async () => {
        const resolved = await resolveQuery(query);
        expect(resolved.domain).toBe(domain);

        // The value ran, and the caller is told Caterva chose it. A
        // default that ran SILENTLY would be the fabrication the hard rule
        // exists to prevent.
        const provenance = resolved.parameterProvenance["starting_frequencies"];
        expect(
          provenance,
          "starting_frequencies has no provenance entry at all",
        ).toBeDefined();
        expect(provenance!.origin).toBe("default");
      });
    }
  });


  it("two_locus_wright_fisher with valid starting_frequencies resolves successfully", async () => {
    const resolved = await resolveQuery(
      "two locus linkage disequilibrium population_size=100 generations=20 " +
        "starting_frequencies=0.5,0,0,0.5 recombination_rate=0.1 mutation_rate=0 replicate_runs=50",
    );
    expect(resolved.domain).toBe("two_locus_wright_fisher");
    expect(resolved.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    const prov = resolved.parameterProvenance.starting_frequencies!;
    expect(prov.origin).toBe("user");
  });

  it("resolves with a defaulted starting_frequencies, and labels it", async () => {
    // INVERTED 2026-09-06, same reason as Target A above. This required a
    // refusal when `starting_frequencies` was absent -- and because that
    // key is an ARRAY, no query string could ever supply it through
    // PARAMETER_PATTERN, so the domain was permanently unreachable and
    // this test pinned it that way.
    //
    // Allele frequencies to start a drift simulation from are a scenario
    // choice, not a measurement. The measured constants in this same query
    // (recombination_rate, mutation_rate) are supplied inline and are
    // still required.
    const resolved = await resolveQuery(
      "two locus linkage disequilibrium population_size=100 generations=20 " +
        "recombination_rate=0.1 mutation_rate=0 replicate_runs=50",
    );
    expect(resolved.domain).toBe("two_locus_wright_fisher");
    const provenance = resolved.parameterProvenance["starting_frequencies"];
    expect(provenance).toBeDefined();
    expect(provenance!.origin).toBe("default");
  });


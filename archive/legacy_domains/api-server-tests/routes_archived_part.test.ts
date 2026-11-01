// Tests from routes.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.

  it("runs a two_locus_wright_fisher query with an array override to completion", async () => {
    const createRes = await request(server)
      .post("/api/simulate")
      .send({
        query:
          "linkage disequilibrium two locus population_size=200 generations=30 " +
          "recombination_rate=0.1 starting_frequencies=0.5,0,0,0.5 " +
          "mutation_rate=0.001 replicate_runs=50",
      });
    const result = (await awaitJob(createRes.body.jobId)) as any;

    expect(result.domain).toBe("two_locus_wright_fisher");
    expect(result.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    expect(result.trajectory.length).toBeGreaterThan(0);
    expect(result.trajectory[0].generation).toBe(0);
  });


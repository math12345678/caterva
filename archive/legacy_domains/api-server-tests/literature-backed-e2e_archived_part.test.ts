// Tests from literature-backed-e2e.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.

    it("sir domain backed by Kermack & McKendrick (1927)", async () => {
      const query = "simulate michaelis menten km=2 vmax=5 s0=10 end=10 points=51";

      const result = await resolveQuery(query);

      expect(result.domain).toBe("sir");

      const citation = getDomainCitation("sir");
      expect(citation).toContain("Kermack");
      expect(citation).toContain("1927");
    });

    it("wright_fisher domain backed by Rahbari et al. (2016)", async () => {
      const query = "simulate wright fisher mutation_rate=1e-8";

      // This may fail if LLM/keyword matching doesn't trigger, but domain should have backing
      const citation = getDomainCitation("wright_fisher");
      expect(citation).toContain("Rahbari");
      expect(citation).toContain("2016");
    });


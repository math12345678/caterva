// Tests from scenarioDefaults.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.

  it("still refuses a measurement nobody can source", async () => {
    // ADR 0017: Guerra et al. found no single defensible R0 for measles,
    // so the registry has no entry and this must stay refused. The point
    // of the change was never to make everything run.
    await expect(resolveQuery("measles outbreak in a school")).rejects.toThrow(
      /beta|gamma|not registered/i,
    );
  }, 120_000);


// moved from src/cli/__tests__/domainCatalogue.test.ts on 2026-09-27 with the archived domains

  it('reports an entry the engine dropped', () => {
    const withoutPcr = ENGINE_IDS.filter((id) => id !== 'pcr');
    const report = reconcileCatalogue(withoutPcr);
    expect(report.phantom).toEqual(['pcr']);
    expect(report.entries.map((e) => e.id)).not.toContain('pcr');
  });

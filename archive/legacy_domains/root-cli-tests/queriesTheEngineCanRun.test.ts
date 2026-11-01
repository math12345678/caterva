// moved from src/validation/__tests__/queriesTheEngineCanRun.test.ts on 2026-09-27 with the archived domains

  it('accepts `sir`, which the old list made unreachable over HTTP', () => {
    // ADR 0020 wired epidemiology end to end. The API refused it for as
    // long as both existed, because the list predated the domain.
    expect(accepts('sir')).toBe(true);
  });

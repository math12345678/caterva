// Tests moved from api-server/src/__tests__/statedQuantities.test.ts on 2026-09-27
// with the epidemiology, population-genetics and PCR domains.

  it("reads a population as a TOTAL and derives the susceptible count", () => {
    // The measured failure that motivated this: the population was in the
    // sentence and the API demanded s0 back as a CLI flag.
    const q = "model a covid-19 outbreak in a town of 10000 people with 5 infected";
    expect(find(q, "sir", "i0")?.value).toBe(5);
    // s0 is SUSCEPTIBLE and N = s0 + i0 + r0, so a town of 10000 with 5
    // already infected has 9995 susceptible. Binding 10000 would simulate a
    // town of 10005 -- not the town described.
    expect(find(q, "sir", "s0")?.value).toBe(9995);
  });

  it("handles a population with no stated infected count", () => {
    const q = "covid-19 outbreak in a population of 500";
    expect(find(q, "sir", "s0")?.value).toBe(500);
    expect(find(q, "sir", "i0")).toBeUndefined();
  });

  it("reads the bare '<n> people' phrasing too", () => {
    expect(find("covid outbreak, 2000 people", "sir", "s0")?.value).toBe(2000);
  });

  it("carries the source phrase so a misreading is auditable", () => {
    const hit = find("outbreak in a town of 10000 people", "sir", "s0");
    // Without this, a wrong binding is only discoverable from the
    // trajectory. With it, provenance can say WHY s0 has this value.
    expect(hit?.sourcePhrase).toMatch(/town of 10000/i);
  });

  it("reads time in the DOMAIN's own unit, which differs between families", () => {
    // Epidemiology is in days (gamma = 1/infectious_period_days).
    expect(find("covid outbreak over 30 days", "sir", "end")?.value).toBe(30);
    expect(find("covid outbreak for 2 weeks", "sir", "end")?.value).toBe(14);

    // Enzyme kinetics is in seconds (Vmax is mM/s). The same words mean a
    // very different number here, and reading "30 days" as 30 would
    // simulate half a minute of a month-long assay.
    expect(find("hexokinase assay for 30 seconds", "mm", "end")?.value).toBe(30);
    expect(find("hexokinase assay for 5 minutes", "mm", "end")?.value).toBe(300);
    expect(find("hexokinase assay over 30 days", "mm", "end")?.value).toBe(2_592_000);
  });

  it("reads PCR cycles", () => {
    expect(find("amplify DNA over 35 cycles", "pcr", "cycles")?.value).toBe(35);
  });

  it("reads generations for popgen, which counts steps rather than time", () => {
    const got = extractStatedQuantities(
      "genetic drift in a population of 250 over 100 generations",
      "wright_fisher",
    );
    expect(got.find((q) => q.key === "generations")?.value).toBe(100);
    expect(got.find((q) => q.key === "population_size")?.value).toBe(250);
    // Generations are discrete steps, not a duration -- "100 generations"
    // must not also become an `end` in days or seconds.
    expect(got.find((q) => q.key === "end")).toBeUndefined();
  });

  it("maps a population to population_size for popgen, not s0", () => {
    const got = extractStatedQuantities(
      "genetic drift in a population of 250",
      "wright_fisher",
    );
    expect(got.find((q) => q.key === "population_size")?.value).toBe(250);
    expect(got.find((q) => q.key === "s0")).toBeUndefined();
  });

  it("does not extract a population smaller than the stated infected count", () => {
    // Would yield a non-positive susceptible count. Forcing that into shape
    // would fail engine validation with a confusing message; leaving it to
    // the refusal path is honest.
    const got = extractStatedQuantities(
      "outbreak in a town of 3 people with 10 infected",
      "sir",
    );
    expect(got.find((q) => q.key === "s0")).toBeUndefined();
  });

  it("does not claim recovered=0 when the query mentions recovered or immune people", () => {
    // Deriving r0_recovered=0 is a READING of "a town of N with M
    // infected" -- everyone is accounted for and nobody was described as
    // recovered. The moment a query does mention them, that reading is no
    // longer available and guessing would be inventing.
    for (const q of [
      "outbreak in a town of 10000 people with 5 infected and 200 recovered",
      "town of 10000 people, 5 infected, 300 already immune",
      "town of 10000 people with 5 infected, 40% vaccinated",
    ]) {
      const got = extractStatedQuantities(q, "sir");
      expect(got.find((x) => x.key === "r0_recovered")).toBeUndefined();
    }
  });

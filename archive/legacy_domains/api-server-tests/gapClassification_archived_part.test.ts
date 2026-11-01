// Tests from gapClassification.test.ts that exercised domains archived on 2026-09-27.
// Kept for reference; not collected. Caterva v0.4.0 runs them.

  it("treats neutral drift's selection coefficient as definitional, not a guess", () => {
    // s = 0 is what "genetic drift" MEANS. Refusing to model neutral drift
    // because we decline to assume neutrality is not caution.
    const verdict = classifyGap(
      "wright_fisher", "selection_coefficient",
      "genetic drift in a small population", undefined, undefined,
    );
    expect(verdict.kind).toBe("definitional");
    expect(verdict.value).toBe(0);
    expect(verdict.reason).toContain("neutral");
  });

  it("withdraws the definitional claim when the query asks about selection", () => {
    // The claim is about what the words mean, so words that contradict it
    // must retract it. Otherwise "drift with a selective advantage" would
    // silently be simulated with s = 0 -- the opposite of what was asked.
    const verdict = classifyGap(
      "wright_fisher", "selection_coefficient",
      "genetic drift with a selective advantage", undefined, undefined,
    );
    expect(verdict.kind).not.toBe("definitional");
  });

  it("emits a flag for every value it supplies", () => {
    // Beside the value, not left to the caller. A placeholder whose label
    // depends on somebody remembering to add it will eventually ship
    // unlabelled.
    // `mutation_rate` is NOT filled: Caterva searches for mutation rates,
    // and a definition must never short-circuit a search that could work.
    const gaps = resolveGaps(
      "wright_fisher", "genetic drift in a small population",
      ["selection_coefficient", "mutation_rate"], {}, {},
    );
    expect(Object.keys(gaps.filled)).toEqual(["selection_coefficient"]);
    expect(gaps.flags).toHaveLength(1);
    expect(gaps.stillMissing).toEqual(["mutation_rate"]);
  });

  it("marks a definitional value with its own origin, not user or resolved", () => {
    // `definitional` is a distinct claim: not that the user said it (they
    // did not), not that it was looked up (nothing was), and not that it is
    // provisional (a different value would be a different model).
    const gaps = resolveGaps(
      "wright_fisher", "genetic drift", ["selection_coefficient"], {}, {},
    );
    expect(gaps.provenance.selection_coefficient!.origin).toBe("definitional");
  });

  it("never attaches a citation to a value it supplied", () => {
    // Nothing was looked up, so there is nothing to cite. A citation here
    // would make a supplied number indistinguishable from a resolved one.
    const gaps = resolveGaps(
      "wright_fisher", "genetic drift",
      ["selection_coefficient", "mutation_rate"], {}, {},
    );
    expect(Object.keys(gaps.provenance)).toEqual(["selection_coefficient"]);
    for (const entry of Object.values(gaps.provenance)) {
      expect(entry.citation).toBeUndefined();
    }
  });

  it("resolves neutral drift's s = 0 but still refuses its mutation rate", async () => {
    // Both halves matter. s = 0 is settled by the words "genetic drift" and
    // nothing resolves it, so it is filled. mu is searched for, so a
    // definitional zero would be a shortcut past a lookup that can succeed
    // -- and the query still refuses on it.
    //
    // This is the narrower claim that replaced "simulates neutral drift".
    // That one passed while `mutation_rate` was also definitional, which
    // `noResolverDomains.test.ts` showed was wrong.
    const gaps = resolveGaps(
      "wright_fisher", "genetic drift in a small population",
      ["selection_coefficient", "mutation_rate"], {}, {},
    );
    expect(gaps.filled.selection_coefficient).toBe(0);
    expect(gaps.stillMissing).toEqual(["mutation_rate"]);

    await expect(
      resolveQuery("genetic drift in a small population"),
    ).rejects.toBeInstanceOf(RequiredParametersMissingError);
  }, 60_000);

  it("STILL refuses measles, and this is the regression that matters", async () => {
    // Measles is not an unwired gap. It is unregistered because Guerra et
    // al. (2017) found R0 estimates vary far more than the cited 12-18
    // range and endorse no single value -- so no honest default exists.
    //
    // An earlier version of this classification gave measles a beta of 0.3
    // labelled "Caterva performs no literature lookup for beta in this
    // domain". Every clause of that was false, and it contradicted a cited
    // scientific position this codebase had already argued at length.
    await expect(
      resolveQuery("SIR model of a measles outbreak in a school"),
    ).rejects.toBeInstanceOf(RequiredParametersMissingError);
  }, 60_000);


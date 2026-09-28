/**
 * Assertions calibrated against the thirteen-domain classifier, archived
 * 2026-09-27 with the domains they measured.
 *
 * Both compare against numbers that cannot be re-derived now:
 *
 *   - "beats the classifier it replaced" checks each fixture's score against
 *     `previousCorrect`, what the PREVIOUS classifier scored on that same
 *     fixture. That classifier is gone, and roughly 70% of every fixture
 *     (54 of 78, 54 of 72, 54 of 78) asks about archived domains, so the
 *     comparison is now current-classifier-on-surviving-domains against
 *     old-classifier-on-everything. It reads as a regression -- 22 against
 *     54 -- and is not one.
 *   - the spread assertion wanted >0.15 between the best and worst fixture,
 *     and gets 0.115, because queries the tool no longer answers fail
 *     uniformly and compress the spread.
 *
 * The finding they record still stands and is worth keeping legible: this
 * classifier has no single accuracy, because who phrased the question
 * changes the number. Re-establishing that for the enzyme-and-Gillespie
 * tree needs fixtures authored against THOSE domains
 * (src/lib/generateProbeQueries.ts writes them) and a fresh baseline.
 *
 * Not collected by CI; the api-server suite is `src/**/*.test.ts`.
 */
    it("beats the classifier it replaced", () => {
      expect(score().correct).toBeGreaterThan(previousCorrect);
    });


describe("across the two fixtures", () => {
  it("shows the keyword table is sensitive to who phrased the question", () => {
    // The finding that matters more than either number: this classifier has
    // no single accuracy. Asserting the spread is real keeps a future reader
    // from quoting one figure as "the" accuracy.
    const rate = (fx: ProbeFixture) => {
      let c = 0;
      for (const q of fx.queries) {
        if (classifyDomainByKeyword(q.query).defaults.domain === q.expected) c++;
      }
      return c / fx.queries.length;
    };
    // Across every fixture, not two of them by index. The first version
    // compared FIXTURES[0] against FIXTURES[1]; adding a third fixture in
    // the middle silently changed which pair was being compared and the
    // test failed for a reason that had nothing to do with the classifier.
    const rates = FIXTURES.map((f) => rate(f.fixture));
    const spread = Math.max(...rates) - Math.min(...rates);
    expect(spread).toBeGreaterThan(0.15);
  });
});

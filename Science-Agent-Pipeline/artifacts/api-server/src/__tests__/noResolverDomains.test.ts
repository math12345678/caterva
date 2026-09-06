/**
 * "Not found" and "never looked" are different facts, and the refusal
 * message was reporting the second as the first.
 *
 * Three of Terrium's fifteen domains have a literature lookup behind any
 * parameter: enzyme kinetics (BRENDA Km/Ki, plus the kcat→Vmax bridge),
 * Wright-Fisher (mutation_rate), and SIR (the R0/infectious-period bridge).
 * The other twelve have none. Every one of them was refusing with
 *
 *     "end could not be resolved from literature and was not supplied"
 *
 * which asserts a search that never happened. The two cases call for
 * opposite actions from a researcher: "the literature has nothing" means
 * stop looking, "Terrium never looked" means the number is probably in a
 * paper you can find in a minute. Being told the first when the second is
 * true is the failure this project exists to refuse, and it was sitting in
 * the most-read sentence in the product.
 */
import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import {
  RequiredParametersMissingError,
  DOMAINS_WITH_LITERATURE_RESOLUTION,
  RESOLVABLE_FIELDS,
  EPIDEMIOLOGY_BRIDGE_DOMAINS,
} from "../lib/provenance";

describe("a domain with no resolver says so, instead of blaming the literature", () => {
  it("the repressilator now runs, because every quantity it needed was a choice", async () => {
    // CHANGED 2026-09-06. This used to assert a REFUSAL, and its own
    // comment below noted that "`end` is a choice, not a measurement".
    // Every parameter the repressilator needs is a choice -- start, end,
    // points, in dimensionless time -- so refusing over them made an
    // oscillator with no measured constants permanently unrunnable.
    //
    // The message-quality property this test existed for is preserved in
    // the test below, exercised against the error type directly rather
    // than through a query that should now succeed.
    const resolved = await resolveQuery("simulate the repressilator");
    expect(resolved.domain).toBe("repressilator");
    for (const [key, p] of Object.entries(resolved.parameterProvenance)) {
      // Nothing here may claim to have come from literature: this domain
      // resolves nothing, which was the original point.
      expect(p.origin, key).not.toBe("resolved");
    }
  }, 60000);

  it("a no-resolver domain never claims the literature was searched", async () => {
    // Nothing in this domain resolves. Elowitz & Leibler's model is cited
    // for the MODEL; its parameters are not looked up anywhere.
    //
    // Built directly rather than provoked through a query: the
    // repressilator no longer refuses (see above), and a message-quality
    // property should not depend on a query continuing to fail.
    // Empty `details` on purpose: a key with no per-key explanation is
    // "unexplained" and takes the generic sentence, which is the branch
    // under test. Passing a detail entry routes it to the per-key list and
    // the sentence never executes -- which is how a first attempt at this
    // test asserted against a message it had not produced.
    const err: Error = new RequiredParametersMissingError(
      "repressilator",
      ["end"],
      {},   // details: empty, so `end` takes the generic sentence
      {},   // resolvedSoFar
      { end: 200 },  // examples: gives the hint a real number to show
    );
    expect((err as Error).message).not.toMatch(/could not be resolved from literature/);
    expect((err as Error).message).toMatch(/no literature lookup/i);
    expect((err as Error).message).toMatch(/never searched for/i);
    // The actionable half must survive the rewrite: a user still needs to
    // be told exactly what to type. `end` is a choice, not a measurement,
    // so the hint carries a real starting number -- "Add end=<value>" is
    // useless for an oscillator in dimensionless time, where a reader
    // cannot tell whether to type 5 or 5000. See refusalExamples.test.ts
    // for why a MEASURED constant must never get the same treatment.
    expect((err as Error).message).toMatch(/Add end=\d/);
    expect((err as Error).message).toMatch(/illustrative starting points/);
    // And still be pointed at --cite, so a value they go and find in a
    // paper is recorded rather than lost.
    expect((err as Error).message).toMatch(/--cite/);
  }, 60000);

  it("still says the literature was searched where it actually was", async () => {
    // Blanket-applying the new wording would be the same defect in
    // reverse, so a domain that DOES resolve has to keep the original
    // sentence. wright_fisher resolves mutation_rate from published
    // literature, and this query leaves several genuinely-searched-for
    // keys unresolved.
    //
    // Chosen over an enzyme-kinetics query on purpose: those now fail on
    // `vmax`, which carries an unresolvedReason and is therefore routed
    // to the per-key detail list instead of the generic sentence. The
    // first version of this test used one, so the sentence under test
    // never executed and the test could not fail -- a mutation applying
    // the new wording to every domain passed it.
    const err = await resolveQuery(
      "genetic drift in a population of 250 over 100 generations",
    ).catch((e: Error) => e);
    expect(err).toBeInstanceOf(Error);
    // Asserted positively as well as negatively: a message that stopped
    // containing EITHER phrasing would otherwise pass.
    expect((err as Error).message).toMatch(/could not be resolved from literature/);
    expect((err as Error).message).not.toMatch(/never searched for/i);
  }, 120000);

  it("records the same fact in provenance, not only in the error", async () => {
    // A caller that catches the refusal and renders provenance should read
    // the same thing the sentence says, rather than a bare
    // origin:"default" with no explanation.
    //
    // `end` is supplied and `points` is not, so the query succeeds (points
    // is the one measured exemption to the hard block) and leaves exactly
    // one origin:"default" entry to inspect. Asserting through a
    // SUCCEEDING query is deliberate: the note has to survive the whole
    // resolution path, not just be present at the moment of refusal.
    const resolved = await resolveQuery("simulate the repressilator end=100");

    const defaults = Object.entries(resolved.parameterProvenance).filter(
      ([, prov]) => prov.origin === "default",
    );
    // Without this the loop below could iterate zero times and pass
    // forever -- which is exactly what the first version of this test did.
    expect(defaults.map(([key]) => key)).toEqual(["points"]);
    for (const [key, prov] of defaults) {
      expect(prov.note, key).toMatch(/no literature lookup/i);
      expect(prov.note, key).toMatch(/repressilator/);
    }
  }, 60000);
});

describe("the resolver list has exactly one definition", () => {
  it("derives the set rather than restating it", () => {
    // Two hand-maintained lists of the same fact is the defect that hit
    // enzyme names vs domain keywords, and unit tables vs src/units.ts,
    // in this same codebase. This one is computed, and this test fails if
    // someone replaces it with a literal.
    const derived = new Set([
      ...Object.keys(RESOLVABLE_FIELDS),
      ...EPIDEMIOLOGY_BRIDGE_DOMAINS,
    ]);
    expect([...DOMAINS_WITH_LITERATURE_RESOLUTION].sort()).toEqual(
      [...derived].sort(),
    );
    // A guard over an empty set would pass forever.
    expect(DOMAINS_WITH_LITERATURE_RESOLUTION.size).toBeGreaterThanOrEqual(4);
  });

  it("names the domains that really do resolve something", () => {
    // Stated explicitly so that quietly adding a domain here -- which is a
    // trust commitment, not a config change -- has to be a deliberate edit
    // to a test that says what the commitment is.
    expect([...DOMAINS_WITH_LITERATURE_RESOLUTION].sort()).toEqual([
      "mm",
      "mm_competitive_inhibition",
      "sir",
      "wright_fisher",
    ]);
  });
});

/**
 * What Caterva does about a quantity nobody resolved.
 *
 * The front door used to throw away a whole result over one gap: on twenty
 * realistic queries it answered three, and fourteen of the seventeen
 * refusals were `RequiredParametersMissingError` after the domain had
 * matched and most parameters had resolved.
 *
 * These tests pin the three-way classification that replaced it, and pin
 * hardest the two ways it could become dishonest: giving a made-up number
 * for something a real search should have found, and letting a supplied
 * value reach a response without a label.
 */

import { describe, expect, it } from "vitest";

import {
  classifyGap,
  resolveGaps,
  RequiredParametersMissingError,
} from "../lib/provenance";
import { resolveQuery } from "../lib/queryResolver";

describe("classifying one gap", () => {
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

  it("will NOT supply an enzyme concentration or a Vmax", () => {
    // Both were briefly classified `your_choice` and given labelled
    // placeholders. It broke twenty-one tests, six of them named after this
    // exact prohibition, and it was right to break them: a scenario default
    // sets the window you look through, while a fabricated Vmax scales every
    // number on the axis. ADR 0013 / ADR 0019.
    for (const key of ["enzyme_conc", "vmax"]) {
      const verdict = classifyGap("mm", key, "hexokinase", undefined, 5);
      expect(verdict.kind).toBe("literature_gap");
      expect(verdict.value).toBeUndefined();
    }
  });

  it("leaves a measured constant a literature gap", () => {
    // km describes the enzyme, not the experiment. No label makes a
    // supplied one acceptable.
    const verdict = classifyGap(
      "mm", "km", "hexokinase kinetics", "BRENDA held nothing", 6,
    );
    expect(verdict.kind).toBe("literature_gap");
    expect(verdict.value).toBeUndefined();
  });

  it("keeps the resolver's own explanation for a gap", () => {
    // "could not be resolved from literature" and "found in a rabbit and
    // withheld" are different facts; the second must survive.
    const detail = "found in another organism and withheld (ADR 0024)";
    expect(
      classifyGap("mm", "km", "q", detail, undefined).reason,
    ).toBe(detail);
  });
});

describe("resolveGaps", () => {
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

  it("refuses a measured constant even when it has an illustrative value", () => {
    // This test replaced one that asserted a `systemIdentified` flag
    // defaulted to strict. Mutation testing showed that flag was DEAD --
    // threaded through two signatures and never read -- and the test passed
    // for a different reason than it claimed. A parameter shaped like a
    // safety check that nothing consults is worse than no check, so it was
    // removed and this asserts the behaviour that actually holds: a
    // domain-table km is a starting point for a hint, never a value.
    const gaps = resolveGaps("mm", "hexokinase", ["km"], {}, { km: 6 });
    expect(gaps.stillMissing).toEqual(["km"]);
    expect(gaps.filled).toEqual({});
  });
});

describe("the end to end behaviour this changed", () => {
  it("STILL refuses the flagship query, and that is the right answer", async () => {
    // "michaelis menten kinetics for hexokinase" resolves km, s0, end and
    // points and then refuses, because Vmax = kcat x [E]0 and [E]0 is the
    // caller's. Briefly it did not refuse, and that was the mistake this
    // file now records: the message tells the reader kcat is resolved and
    // cited, that [E]0 is theirs, and exactly what to type. A curve whose
    // height means nothing would be a worse product than that sentence.
    await expect(
      resolveQuery("michaelis menten kinetics for hexokinase"),
    ).rejects.toBeInstanceOf(RequiredParametersMissingError);
  }, 60_000);

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

  it("still refuses a Km for a named enzyme it could not find", async () => {
    // The gate that separates "demonstrate the mechanism" from "tell me
    // about this enzyme". A named enzyme with no resolvable Km is a gap.
    await expect(
      resolveQuery("michaelis menten kinetics for a MAP kinase cascade"),
    ).rejects.toBeInstanceOf(RequiredParametersMissingError);
  }, 60_000);
});

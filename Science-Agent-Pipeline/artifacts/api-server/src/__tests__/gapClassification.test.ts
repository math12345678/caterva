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

  it("still refuses a Km for a named enzyme it could not find", async () => {
    // The gate that separates "demonstrate the mechanism" from "tell me
    // about this enzyme". A named enzyme with no resolvable Km is a gap.
    await expect(
      resolveQuery("michaelis menten kinetics for a MAP kinase cascade"),
    ).rejects.toBeInstanceOf(RequiredParametersMissingError);
  }, 60_000);
});

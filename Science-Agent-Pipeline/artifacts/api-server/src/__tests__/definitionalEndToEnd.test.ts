/**
 * Does the definitional value change any real answer?
 *
 * `selection_coefficient = 0` is legitimate -- neutral drift IS s = 0 -- but
 * the twenty-query harness cannot show it, because every drift query there
 * ALSO lacks a mutation rate, and mutation rates are searched for. The
 * capability is real and invisible in that measurement.
 *
 * This is the case where it shows: the caller supplies the one quantity
 * Caterva looks up, and the one it does not look up is settled by the words.
 * Without this file the mechanism would be correct, tested at unit level, and
 * unable to demonstrate that it does anything to a user.
 */

import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";

describe("the definitional value, where it changes the answer", () => {
  it("answers a drift query once the mutation rate is supplied", async () => {
    const resolved = await resolveQuery(
      "genetic drift in a population of 500 with mutation_rate=0.000001",
    );
    expect(resolved.domain).toBe("wright_fisher");
    expect(resolved.parameters.selection_coefficient).toBe(0);
    expect(resolved.parameterProvenance!.selection_coefficient!.origin).toBe(
      "definitional",
    );
    // The reader is told why, not just given a zero.
    expect(resolved.provenance.flags.join(" ")).toContain("definitional");
  }, 60_000);

  it("withdraws it when the query asks about selection", async () => {
    // The claim is about what the words mean, so contradicting words must
    // retract it rather than silently simulating s = 0 -- which would be
    // the opposite of what was asked, with no flag saying so.
    await expect(
      resolveQuery(
        "drift with a selective advantage in a population of 500 " +
          "with mutation_rate=0.000001",
      ),
    ).rejects.toThrow();
  }, 60_000);
});

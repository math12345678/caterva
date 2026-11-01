/**
 * A refusal should tell you what to type -- without telling you to type a
 * number nobody measured.
 *
 * "Add end=<value>" is useless for a repressilator, whose time is
 * dimensionless and whose sensible window is a few hundred units: a
 * reader cannot tell whether to type 5 or 5000, so the message meant to
 * unblock them does not. "Add end=200" does.
 *
 * The dangerous version of that feature suggests `km=2`. The domain
 * tables carry illustrative Km and Vmax values that the hard rule exists
 * to keep out of simulations -- domain-literature.ts calls them
 * "unverified teaching defaults chosen for legibility". Offering one in
 * an error message would walk the user into pasting it back as
 * origin:"user", laundering a fabricated number through the person the
 * rule protects, using the message written to protect them.
 *
 * So the whitelist is the test.
 */
import { describe, expect, it } from "vitest";

import { RequiredParametersMissingError } from "../lib/provenance";

const message = (
  missing: string[],
  examples: Record<string, number>,
): string =>
  new RequiredParametersMissingError("mm", missing, {}, {}, examples).message;

describe("refusal hints", () => {
  it("shows a concrete number for a parameter the user chooses", () => {
    const m = message(["end"], { end: 200 });
    expect(m).toContain("end=200");
    expect(m).toMatch(/illustrative starting points/);
  });

  it("NEVER shows a number for a measured constant", () => {
    // The whole point. km/vmax/ki/kcat are measurements; the values in
    // the domain table are teaching defaults the hard rule blocks.
    for (const key of ["km", "vmax", "ki", "kcat", "mutation_rate", "beta", "gamma"]) {
      const m = message([key], { [key]: 2 });
      expect(m, key).toContain(`${key}=<value>`);
      expect(m, key).not.toContain(`${key}=2`);
    }
  });

  it("does not call anything illustrative when nothing illustrative is shown", () => {
    // The sentence explaining the numbers must not appear when there are
    // no numbers, or it becomes a claim about `<value>`.
    const m = message(["km"], { km: 2 });
    expect(m).not.toMatch(/illustrative starting points/);
  });

  it("mixes both correctly in one message", () => {
    const m = message(["km", "end"], { km: 2, end: 10 });
    expect(m).toContain("km=<value>");
    expect(m).toContain("end=10");
    expect(m).not.toContain("km=2");
  });

  it("keeps the --cite pointer, which is what stops silent hardcoding", () => {
    const m = message(["km"], { km: 2 });
    expect(m).toContain("--cite");
  });

  it("falls back to <value> when the caller offers no example", () => {
    expect(message(["end"], {})).toContain("end=<value>");
  });

  it("does not offer an array as an example", () => {
    // starting_frequencies is a vector; "key=1,2,3" is not valid syntax
    // for the override parser, so a hint in that shape would be wrong.
    const m = new RequiredParametersMissingError(
      "two_locus_wright_fisher",
      ["starting_frequencies"],
      {},
      {},
      { starting_frequencies: [0.1, 0.2] },
    ).message;
    expect(m).toContain("starting_frequencies=<value>");
  });
});

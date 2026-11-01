/**
 * A refusal should tell you what to type -- without telling you to type a
 * number nobody measured.
 *
 * "Add end=<value>" is useless for a repressilator, whose time is
 * dimensionless and whose sensible window is a few hundred units: a
 * reader cannot tell whether to type 5 or 5000, so the message meant to
 * unblock them does not. "Add end=200" does. (Note, 2026-11-01: the
 * repressilator was archived on 2026-09-27, after v0.4.0, the last
 * release that runs it; the cases below use live keys.)
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
    for (const key of ["km", "vmax", "ki", "kcat", "k"]) {
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
    // "key=1,2,3" is not valid syntax for the override parser (a list is
    // refused with ArrayOverrideValidationError), so a hint in that shape
    // would be wrong. No live parameter is array-valued, but the examples
    // map can still carry one from LLM-supplied parameters, so the guard
    // is tested on a key that otherwise WOULD get a number: `end`.
    // (Until 2026-11-01 this case used two-locus Wright-Fisher's
    // starting_frequencies, archived on 2026-09-27, after v0.4.0, the last
    // release that runs it.)
    const m = new RequiredParametersMissingError(
      "mm",
      ["end"],
      {},
      {},
      { end: [10, 20] },
    ).message;
    expect(m).toContain("end=<value>");
    expect(m).not.toContain("end=10");
  });
});

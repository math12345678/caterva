/**
 * The organism the user names must be the organism that is looked up.
 *
 * `extractEntitiesFromQuery` never read one from the query. It used the
 * enzymes.ts table's hardcoded organism, or the literal "Homo sapiens".
 * Measured before organisms.ts existed:
 *
 *   "simulate hexokinase in E. coli with glucose ..."
 *     -> km 6 mM, organism "Homo sapiens", brenda_exact, verified
 *   "simulate hexokinase in Saccharomyces cerevisiae ..."
 *     -> the identical human value, also brenda_exact / verified
 *
 * BRENDA holds genuinely different values for those species -- 0.06 mM
 * for E. coli and 0.13 mM for yeast against 6 mM for human, a hundredfold
 * spread -- so this was a 100x error on a species-specific constant,
 * delivered silently under the product's strongest badge.
 *
 * It was worse than the case ADR 0024 exists for. A real cross-species
 * value is withheld unless opted into and arrives flagged. That never
 * fired: from its point of view the requested organism matched, because
 * the request had been rewritten to match.
 *
 * Unmocked, because the point is that the real lookup receives the real
 * organism -- a fixture would pass with the bug present.
 */
import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { matchOrganism } from "../lib/organisms";

const TAIL = "with glucose vmax=5 s0=10 end=10 points=51";

describe("matchOrganism", () => {
  it("reads the organisms a lab actually types", () => {
    expect(matchOrganism("hexokinase in E. coli")).toBe("Escherichia coli");
    expect(matchOrganism("hexokinase in E coli")).toBe("Escherichia coli");
    expect(matchOrganism("in Escherichia coli")).toBe("Escherichia coli");
    expect(matchOrganism("in yeast")).toBe("Saccharomyces cerevisiae");
    expect(matchOrganism("S. cerevisiae")).toBe("Saccharomyces cerevisiae");
    expect(matchOrganism("mouse liver")).toBe("Mus musculus");
    expect(matchOrganism("in Drosophila")).toBe("Drosophila melanogaster");
  });

  it("returns undefined when no organism is named", () => {
    // A real answer, not a failure: the caller keeps its documented
    // default rather than being handed a guess.
    expect(matchOrganism("simulate hexokinase with glucose")).toBeUndefined();
    expect(matchOrganism("model a covid-19 outbreak")).toBeUndefined();
  });

  it("does not match an organism name buried inside another word", () => {
    // The lesson PARAMETER_PATTERN learned reading "k" out of CDK1: an
    // unanchored pattern harvests substrings.
    expect(matchOrganism("treatment for colitis")).toBeUndefined();
    expect(matchOrganism("the reaction rate is high")).toBeUndefined();
    expect(matchOrganism("temperature 25 C")).toBeUndefined();
  });
});

describe("the named organism reaches the literature lookup", () => {
  it("looks up E. coli when the query says E. coli", async () => {
    const resolved = await resolveQuery(`simulate hexokinase in E. coli ${TAIL}`);
    const km = resolved.parameterProvenance["km"]!;
    expect(km.organism).toBe("Escherichia coli");
    expect(km.origin).toBe("resolved");
  }, 180000);

  it("gives a different answer for a different organism", async () => {
    // The assertion that makes the one above meaningful. If the organism
    // were still discarded, both would return the same human number --
    // which is exactly what happened before.
    const coli = await resolveQuery(`simulate hexokinase in E. coli ${TAIL}`);
    const yeast = await resolveQuery(`simulate hexokinase in yeast ${TAIL}`);

    expect(yeast.parameterProvenance["km"]!.organism).toBe(
      "Saccharomyces cerevisiae",
    );
    expect(coli.parameters["km"]).not.toBe(yeast.parameters["km"]);
  }, 300000);

  it("leaves the documented default alone when no organism is named", async () => {
    // The fix reads what the query says; it does not start guessing when
    // the query says nothing.
    const resolved = await resolveQuery(`simulate hexokinase ${TAIL}`);
    expect(resolved.parameterProvenance["km"]!.organism).toBe("Homo sapiens");
  }, 180000);
});

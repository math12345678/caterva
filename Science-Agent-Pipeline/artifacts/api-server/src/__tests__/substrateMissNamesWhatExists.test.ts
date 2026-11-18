/**
 * The miss a student actually hits, and what they are told about it.
 *
 * THE MEASUREMENT
 * ---------------
 * Through the real resolver, on the LDH fixture:
 *
 *     substrate="lactate"    -> found, 10.73
 *     substrate="L-lactate"  -> found=false, source="not_found"
 *
 * Both name the same compound. BRENDA's label is `(S)-lactate`: "lactate"
 * matches as a substring, "L-lactate" does not. The message the student got
 * was "Could not resolve a real KM value from BRENDA/KEGG/PubMed" — which
 * reads as "the literature has nothing", and is false.
 *
 * `cross_species_withheld` and `variant_withheld` already name what they
 * refused, for exactly this reason. Substrates were the field left out, and
 * they are the field a reader is most likely to get wrong: an organism has
 * one binomial name, a metabolite has a dozen aliases.
 */

import { describe, expect, it } from "vitest";

import { buildUnresolvedKineticProvenanceForTest as build } from "../lib/queryResolver";

const LDH_SUBSTRATES = ["(S)-lactate", "NAD+", "oxamate", "pyruvate"];

describe("a substrate miss names what the enzyme does report", () => {
  it("names the label that would have worked", () => {
    const provenance = build("km", "not_found", undefined, undefined, LDH_SUBSTRATES);
    expect(provenance.note).toContain("(S)-lactate");
    expect(provenance.note).toContain("oxamate");
  });

  it("does not claim the literature is empty", () => {
    // The old message. It is the reason a student stops here.
    const provenance = build("km", "not_found", undefined, undefined, LDH_SUBSTRATES);
    expect(provenance.note).not.toContain("Could not resolve a real KM value");
  });

  it("refuses to substitute, and says why in chemical terms", () => {
    // Not "we could not find it" — the reason a near-miss is not taken is
    // that a similar name can be a different molecule. A student who
    // understands that will not ask the tool to guess.
    const provenance = build("km", "not_found", undefined, undefined, LDH_SUBSTRATES);
    expect(provenance.note).toMatch(/salt, a stereoisomer or an ester/);
    expect(provenance.note).toContain("does not substitute");
  });

  it("falls back to the plain message when there is nothing to suggest", () => {
    // An enzyme BRENDA genuinely has no table for. Naming an empty list
    // would be worse than the old message, not better.
    const provenance = build("km", "not_found", undefined, undefined, []);
    expect(provenance.note).toContain("Could not resolve a real KM value");
    expect(provenance.note).not.toContain("this enzyme reports");
  });

  it("still tells an organism refusal apart from a substrate one", () => {
    // These must not converge. "Your organism has no value" and "your
    // substrate name matched nothing" send a reader to different fixes,
    // and a message that covered both would send them to neither.
    const organism = build("km", "cross_species_withheld", ["Sus scrofa"]);
    expect(organism.note).toContain("allowCrossSpecies");
    expect(organism.note).not.toContain("stereoisomer");

    const substrate = build("km", "not_found", undefined, undefined, LDH_SUBSTRATES);
    expect(substrate.note).not.toContain("allowCrossSpecies");
  });

  it("names the inhibitor for a Ki, and never calls it a substrate", () => {
    // "acetylcholinesterase inhibited by donepezil in human": the Ki miss
    // said "No KI was found for the substrate you named", although the
    // user named an inhibitor and no substrate (adversarial round,
    // 2026-11-11).
    const ki = build("ki", "not_found", undefined, undefined, ["huperzine A", "tacrine"],
      undefined, undefined, undefined, { name: "donepezil", named: true });
    expect(ki.note).toContain("No KI was found for donepezil, the inhibitor you named");
    expect(ki.note).toContain("values for these inhibitors: huperzine A, tacrine");
    expect(ki.note).not.toContain("substrate");
  });

  it("does not say 'you named' of a name Caterva chose", () => {
    const km = build("km", "not_found", undefined, undefined, LDH_SUBSTRATES,
      undefined, undefined, undefined, { name: "pyruvate", named: false });
    expect(km.note).toContain("No KM was found for pyruvate, the substrate Caterva chose");
    expect(km.note).not.toContain("you named");
  });
});

/**
 * Reading quantities the user stated in words.
 *
 * The false-positive tests below matter more than the happy paths. A missed
 * extraction is visible -- the existing refusal path names what is missing
 * and how to supply it. A WRONG extraction is invisible: it produces a
 * plausible trajectory for a question nobody asked, stamped origin "user"
 * as though the user had chosen it. So "does not extract" is asserted at
 * least as carefully as "extracts".
 */
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";
import {
  extractStatedQuantities,
  CONCENTRATION_TO_MM,
  TIME_IN_SECONDS,
} from "../lib/statedQuantities";
import { REPO_ROOT } from "../lib/catervaRunner";

const find = (
  query: string,
  domain: Parameters<typeof extractStatedQuantities>[1],
  key: string,
) => extractStatedQuantities(query, domain).find((q) => q.key === key);

describe("extractStatedQuantities — what the user actually said", () => {




  // ---- units: getting these wrong is silent, plausible, wrong science ---

  it("converts concentrations into mM, the canonical unit", () => {
    // BRENDA normalises Km to mM, so s0 must be mM or the two sides of the
    // same equation disagree by orders of magnitude.
    expect(find("hexokinase with 10 mM glucose", "mm", "s0")?.value).toBe(10);
    expect(find("hexokinase with 10 uM glucose", "mm", "s0")?.value).toBeCloseTo(0.01, 12);
    expect(find("hexokinase with 250 nM glucose", "mm", "s0")?.value).toBeCloseTo(2.5e-4, 12);
    expect(find("hexokinase with 2 M glucose", "mm", "s0")?.value).toBe(2000);
  });


  it("extracts no time for a domain whose time unit is not established", () => {
    // Guessing would be worse than refusing. gillespie_ssa is absent from
    // DOMAIN_TIME_UNIT on purpose: its time is in the rate constant's units.
    expect(find("run for 30 days", "gillespie_ssa", "end")).toBeUndefined();
  });




  // ---- the part that matters most --------------------------------------

  it("does not harvest numbers out of names", () => {
    // "CDK1" contains 1. EC 1.1.1.27 is four numbers. An unanchored regex
    // would bind them; PARAMETER_PATTERN in queryResolver.ts learned this
    // exact lesson when it read "k" out of CDK1 and ERK2.
    for (const q of [
      "cdk1 and erk2 kinetics",
      "simulate lactate dehydrogenase 1.1.1.27",
      "hexokinase 2 in yeast",
    ]) {
      expect(extractStatedQuantities(q, "mm")).toEqual([]);
    }
  });

  it("does not bind a bare number with no anchoring noun or unit", () => {
    // "10000" alone could be anything. Extracting nothing is the safe
    // outcome; the refusal path then asks for it by name.
    expect(extractStatedQuantities("hexokinase with 10", "mm")).toEqual([]);
  });


  // ---- enzyme vs substrate: two concentrations, five orders apart ------

  it("reads the enzyme concentration as [E]0, not as the substrate", () => {
    // The bug this replaces: the FIRST concentration in the sentence was
    // bound to s0 unconditionally, so this query resolved s0 = 0.00005 mM
    // -- the enzyme's concentration, presented as glucose's, stamped
    // origin "user". A 200,000x error that simulates a flat, entirely
    // plausible curve.
    const q = "hexokinase with 50 nM enzyme and 10 mM glucose over 30 seconds";
    expect(find(q, "mm", "enzyme_conc")?.value).toBeCloseTo(5e-5, 15);
    expect(find(q, "mm", "s0")?.value).toBe(10);
  });

  it("reads [E]0 whichever side of the number the enzyme noun sits on", () => {
    // "50 nM enzyme" and "enzyme at 50 nM" are the same statement.
    for (const q of [
      "hexokinase with 50 nM enzyme, glucose at 10 mM",
      "hexokinase with enzyme at 50 nM, glucose at 10 mM",
      "hexokinase at 50 nM with 10 mM glucose",
      "hexokinase, [E]0 = 50 nM, 10 mM glucose",
    ]) {
      expect(find(q, "mm", "enzyme_conc")?.value, q).toBeCloseTo(5e-5, 15);
      expect(find(q, "mm", "s0")?.value, q).toBe(10);
    }
  });

  it("names the noun in the source phrase, so a mix-up is visible", () => {
    // "s0 = 10 because you wrote '10 mM'" cannot be checked by a reader.
    // "because you wrote '10 mM glucose'" can.
    const q = "hexokinase with 50 nM enzyme and 10 mM glucose";
    expect(find(q, "mm", "s0")?.sourcePhrase).toMatch(/glucose/i);
    expect(find(q, "mm", "enzyme_conc")?.sourcePhrase).toMatch(/enzyme/i);
  });

  it("picks the enzyme's primary substrate when several are named", () => {
    // Hexokinase phosphorylates glucose using ATP. Michaelis-Menten models
    // saturation in ONE substrate, and enzymes.ts lists glucose first for
    // exactly that reason -- so position in the sentence must not decide.
    const q = "hexokinase with 1 mM ATP and 10 mM glucose";
    expect(find(q, "mm", "s0")?.value).toBe(10);
  });

  it("refuses rather than guessing between two unlabelled concentrations", () => {
    // Neither number is attached to a noun that says which is which.
    // Extracting nothing hands this to the refusal path, which asks for s0
    // by name -- a visible question instead of a silent coin-flip.
    expect(find("michaelis menten with 10 mM and 2 mM", "mm", "s0")).toBeUndefined();
  });

  it("still reads a lone unlabelled concentration as the substrate", () => {
    // Nothing else it could be, and this is the common phrasing.
    expect(
      find("how fast does hexokinase convert glucose at 10 mM", "mm", "s0")?.value,
    ).toBe(10);
  });

  it("does not invent an enzyme concentration from an ordinary mention", () => {
    // "enzyme kinetics at 10 mM" is a substrate concentration in a
    // sentence that happens to contain the word "enzyme".
    const q = "enzyme kinetics for hexokinase at 10 mM glucose";
    expect(find(q, "mm", "enzyme_conc")).toBeUndefined();
    expect(find(q, "mm", "s0")?.value).toBe(10);
  });

  it("does not apply epidemiology nouns to unrelated domains", () => {
    // "people" means nothing to enzyme kinetics.
    expect(find("hexokinase with 500 people", "mm", "s0")).toBeUndefined();
  });

  it("returns nothing for a query that states no quantities", () => {
    expect(
      extractStatedQuantities("simulate lactate dehydrogenase with pyruvate", "mm"),
    ).toEqual([]);
  });

});

/**
 * The api-server cannot import src/units.ts -- separate package, and its
 * tsconfig is rootDir/include "src", so the repo-root tree is outside its
 * compilation. So the conversion factors are duplicated, and this guard is
 * what stops that duplication being silent.
 *
 * This repo has been bitten by exactly this before: KM_PLAUSIBLE_MAX_MM
 * differed between the literature layer and the engine, so a value flagged
 * implausible upstream arrived "confirmed" downstream. It was fixed by
 * pinning the two equal with a regression test. Same remedy here.
 *
 * Reads the file as TEXT rather than importing it, because the import is
 * the thing that isn't available.
 */
describe("unit factors must not drift from src/units.ts", () => {
  const unitsSrc = readFileSync(
    path.join(REPO_ROOT, "src", "units.ts"),
    "utf-8",
  );

  /** Pull `['key', value]` pairs out of a named Map literal. */
  function parseMap(name: string): Record<string, number> {
    const start = unitsSrc.indexOf(name);
    expect(start, `${name} not found in src/units.ts`).toBeGreaterThan(-1);
    const body = unitsSrc.slice(start, unitsSrc.indexOf("]);", start));
    const out: Record<string, number> = {};
    for (const m of body.matchAll(/\[\s*'([^']+)'\s*,\s*([0-9.e+-]+)\s*\]/g)) {
      out[m[1]!] = Number.parseFloat(m[2]!);
    }
    return out;
  }

  it("agrees with CONCENTRATION_TO_MOLAR on every shared unit", () => {
    const molar = parseMap("CONCENTRATION_TO_MOLAR");
    expect(Object.keys(molar).length).toBeGreaterThan(3);

    // Different bases: src/units.ts converts to MOLAR, this file to mM.
    // So compare ratios -- 1 M is 1000 mM.
    for (const [unit, toMm] of Object.entries(CONCENTRATION_TO_MM)) {
      const toMolar = molar[unit];
      if (toMolar === undefined) continue; // µ/μ spellings src/ lacks
      expect(
        toMm,
        `'${unit}' disagrees between statedQuantities.ts and src/units.ts`,
      ).toBeCloseTo(toMolar * 1000, 12);
    }
  });

  it("agrees with TIME_TO_SECONDS on every shared unit", () => {
    const seconds = parseMap("TIME_TO_SECONDS");
    expect(Object.keys(seconds).length).toBeGreaterThan(3);

    let compared = 0;
    for (const [unit, secs] of Object.entries(TIME_IN_SECONDS)) {
      const theirs = seconds[unit];
      if (theirs === undefined) continue; // day/week: src/ has no entry
      expect(
        secs,
        `'${unit}' disagrees between statedQuantities.ts and src/units.ts`,
      ).toBe(theirs);
      compared++;
    }
    // A guard that compared nothing would pass forever.
    expect(compared).toBeGreaterThan(3);
  });
});

describe("the hard block stays hard except where measured otherwise", () => {
  it("blocks measured constants and permits chosen ones", async () => {
    const { unverifiedOriginKeys } = await import("../lib/provenance");
    // WIDENED DELIBERATELY, 2026-09-06. This test previously required that
    // ONLY `points` be exempt, warning that "an exemption that widened
    // would silently reintroduce the fabrication the block exists to
    // prevent". The warning is right about measurements and was applied to
    // a list its own comment describes as "chosen OR measured" -- the two
    // categories treated identically.
    //
    // The cost was measured: of twenty queries a lab would type, TWO ran.
    // "michaelis menten for hexokinase" was refused because it could not
    // resolve `s0` and `end` from literature -- a starting concentration
    // and a plot window, for which no literature value exists or ever
    // will. ADR 0044, quoted in provenance.ts, already says a pre-filled
    // experimental condition is a UI convenience and a pre-filled
    // measurement is a fabrication.
    //
    // So the split is by CATEGORY now, not by a single key. km and vmax
    // still block, which is the fabrication this test exists to prevent.
    const blocked = unverifiedOriginKeys({
      points: { origin: "default" },
      s0: { origin: "default" },
      end: { origin: "default" },
      i0: { origin: "default" },
      r0_recovered: { origin: "default" },
      km: { origin: "default" },
      vmax: { origin: "llm" },
    });
    // Chosen: a documented default is allowed.
    for (const chosen of ["points", "s0", "end", "i0", "r0_recovered"]) {
      expect(blocked, `${chosen} is a choice, not a measurement`).not.toContain(
        chosen,
      );
    }
    // Measured: still blocked, and that is the product.
    expect(blocked.sort()).toEqual(["km", "vmax"]);
  });

  it("still blocks the one experimental choice that would fabricate a measurement", async () => {
    const { unverifiedOriginKeys } = await import("../lib/provenance");
    // enzyme_conc IS a choice, and is deliberately not defaultable:
    // Vmax = kcat x [E]0, so a defaulted [E]0 manufactures a Vmax and
    // prints it beside a real literature kcat (ADR 0013). It is the
    // exception that shows the rule is about consequences, not categories.
    expect(unverifiedOriginKeys({ enzyme_conc: { origin: "default" } })).toEqual(
      ["enzyme_conc"],
    );
  });

  it("still blocks a model-invented value for a key whose default is allowed", async () => {
    const { unverifiedOriginKeys } = await import("../lib/provenance");
    // A default is a documented value in this repository, the same for
    // everyone and auditable. A number a model produced is not a default.
    expect(unverifiedOriginKeys({ s0: { origin: "llm" } })).toEqual(["s0"]);
    expect(unverifiedOriginKeys({ end: { origin: "llm" } })).toEqual(["end"]);
  });

  it("leaves a user-supplied points alone", async () => {
    const { unverifiedOriginKeys } = await import("../lib/provenance");
    // The exemption is about not BLOCKING a defaulted points, not about
    // ignoring the key. An origin "user" points was never blocked anyway,
    // and must not start being treated as absent.
    expect(unverifiedOriginKeys({ points: { origin: "user" } })).toEqual([]);
  });
});

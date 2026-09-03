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
import { REPO_ROOT } from "../lib/teriumRunner";

const find = (
  query: string,
  domain: Parameters<typeof extractStatedQuantities>[1],
  key: string,
) => extractStatedQuantities(query, domain).find((q) => q.key === key);

describe("extractStatedQuantities — what the user actually said", () => {
  it("reads a population as a TOTAL and derives the susceptible count", () => {
    // The measured failure that motivated this: the population was in the
    // sentence and the API demanded s0 back as a CLI flag.
    const q = "model a covid-19 outbreak in a town of 10000 people with 5 infected";
    expect(find(q, "sir", "i0")?.value).toBe(5);
    // s0 is SUSCEPTIBLE and N = s0 + i0 + r0, so a town of 10000 with 5
    // already infected has 9995 susceptible. Binding 10000 would simulate a
    // town of 10005 -- not the town described.
    expect(find(q, "sir", "s0")?.value).toBe(9995);
  });

  it("handles a population with no stated infected count", () => {
    const q = "covid-19 outbreak in a population of 500";
    expect(find(q, "sir", "s0")?.value).toBe(500);
    expect(find(q, "sir", "i0")).toBeUndefined();
  });

  it("reads the bare '<n> people' phrasing too", () => {
    expect(find("covid outbreak, 2000 people", "sir", "s0")?.value).toBe(2000);
  });

  it("carries the source phrase so a misreading is auditable", () => {
    const hit = find("outbreak in a town of 10000 people", "sir", "s0");
    // Without this, a wrong binding is only discoverable from the
    // trajectory. With it, provenance can say WHY s0 has this value.
    expect(hit?.sourcePhrase).toMatch(/town of 10000/i);
  });

  // ---- units: getting these wrong is silent, plausible, wrong science ---

  it("converts concentrations into mM, the canonical unit", () => {
    // BRENDA normalises Km to mM, so s0 must be mM or the two sides of the
    // same equation disagree by orders of magnitude.
    expect(find("hexokinase with 10 mM glucose", "mm", "s0")?.value).toBe(10);
    expect(find("hexokinase with 10 uM glucose", "mm", "s0")?.value).toBeCloseTo(0.01, 12);
    expect(find("hexokinase with 250 nM glucose", "mm", "s0")?.value).toBeCloseTo(2.5e-4, 12);
    expect(find("hexokinase with 2 M glucose", "mm", "s0")?.value).toBe(2000);
  });

  it("reads time in the DOMAIN's own unit, which differs between families", () => {
    // Epidemiology is in days (gamma = 1/infectious_period_days).
    expect(find("covid outbreak over 30 days", "sir", "end")?.value).toBe(30);
    expect(find("covid outbreak for 2 weeks", "sir", "end")?.value).toBe(14);

    // Enzyme kinetics is in seconds (Vmax is mM/s). The same words mean a
    // very different number here, and reading "30 days" as 30 would
    // simulate half a minute of a month-long assay.
    expect(find("hexokinase assay for 30 seconds", "mm", "end")?.value).toBe(30);
    expect(find("hexokinase assay for 5 minutes", "mm", "end")?.value).toBe(300);
    expect(find("hexokinase assay over 30 days", "mm", "end")?.value).toBe(2_592_000);
  });

  it("extracts no time for a domain whose time unit is not established", () => {
    // Guessing would be worse than refusing. molecular_dynamics is absent
    // from DOMAIN_TIME_UNIT on purpose.
    expect(find("run for 30 days", "molecular_dynamics", "end")).toBeUndefined();
  });

  it("reads PCR cycles", () => {
    expect(find("amplify DNA over 35 cycles", "pcr", "cycles")?.value).toBe(35);
  });

  it("reads generations for popgen, which counts steps rather than time", () => {
    const got = extractStatedQuantities(
      "genetic drift in a population of 250 over 100 generations",
      "wright_fisher",
    );
    expect(got.find((q) => q.key === "generations")?.value).toBe(100);
    expect(got.find((q) => q.key === "population_size")?.value).toBe(250);
    // Generations are discrete steps, not a duration -- "100 generations"
    // must not also become an `end` in days or seconds.
    expect(got.find((q) => q.key === "end")).toBeUndefined();
  });

  it("maps a population to population_size for popgen, not s0", () => {
    const got = extractStatedQuantities(
      "genetic drift in a population of 250",
      "wright_fisher",
    );
    expect(got.find((q) => q.key === "population_size")?.value).toBe(250);
    expect(got.find((q) => q.key === "s0")).toBeUndefined();
  });

  // ---- the part that matters most --------------------------------------

  it("does not harvest numbers out of names", () => {
    // "COVID-19" contains 19. "SARS-CoV-2" contains 2. An unanchored regex
    // would bind them; PARAMETER_PATTERN in queryResolver.ts learned this
    // exact lesson when it read "k" out of CDK1 and ERK2.
    for (const q of [
      "model a covid-19 outbreak",
      "sars-cov-2 transmission",
      "simulate lactate dehydrogenase 1.1.1.27",
    ]) {
      const got = extractStatedQuantities(q, "sir");
      expect(got.filter((g) => g.key === "s0" || g.key === "i0")).toEqual([]);
    }
  });

  it("does not bind a bare number with no anchoring noun or unit", () => {
    // "10000" alone could be anything. Extracting nothing is the safe
    // outcome; the refusal path then asks for it by name.
    expect(extractStatedQuantities("outbreak with 10000", "sir")).toEqual([]);
    expect(extractStatedQuantities("hexokinase with 10", "mm")).toEqual([]);
  });

  it("does not extract a population smaller than the stated infected count", () => {
    // Would yield a non-positive susceptible count. Forcing that into shape
    // would fail engine validation with a confusing message; leaving it to
    // the refusal path is honest.
    const got = extractStatedQuantities(
      "outbreak in a town of 3 people with 10 infected",
      "sir",
    );
    expect(got.find((q) => q.key === "s0")).toBeUndefined();
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

  it("does not claim recovered=0 when the query mentions recovered or immune people", () => {
    // Deriving r0_recovered=0 is a READING of "a town of N with M
    // infected" -- everyone is accounted for and nobody was described as
    // recovered. The moment a query does mention them, that reading is no
    // longer available and guessing would be inventing.
    for (const q of [
      "outbreak in a town of 10000 people with 5 infected and 200 recovered",
      "town of 10000 people, 5 infected, 300 already immune",
      "town of 10000 people with 5 infected, 40% vaccinated",
    ]) {
      const got = extractStatedQuantities(q, "sir");
      expect(got.find((x) => x.key === "r0_recovered")).toBeUndefined();
    }
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
  it("exempts only points, and still blocks every scientific parameter", async () => {
    const { unverifiedOriginKeys } = await import("../lib/provenance");
    // points is display resolution and provably does not move the result.
    // Everything else here is chosen or measured and must still block --
    // an exemption that widened would silently reintroduce the fabrication
    // the block exists to prevent.
    const blocked = unverifiedOriginKeys({
      points: { origin: "default" },
      s0: { origin: "default" },
      end: { origin: "default" },
      i0: { origin: "default" },
      r0_recovered: { origin: "default" },
      km: { origin: "default" },
      vmax: { origin: "llm" },
    });
    expect(blocked).not.toContain("points");
    expect(blocked.sort()).toEqual(
      ["end", "i0", "km", "r0_recovered", "s0", "vmax"].sort(),
    );
  });

  it("leaves a user-supplied points alone", async () => {
    const { unverifiedOriginKeys } = await import("../lib/provenance");
    // The exemption is about not BLOCKING a defaulted points, not about
    // ignoring the key. An origin "user" points was never blocked anyway,
    // and must not start being treated as absent.
    expect(unverifiedOriginKeys({ points: { origin: "user" } })).toEqual([]);
  });
});

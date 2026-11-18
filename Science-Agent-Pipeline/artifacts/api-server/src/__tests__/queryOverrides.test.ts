import { describe, expect, it, vi } from "vitest";

import {
  extractParameterOverrides,
  ArrayOverrideValidationError,
  resolveQuery,
} from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";
import { UnrecognizedQueryError } from "../lib/provenance";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({ found: false })),
  };
});

// ─── Unit tests: extractParameterOverrides ────────────────────────────────

describe("extractParameterOverrides", () => {
  describe("scalar overrides (existing behavior)", () => {
    it("extracts a single scalar from key=value", () => {
      const result = extractParameterOverrides("km=5");
      expect(result).toEqual({ km: 5 });
    });

    it("extracts space-separated key value ('km 5'), correcting a real product bug", () => {
      // This test used to assert the OPPOSITE and named it "no
      // delimiter" as if that were the rule -- it wasn't a rule, it was
      // a gap the function's own docstring and its own "Fallback"
      // comment both said should already work, giving "km 5" as the
      // worked example. `query.split(/\s+/)` yields "km" and "5" as two
      // separate tokens, and no single-token regex can see across that
      // space; the extraction loop had to look at the PAIR, which it now
      // does.
      //
      // This was not a hypothetical: every homepage example on the
      // landing page's own "Try the agent" panel used this exact
      // space-separated form ("enzyme kinetics km 5 vmax 10", "model an
      // outbreak with beta 0.4 and gamma 0.1"), and every one of them
      // 422'd, reporting km/vmax/beta/gamma as "could not be resolved"
      // when the user had typed them plainly. Measured live against the
      // running app before this fix.
      const result = extractParameterOverrides("km 5");
      expect(result).toEqual({ km: 5 });
    });

    it("does not pair a bare parameter name with a non-numeric neighbor", () => {
      // The other direction of the same fix. "km" followed by a word
      // that is not a number must not be treated as an override --
      // otherwise ordinary prose containing a parameter name ("the km
      // reading was inconclusive") could silently inject a value from
      // an adjacent number that has nothing to do with it.
      const result = extractParameterOverrides("km unknown 5");
      expect(result).toEqual({});
    });

    it("extracts a single scalar from key:value (no space)", () => {
      const result = extractParameterOverrides("km:5");
      expect(result).toEqual({ km: 5 });
    });

    it("extracts multiple scalars", () => {
      const result = extractParameterOverrides("km=2 vmax=10 s0=100");
      expect(result).toEqual({ km: 2, vmax: 10, s0: 100 });
    });

    it("handles decimal values", () => {
      expect(extractParameterOverrides("s0=0.3")).toEqual({ s0: 0.3 });
    });

    it("handles scientific notation", () => {
      expect(extractParameterOverrides("k=1.5e-3")).toEqual({ k: 1.5e-3 });
    });

    it("ignores non-parameter tokens", () => {
      expect(
        extractParameterOverrides("simulate enzyme kinetics km=5"),
      ).toEqual({ km: 5 });
    });

    it("returns empty object for no matches", () => {
      expect(extractParameterOverrides("simulate enzyme kinetics")).toEqual({});
    });

    it("ignores invalid numbers", () => {
      expect(extractParameterOverrides("km=abc vmax=5")).toEqual({ vmax: 5 });
    });
  });

  describe("a list where one number belongs", () => {
    // No live parameter is array-valued. starting_frequencies was, for
    // two-locus Wright-Fisher, and went with that domain into the
    // 2026-09-27 archive (after v0.4.0, the last release that runs it).
    // A list is still refused loudly rather than truncated to its first
    // element: "km=1,2" read as km=1 would run on half of what the user
    // typed and call it their choice.
    it.each(["km=1,2", "s0=[10]", "vmax=5, 6"])("rejects %j", (q) => {
      expect(() => extractParameterOverrides(q)).toThrow(
        ArrayOverrideValidationError,
      );
      expect(() => extractParameterOverrides(q)).toThrow(/single number/);
    });
  });

  describe("archived-domain parameter names are not overrides", () => {
    // Until 2026-11-01 PARAMETER_NAMES also held the keys of the domains
    // archived on 2026-09-27, after v0.4.0 (the last release that runs
    // them). They are now ordinary unrecognised tokens: extracted as
    // nothing, so they cannot reach the engine, and a malformed value for
    // one (a list that does not sum to 1, a scalar where a vector was
    // expected) no longer raises a validation error that reads as though
    // the domain still ran.
    it.each([
      "beta=0.3",
      "gamma:0.1",
      "sigma 0.2",
      "r0_recovered=0",
      "population_size=200",
      "generations=30",
      "mutation_rate=1.29e-8",
      "recombination_rate=0.05",
      "starting_frequency=0.5",
      "starting_frequencies=0.5,0,0,0.4",
      "starting_frequencies=[0.5,0,0,0.5]",
      "n_particles=64 temperature=1.0 timestep=0.005",
      "cycles=30 efficiency=0.9",
    ])("%j yields no override", (q) => {
      expect(extractParameterOverrides(q)).toEqual({});
    });

    it("keeps the live keys beside an archived one", () => {
      expect(
        extractParameterOverrides("km=2 beta=0.3 vmax=5 population_size=100"),
      ).toEqual({ km: 2, vmax: 5 });
    });
  });

  describe("edge cases", () => {
    it("case-insensitive parameter names", () => {
      expect(extractParameterOverrides("KM=0.5 Vmax=5")).toEqual({
        km: 0.5,
        vmax: 5,
      });
    });
  });
});

// ─── Integration: an archived parameter in an archived-domain question ───
//
// extractParameterOverrides runs before domain classification. While
// starting_frequencies was still a recognised array key, this exact query
// was answered with ArrayOverrideValidationError ("values must sum to 1")
// -- a request to fix the haplotype frequencies of a domain that no longer
// runs. It now reaches classification and gets the archive refusal.

describe("resolveQuery — archived domain with archived key=value parameters", () => {
  it("refuses with the archive date and v0.4.0, not a parameter error", async () => {
    const err = await resolveQuery(
      "linkage disequilibrium two locus wright fisher population_size=200 " +
        "generations=30 recombination_rate=0.1 starting_frequencies=0.5,0,0,0.4 " +
        "mutation_rate=0.001 replicate_runs=100",
    ).catch((e: unknown) => e);
    expect(err).not.toBeInstanceOf(ArrayOverrideValidationError);
    expect(err).toBeInstanceOf(UnrecognizedQueryError);
    const message = String((err as Error).message);
    expect(message).toContain("archived on 2026-09-27");
    expect(message).toContain("v0.4.0");
  });

  it("an archived key on a live-domain query is ignored, not run", async () => {
    // beta is not a parameter of Michaelis-Menten and is no longer an
    // override at all: the run carries exactly the mm parameters.
    const resolved = await resolveQuery(
      "simulate enzyme kinetics km=0.5 vmax=5 s0=10 end=10 points=51 beta=0.3",
    );
    expect(resolved.domain).toBe("mm");
    expect(resolved.parameters).not.toHaveProperty("beta");
    expect(resolved.parameterProvenance).not.toHaveProperty("beta");
    expect(resolved.parameters["km"]).toBe(0.5);
  });
});

// ─── Regression: existing mm golden query ──────────────────────────────────
//
// An existing mm query must not regress. This also proves that scalar
// override behaviour and RESOLVABLE_FIELDS / provenance validation are
// untouched by the removal of the archived keys and the array parser.
//
// Bare "simulate lactate dehydrogenase" resolves km from BRENDA (via the
// mocked science agent) but vmax/s0/end/points are not literature-resolvable
// and not supplied, so the hard-block rule throws RequiredParametersMissingError.

const GOLDEN_LDH_RESULT = {
  found: true,
  km: 10.73,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "740253",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  literatureCandidates: [],
  logs: ["Looked up Km for lactate dehydrogenase (1.1.1.27)"],
};

const MM_EC_OVERRIDES = "vmax=5 s0=10 end=10 points=51";

describe("resolveQuery — mm golden regression", () => {
  // Test 5: mm + LDH with teaching defaults resolves km=10.73 from BRENDA
  it("mm + LDH resolves km=10.73 from BRENDA", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(GOLDEN_LDH_RESULT);
    const result = await resolveQuery(
      `simulate lactate dehydrogenase ${MM_EC_OVERRIDES}`,
    );
    expect(result.domain).toBe("mm");
    expect(result.parameters["km"]).toBe(10.73);
    const km = result.parameterProvenance["km"]!;
    expect(km.origin).toBe("resolved");
    expect(km.citation).toContain("(ref 740253)");
  });

  // Test 6: mm + user override km=1.5 → origin 'user'
  it("mm + user override km=1.5 → origin 'user'", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(GOLDEN_LDH_RESULT);
    const result = await resolveQuery(
      `simulate lactate dehydrogenase km=1.5 ${MM_EC_OVERRIDES}`,
    );
    expect(result.parameters["km"]).toBe(1.5);
    expect(result.parameterProvenance["km"]!.origin).toBe("user");
  });
});
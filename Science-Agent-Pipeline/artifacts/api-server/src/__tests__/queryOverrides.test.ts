import { describe, expect, it, vi } from "vitest";

import {
  extractParameterOverrides,
  ArrayOverrideValidationError,
} from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";

// ─── Unit tests: extractParameterOverrides ────────────────────────────────

describe("extractParameterOverrides", () => {
  describe("scalar overrides (existing behavior)", () => {
    it("extracts a single scalar from key=value", () => {
      const result = extractParameterOverrides("km=5");
      expect(result).toEqual({ km: 5 });
    });

    it("does not extract space-separated key value (no delimiter)", () => {
      const result = extractParameterOverrides("km 5");
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
      expect(extractParameterOverrides("beta=0.3")).toEqual({ beta: 0.3 });
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

  describe("array overrides (new behavior)", () => {
    it("extracts a comma-separated array from key=value", () => {
      expect(
        extractParameterOverrides("starting_frequencies=0.5,0,0,0.5"),
      ).toEqual({ starting_frequencies: [0.5, 0, 0, 0.5] });
    });

    it("extracts a bracket-enclosed array from key=value", () => {
      expect(
        extractParameterOverrides("starting_frequencies=[0.5,0,0,0.5]"),
      ).toEqual({ starting_frequencies: [0.5, 0, 0, 0.5] });
    });

    it("extracts array with key:value syntax (no space)", () => {
      expect(
        extractParameterOverrides("starting_frequencies:0.5,0,0,0.5"),
      ).toEqual({ starting_frequencies: [0.5, 0, 0, 0.5] });
    });

    it("handles scientific notation elements", () => {
      expect(
        extractParameterOverrides("starting_frequencies=1e-1,2e-1,3e-1,4e-1"),
      ).toEqual({ starting_frequencies: [0.1, 0.2, 0.3, 0.4] });
    });

    it("rejects array with wrong length", () => {
      expect(() =>
        extractParameterOverrides("starting_frequencies=0.5,0,0"),
      ).toThrow(ArrayOverrideValidationError);
    });

    it("rejects array that doesn't sum to 1", () => {
      expect(() =>
        extractParameterOverrides("starting_frequencies=0.5,0,0,0.4"),
      ).toThrow(ArrayOverrideValidationError);
    });

    it("rejects array with non-numeric elements", () => {
      // Non-numeric elements cause parseArrayValue to return undefined,
      // so the override is silently skipped (no error thrown at parse time).
      // The parameter will then be origin: "default", triggering the hard-block.
      const result = extractParameterOverrides(
        "starting_frequencies=0.5,abc,0,0.5",
      );
      expect(result).toEqual({});
    });

    it("rejects bracket-enclosed array with spaces (token gets split)", () => {
      const result = extractParameterOverrides(
        "starting_frequencies=[0.5, 0, 0, 0.5]",
      );
      expect(result).toEqual({});
    });
  });

  describe("mixed scalar and array overrides", () => {
    it("extracts both from the same query", () => {
      expect(
        extractParameterOverrides(
          "starting_frequencies=0.8,0,0,0.2 recombination_rate=0.05 population_size=200",
        ),
      ).toEqual({
        starting_frequencies: [0.8, 0, 0, 0.2],
        recombination_rate: 0.05,
        population_size: 200,
      });
    });

    it("does not confuse scalar for part of array", () => {
      expect(extractParameterOverrides("starting_frequency=0.5")).toEqual({
        starting_frequency: 0.5,
      });
    });
  });

  describe("edge cases", () => {
    it("case-insensitive parameter names", () => {
      expect(
        extractParameterOverrides("Starting_Frequencies=0.5,0,0,0.5"),
      ).toEqual({ starting_frequencies: [0.5, 0, 0, 0.5] });
    });
  });
});

// ─── Integration tests: resolveQuery with two_locus_wright_fisher ─────────

// Import resolveQuery for the integration tests. The deterministic path is
// used (no LLM configured), so we mock the science agent to avoid network.
import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<
    typeof import("../lib/scienceAgent")
  >();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({ found: false })),
  };
});

// All overrides required for two_locus_wright_fisher (no literature-resolvable
// fields exist for this domain, so every parameter must be user-supplied).
const TWO_LOCUS_OVERRIDES =
  "population_size=200 generations=30 recombination_rate=0.1 starting_frequencies=0.5,0,0,0.5 mutation_rate=0.001 replicate_runs=100";

describe("resolveQuery — two_locus_wright_fisher array overrides", () => {
  // Test 1: Full success — all required overrides supplied
  it("test 1: succeeds end-to-end with all overrides", async () => {
    const result = await resolveQuery(
      `linkage disequilibrium two locus ${TWO_LOCUS_OVERRIDES}`,
    );
    expect(result.domain).toBe("two_locus_wright_fisher");
    expect(result.parameters.starting_frequencies).toEqual([
      0.5, 0, 0, 0.5,
    ]);
    // starting_frequencies must be origin: "user"
    expect(result.parameterProvenance["starting_frequencies"]!.origin).toBe(
      "user",
    );
    // No parameters should be origin: "default" (hard-block)
    for (const [key, prov] of Object.entries(result.parameterProvenance)) {
      expect(prov.origin).not.toBe("default");
    }
  });

  // Test 2: Sum ≠ 1 → rejected
  it("test 2: rejects sum≠1 with clear error", async () => {
    await expect(
      resolveQuery(
        `linkage disequilibrium two locus population_size=200 generations=30 recombination_rate=0.1 starting_frequencies=0.5,0,0,0.4 mutation_rate=0.001 replicate_runs=100`,
      ),
    ).rejects.toThrow(ArrayOverrideValidationError);
    await expect(
      resolveQuery(
        `linkage disequilibrium two locus population_size=200 generations=30 recombination_rate=0.1 starting_frequencies=0.5,0,0,0.4 mutation_rate=0.001 replicate_runs=100`,
      ),
    ).rejects.toThrow(/must sum to 1/);
  });

  // Test 3: Only 3 values → rejected
  it("test 3: rejects wrong length with clear error", async () => {
    await expect(
      resolveQuery(
        `linkage disequilibrium two locus population_size=200 generations=30 recombination_rate=0.1 starting_frequencies=0.5,0,0 mutation_rate=0.001 replicate_runs=100`,
      ),
    ).rejects.toThrow(ArrayOverrideValidationError);
    await expect(
      resolveQuery(
        `linkage disequilibrium two locus population_size=200 generations=30 recombination_rate=0.1 starting_frequencies=0.5,0,0 mutation_rate=0.001 replicate_runs=100`,
      ),
    ).rejects.toThrow(/exactly 4 values/);
  });

  // Test 4: Absent starting_frequencies → RequiredParametersMissingError
  it("test 4: absent starting_frequencies triggers RequiredParametersMissingError", async () => {
    await expect(
      resolveQuery(
        "linkage disequilibrium two locus population_size=200 generations=30 recombination_rate=0.1 mutation_rate=0.001 replicate_runs=100",
      ),
    ).rejects.toThrow(RequiredParametersMissingError);
    try {
      await resolveQuery(
        "linkage disequilibrium two locus population_size=200 generations=30 recombination_rate=0.1 mutation_rate=0.001 replicate_runs=100",
      );
    } catch (e) {
      expect(e).toBeInstanceOf(RequiredParametersMissingError);
      expect((e as RequiredParametersMissingError).missing).toContain(
        "starting_frequencies",
      );
    }
  });
});

// ─── Regression: existing mm golden query ──────────────────────────────────

// Test 5: An existing mm query must not regress. This also proves that
// scalar override behaviour and RESOLVABLE_FIELDS / provenance validation
// are untouched by the array-override changes.
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

describe("resolveQuery — mm golden regression (test 5)", () => {
  it("mm + LDH resolves km=10.73 from BRENDA", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(GOLDEN_LDH_RESULT);
    const result = await resolveQuery("simulate lactate dehydrogenase");
    expect(result.domain).toBe("mm");
    expect(result.parameters["km"]).toBe(10.73);
    const km = result.parameterProvenance["km"]!;
    expect(km.origin).toBe("resolved");
    expect(km.citation).toContain("(ref 740253)");
    // km must be resolved from literature (not default)
    expect(result.parameterProvenance["km"]!.origin).toBe("resolved");
    // Teaching defaults (vmax, s0, end, points) are legitimately origin: "default"
    // — they are deliberately chosen by the project, not silently invented.
  });

  it("mm + user override km=1.5 → origin 'user'", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(GOLDEN_LDH_RESULT);
    const result = await resolveQuery(
      "simulate lactate dehydrogenase km=1.5",
    );
    expect(result.parameters["km"]).toBe(1.5);
    expect(result.parameterProvenance["km"]!.origin).toBe("user");
  });
});

import { describe, expect, it } from "vitest";

import { resolveQuery, ArrayOverrideValidationError } from "../lib/queryResolver";
import {
  RequiredParametersMissingError,
} from "../lib/provenance";

/**
 * Test cases for array-valued query-string overrides (starting_frequencies).
 * These verify the extractParameterOverrides() array parsing and validation.
 *
 * Verification target (this is parsing/plumbing, not physics -- there is no
 * closed form; the verification target is a table of exact input/output
 * pairs, each one a real test):
 *   1. `starting_frequencies=0.5,0,0,0.5` plus the domain's other required
 *      overrides -> resolveQuery() succeeds end-to-end. This exact case has
 *      never once succeeded before; making it succeed IS the deliverable.
 *   2. `starting_frequencies=0.5,0,0,0.4` (sums to 0.9) -> rejected.
 *   3. `starting_frequencies=0.5,0,0` (only 3 values) -> rejected.
 *   4. `starting_frequencies` absent -> RequiredParametersMissingError names
 *      it among the missing keys (regression pin for existing behavior).
 *   5. Scalar overrides are not regressed -- the mm golden query lives in
 *      provenance.test.ts (Target A/D) and runs unchanged.
 */
describe("array-valued parameter overrides", () => {
  // Test 1: Valid starting_frequencies override with all other required overrides
  it("two_locus_wright_fisher with valid starting_frequencies and all required overrides succeeds", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5,0,0,0.5";

    const resolved = await resolveQuery(query);
    expect(resolved.domain).toBe("two_locus_wright_fisher");
    expect(resolved.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    const prov = resolved.parameterProvenance.starting_frequencies!;
    expect(prov.origin).toBe("user");
  });

  // Test 2: starting_frequencies sums to 0.9 (not 1) -> rejected
  it("rejects starting_frequencies that sum to 0.9", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5,0,0,0.4";

    await expect(resolveQuery(query)).rejects.toMatchObject({
      name: "ArrayOverrideValidationError",
      key: "starting_frequencies",
    });
    try {
      await resolveQuery(query);
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ArrayOverrideValidationError);
      expect((err as ArrayOverrideValidationError).message).toMatch(/sum to 1/);
    }
  });

  // Test 3: starting_frequencies with only 3 values -> rejected
  it("rejects starting_frequencies with only 3 values", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5,0,0";

    await expect(resolveQuery(query)).rejects.toMatchObject({
      name: "ArrayOverrideValidationError",
      key: "starting_frequencies",
    });
    try {
      await resolveQuery(query);
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ArrayOverrideValidationError);
      expect((err as ArrayOverrideValidationError).message).toMatch(
        /exactly 4 values/,
      );
    }
  });

  // Test 4: No starting_frequencies override -> RequiredParametersMissingError names it
  it("throws RequiredParametersMissingError naming starting_frequencies when absent", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50";

    await expect(resolveQuery(query)).rejects.toMatchObject({
      name: "RequiredParametersMissingError",
      domain: "two_locus_wright_fisher",
    });
    try {
      await resolveQuery(query);
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(RequiredParametersMissingError);
      const missing = (err as RequiredParametersMissingError).missing;
      expect(missing).toContain("starting_frequencies");
    }
  });

  // Additional: Test with spaces after commas
  it("accepts starting_frequencies with spaces after commas", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5, 0, 0, 0.5";

    const resolved = await resolveQuery(query);
    expect(resolved.parameters.starting_frequencies).toEqual([0.5, 0, 0, 0.5]);
    const prov = resolved.parameterProvenance.starting_frequencies!;
    expect(prov.origin).toBe("user");
  });

  // Additional: Test non-numeric values rejected
  it("rejects starting_frequencies with non-numeric values", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5,foo,0,0.5";

    await expect(resolveQuery(query)).rejects.toMatchObject({
      name: "ArrayOverrideValidationError",
      key: "starting_frequencies",
    });
  });

  // Additional: Test NaN values rejected (finite check)
  it("rejects starting_frequencies with NaN", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5,NaN,0,0.5";

    await expect(resolveQuery(query)).rejects.toMatchObject({
      name: "ArrayOverrideValidationError",
      key: "starting_frequencies",
    });
  });

  // Additional: a comma list on a scalar-only parameter is rejected, not
  // silently coerced into an array (the generic ARRAY_VALUED_KEYS gate).
  it("rejects a comma list on a scalar-only parameter", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100,200 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5,0,0,0.5";

    await expect(resolveQuery(query)).rejects.toMatchObject({
      name: "ArrayOverrideValidationError",
      key: "population_size",
    });
  });

  // Additional: a single scalar value for an array parameter is present but
  // malformed (1 value where 4 are required) and must be rejected with
  // actionable guidance, not reported as "not supplied".
  it("rejects a single scalar value for an array parameter", async () => {
    const query =
      "linkage disequilibrium two locus " +
      "population_size=100 generations=20 recombination_rate=0.1 " +
      "mutation_rate=0 replicate_runs=50 " +
      "starting_frequencies=0.5";

    await expect(resolveQuery(query)).rejects.toMatchObject({
      name: "ArrayOverrideValidationError",
      key: "starting_frequencies",
    });
    try {
      await resolveQuery(query);
      expect.unreachable();
    } catch (err) {
      expect(err).toBeInstanceOf(ArrayOverrideValidationError);
      expect((err as ArrayOverrideValidationError).message).toMatch(
        /comma-separated list/,
      );
    }
  });
});

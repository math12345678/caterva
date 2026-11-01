import { describe, expect, it } from "vitest";

import { RunSimulationBody } from "@workspace/api-zod";

/**
 * `physiologicalReference` over HTTP.
 *
 * The zod schema is the part that matters and the part most likely to be
 * silently wrong: zod strips unknown keys by default, so a field present in
 * `openapi.yaml`, present in the TypeScript types, and absent from the
 * generated schema would compile, type-check, and then vanish between the
 * client and the resolver with no error anywhere. The caller would state
 * their modelled conditions, get back `conditionProximity: not_assessed`,
 * and have no way to tell they had been ignored.
 *
 * That is the same failure ADR 0027 was written about — an input that looks
 * supplied and never arrives — so it gets a test at the boundary rather than
 * trust in a code generator.
 */

const VALID = {
  ph: 7.4,
  temperatureC: 37,
  basis: "human blood plasma, stated by the caller",
  phTolerance: 0.3,
  temperatureToleranceC: 5,
};

const QUERY = "simulate michaelis menten of lactate dehydrogenase";

describe("the request schema accepts a physiological reference", () => {
  it("keeps the field instead of stripping it", () => {
    const parsed = RunSimulationBody.parse({
      query: QUERY,
      physiologicalReference: VALID,
    });
    expect(parsed.physiologicalReference).toEqual(VALID);
  });

  it("keeps the tolerances", () => {
    // The half most likely to be lost to a partial schema. Losing them is
    // not a smaller version of the same bug: the runner refuses a reference
    // missing any of the five fields, so a reference stripped of its
    // tolerances is silently equivalent to no reference at all.
    const parsed = RunSimulationBody.parse({
      query: QUERY,
      physiologicalReference: VALID,
    });
    expect(parsed.physiologicalReference?.phTolerance).toBe(0.3);
    expect(parsed.physiologicalReference?.temperatureToleranceC).toBe(5);
    expect(parsed.physiologicalReference?.basis).toBe(VALID.basis);
  });

  it("stays optional — omitting it is the normal case", () => {
    const parsed = RunSimulationBody.parse({ query: QUERY });
    expect(parsed.physiologicalReference).toBeUndefined();
  });
});

describe("a partial reference is refused at the boundary", () => {
  // The runner already refuses one, returning `not_assessed`. Refusing at
  // the edge instead turns a silently-ignored input into a 400 that says
  // which field is missing — the difference between a user learning their
  // request was incomplete and a user believing it was honoured.
  it.each([
    ["ph", { ...VALID, ph: undefined }],
    ["temperatureC", { ...VALID, temperatureC: undefined }],
    ["basis", { ...VALID, basis: undefined }],
    ["phTolerance", { ...VALID, phTolerance: undefined }],
    ["temperatureToleranceC", { ...VALID, temperatureToleranceC: undefined }],
  ])("rejects a reference missing %s", (_field, reference) => {
    const result = RunSimulationBody.safeParse({
      query: QUERY,
      physiologicalReference: reference,
    });
    expect(result.success).toBe(false);
  });

  it("rejects a non-numeric pH rather than coercing it", () => {
    // "7.4" is not 7.4. Coercion here would let a string reach the runner's
    // float() and either throw far from the cause or, worse, succeed.
    const result = RunSimulationBody.safeParse({
      query: QUERY,
      physiologicalReference: { ...VALID, ph: "7.4" },
    });
    expect(result.success).toBe(false);
  });
});

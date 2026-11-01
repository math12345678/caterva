/**
 * Regression: PARAMETER_PATTERN must not mint overrides out of ordinary words.
 *
 * The pattern was unanchored, so a parameter name occurring ANYWHERE inside a
 * whitespace-delimited token was harvested as a user-supplied value. Protein
 * names are `<letters><digit>`, and `k` is a parameter name, so:
 *
 *     "...decay of CDK1 ..."  ->  { k: 1 }
 *     "...decay of ERK2 ..."  ->  { k: 2 }
 *     "simulate backend2 ..." ->  { end: 2 }
 *
 * Those were stamped `origin: "user"`, so unverifiedOriginKeys() saw nothing
 * to block and the engine ran with a rate constant read off a protein's NAME.
 * It defeated the hard rule (ADR 0008) and changed the scientific answer
 * silently instead of failing loudly.
 */
import { describe, expect, it } from "vitest";
import { extractParameterOverrides } from "../lib/queryResolver";

describe("parameter overrides are never laundered out of ordinary words", () => {
  it.each([
    ["gillespie stochastic decay of CDK1 a0=100 end=10 seed=1", "k"],
    ["gillespie stochastic decay of ERK2 a0=100 end=10 seed=1", "k"],
    ["simulate MAPK3 signalling a0=10", "k"],
    ["simulate backend2 gillespie a0=10", "end"],
    ["simulate p53 dynamics a0=10", "p"],
  ])("%s does not mint %s", (query, leaked) => {
    expect(extractParameterOverrides(query)).not.toHaveProperty(leaked);
  });

  it("a protein name never determines a rate constant", () => {
    // The two queries differ ONLY in the protein name. If the name leaks into
    // the parameters, they produce different physics.
    const a = extractParameterOverrides("gillespie decay of CDK1 a0=100 end=10");
    const b = extractParameterOverrides("gillespie decay of ERK2 a0=100 end=10");
    expect(a).toEqual(b);
  });

  it("still extracts genuine explicit overrides", () => {
    expect(extractParameterOverrides("simulate mm km=2 vmax=5 s0=10")).toEqual({
      km: 2,
      vmax: 5,
      s0: 10,
    });
  });

  it("still extracts colon and scientific notation forms", () => {
    expect(
      extractParameterOverrides("wright fisher mutation_rate=1.29e-8 k:3"),
    ).toMatchObject({ mutation_rate: 1.29e-8, k: 3 });
  });
});

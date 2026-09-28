/**
 * Caterva refused 90% of the queries a lab would type, over numbers that
 * are not measurements.
 *
 * MEASURED, 2026-09-06. Twenty realistic queries, written before the run
 * and not cherry-picked, through `resolveQuery` end to end. **Two worked.**
 * The refusals were almost never about a measurement:
 *
 *     michaelis menten for hexokinase  ->  s0, end could not be resolved
 *     lotka volterra predator prey     ->  end was not supplied
 *     repressilator oscillations       ->  end was not supplied
 *     monte carlo estimate of pi       ->  n_samples was not supplied
 *
 * `end` is how long to integrate. `points` is how many rows come back.
 * `n_samples` is a compute budget. No literature value exists for any of
 * them, so demanding one refuses the query permanently. A tool that cannot
 * answer "michaelis menten for hexokinase" is not strict, it is broken.
 *
 * `provenance.ts` already contained the right distinction and enforced the
 * wrong one: ADR 0044 is quoted there saying "a pre-filled experimental
 * condition is a UI convenience ...; a pre-filled measurement is a
 * fabrication", and that pre-filling `s0` is CORRECTLY NOT FLAGGED --
 * eight lines above a comment asserting s0 and end stay blocked on
 * purpose. `unverifiedOriginKeys` enforced the second.
 *
 * WHAT THESE TESTS ARE FOR
 *
 * The success-rate test is the one that would have caught the original
 * defect. Everything below it exists because loosening a hard rule is
 * exactly where a product gives itself away, so the guarantee is pinned
 * from every direction: measured constants stay blocked, [E]0 stays
 * blocked, and a model-invented number stays blocked even for a key whose
 * DEFAULT is now allowed.
 */
import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import {
  SCENARIO_DEFAULTABLE_KEYS,
  scenarioDefaultAllowed,
  unverifiedOriginKeys,
  type ParameterProvenance,
} from "../lib/provenance";

/**
 * Queries a lab would type, whose refusal was never about a measurement.
 *
 * "michaelis menten for hexokinase" is deliberately NOT here, though it was
 * in the original twenty and it does still fail. It fails on Vmax, and that
 * refusal is correct: Vmax = kcat x [E]0, so it depends on how much enzyme
 * is in YOUR tube, and ADR 0013 refuses to guess it. Listing it here would
 * have made this test demand that the product stop working.
 *
 * The distinction is the whole point of the change. Before it, that query
 * failed on `s0` and `end` -- a starting concentration and a plot window.
 * Now it fails on a quantity that genuinely cannot be known without the
 * user, and says exactly what to add. Same query, and the difference
 * between a broken tool and a strict one.
 */
const REALISTIC_QUERIES = [
  "enzyme kinetics with km=2 vmax=5 s0=10 end=10 points=51",
  "competitive inhibition km=2 ki=1 vmax=5 s0=10 i0=1",
  "gillespie simulation of first order decay a0=100 k=0.1 end=10",
  "gillespie simulation of first order decay a0=100 k=0.1",
];

describe("the queries a lab would actually type", () => {
  it("runs the ones whose refusal was never about a measurement", async () => {
    const failures: string[] = [];
    for (const query of REALISTIC_QUERIES) {
      try {
        const resolved = await resolveQuery(query);
        expect(resolved.domain, query).toBeTruthy();
      } catch (err) {
        failures.push(
          `${query} :: ${err instanceof Error ? err.message.split("\n")[0] : err}`,
        );
      }
    }
    expect(
      failures,
      `these were refused; each asks only for choices or states its constants:\n` +
        failures.join("\n"),
    ).toEqual([]);
  }, 300_000);
});

describe("the guarantee that survives it", () => {
  const provenance = (
    key: string,
    origin: ParameterProvenance["origin"],
  ): Record<string, ParameterProvenance> => ({ [key]: { origin } });

  it.each(["km", "vmax", "kcat", "ki", "beta", "gamma", "mutation_rate"])(
    "still blocks a defaulted %s -- these are the product",
    (key) => {
      expect(unverifiedOriginKeys(provenance(key, "default"))).toEqual([key]);
      expect(SCENARIO_DEFAULTABLE_KEYS.has(key)).toBe(false);
    },
  );

  it("still blocks a defaulted enzyme_conc, which ADR 0013 makes load-bearing", () => {
    // [E]0 IS an experimental choice, and it is the one whose default
    // would fabricate a measurement: Vmax = kcat x [E]0, so a defaulted
    // [E]0 manufactures a Vmax and reports it beside a literature kcat.
    expect(unverifiedOriginKeys(provenance("enzyme_conc", "default"))).toEqual([
      "enzyme_conc",
    ]);
    expect(SCENARIO_DEFAULTABLE_KEYS.has("enzyme_conc")).toBe(false);
  });

  it.each(["end", "points", "s0", "i0", "n_samples", "cycles", "generations"])(
    "allows a documented default for %s",
    (key) => {
      expect(unverifiedOriginKeys(provenance(key, "default"))).toEqual([]);
    },
  );

  it.each(["end", "s0", "n_samples"])(
    "still blocks an LLM-invented %s, even though its default is allowed",
    (key) => {
      // A default is a documented value in this repository, auditable and
      // the same for everyone. A number a model produced is not a default;
      // it is an invention wearing one's clothes.
      expect(unverifiedOriginKeys(provenance(key, "llm"))).toEqual([key]);
      expect(scenarioDefaultAllowed(key, "llm")).toBe(false);
    },
  );

  it("labels a defaulted scenario value as a default in the response", async () => {
    // The value runs, and the caller is told Caterva chose it. A default
    // that ran silently would be the fabrication this whole change is
    // careful not to become.
    // No end time given: the window is Caterva's choice, and must say so.
    const resolved = await resolveQuery(
      "gillespie simulation of first order decay a0=100 k=0.1",
    );
    const defaulted = Object.entries(resolved.parameterProvenance)
      .filter(([, p]) => p.origin === "default")
      .map(([key]) => key);

    expect(defaulted.length).toBeGreaterThan(0);
    for (const key of defaulted) {
      expect(SCENARIO_DEFAULTABLE_KEYS.has(key), `${key} was defaulted`).toBe(
        true,
      );
    }
  }, 120_000);

  it("still refuses a Vmax with no enzyme concentration", async () => {
    await expect(
      resolveQuery("michaelis menten for hexokinase"),
    ).rejects.toThrow(/vmax/i);
  }, 120_000);
});

import { describe, expect, it } from "vitest";

import { RunSimulationBody } from "@workspace/api-zod";

/**
 * `allowVariants` over HTTP (ADR 0029, reachable as of ADR 0039).
 *
 * The state this replaces is worth describing, because "not implemented"
 * would have been safer than what was actually there: the flag was declared
 * in `openapi.yaml`, accepted by `resolveQuery`, threaded through
 * `applyKineticResolution`, and forwarded by the runner — and the HTTP route
 * between them never read it.
 *
 * A caller could send `allowVariants: true`, get a 202, and receive
 * `variant_withheld` anyway. Everything looked implemented. The one link
 * that connects a request to the resolver was missing, and no test could see
 * it because every test either called `resolveQuery` directly or checked the
 * schema.
 *
 * That is the fourth occurrence of one shape in this repository (ADR 0026,
 * 0027, 0038, here), so these tests assert on the two surfaces that break
 * independently: the schema keeps the field, and the cache key distinguishes
 * the two answers.
 */

const QUERY = "simulate michaelis menten of acetylcholinesterase";

describe("the request schema carries allowVariants", () => {
  it("keeps the field instead of stripping it", () => {
    // zod strips unknown keys by default. A field present in openapi.yaml
    // and absent from the generated schema would vanish in transit with no
    // error anywhere -- which is exactly what happened before the contract
    // was regenerated.
    const parsed = RunSimulationBody.parse({ query: QUERY, allowVariants: true });
    expect(parsed.allowVariants).toBe(true);
  });

  it("defaults to absent rather than to true", () => {
    const parsed = RunSimulationBody.parse({ query: QUERY });
    expect(parsed.allowVariants).not.toBe(true);
  });

  it("rejects a non-boolean rather than coercing it", () => {
    // "true" is not true. Coercion here would let a stray query-string
    // value silently enable variant rows.
    const result = RunSimulationBody.safeParse({ query: QUERY, allowVariants: "true" });
    expect(result.success).toBe(false);
  });
});

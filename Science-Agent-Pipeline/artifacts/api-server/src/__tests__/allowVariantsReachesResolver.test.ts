import { describe, expect, it, vi, beforeEach } from "vitest";
import request from "supertest";

import * as queryResolver from "../lib/queryResolver";

/**
 * Does `allowVariants: true` in an HTTP body actually reach `resolveQuery`?
 *
 * This test exists because the mutation that severs the link was NOT caught
 * by anything else. `cacheKey.test.ts` calls `normalizeQuery` directly;
 * `allowVariantsRoute.test.ts` checks the schema. Replacing
 *
 *     const allowVariants = parse.data.allowVariants === true;
 * with
 *     const allowVariants = false;
 *
 * left both of them passing. The flag would be accepted, validated, put in
 * the cache key — and never acted on.
 *
 * That is the fifth time this repository has hit one shape (ADR 0026, 0027,
 * 0038, 0039's cache key, here): **a test that constructs its own input
 * cannot verify how the input is produced.** The only cure is to exercise
 * the real entry point, which is what this does.
 *
 * It asserts on the CALL rather than the response, because the response is
 * identical either way: a job id, 202, and the difference appears much later
 * inside a subprocess.
 */

vi.mock("../lib/queryResolver", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/queryResolver")>();
  return {
    ...original,
    resolveQuery: vi.fn(async () => {
      // Enough shape for runPipeline to get past resolution; it will fail
      // later, which is fine -- the assertion is on what resolveQuery was
      // handed, and that happens first.
      throw new Error("stopped after resolution: this test asserts on the call");
    }),
  };
});

const QUERY = "simulate michaelis menten of acetylcholinesterase";

async function post(body: Record<string, unknown>) {
  const { default: app } = await import("../app");
  const res = await request(app).post("/api/simulate").send(body);
  // The pipeline runs asynchronously; give the mocked resolver a tick.
  await new Promise((r) => setTimeout(r, 50));
  return res;
}

function lastOptions() {
  const calls = vi.mocked(queryResolver.resolveQuery).mock.calls;
  return calls.at(-1)?.[1];
}

describe("allowVariants reaches the resolver", () => {
  beforeEach(() => {
    vi.mocked(queryResolver.resolveQuery).mockClear();
  });

  it("forwards true when the request says true", async () => {
    await post({ query: QUERY, allowVariants: true });
    expect(lastOptions()?.allowVariants).toBe(true);
  });

  it("forwards false when the request omits it", async () => {
    // Absent must not read as permission. This is the assertion that would
    // fail if someone made the flag default-on to "fix" a missing value.
    await post({ query: `${QUERY} without the flag` });
    expect(lastOptions()?.allowVariants).not.toBe(true);
  });

  it("does not confuse it with allowCrossSpecies", async () => {
    // Two independent opt-ins. Neither may stand in for the other, and a
    // route that assigned one from the other would satisfy every test
    // above.
    await post({ query: `${QUERY} species only`, allowCrossSpecies: true });
    expect(lastOptions()?.allowCrossSpecies).toBe(true);
    expect(lastOptions()?.allowVariants).not.toBe(true);
  });
});

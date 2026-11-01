/**
 * Reading a user's own words must not depend on whether an LLM key is set.
 *
 * `resolveQuery` has two paths. The keyword fallback runs when no LLM is
 * configured; the LLM path runs when one is. Prose quantity extraction
 * landed in the fallback only, so the entire natural-language capability
 * switched off the moment a lab set ANTHROPIC_API_KEY -- the same question
 * worked on one deployment and failed on another, for a reason no user
 * could see from the outside.
 *
 * Worse than merely absent: the LLM path built provenance from the
 * key=value overrides alone, so a number the user had plainly written in
 * their sentence could only reach `parameters` as the LLM's own guess at
 * it -- origin "llm", which ADR 0011 hard-blocks. The system would refuse
 * a query for containing model output, when the user had stated the value
 * themselves.
 *
 * These tests drive the LLM path directly by mocking the resolver, so they
 * fail if the extraction is ever wired into one path and not the other.
 */
import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveQueryWithLLM } from "../lib/llmResolver";

vi.mock("../lib/llmResolver", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/llmResolver")>();
  return { ...original, resolveQueryWithLLM: vi.fn() };
});

// beta/gamma are supplied explicitly so the epidemiology bridge short-
// circuits and these tests make no network call. What is under test is
// the reading of s0/i0/end out of the sentence, not the R0 lookup.
const QUERY =
  "model a covid-19 outbreak in a town of 10000 people with 5 infected " +
  "over 60 days beta=0.5 gamma=0.2";

const llmSays = (parameters: Record<string, number>) => {
  vi.mocked(resolveQueryWithLLM).mockResolvedValue({
    domain: "sir",
    parameters,
    reasoning: "test",
    modelCitations: [],
  });
};

describe("stated quantities on the LLM path", () => {
  it("reads the sentence, and marks what it read as the user's", async () => {
    llmSays({});
    const resolved = await resolveQuery(QUERY);

    // s0 is SUSCEPTIBLE and N = s0 + i0 + r0_recovered, so a town of 10000
    // with 5 infected has 9995 susceptible.
    expect(resolved.parameters["s0"]).toBe(9995);
    expect(resolved.parameters["i0"]).toBe(5);
    expect(resolved.parameters["end"]).toBe(60);

    for (const key of ["s0", "i0", "end"]) {
      expect(resolved.parameterProvenance[key]!.origin, key).toBe("user");
    }
    // And the words that produced it, so a misreading is catchable on the
    // page rather than only in the trajectory.
    expect(resolved.parameterProvenance["s0"]!.note).toMatch(/town of 10000/i);
  });

  it("prefers what the user wrote over what the model guessed", async () => {
    // The LLM claims a population of 42. The user's sentence says 10000.
    // Model output is origin "llm" and hard-blocked; the user's own words
    // are not. Letting the model's number win would both discard the
    // user's statement AND make the query unrunnable.
    llmSays({ s0: 42, i0: 7 });
    const resolved = await resolveQuery(QUERY);

    expect(resolved.parameters["s0"]).toBe(9995);
    expect(resolved.parameters["i0"]).toBe(5);
    expect(resolved.parameterProvenance["s0"]!.origin).toBe("user");
    expect(resolved.parameterProvenance["i0"]!.origin).toBe("user");
  });

  it("still lets an explicit key=value correct the prose", async () => {
    // Someone who writes s0=500 after describing a town of 10000 is
    // correcting themselves; the more precise statement is the one they
    // meant. Same precedence as the fallback path.
    llmSays({});
    const resolved = await resolveQuery(`${QUERY} s0=500`);
    expect(resolved.parameters["s0"]).toBe(500);
    expect(resolved.parameterProvenance["s0"]!.origin).toBe("user");
    // The key=value did not come from prose, so it carries no source
    // phrase -- claiming one would be a fabricated audit trail.
    expect(resolved.parameterProvenance["s0"]!.note).toBeUndefined();
  });

  it("leaves the model's own numbers labelled llm when prose says nothing", async () => {
    // The point is not to relabel LLM output as user input. A parameter
    // the user never stated stays origin "llm" and stays blocked.
    llmSays({ s0: 9995, i0: 5, end: 60, r0_recovered: 0 });
    await expect(
      resolveQuery("model an outbreak beta=0.5 gamma=0.2"),
    ).rejects.toThrow(/could not be resolved|unresolved/i);
  });
});

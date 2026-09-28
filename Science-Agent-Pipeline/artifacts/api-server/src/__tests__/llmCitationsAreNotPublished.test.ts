/**
 * A citation the model wrote is not a citation.
 *
 * `SYSTEM_PROMPT` in llmResolver.ts asks the language model for
 *
 *     "modelCitations": ["optional literature reference"]
 *
 * and whatever it returned was spread straight into
 * `provenance.modelCitations`, alongside the curated domain citation, in
 * the same array of the same shape. That array is served to callers by
 * /api/simulate and /api/enzymes. A reader had no way to tell which entry
 * a human had checked and which one a model had produced from nothing.
 *
 * This is the defect auditIntegrity.test.ts already named for the easy
 * case -- the "Domain: <name>" placeholder was "a label shipped to the
 * client inside the list of citations backing a scientific result" -- with
 * a better disguise. A placeholder is obviously not a citation. An
 * invented reference looks exactly like a real one, which is the whole
 * problem: this repository has already found five DOIs that resolved to
 * the wrong paper or to nothing, every one of them plausible on sight.
 *
 * It is also the rule `provenance.ts` already applies to VALUES: an `llm`
 * origin is blocked unless a resolvable citation backs it. There is no
 * reason a citation should be trusted on terms a number is not.
 *
 * So the model's citations are discarded, and the response says so in
 * `flags` rather than dropping them silently.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveQueryWithLLM } from "../lib/llmResolver";

vi.mock("../lib/llmResolver", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/llmResolver")>();
  return { ...original, resolveQueryWithLLM: vi.fn() };
});

// beta/gamma supplied so the epidemiology bridge short-circuits: no
// network, and what is under test is the citation handling.
const QUERY =
  "michaelis menten kinetics with km=0.5 vmax=2 s0=10";

/** A reference that does not exist, in the shape a model would invent. */
const FABRICATED =
  "Hartley, J. & Vance, R. (2019). Transmission dynamics of respiratory " +
  "pathogens in small populations. Journal of Epidemic Modelling 12(3), " +
  "441-459. doi:10.1016/j.jem.2019.03.007";

const llmReturns = (modelCitations: string[]) => {
  vi.mocked(resolveQueryWithLLM).mockResolvedValue({
    domain: "mm",
    parameters: {},
    reasoning: "test",
    modelCitations,
  });
};

beforeEach(() => {
  vi.mocked(resolveQueryWithLLM).mockReset();
});

describe("model-authored citations never reach the caller", () => {
  it("does not publish a reference the model invented", async () => {
    llmReturns([FABRICATED]);
    const resolved = await resolveQuery(QUERY);

    // Premise: the LLM path was taken, so this is not passing by never
    // having run the code under test.
    expect(vi.mocked(resolveQueryWithLLM)).toHaveBeenCalled();

    const published = JSON.stringify(resolved.provenance.modelCitations);
    expect(published).not.toContain("Hartley");
    expect(published).not.toContain("Journal of Epidemic Modelling");
    expect(published).not.toContain("10.1016/j.jem.2019.03.007");
  }, 60000);

  it("still publishes the curated domain citation", async () => {
    // The fix must not be "return no citations". The Michaelis-Menten entry
    // is real, checked, and the thing a reader is entitled to.
    llmReturns([FABRICATED]);
    const resolved = await resolveQuery(QUERY);

    expect(resolved.provenance.modelCitations.length).toBe(1);
    expect(resolved.provenance.modelCitations[0]).toMatch(/Michaelis/);
  }, 60000);

  it("says that it discarded something, rather than dropping it silently", async () => {
    llmReturns([FABRICATED, "Another invented paper (2021)"]);
    const resolved = await resolveQuery(QUERY);

    const flag = resolved.provenance.flags.find((f) =>
      f.startsWith("discarded_unverified_model_citation"),
    );
    expect(
      flag,
      "the model offered citations and the response says nothing about it",
    ).toBeDefined();
    expect(flag).toContain("2 reference");
  }, 60000);

  it("adds no flag when the model offered nothing", async () => {
    // A flag on every response would be noise, and would stop meaning
    // anything on the responses where it matters.
    llmReturns([]);
    const resolved = await resolveQuery(QUERY);

    expect(
      resolved.provenance.flags.some((f) =>
        f.startsWith("discarded_unverified_model_citation"),
      ),
    ).toBe(false);
    // And the real citation is still there.
    expect(resolved.provenance.modelCitations.length).toBe(1);
  }, 60000);

  it("the flag survives the paths that REASSIGN flags", async () => {
    // `flags` is reassigned (flags = result.flags, = vmaxResult.flags,
    // = epiResult.flags, = popgenResult.flags) after the point where the
    // citations are discarded. A flag pushed at the point of discard is
    // silently lost on four of the paths through resolveQuery, so it is
    // appended at final assembly instead. This pins that.
    //
    // An enzyme query with km/vmax supplied takes the override path; the
    // assertion is that the flag is present anyway.
    llmReturns([FABRICATED]);
    const resolved = await resolveQuery(QUERY);
    expect(resolved.domain).toBe("mm");
    expect(
      resolved.provenance.flags.some((f) =>
        f.startsWith("discarded_unverified_model_citation"),
      ),
    ).toBe(true);
  }, 60000);
});

/**
 * The `llm` parameter origin (ADR 0011).
 *
 * Stage 4 Part 6 left this open, and called it "the one that matters":
 *
 *   "no source, or LLM-generated with no corroborating record, is `rejected`"
 *
 * Until now a value the LLM resolver produced was labelled `origin:
 * "default"`. That states something false at the API surface. A default is a
 * value this project chose and documented and can defend; an LLM-supplied
 * number is one a language model generated from a prompt. Collapsing them
 * means a student cannot tell the difference between "the textbook value for
 * this domain" and "a number that came out of an LLM".
 *
 * `llm` is deliberately not `resolved` either: nothing was looked up, so it
 * must never carry a citation.
 *
 * The user directive now hard-blocks `llm` at the resolver: an LLM-supplied
 * parameter is neither user-supplied nor literature-resolved, so
 * resolveQuery() throws RequiredParametersMissingError rather than let an
 * unverified number reach the engine. The validator rules below still hold
 * for any provenance object the API might receive; the resolver simply never
 * emits a passing `llm` parameter anymore.
 */

import { describe, expect, it, vi, beforeEach } from "vitest";
import {
  RequiredParametersMissingError,
  validateParameterProvenance,
  type ParameterProvenance,
} from "../lib/provenance";
import { resolveQuery } from "../lib/queryResolver";
import { resolveQueryWithLLM } from "../lib/llmResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

vi.mock("../lib/llmResolver", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/llmResolver")>();
  return {
    ...original,
    resolveQueryWithLLM: vi.fn(),
  };
});

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({
      found: false,
      source: "not_found",
      literatureCandidates: [],
      logs: [],
    })),
  };
});

const NOTE =
  "Value supplied by the LLM resolver; not verified against literature.";

describe("the llm origin is distinct from default", () => {
  it("accepts an llm entry that explains itself", () => {
    const v = validateParameterProvenance(
      { beta: 0.4 },
      { beta: { origin: "llm", note: NOTE } },
    );
    expect(v).toEqual([]);
  });

  it("an llm entry with no note is a violation", () => {
    // The note is the only thing distinguishing this from a documented
    // default once it reaches the API, because an llm entry carries no
    // citation by construction.
    const v = validateParameterProvenance(
      { beta: 0.4 },
      { beta: { origin: "llm" } },
    );
    expect(v).toEqual([
      "beta is marked llm but carries no note explaining that the value is unverified",
    ]);
  });

  it("an llm entry must never carry a citation", () => {
    // Nothing was looked up. A citation here would assert provenance that
    // does not exist -- worse than no provenance at all.
    const v = validateParameterProvenance(
      { beta: 0.4 },
      { beta: { origin: "llm", note: NOTE, citation: "BRENDA (ref 12345)" } },
    );
    expect(v).toContain("beta has a citation but origin is 'llm'");
  });

  it("an llm entry must never carry a citation status", () => {
    const v = validateParameterProvenance(
      { beta: 0.4 },
      { beta: { origin: "llm", note: NOTE, citationStatus: "verified" } },
    );
    expect(v).toContain("beta has a citation status but origin is 'llm'");
  });

  it("a plain default still needs no note", () => {
    // The new rule must not leak onto `default`, or every domain's
    // documented defaults would start demanding explanations.
    const v = validateParameterProvenance(
      { beta: 0.4 },
      { beta: { origin: "default" } },
    );
    expect(v).toEqual([]);
  });
});

describe("Target J — an LLM-supplied parameter is hard-blocked (user directive)", () => {
  beforeEach(() => {
    vi.mocked(resolveQueryWithLLM).mockReset();
  });

  it("rejects a parameter the LLM invented instead of letting it reach the engine", async () => {
    // The LLM resolver returns a beta that is not in the query and has no
    // literature lookup behind it. The user directive hard-blocks any
    // parameter whose origin is "llm": the value must be user-supplied or
    // literature-resolved, so resolveQuery() throws and names the key.
    vi.mocked(resolveQueryWithLLM).mockResolvedValueOnce({
      domain: "sir",
      parameters: { beta: 0.42, r0_recovered: 0 },
      reasoning: "inferred a plausible transmission rate",
      modelCitations: [],
    } as never);

    const error = await resolveQuery(
      "simulate a moderately contagious outbreak gamma=0.1 s0=990 i0=10 end=100 points=101",
    ).catch((e) => e);
    expect(error).toBeInstanceOf(RequiredParametersMissingError);
    expect(String(error.message)).toContain("beta");
  });

  it("a user override in the query text still wins over an LLM value", async () => {
    vi.mocked(resolveQueryWithLLM).mockResolvedValueOnce({
      domain: "sir",
      parameters: { beta: 0.42 },
      reasoning: "inferred a plausible transmission rate",
      modelCitations: [],
    } as never);

    const resolved = await resolveQuery(
      "simulate an outbreak beta=0.2 gamma=0.1 s0=990 i0=10 end=100 points=101 r0_recovered=0",
    );
    expect(resolved.parameters["beta"]).toBe(0.2);
    expect(resolved.parameterProvenance["beta"]!.origin).toBe("user");
  });

  it("a literature-resolved value still passes through the llm path", async () => {
    // The hard-block must not break legitimate queries. When every parameter
    // is user-supplied or resolved from literature (km from BRENDA via the
    // mocked science agent), the llm path succeeds.
    vi.mocked(resolveQueryWithLLM).mockResolvedValueOnce({
      domain: "mm",
      parameters: {},
      reasoning: "identified lactate dehydrogenase kinetics",
      modelCitations: [],
      entities: {
        enzymeName: "lactate dehydrogenase",
        organism: "Homo sapiens",
      },
    } as never);
    vi.mocked(resolveKineticValue).mockResolvedValueOnce({
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
    } as never);

    const resolved = await resolveQuery(
      "simulate lactate dehydrogenase vmax=5 s0=10 end=10 points=51",
    );
    expect(resolved.parameters["km"]).toBe(10.73);
    expect(resolved.parameterProvenance["km"]!.origin).toBe("resolved");
  });
});

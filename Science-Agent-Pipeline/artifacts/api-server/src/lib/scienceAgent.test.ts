import { describe, expect, it } from "vitest";

import { parseAgentOutput } from "./scienceAgent";

/**
 * Stage 5 Part 4: the runner-boundary contract, TS side.
 *
 * The exact JSON the Python runner emits for the golden G1 lookup
 * (captured from science_agent_runner.py with a golden KineticResult).
 * If a refactor renames a field on either side of the boundary, these
 * assertions fail — the value and its citation cannot silently drift apart.
 */
const GOLDEN_RUNNER_OUTPUT = JSON.stringify({
  ok: true,
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
    title: null,
    organism: "Homo sapiens",
    notes: null,
  },
  literatureCandidates: [],
  logs: ["BRENDA exact: 1.1.1.27, Homo sapiens, lactate"],
});

describe("runner-boundary contract (Stage 5 Part 4)", () => {
  it("parses the golden runner output into the full result record", () => {
    const result = parseAgentOutput(GOLDEN_RUNNER_OUTPUT);
    expect(result.found).toBe(true);
    expect(result.km).toBe(10.73);
    expect(result.unit).toBe("mM");
    expect(result.organism).toBe("Homo sapiens");
    expect(result.source).toBe("brenda_exact");
    expect(result.crossSpecies).toBe(false);
    expect(result.citation).toEqual({
      source: "BRENDA",
      referenceId: "740253",
      url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
      title: null,
      organism: "Homo sapiens",
      notes: null,
    });
    expect(result.logs).toContain(
      "BRENDA exact: 1.1.1.27, Homo sapiens, lactate",
    );
  });

  it("carries the cross-species flag when present", () => {
    const result = parseAgentOutput(
      JSON.stringify({
        ok: true,
        found: true,
        km: 0.0026,
        unit: "mM",
        organism: "Sus scrofa",
        source: "brenda_cross_species",
        crossSpecies: true,
        citation: { source: "BRENDA", referenceId: "740001" },
        literatureCandidates: [],
        logs: [],
      }),
    );
    expect(result.crossSpecies).toBe(true);
    expect(result.source).toBe("brenda_cross_species");
  });

  it("a not-found result parses without a value", () => {
    const result = parseAgentOutput(
      JSON.stringify({ ok: true, found: false, source: "not_found", logs: [] }),
    );
    expect(result.found).toBe(false);
    expect(result.km).toBeUndefined();
  });

  it("a Python-side error report throws with its message", () => {
    expect(() =>
      parseAgentOutput(
        JSON.stringify({ ok: false, error: "ecNumber is required" }),
      ),
    ).toThrow("ecNumber is required");
  });

  it("unexpected JSON throws", () => {
    expect(() => parseAgentOutput(JSON.stringify({ nope: true }))).toThrow(
      "Science agent runner returned unexpected JSON",
    );
  });

  it("empty output throws", () => {
    expect(() => parseAgentOutput("  ")).toThrow(
      "Science agent runner returned no output",
    );
  });

  it("malformed JSON throws", () => {
    expect(() => parseAgentOutput("{not json")).toThrow();
  });
});

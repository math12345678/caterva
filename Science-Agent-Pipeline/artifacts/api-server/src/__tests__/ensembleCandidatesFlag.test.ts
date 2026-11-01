import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

/**
 * The ensemble weights reach the API, not just the CLI.
 *
 * `scientific ensemble` (ADR 0135/0137) shows a student the spread of
 * published values and what it does to the simulation. That command is on
 * the CLI, and this repository has now recorded four times that a finding
 * built for one front end reaches half the users — which is what
 * `docs/one-sided-findings.txt` and `check_both_front_ends_read_it.py` exist
 * to stop.
 *
 * So the grades that weight the sampling are emitted by the runner and
 * rendered into `provenance.flags` here: the list the CLI and the web UI
 * both read. These tests assert on the FLAG, not on the response field,
 * because ADR 0040 is the record of what happens otherwise — findings that
 * reached the API and never reached the student.
 */

const CANDIDATES = [
  {
    value: 0.03,
    unit: "mM",
    organism: "Homo sapiens",
    reference_id: "286469",
    conditions: null,
    grades: {
      assay_completeness: "absent",
      condition_proximity: "not_assessed",
      organism_match: "exact",
    },
  },
  {
    value: 0.398,
    unit: "mM",
    organism: "Homo sapiens",
    reference_id: "286442",
    conditions: null,
    grades: {
      assay_completeness: "complete",
      condition_proximity: "near",
      organism_match: "exact",
    },
  },
];

const RESOLVED = {
  found: true,
  km: 0.03,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "286469",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 7.4, temperatureC: 37 },
  ensembleCandidates: CANDIDATES,
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => RESOLVED),
  };
});

const QUERY =
  "simulate michaelis menten of lactate dehydrogenase on pyruvate in " +
  "Homo sapiens vmax=5 s0=10 end=10 points=51";

async function flagsFor(result: unknown): Promise<string> {
  vi.mocked(resolveKineticValue).mockResolvedValue(result as never);
  const resolved = await resolveQuery(QUERY);
  return resolved.provenance.flags.join("\n");
}

describe("the ensemble weights reach provenance.flags", () => {
  it("names every surviving value, not just the one returned", async () => {
    const flags = await flagsFor(RESOLVED);
    expect(flags).toContain("0.03");
    expect(flags).toContain("0.398");
  });

  it("carries each value's grades, which are the sampling weights", async () => {
    const flags = await flagsFor(RESOLVED);
    expect(flags).toContain("absent/not_assessed/exact");
    expect(flags).toContain("complete/near/exact");
  });

  it("carries a reference for each, so an alternative is checkable", async () => {
    const flags = await flagsFor(RESOLVED);
    expect(flags).toContain("286469");
    expect(flags).toContain("286442");
  });

  /**
   * A reader told a spread exists, without being told how to see its effect,
   * is left exactly where ADR 0115 found them: holding a finding with no
   * next step. The flag names the command.
   */
  it("tells the reader what to run to see the effect", async () => {
    expect(await flagsFor(RESOLVED)).toContain("scientific ensemble");
  });

  it("says the grades are what the sampling weights by", async () => {
    expect(await flagsFor(RESOLVED)).toMatch(/weights an ensemble\s+samples by/);
  });
});

describe("when it stays quiet", () => {
  /**
   * One row is not a disagreement, and a flag about it would be noise. This
   * project prints a lot of flags and cannot afford ones that do not carry a
   * decision.
   */
  it("says nothing when only one value survived", async () => {
    const flags = await flagsFor({
      ...RESOLVED,
      ensembleCandidates: [CANDIDATES[0]],
    });
    expect(flags).not.toMatch(/survive the evidence ranking/);
  });

  it("says nothing when the field is absent", async () => {
    const { ensembleCandidates, ...without } = RESOLVED;
    const flags = await flagsFor(without);
    expect(flags).not.toMatch(/survive the evidence ranking/);
  });

  it("says nothing when nothing was resolved", async () => {
    const flags = await flagsFor({ ...RESOLVED, ensembleCandidates: [] });
    expect(flags).not.toMatch(/survive the evidence ranking/);
  });
});

describe("it stays readable when the pool is large", () => {
  /**
   * Capped at four with an explicit remainder — the reason
   * `selectionTieFlags` gives: a flag nobody finishes reading is a flag
   * nobody reads. The count is still the true one, so the cap can never
   * understate the disagreement.
   */
  it("caps the list and says how many were left out", async () => {
    const many = Array.from({ length: 7 }, (_, i) => ({
      ...CANDIDATES[0],
      value: i + 1,
      reference_id: `ref${i}`,
    }));
    const flags = await flagsFor({ ...RESOLVED, ensembleCandidates: many });
    expect(flags).toContain("7 published values");
    expect(flags).toContain("and 3 more");
    expect(flags).not.toContain("ref5");
  });
});

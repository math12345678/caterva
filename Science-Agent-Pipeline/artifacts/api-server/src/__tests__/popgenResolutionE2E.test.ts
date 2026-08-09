/**
 * End-to-end coverage for applyPopgenResolution's SUCCESS branch.
 *
 * This file exists because of the gap ADR 0021 identified: `stdpopsim` is
 * not installable in the review sandbox (it needs `libgsl-dev` to build
 * msprime's C extension), so `popgen_resolver` always returned
 * `found=False` there, the success branch never executed in any test run,
 * and a crash lived in it undetected -- `buildResolvedKineticProvenance`
 * stamped a STRENDA status onto `mutation_rate`, which
 * `validateParameterProvenance` rejects and `resolveQuery` throws on.
 *
 * The fix for the crash is ADR 0021. This file fixes the reason nothing
 * caught it: by mocking at the science-agent boundary (exactly as
 * kiProvenance.test.ts and vmaxFromKcatProvenance.test.ts do), the success
 * branch is exercised on every CI run regardless of whether stdpopsim is
 * present on the machine.
 */
import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

// Shape the real runner emits for parameterType="mutation_rate": the value
// travels in the `km` field (the runner reuses it as a generic value slot
// for popgen -- see science_agent_runner.py), with a DOI-based citation.
// Figures are Rahbari et al. (2016)'s human autosomal mutation rate.
const POPGEN_RESULT = {
  found: true,
  km: 1.29e-8,
  unit: "per bp per generation",
  organism: "Homo sapiens",
  source: "popgen_literature",
  crossSpecies: false,
  citation: {
    source: "stdpopsim",
    referenceId: "10.1038/ng.3469",
    url: "https://doi.org/10.1038/ng.3469",
    title: "Rahbari et al., Nature Genetics, 2016",
  },
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => POPGEN_RESULT),
  };
});

const WF_QUERY =
  "simulate genetic drift in humans population_size=100 starting_frequency=0.5 " +
  "generations=100 replicate_runs=100 selection_coefficient=0";

describe("popgen mutation_rate resolution — end to end (ADR 0021 regression)", () => {
  it("resolves mutation_rate from literature without throwing", async () => {
    // Before ADR 0021 this threw "Internal error: invalid parameter
    // provenance" -- a successful lookup turned into a 500.
    const resolved = await resolveQuery(WF_QUERY);

    expect(resolved.domain).toBe("wright_fisher");
    expect(resolved.parameters["mutation_rate"]).toBe(1.29e-8);
  });

  it("the resolved mutation_rate keeps verified status and carries no STRENDA fields", async () => {
    const resolved = await resolveQuery(WF_QUERY);
    const prov = resolved.parameterProvenance["mutation_rate"]!;

    expect(prov.origin).toBe("resolved");
    expect(prov.citationStatus).toBe("verified");
    expect(prov.source).toBe("popgen_literature");
    expect(prov.organism).toBe("Homo sapiens");
    // The heart of ADR 0021: no enzymology reporting standard attached to
    // a per-generation substitution rate.
    expect(prov.strendaStatus).toBeUndefined();
    expect(prov.assayConditions).toBeUndefined();
    expect(prov.note ?? "").not.toMatch(/STRENDA/);
    expect(prov.note ?? "").not.toMatch(/pH/);
  });

  it("the citation is locatable and points at the real DOI", async () => {
    const resolved = await resolveQuery(WF_QUERY);
    const prov = resolved.parameterProvenance["mutation_rate"]!;

    expect(prov.citation).toContain("10.1038/ng.3469");
    expect(prov.citationLocators).toContainEqual({
      kind: "doi",
      value: "10.1038/ng.3469",
      deepLink: "https://doi.org/10.1038/ng.3469",
    });
  });

  it("an explicit mutation_rate override wins and is not overwritten by literature", async () => {
    const resolved = await resolveQuery(`${WF_QUERY} mutation_rate=5e-9`);
    expect(resolved.parameters["mutation_rate"]).toBe(5e-9);
    expect(resolved.parameterProvenance["mutation_rate"]!.origin).toBe("user");
  });
});

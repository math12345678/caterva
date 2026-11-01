import { describe, expect, it, vi } from "vitest";

import { isSimulationDomain } from "../lib/catervaRunner";
import { resolveQuery } from "../lib/queryResolver";
import {
  DOMAINS_WITH_LITERATURE_RESOLUTION,
  RESOLVABLE_FIELDS,
  UnrecognizedQueryError,
} from "../lib/provenance";
import type { ScienceAgentResult } from "../lib/scienceAgent";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => ({ found: false })),
  };
});

// Epidemiology and population genetics were archived on 2026-09-27
// (archive/legacy_domains/README.md; v0.4.0 is the last release that runs
// them). The runner answers their parameter types with "domain_archived"
// and caterva_runner.py answers their domains with ARCHIVED_DOMAINS. What
// these tests hold is the API server's side: no live table still names an
// archived domain as resolvable, and a question about one is refused with
// the archive and the release named, not with a literature flag about
// beta/gamma that reads as though the domain still ran.

describe("archived domains leave no resolver residue in the API server", () => {
  it("every domain with a literature lookup is a domain this build runs", () => {
    // wright_fisher: ["mutation_rate"] sat in RESOLVABLE_FIELDS for a month
    // after the archive, with nothing able to resolve it.
    const stale = [
      ...Object.keys(RESOLVABLE_FIELDS),
      ...DOMAINS_WITH_LITERATURE_RESOLUTION,
    ].filter((d) => !isSimulationDomain(d));
    expect(stale).toEqual([]);
  });

  it.each([
    "I want to model the spread of measles in a school with 500 students",
    "model a covid-19 outbreak s0=990 i0=10 end=100",
    "wright fisher drift population_size=100 generations=50",
  ])("refuses %j naming the archive date and v0.4.0", async (q) => {
    const err = await resolveQuery(q).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(UnrecognizedQueryError);
    const message = String((err as Error).message);
    expect(message).toContain("archived on 2026-09-27");
    expect(message).toContain("v0.4.0");
  });

  it("ScienceAgentResult no longer declares the disease fields", () => {
    // Compile-time: `tsc --noEmit` fails here if ANY of the nine is declared
    // on ScienceAgentResult again. (An excess-property check in a literal
    // only ever saw `r0`.) vitest does not type-check; tsc does.
    type Restored = Extract<
      keyof ScienceAgentResult,
      | "disease"
      | "r0"
      | "infectiousPeriodDays"
      | "crossStudyComposite"
      | "compositeNote"
      | "secondaryCitation"
      | "beta"
      | "gamma"
      | "betaGammaValidation"
    >;
    const noneRestored: [Restored] extends [never] ? true : false = true;
    expect(noneRestored).toBe(true);
  });
});

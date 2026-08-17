import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

/**
 * The tie must reach `provenance.flags` — the list the CLI and web UI both
 * render — not merely the response object.
 *
 * ADR 0040 is the record of what happens otherwise: findings that reached
 * the API and never reached the student. A field on the response that no
 * surface renders is computed, transmitted, and unread.
 *
 * The numbers below are the real LDH turnover frontier: six non-dominated
 * rows spanning 21.1 to 6467, every one wild-type with pH and temperature
 * reported. `min()` returns 21.1.
 */

const TIE = {
  candidates: [
    { value: 21.1, unit: "mM", reference_id: "684519", selected: true,
      conditions: "pH 6.0, 25°C, recombinant wild-type enzyme in presence of FBP" },
    { value: 6467, unit: "mM", reference_id: "761568", selected: false,
      conditions: "wild-type, presence of D-fructose-1,6-diphosphate" },
  ],
  low: 21.1,
  high: 6467,
  fold_range: 306.5,
  reason:
    "2 rows were equally well evidenced and their values span 21.1 to 6467, " +
    "a 306-fold range. The value returned was chosen by taking the lowest, " +
    "which the evidence does not justify.",
};

const KM_WITH_TIE = {
  found: true,
  km: 21.1,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "684519",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 6.0, temperatureC: 25, unreported: [] },
  selectionTie: TIE,
  literatureCandidates: [],
  logs: [],
};

const KM_NO_TIE = { ...KM_WITH_TIE, selectionTie: null };

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => KM_NO_TIE),
  };
});

const MM_QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate " +
  "in Homo sapiens vmax=5 s0=10 end=10 points=51";

function tieFlag(flags: string[]) {
  return flags.find((f) => f.includes("the evidence did not choose"));
}

describe("the tie reaches a surface", () => {
  it("appears in the flags a reader sees", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_WITH_TIE as never);
    const resolved = await resolveQuery(MM_QUERY);

    expect(tieFlag(resolved.provenance.flags)).toBeDefined();
  });

  it("names the alternatives, with their references", async () => {
    // A bare "there was a tie" is unactionable. The reader needs to be able
    // to go and look at the row that was not returned.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_WITH_TIE as never);
    const resolved = await resolveQuery(MM_QUERY);
    const flag = tieFlag(resolved.provenance.flags) ?? "";

    expect(flag).toContain("6467");
    expect(flag).toContain("761568");
    expect(flag).toContain("(returned)");
  });

  it("carries the reason, including that the tie-break is unjustified", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_WITH_TIE as never);
    const resolved = await resolveQuery(MM_QUERY);

    expect(tieFlag(resolved.provenance.flags)).toMatch(
      /the evidence does not justify/,
    );
  });

  it("says nothing when the evidence resolved the choice", async () => {
    // The counterpart. Without it, the tests above could pass because the
    // flag is emitted unconditionally — which would make it noise, and
    // noise is what gets a real finding skipped.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_NO_TIE as never);
    const resolved = await resolveQuery(MM_QUERY);

    expect(tieFlag(resolved.provenance.flags)).toBeUndefined();
  });

  it("says nothing for a tie with a single candidate", async () => {
    // A one-candidate tie cannot occur upstream, but a flag that fires on
    // it would report "the evidence did not choose" about a pool where
    // there was nothing to choose between.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce({
      ...KM_WITH_TIE,
      selectionTie: { ...TIE, candidates: [TIE.candidates[0]] },
    } as never);
    const resolved = await resolveQuery(MM_QUERY);

    expect(tieFlag(resolved.provenance.flags)).toBeUndefined();
  });
});

import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

/**
 * The other half of the single-source fix.
 *
 * `reliabilityFromRunner.test.ts` asserts the runner's score reaches the
 * response unchanged. That is necessary and not sufficient: the score can
 * arrive intact and still be a permanent `not_assessed`, because the
 * proximity axis has nothing to grade against unless a
 * `PhysiologicalReference` reaches the runner.
 *
 * Until this change there was no way to supply one to the API server. The
 * Python side had parsed `physiologicalReference` from its payload for as
 * long as the axis existed; nothing ever put it there. An input reachable
 * only from an internal subprocess payload is not an input, it is a
 * constant — the same argument that made `allowCrossSpecies` a real option
 * rather than a message about one.
 *
 * So these tests are about the argument's journey, not the score's. They
 * assert on the CALL, because the response looks identical whether or not
 * the reference was forwarded: the runner returns `not_assessed` rather
 * than an error when it has none. That symmetry is exactly what let the
 * original defect survive a parity test.
 */

const REFERENCE = {
  ph: 7.4,
  temperatureC: 37,
  basis: "test fixture, not a scientific claim",
  phTolerance: 0.3,
  temperatureToleranceC: 5,
};

const KM_RESULT = {
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
  assayConditions: { ph: 6.0, temperatureC: 25, unreported: [] },
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => KM_RESULT),
  };
});

const MM_QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate " +
  "in Homo sapiens vmax=5 s0=10 end=10 points=51";

function lastCall() {
  return vi.mocked(resolveKineticValue).mock.calls.at(-1)?.[0];
}

describe("the physiological reference reaches the resolver", () => {
  it("forwards it to the runner when the caller supplies one", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_RESULT as never);
    await resolveQuery(MM_QUERY, { physiologicalReference: REFERENCE });

    expect(lastCall()?.physiologicalReference).toEqual(REFERENCE);
  });

  it("forwards it unaltered — tolerances included", async () => {
    // The tolerances are the half most likely to be dropped by a partial
    // mapping, and dropping them is not a smaller version of the same bug:
    // the runner refuses a reference missing any of the five fields, so a
    // reference stripped of its tolerances is silently equivalent to no
    // reference at all, and the axis returns to `not_assessed`.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_RESULT as never);
    await resolveQuery(MM_QUERY, { physiologicalReference: REFERENCE });

    const sent = lastCall()?.physiologicalReference;
    expect(sent?.phTolerance).toBe(REFERENCE.phTolerance);
    expect(sent?.temperatureToleranceC).toBe(REFERENCE.temperatureToleranceC);
    expect(sent?.basis).toBe(REFERENCE.basis);
  });

  it("omits it entirely when the caller states nothing", async () => {
    // Not sent as `undefined`. The runner's `_parse_physiological` refuses a
    // partial reference, and once through JSON an explicit undefined is
    // indistinguishable from a partial one.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_RESULT as never);
    await resolveQuery(MM_QUERY);

    expect(lastCall()?.physiologicalReference).toBeUndefined();
  });

  it("does not invent a reference when the caller omits one", async () => {
    // pH 7.4 and 37 °C describe a mammal and misdescribe Thermus
    // thermophilus, whose enzymes are measured near 70 °C. Defaulting here
    // would report a confident `far` for a thermophile assay that was in
    // fact ideal — the precise assumption this axis was designed not to
    // make, and one nobody downstream could detect, because a graded axis
    // looks more trustworthy than an ungraded one.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_RESULT as never);
    await resolveQuery(MM_QUERY);

    const serialized = JSON.stringify(lastCall() ?? {});
    expect(serialized).not.toContain("physiologicalReference");
    expect(serialized).not.toContain("7.4");
  });

  it("keeps it per-query, never sticky across calls", async () => {
    // The resolver caches an interpreter and normalises queries; a
    // reference cached alongside either would leak one caller's stated
    // conditions into the next caller's grades. Same failure mode as a
    // cache key that ignores allowCrossSpecies, one field over.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_RESULT as never);
    await resolveQuery(MM_QUERY, { physiologicalReference: REFERENCE });
    expect(lastCall()?.physiologicalReference).toEqual(REFERENCE);

    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KM_RESULT as never);
    await resolveQuery(MM_QUERY);
    expect(lastCall()?.physiologicalReference).toBeUndefined();
  });
});

/**
 * The API says when a row is evidence against the model's mechanism, as
 * `caterva compose` does.
 *
 * BRENDA ref 739793 gives human LDH and one quinoline sulfonamide 0.00059 mM
 * "competitive versus NADH" and 0.00252 mM "noncompetitive versus pyruvate".
 * The API's competitive inhibition model of pyruvate asks for its Ki by mode
 * and gets the first, which is right: it is the only row stating the model's
 * mode. The second says that against pyruvate the inhibitor is not
 * competitive. `caterva compose` put that in its report; the API, choosing
 * the same row by the same ranking, never saw the row, because the runner's
 * mode step sets a row of another mode aside.
 *
 * The runner now sends it as `mechanismEvidence`, found in Python by the
 * function compose uses (caterva.compose.ki_mode's `evidence_against`), and
 * this side only puts it into words. The finding itself is tested on the
 * committed BRENDA page in Tests/test_ki_mode_resolution.py and through the
 * runner in Tests/test_runner_contract.py.
 */
import { describe, expect, it, vi } from "vitest";

import { mechanismEvidenceFlags, resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue, type ScienceAgentResult } from "../lib/scienceAgent";

const QUINOLINE =
  "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid";
const COMPETITIVE_VS_NADH =
  "pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, competitive versus NADH";
const NONCOMPETITIVE_VS_PYRUVATE =
  "pH 7.5, 37°C, recombinant His-tagged enzyme, pyruvate reduction, noncompetitive versus pyruvate";

/**
 * The runner's answer for `quantity: "ki"`, the quinoline sulfonamide,
 * `inhibitionMode: "competitive"`, `modelSubstrate: "pyruvate"`: these
 * fields as science_agent_runner.py emitted them on 2026-09-30, reading the
 * committed BRENDA page Tests/fixtures/ki_mode/brenda_1.1.1.27.html.gz
 * (Tests/test_runner_contract.py asserts the same `mechanismEvidence`), and
 * the same again reading BRENDA live. Only the fields a flag is built from
 * are kept.
 */
const COMPETITIVE_PYRUVATE_KI: ScienceAgentResult = {
  found: true,
  ki: 0.00059,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "739793",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 7.5, temperatureC: 37, buffer: null, unreported: [] },
  commentary: COMPETITIVE_VS_NADH,
  rowScope: { isoform: null, inhibitionMode: "competitive", versus: "NADH", kitzWilson: false },
  mechanismEvidence: {
    value: 0.00252,
    unit: "mM",
    organism: "Homo sapiens",
    referenceId: "739793",
    inhibitionMode: "noncompetitive",
    versus: "pyruvate",
    conditions: NONCOMPETITIVE_VS_PYRUVATE,
    modelMode: "competitive",
    modelSubstrate: "pyruvate",
  },
  literatureCandidates: [],
  logs: [],
};

const NOT_FOUND: ScienceAgentResult = {
  found: false,
  source: "not_found",
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return { ...original, resolveKineticValue: vi.fn(async () => NOT_FOUND) };
});

/** km is supplied, so the Ki is the only lookup, as in kiModeFromDomain. */
const QUERY =
  `competitive inhibition of human lactate dehydrogenase by ${QUINOLINE} with pyruvate ` +
  "km=0.1 vmax=1 s0=1 i0=1";

const THE_FLAG =
  "KI: evidence against this model's mechanism. Another row for this inhibitor, 0.00252 mM " +
  "(Homo sapiens, BRENDA ref 739793), states noncompetitive inhibition versus pyruvate, and " +
  "pyruvate is this model's substrate: measured against it, the inhibitor is not competitive, " +
  "and this model says it is. No choice of row fixes that. The other row: " +
  `"${NONCOMPETITIVE_VS_PYRUVATE}".`;

async function flagsFor(ki: ScienceAgentResult): Promise<string[]> {
  vi.mocked(resolveKineticValue).mockImplementation(async (entities) =>
    (entities as { quantity?: string }).quantity === "ki" ? ki : NOT_FOUND,
  );
  const resolved = await resolveQuery(QUERY);
  return resolved.provenance.flags;
}

describe("the runner's mechanismEvidence reaches provenance.flags", () => {
  it("names the row, its numbers and what it contradicts", async () => {
    const flags = await flagsFor(COMPETITIVE_PYRUVATE_KI);
    expect(flags).toContain("Resolved KI=0.00059 mM from brenda_exact.");
    expect(flags).toContain(THE_FLAG);
  });

  it("comes after what the row carried measured, which it qualifies", async () => {
    const flags = await flagsFor(COMPETITIVE_PYRUVATE_KI);
    const measured = flags.findIndex((f) =>
      f.startsWith("KI: the source row measured competitive inhibition versus NADH"),
    );
    expect(measured).toBeGreaterThanOrEqual(0);
    expect(flags.indexOf(THE_FLAG)).toBeGreaterThan(measured);
  });

  it("says nothing when the runner found no such row", async () => {
    // The noncompetitive pyruvate model carries the pyruvate row itself,
    // and the runner sends null (Tests/test_runner_contract.py).
    for (const none of [null, undefined]) {
      const flags = await flagsFor({ ...COMPETITIVE_PYRUVATE_KI, mechanismEvidence: none });
      expect(flags.join("\n")).not.toContain("evidence against this model's mechanism");
    }
  });
});

describe("mechanismEvidenceFlags decides nothing", () => {
  const evidence = COMPETITIVE_PYRUVATE_KI.mechanismEvidence;

  it("is only about a Ki", () => {
    expect(mechanismEvidenceFlags("km", evidence)).toEqual([]);
    expect(mechanismEvidenceFlags("ki", evidence)).toEqual([THE_FLAG]);
  });

  it("names only what the runner sent", () => {
    const bare = mechanismEvidenceFlags("ki", {
      ...evidence!,
      organism: null,
      referenceId: null,
      conditions: null,
    });
    expect(bare).toEqual([
      "KI: evidence against this model's mechanism. Another row for this inhibitor, 0.00252 mM, " +
        "states noncompetitive inhibition versus pyruvate, and pyruvate is this model's " +
        "substrate: measured against it, the inhibitor is not competitive, and this model says " +
        "it is. No choice of row fixes that.",
    ]);
  });
});

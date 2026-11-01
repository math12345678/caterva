import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

/**
 * Do the pool-level findings reach a reader?
 *
 * They did not, for four ADRs. `effector_contrasts` (ADR 0033),
 * `form_mixtures` (ADR 0035), `organism_discrepancies` and `source_mixtures`
 * (ADR 0037) were computed by the resolver, attached to its result, and
 * dropped at the process boundary — the runner never emitted them. Only a
 * prose line reached the diagnostic `logs`, which is not `provenance.flags`,
 * the list the CLI and web UI render.
 *
 * Every test on every detector passed the whole time. Each one tested the
 * computation; none tested the boundary. That is ADR 0027's defect repeated
 * four times, and it is why this file asserts on the FLAGS rather than on
 * the field: a field that arrives and is never rendered is the same failure
 * one layer along.
 */

const CONTRAST_REASON =
  "The candidate rows include measurements made BOTH with and without " +
  "fructose 1,6-bisphosphate: [21.1] present, [327.2] absent. The values " +
  "span a factor of 15.5.";

const MIXTURE_REASON =
  "The candidate rows name 3 different forms of LDH: LDHB = 142, " +
  "LDH1 = 1500, LDH2 = 1300. The values span a factor of 11.";

const DISCREPANCY_REASON =
  "The organism column says 'Drosophila melanogaster' (taxon 7227) and the " +
  "commentary says the enzyme came from 'human' (taxon 9606).";

const SOURCE_REASON =
  "Within Gallus gallus, the candidate rows report 2 different biological " +
  "sources: heart = 60.0, muscle = 1.1–3.3. The values span a factor of 54.";

const RESOLVED_WITH_FINDINGS = {
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
  assayConditions: { ph: 7.4, temperatureC: 25, unreported: [] },
  poolFindings: {
    effectorContrasts: [
      {
        compound: "fructose 1,6-bisphosphate",
        present_values: [21.1],
        absent_values: [327.2],
        reason: CONTRAST_REASON,
      },
    ],
    formMixtures: [
      {
        base: "LDH",
        values_by_form: { B: [142.0], "1": [1500.0], "2": [1300.0] },
        reason: MIXTURE_REASON,
      },
    ],
    organismDiscrepancies: [
      {
        value: 6670.0,
        column_organism: "Drosophila melanogaster",
        commentary_organism: "human",
        reason: DISCREPANCY_REASON,
      },
    ],
    sourceMixtures: [
      {
        organism: "Gallus gallus",
        values_by_source: { heart: [60.0], muscle: [1.1, 3.3] },
        reason: SOURCE_REASON,
      },
    ],
  },
  literatureCandidates: [],
  logs: [],
};

const RESOLVED_CLEAN = {
  ...RESOLVED_WITH_FINDINGS,
  poolFindings: {
    effectorContrasts: [],
    formMixtures: [],
    organismDiscrepancies: [],
    sourceMixtures: [],
  },
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => RESOLVED_WITH_FINDINGS),
  };
});

const MM_QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate " +
  "in Homo sapiens vmax=5 s0=10 end=10 points=51";

async function flagsFor(agentResult: unknown): Promise<string[]> {
  vi.mocked(resolveKineticValue).mockResolvedValueOnce(agentResult as never);
  const resolved = await resolveQuery(MM_QUERY);
  return resolved.provenance.flags;
}

describe("pool findings reach provenance.flags", () => {
  it.each([
    ["effector contrast", "effector contrast", CONTRAST_REASON],
    ["mixed enzyme forms", "mixed enzyme forms", MIXTURE_REASON],
    ["organism mismatch", "organism mismatch", DISCREPANCY_REASON],
    ["mixed biological sources", "mixed biological sources", SOURCE_REASON],
  ])("surfaces a %s", async (_name, label, reason) => {
    const flags = await flagsFor(RESOLVED_WITH_FINDINGS);
    const flag = flags.find((f) => f.includes(label));
    expect(flag, `no flag mentioning ${label}; got ${JSON.stringify(flags)}`).toBeDefined();
    expect(flag).toContain(reason);
  });

  it("names the parameter each finding belongs to", async () => {
    // A model resolves several parameters. A flag that does not say which
    // one it concerns sends the reader to check all of them.
    const flags = await flagsFor(RESOLVED_WITH_FINDINGS);
    for (const f of flags.filter((f) => f.includes("—"))) {
      expect(f.startsWith("KM")).toBe(true);
    }
  });

  it("does not paraphrase the finding", async () => {
    // The reason was argued over in the Python module. A client that
    // rewords it becomes a second place the wording can drift, which is
    // ADR 0027's shape applied to prose.
    const flags = await flagsFor(RESOLVED_WITH_FINDINGS);
    expect(flags.some((f) => f.includes(CONTRAST_REASON))).toBe(true);
  });

  it("adds nothing when the pool held nothing worth saying", async () => {
    const flags = await flagsFor(RESOLVED_CLEAN);
    expect(flags.some((f) => f.includes("—"))).toBe(false);
  });

  it("still reports the resolution itself", async () => {
    // The findings ride ALONGSIDE the resolution flag, not instead of it.
    // The value was resolved and is cited; the findings say the pool it came
    // from held something to look at.
    const flags = await flagsFor(RESOLVED_WITH_FINDINGS);
    expect(flags.some((f) => f.startsWith("Resolved KM="))).toBe(true);
  });

  it("survives a runner that emits no poolFindings at all", async () => {
    // Older runners, and every non-BRENDA resolution path. Absent must not
    // throw and must not fabricate.
    const withoutField = { ...RESOLVED_WITH_FINDINGS, poolFindings: undefined };
    const flags = await flagsFor(withoutField);
    expect(flags.some((f) => f.startsWith("Resolved KM="))).toBe(true);
    expect(flags.some((f) => f.includes("—"))).toBe(false);
  });
});

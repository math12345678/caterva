import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";

/**
 * Does the preparation finding reach a reader?
 *
 * ADR 0092 classified how the enzyme was prepared — immobilised, affinity
 * tagged, covalently modified — because the human LDH Ki resolved to
 * **0.00059**, a `"recombinant His-tagged enzyme"` row, with `notes: null`
 * and no flag saying so. ADR 0029's variant filter cannot see it: a tag is
 * not a sequence change.
 *
 * This file asserts on `provenance.flags`, not on the field, and not on the
 * helper that builds the string. `poolFindingsReachTheUser.test.ts` exists
 * because four ADRs' findings were computed correctly and dropped at the
 * process boundary, with every unit test passing throughout — "each one
 * tested the computation; none tested the boundary".
 *
 * The first version of this change appended to the resolver's diagnostic
 * log and stopped, which `queryResolver.ts` already records as "the same as
 * reaching nobody". It would have been the fifth.
 */

const TAGGED_KI = {
  found: true,
  km: 0.00059,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "739793",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 7.5, temperatureC: 37, unreported: [] },
  // The real verdict for the real row, as the runner emits it.
  preparation: {
    status: "tagged",
    evidence: "His-tagged",
    warrantsWarning: true,
  },
  literatureCandidates: [],
  logs: [],
};

const UNSTATED = {
  ...TAGGED_KI,
  preparation: { status: "unstated", warrantsWarning: false },
};

// Golden tuple G2's row: PEGylated, and the curator says so explicitly —
// "attachment of polyethylene glycol side chains ... does not alter the Km
// value". Resolved as KM here, so the flag must stay silent.
const PEGYLATED_KM_STATED_UNAFFECTED = {
  ...TAGGED_KI,
  km: 0.09,
  preparation: {
    status: "modified",
    evidence: "polyethylene glycol",
    stated_not_to_affect: "KM",
    // Python decided: resolved as KM, and the curator says KM is
    // unaffected, so no warning is warranted.
    warrantsWarning: false,
  },
};
const NATIVE = {
  ...TAGGED_KI,
  preparation: {
    status: "native",
    evidence: "native enzyme",
    warrantsWarning: false,
  },
};

let current: unknown = TAGGED_KI;

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => current),
  };
});

const MM_QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate " +
  "in Homo sapiens vmax=5 s0=10 end=10 points=51";

async function flagsFor(result: unknown): Promise<string[]> {
  current = result;
  const resolved = await resolveQuery(MM_QUERY);
  return resolved.provenance.flags;
}

describe("preparation reaches provenance.flags", () => {
  it("says the value came from a tagged construct, quoting the commentary", async () => {
    const flags = await flagsFor(TAGGED_KI);
    const flag = flags.find((f) => /TAGGED/.test(f));

    expect(flag, `no preparation flag in: ${JSON.stringify(flags)}`).toBeDefined();
    expect(flag).toContain("His-tagged");
    expect(flag).toContain("not of the free enzyme");
  });

  it("does not replace the resolution flag", async () => {
    // The value WAS resolved and IS cited. What the finding adds is what it
    // measured — the same "rides alongside, not instead of" rule the pool
    // findings follow.
    const flags = await flagsFor(TAGGED_KI);
    expect(flags.some((f) => /Resolved KM=/i.test(f))).toBe(true);
  });

  // The silence assertions match on the sentence EVERY preparation flag
  // ends with, not on the three status words.
  //
  // Matching `/TAGGED|IMMOBILISED|COVALENTLY/` was the first version, and
  // mutation showed what it was worth: making the builder fall back to
  // "measured on an enzyme" for every status emitted a flag on all 263
  // commentaries and both tests still passed, because the fallback string
  // contains none of those three words. They tested the vocabulary, not the
  // silence.
  const PREPARATION_FLAG = /not of the free enzyme/;

  it("stays silent when the row said nothing about preparation", async () => {
    // `unstated` is the majority case. A flag on every row is noise, and
    // noise is how the flags that matter stop being read (ADR 0028).
    const flags = await flagsFor(UNSTATED);
    expect(flags.filter((f) => PREPARATION_FLAG.test(f))).toEqual([]);
  });

  it("stays silent when the row said the enzyme was native", async () => {
    const flags = await flagsFor(NATIVE);
    expect(flags.filter((f) => PREPARATION_FLAG.test(f))).toEqual([]);
  });

  it("stays silent when the curator says this quantity was unaffected", async () => {
    // Golden tuple G2. Warning here would contradict the source, and would
    // contradict the Python side, whose search log is already silent —
    // two renderers of one fact disagreeing (ADR 0003, ADR 0027).
    const flags = await flagsFor(PEGYLATED_KM_STATED_UNAFFECTED);
    expect(flags.filter((f) => PREPARATION_FLAG.test(f))).toEqual([]);
  });

  it("still warns when the statement names a DIFFERENT quantity", async () => {
    // The exception is about a measurement, not the protein. A row saying
    // "does not alter the Km value" says nothing about its Ki, and the
    // resolution here is keyed on KM — so a KCAT statement must not silence
    // it.
    const kcatStatement = {
      ...PEGYLATED_KM_STATED_UNAFFECTED,
      preparation: {
        ...PEGYLATED_KM_STATED_UNAFFECTED.preparation,
        stated_not_to_affect: "KCAT",
        // A KCAT statement does not cover a KM resolution, so Python's
        // differs_for("km") returns True.
        warrantsWarning: true,
      },
    };
    const flags = await flagsFor(kcatStatement);
    expect(flags.filter((f) => PREPARATION_FLAG.test(f))).toHaveLength(1);
  });
});

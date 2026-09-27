import { describe, expect, it } from "vitest";

import { buildTrajectoryCsv } from "../lib/trajectoryCsv";

/**
 * The exported CSV is the artifact that outlives the session.
 *
 * Every other surface Caterva has is attached to a session that ends: the
 * CLI warning scrolls away, the API flags are discarded with the response,
 * the Antimony comment is read once. The CSV gets opened in Excel, plotted,
 * pasted into a lab report, and mailed to a supervisor months later.
 *
 * It carried no citation at all. These tests are about the one file where a
 * missing provenance line cannot be recovered by asking again.
 */

const FULL = {
  runId: "run-abc123",
  domain: "mm_competitive_inhibition",
  completedAt: "2026-08-14T22:00:00Z",
  parameters: { km: 10.73, ki: 1.4, vmax: 5, s0: 10 },
  trajectory: [
    { time: 0, S: 10, P: 0 },
    { time: 1, S: 8.2, P: 1.8 },
  ],
  provenance: {
    reasoning: "resolved from BRENDA",
    modelCitations: ["Michaelis & Menten (1913)"],
    flags: [
      "Resolved KM=10.73 mM from brenda_exact.",
      "KM — organism mismatch: the column says 'Drosophila melanogaster' " +
        "and the commentary says the enzyme came from 'human'.",
      "KM — mixed biological sources: within Gallus gallus, heart = 60.0, " +
        "muscle = 1.1–3.3.",
      // ADR 0051's finding, added here deliberately. It is the newest flag
      // class in the project and it was written by a different agent after
      // this exporter existed. If the header needed editing to carry it, the
      // design would be wrong: a detector added next month must reach the
      // file that leaves the building without anyone remembering to come
      // back here. This asserts that property against a real instance of it.
      "KM — the evidence did not choose: several rows were equally well " +
        "evidenced and the tie-break is not justified by the evidence; the " +
        "spread is disagreement in the literature, not measurement " +
        "uncertainty. Candidates: 21.1 (ref 684519), 6467 (ref 761568).",
    ],
  },
  parameterProvenance: {
    km: {
      origin: "resolved" as const,
      citation: "BRENDA ref 740253",
      organism: "Homo sapiens",
      assayConditions: { ph: 7.4, temperatureC: 25, buffer: "Tris" },
    },
    ki: {
      origin: "default" as const,
      note: "Could not resolve a real KI value from BRENDA/KEGG/PubMed; using default KI.",
    },
  },
};

function dataLines(csv: string): string[] {
  return csv.split("\n").filter((l) => !l.startsWith("#") && l.trim() !== "");
}

describe("the exported CSV carries its provenance", () => {
  it("names the citation for a resolved parameter", () => {
    // The single thing the old export omitted, and the reason this file
    // exists: a number in a lab report with no way back to its source.
    expect(buildTrajectoryCsv(FULL)).toContain("BRENDA ref 740253");
  });

  it("says which parameters were NOT resolved, and why", () => {
    // A defaulted parameter is the most important line on the page: the
    // number beside it came from nowhere. Reporting only the resolved ones
    // would make the document look better and be worse.
    const csv = buildTrajectoryCsv(FULL);
    expect(csv).toContain("ki = 1.4");
    expect(csv).toContain("[default]");
    expect(csv).toMatch(/Could not resolve a real KI value/);
  });

  it("carries the assay conditions", () => {
    const csv = buildTrajectoryCsv(FULL);
    expect(csv).toContain("pH 7.4");
    expect(csv).toContain("25 C");
  });

  it("carries EVERY flag, including the pool-level findings", () => {
    // ADR 0033/0035/0037's findings reach the API flags. A reader plotting
    // this file has no other route to them, so dropping the inconvenient
    // ones here would be worse than no header -- it would look complete.
    const csv = buildTrajectoryCsv(FULL);
    for (const flag of FULL.provenance.flags) {
      expect(csv).toContain(flag);
    }
  });

  it("tells the reader how to skip the header", () => {
    const csv = buildTrajectoryCsv(FULL);
    expect(csv).toContain('comment="#"');
    expect(csv).toContain("comment.char");
  });
});

describe("the data is unchanged by the header", () => {
  it("emits exactly the rows the old export emitted", () => {
    // Stripping `#` lines must yield byte-identical data to the previous
    // behaviour, or this change breaks every existing consumer.
    const lines = dataLines(buildTrajectoryCsv(FULL));
    expect(lines).toEqual(["time,S,P", "0,10,0", "1,8.2,1.8"]);
  });

  it("puts every provenance line behind a # so parsers skip it", () => {
    const csv = buildTrajectoryCsv(FULL);
    const header = csv.split("\n").slice(0, csv.split("\n").indexOf("time,S,P"));
    expect(header.every((l) => l.startsWith("#"))).toBe(true);
  });

  it("flattens a multi-line reason onto one physical line", () => {
    // A note containing a newline would otherwise emit a bare data row into
    // the middle of the header, and pandas would read it as data.
    const csv = buildTrajectoryCsv({
      ...FULL,
      parameterProvenance: {
        km: {
          origin: "default" as const,
          note: "line one\nline two\nline three",
        },
      },
    });
    const header = csv.split("\n").slice(0, csv.split("\n").indexOf("time,S,P"));
    expect(header.every((l) => l.startsWith("#"))).toBe(true);
    expect(csv).toContain("line one line two line three");
  });
});

describe("degrading honestly", () => {
  it("still emits the header when there is no trajectory", () => {
    // A header with no data is a truthful document: it says what was asked
    // and that nothing came back. An empty string would lose the reason.
    const csv = buildTrajectoryCsv({ ...FULL, trajectory: [] });
    expect(csv).toContain("BRENDA ref 740253");
    expect(dataLines(csv)).toEqual([]);
  });

  it("survives a job with no provenance at all", () => {
    const csv = buildTrajectoryCsv({
      runId: "r", domain: "mm", parameters: {}, trajectory: [{ time: 0 }],
    });
    expect(dataLines(csv)).toEqual(["time", "0"]);
    expect(csv).toContain("Caterva simulation export");
  });

  it("marks a parameter with no provenance as unknown, not as resolved", () => {
    // Absence of a provenance entry must not read as "fine". It is the same
    // rule as `unstated` not being `wild_type` (ADR 0029).
    const csv = buildTrajectoryCsv({
      ...FULL,
      parameterProvenance: {},
    });
    expect(csv).toContain("[unknown]");
    expect(csv).not.toContain("[resolved]");
  });
});

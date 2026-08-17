/**
 * Attribution in the trajectory CSV, and the one table behind it.
 *
 * The CSV is described in its own module docstring as "the artifact that
 * OUTLIVES THE SESSION" — opened in Excel, pasted into a lab report, mailed
 * to a supervisor. It carried the resolved Km with its BRENDA reference and
 * no licence at all.
 *
 * These tests assert the CC BY 4.0 clauses rather than the wording, so the
 * block can be rephrased but not thinned. They mirror
 * `Terium/tests/test_data_sources.py`, because the two renderers read the
 * same `docs/data-sources.json` and must not drift.
 */

import { describe, expect, it } from "vitest";

import {
  attributionLines,
  citationObligations,
  loadDataSources,
  sourcesUsed,
} from "../lib/dataSources";
import { buildTrajectoryCsv } from "../lib/trajectoryCsv";
import type { ParameterProvenance } from "../lib/provenance";

const brenda = {
  origin: "resolved",
  citation: "BRENDA ref 740253",
  source: "brenda_exact",
  organism: "Homo sapiens",
} as unknown as ParameterProvenance;

const user = { origin: "user" } as unknown as ParameterProvenance;

function csv(parameterProvenance: Record<string, ParameterProvenance>): string {
  return buildTrajectoryCsv({
    runId: "r1",
    domain: "mm",
    parameters: { km: 10.73, s0: 10 },
    trajectory: [
      { time: 0, S: 10 },
      { time: 1, S: 9 },
    ],
    parameterProvenance,
  });
}

describe("the one table", () => {
  it("loads, and is not silently empty", () => {
    const sources = loadDataSources();
    expect(sources.length).toBeGreaterThan(0);
    expect(sources.map((s) => s.tokens).flat()).toContain("brenda");
  });

  it("matches what the Python side records for BRENDA", () => {
    // Both languages read docs/data-sources.json. If TypeScript ever grows
    // its own copy, these literals — transcribed from NOTICE — stop agreeing
    // with it.
    const brendaSource = loadDataSources().find((s) =>
      s.tokens.includes("brenda"),
    );
    expect(brendaSource?.licence).toBe("CC BY 4.0");
    expect(brendaSource?.licence_uri).toBe(
      "https://creativecommons.org/licenses/by/4.0/",
    );
    expect(brendaSource?.creator).toContain("Leibniz Institute DSMZ");
  });
});

describe("crediting only what contributed", () => {
  it("names nobody when every value came from the user", () => {
    expect(attributionLines({ km: user, s0: user })).toEqual([]);
    expect(csv({ km: user, s0: user })).not.toContain("CC BY");
  });

  it("credits BRENDA only when BRENDA supplied a value", () => {
    const used = sourcesUsed({ km: brenda }).map((u) => u.source?.tokens[0]);
    expect(used).toEqual(["brenda"]);
  });

  it("names an undescribed source rather than dropping it", () => {
    // Three-state discipline: "we do not know the terms" must not render
    // the same as "there are no terms".
    const lines = attributionLines({
      km: {
        origin: "resolved",
        citation: "SABIO-RK ref 41221",
        source: "sabio_rk",
      } as unknown as ParameterProvenance,
    }).join("\n");
    expect(lines).toContain("SABIO-RK ref 41221");
    expect(lines).toContain("NOT RECORDED");
  });

  it("does not mistake a user-supplied value for a database", () => {
    // A cry-wolf warning on every hand-supplied number trains readers to
    // skip the block — ADR 0028's reasoning about buffer strings.
    expect(
      attributionLines({
        s0: user,
        p: {
          origin: "user",
          note: "model structure: fixed by the model definition, not measured",
        } as unknown as ParameterProvenance,
      }),
    ).toEqual([]);
  });
});

describe("what CC BY 4.0 §3(a)(1) asks to be retained", () => {
  const text = () => csv({ km: brenda, s0: user });

  it("carries the creator, licence, URIs and modifications", () => {
    const out = text();
    expect(out).toContain("Leibniz Institute DSMZ"); // §3(a)(1)(A)(i)
    expect(out).toContain("CC BY 4.0"); // §3(a)(1)(C)
    expect(out).toContain("creativecommons.org/licenses/by/4.0"); // §3(a)(1)(C)
    expect(out).toContain("brenda-enzymes.org"); // §3(a)(1)(A)(v)
    expect(out).toContain("filtered"); // §3(a)(1)(B)
    expect(out).toContain("NOTICE"); // §3(a)(2)
  });

  it("disclaims endorsement", () => {
    // §2(a)(6). Load bearing here: a researcher already read a Terrium
    // outreach email as claiming credit that was not ours.
    expect(text()).toContain("endorsed");
    expect(text()).toContain("Terrium's, not theirs");
  });
});

describe("the block must not damage the data", () => {
  it("keeps every attribution line behind a # so parsers skip it", () => {
    const out = csv({ km: brenda, s0: user });
    const header = out.split("\n").findIndex((l) => l.startsWith("time"));
    expect(header).toBeGreaterThan(0);
    for (const line of out.split("\n").slice(0, header)) {
      expect(line.startsWith("#")).toBe(true);
    }
  });

  it("leaves the data rows byte-identical to a run without attribution", () => {
    // pandas: read_csv(path, comment="#"). Stripping the comments must yield
    // exactly what the file held before any of this was added.
    const withAttribution = csv({ km: brenda, s0: user });
    const data = withAttribution
      .split("\n")
      .filter((l) => !l.startsWith("#"))
      .join("\n");
    expect(data).toBe("time,S\n0,10\n1,9");
  });
});

describe("what publication obliges", () => {
  it("reports the citation the source asks for", () => {
    // NOTICE: "Citing Terrium is not a substitute for citing BRENDA."
    // The audit endpoint judges publication-readiness and said nothing
    // about this.
    const obligations = citationObligations({ km: brenda });
    expect(obligations).toHaveLength(1);
    expect(obligations[0]?.source).toBe("brenda");
    expect(obligations[0]?.citationRequest).toContain(
      "brenda-enzymes.org/references.php",
    );
    expect(obligations[0]?.licence).toBe("CC BY 4.0");
  });

  it("obliges nothing when no described source contributed", () => {
    // An obligation to cite data the run did not use is a false one.
    expect(citationObligations({ km: user, s0: user })).toEqual([]);
  });

  // The test that used to sit here was named "omits a source with no
  // recorded citation request" and asserted a field of the JSON table
  // instead of calling citationObligations at all. It could not fail for
  // the reason it named, and it passed while ADR 0081 stated behaviour the
  // code did not have. Replaced by dataSourceObligations.test.ts, which
  // exercises the function.

  it("reads the same table as the file exports", () => {
    // One drift check: the obligation and the CSV block must name the same
    // licensor, because both come from docs/data-sources.json.
    const obligation = citationObligations({ km: brenda })[0];
    expect(csv({ km: brenda })).toContain(obligation!.creator);
  });
});

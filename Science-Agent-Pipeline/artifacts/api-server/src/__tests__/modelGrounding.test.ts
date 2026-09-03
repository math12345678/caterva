/**
 * A model the caller wrote, with its constants traced to the literature.
 *
 * This is the capability Terrium existed to have and did not: `POST
 * /simulate/model` ran any Antimony document and stamped every parameter
 * origin "user" with no citations, so a lab that brought its own model --
 * the only case a real lab has -- got plain Tellurium with extra steps.
 *
 * Mocked at the science-agent boundary, like the other resolver tests.
 * The Python bridge and BRENDA are exercised for real elsewhere; what is
 * under test here is whether a declaration in a comment becomes a cited
 * parameter, and whether the refusals hold.
 */
import { describe, expect, it, vi } from "vitest";

import { groundAnnotatedModel } from "../lib/modelGrounding";
import { resolveKineticValue } from "../lib/scienceAgent";

const CITED = {
  found: true,
  km: 0.12,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "715396",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
  },
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return { ...original, resolveKineticValue: vi.fn(async () => CITED) };
});

const model = (annotation: string, assignment: string) =>
  [
    "model hexokinase_assay",
    "  S -> P; (Vmax * S) / (Km_hex + S);",
    `  ${annotation}`,
    `  ${assignment}`,
    "  Vmax = 0.5;",
    "  S = 10;",
    "end",
  ].join("\n");

describe("grounding a caller's own model", () => {
  it("checks the caller's value against literature without changing it", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      model(
        '// terrium: km enzyme="hexokinase" substrate="glucose" unit="mM"',
        "Km_hex = 0.15;",
      ),
    );

    expect(report.problems).toEqual([]);
    expect(report.blocking).toEqual([]);
    const entry = report.entries[0]!;
    expect(entry.status).toBe("grounded");
    expect(entry.yourValue).toBe(0.15);
    expect(entry.literatureValue).toBe(0.12);
    expect(entry.citation).toContain("715396");
    expect(entry.comparison?.foldDifference).toBeCloseTo(0.15 / 0.12, 10);

    // check mode is non-invasive by construction. A lab's model is theirs.
    expect(report.groundedSource).toBeUndefined();
  });

  it("converts the literature value into the model's own unit", async () => {
    // THE trap. BRENDA normalises Km to mM; a model written in uM would
    // disagree by 1000x for a reason that has nothing to do with the
    // science, and it would look like a finding.
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      model(
        '// terrium: km enzyme="hexokinase" substrate="glucose" unit="uM"',
        "Km_hex = 120;",
      ),
    );
    const entry = report.entries[0]!;
    // 0.12 mM is 120 uM, so a model written in uM with 120 agrees exactly.
    expect(entry.comparison?.literatureInYourUnit).toBeCloseTo(120, 8);
    expect(entry.comparison?.foldDifference).toBeCloseTo(1, 8);
  });

  it("refuses to compare when no unit was declared", async () => {
    // Reporting a fold difference between two numbers in unknown units
    // would be a fabricated finding. The citation is still delivered.
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      model('// terrium: km enzyme="hexokinase"', "Km_hex = 0.15;"),
    );
    const entry = report.entries[0]!;
    expect(entry.status).toBe("grounded");
    expect(entry.citation).toContain("715396");
    expect(entry.comparison).toBeUndefined();
    expect(entry.comparisonSkipped).toMatch(/no unit was declared/i);
  });

  // ---- resolve mode: Terrium supplies the number, or nothing runs -----

  it("fills a placeholder from literature, in the model's unit", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      model(
        '// terrium: km enzyme="hexokinase" substrate="glucose" unit="uM" resolve',
        "Km_hex = ?;",
      ),
    );
    expect(report.blocking).toEqual([]);
    // 0.12 mM written into a uM model must be 120, not 0.12.
    expect(report.groundedSource).toContain("Km_hex = 120;");
    expect(report.groundedSource).not.toContain("?");
    // ...and the rest of the model is untouched.
    expect(report.groundedSource).toContain("Vmax = 0.5;");
    expect(report.groundedSource).toContain("(Vmax * S) / (Km_hex + S)");
  });

  it("refuses to write a value when it does not know the unit to write it in", async () => {
    // A millimolar number written into a micromolar model is a silent
    // 1000x error in a simulation that runs perfectly.
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      model('// terrium: km enzyme="hexokinase" resolve', "Km_hex = ?;"),
    );
    expect(report.groundedSource).toBeUndefined();
    expect(report.blocking).toHaveLength(1);
    expect(report.blocking[0]).toMatch(/unit/i);
  });

  it("refuses the run when the literature has nothing, rather than defaulting", async () => {
    // The entire point of `resolve`: no fallback exists, because a
    // fallback is the fabrication this project refuses.
    vi.mocked(resolveKineticValue).mockResolvedValue({
      found: false,
      literatureCandidates: [],
      logs: [],
    } as never);
    const report = await groundAnnotatedModel(
      model(
        '// terrium: km enzyme="hexokinase" unit="mM" resolve',
        "Km_hex = ?;",
      ),
    );
    expect(report.groundedSource).toBeUndefined();
    expect(report.blocking[0]).toMatch(/hold no KM/i);
  });

  it("refuses a value whose citation cannot be followed", async () => {
    // An uncheckable citation is not a citation. Substituting the value
    // anyway would put an unverifiable number into the caller's model.
    vi.mocked(resolveKineticValue).mockResolvedValue({
      ...CITED,
      citation: { source: "BRENDA" },
    } as never);
    const report = await groundAnnotatedModel(
      model(
        '// terrium: km enzyme="hexokinase" unit="mM" resolve',
        "Km_hex = ?;",
      ),
    );
    expect(report.groundedSource).toBeUndefined();
    expect(report.blocking[0]).toMatch(/no reference id or URL/i);
  });

  it("does not spend lookups on a model whose declarations are wrong", async () => {
    vi.mocked(resolveKineticValue).mockClear();
    const report = await groundAnnotatedModel(
      model('// terrium: km substrate="glucose" unit="mM"', "Km_hex = 0.15;"),
    );
    expect(report.problems).toHaveLength(1);
    expect(report.entries).toEqual([]);
    expect(vi.mocked(resolveKineticValue)).not.toHaveBeenCalled();
  });

  it("does nothing at all to a model with no declarations", async () => {
    vi.mocked(resolveKineticValue).mockClear();
    const report = await groundAnnotatedModel(
      "model m\n  S -> P; k*S;\n  k = 0.1;\n  S = 10;\nend",
    );
    expect(report.entries).toEqual([]);
    expect(report.problems).toEqual([]);
    expect(report.groundedSource).toBeUndefined();
    expect(vi.mocked(resolveKineticValue)).not.toHaveBeenCalled();
  });

  it("rewrites only the annotated line, not every mention of the symbol", async () => {
    // `Km_hex` appears in the rate law too. A blind source-wide replace
    // would corrupt the model's structure.
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      model(
        '// terrium: km enzyme="hexokinase" unit="mM" resolve',
        "Km_hex = ?;",
      ),
    );
    const occurrences = (report.groundedSource ?? "").match(/Km_hex/g) ?? [];
    expect(occurrences).toHaveLength(2); // the rate law and the assignment
    expect(report.groundedSource).toContain("(Vmax * S) / (Km_hex + S)");
  });
});

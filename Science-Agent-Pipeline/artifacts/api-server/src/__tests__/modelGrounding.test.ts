/**
 * A model the caller wrote, with its constants traced to the literature.
 *
 * This is the capability Caterva existed to have and did not: `POST
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
        '// caterva: km enzyme="hexokinase" substrate="glucose" unit="mM"',
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
        '// caterva: km enzyme="hexokinase" substrate="glucose" unit="uM"',
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
      model('// caterva: km enzyme="hexokinase"', "Km_hex = 0.15;"),
    );
    const entry = report.entries[0]!;
    expect(entry.status).toBe("grounded");
    expect(entry.citation).toContain("715396");
    expect(entry.comparison).toBeUndefined();
    expect(entry.comparisonSkipped).toMatch(/no unit was declared/i);
  });

  // ---- resolve mode: Caterva supplies the number, or nothing runs -----

  it("fills a placeholder from literature, in the model's unit", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      model(
        '// caterva: km enzyme="hexokinase" substrate="glucose" unit="uM" resolve',
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
      model('// caterva: km enzyme="hexokinase" resolve', "Km_hex = ?;"),
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
        '// caterva: km enzyme="hexokinase" unit="mM" resolve',
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
        '// caterva: km enzyme="hexokinase" unit="mM" resolve',
        "Km_hex = ?;",
      ),
    );
    expect(report.groundedSource).toBeUndefined();
    expect(report.blocking[0]).toMatch(/no reference id or URL/i);
  });

  it("does not spend lookups on a model whose declarations are wrong", async () => {
    vi.mocked(resolveKineticValue).mockClear();
    const report = await groundAnnotatedModel(
      model('// caterva: km substrate="glucose" unit="mM"', "Km_hex = 0.15;"),
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
        '// caterva: km enzyme="hexokinase" unit="mM" resolve',
        "Km_hex = ?;",
      ),
    );
    const occurrences = (report.groundedSource ?? "").match(/Km_hex/g) ?? [];
    expect(occurrences).toHaveLength(2); // the rate law and the assignment
    expect(report.groundedSource).toContain("(Vmax * S) / (Km_hex + S)");
  });

  // ---- SBML: the format labs actually exchange -------------------------

  const SBML = (paramLine: string, directive: string) =>
    [
      '<?xml version="1.0" encoding="UTF-8"?>',
      '<sbml xmlns="http://www.sbml.org/sbml/level3/version1/core" level="3" version="1">',
      '  <model id="m">',
      "    <listOfParameters>",
      `      ${directive}`,
      `      ${paramLine}`,
      '      <parameter id="Vmax" value="0.5" constant="true"/>',
      "    </listOfParameters>",
      "  </model>",
      "</sbml>",
    ].join("\n");

  it("checks a value declared in an SBML comment", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      SBML(
        '<parameter id="Km_hex" value="0.15" constant="true"/>',
        '<!-- caterva: km parameter="Km_hex" enzyme="hexokinase" unit="mM" -->',
      ),
      { format: "sbml" },
    );
    expect(report.problems).toEqual([]);
    const entry = report.entries[0]!;
    expect(entry.parameter).toBe("Km_hex");
    expect(entry.yourValue).toBe(0.15);
    expect(entry.literatureValue).toBe(0.12);
    expect(entry.citation).toContain("715396");
  });

  it("fills an SBML value attribute in resolve mode, in the model's unit", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      SBML(
        '<parameter id="Km_hex" constant="true"/>',
        '<!-- caterva: km parameter="Km_hex" enzyme="hexokinase" unit="uM" resolve -->',
      ),
      { format: "sbml" },
    );
    expect(report.blocking).toEqual([]);
    // 0.12 mM into a uM model is 120.
    expect(report.groundedSource).toContain('value="120"');
    // ...and nothing else was rewritten.
    expect(report.groundedSource).toContain('<parameter id="Vmax" value="0.5"');
  });

  it("rewrites only the declared parameter, not another with a similar id", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const source = SBML(
      '<parameter id="Km_hex" value="0.9" constant="true"/>\n      <parameter id="Km_hex_2" value="0.3" constant="true"/>',
      '<!-- caterva: km parameter="Km_hex_2" enzyme="hexokinase" unit="mM" resolve -->',
    );
    const report = await groundAnnotatedModel(source, { format: "sbml" });
    expect(report.blocking).toEqual([]);
    expect(report.groundedSource).toContain('<parameter id="Km_hex" value="0.9"');
    expect(report.groundedSource).toContain('<parameter id="Km_hex_2" value="0.12"');
  });

  it("reports an SBML declaration naming a parameter that does not exist", async () => {
    // A typo would otherwise silently check nothing.
    const report = await groundAnnotatedModel(
      SBML(
        '<parameter id="Km_hex" value="0.15" constant="true"/>',
        '<!-- caterva: km parameter="Km_typo" enzyme="hexokinase" unit="mM" -->',
      ),
      { format: "sbml" },
    );
    expect(report.entries).toEqual([]);
    expect(report.problems[0]!.message).toMatch(/no <parameter id="Km_typo">/);
  });

  it("holds SBML to the same identity rule as Antimony", async () => {
    // The weaker format must not become the way to get an unidentified
    // parameter resolved.
    const report = await groundAnnotatedModel(
      SBML(
        '<parameter id="Km_hex" value="0.15" constant="true"/>',
        '<!-- caterva: km parameter="Km_hex" unit="mM" -->',
      ),
      { format: "sbml" },
    );
    expect(report.entries).toEqual([]);
    expect(report.problems[0]!.message).toMatch(/enzyme must be named/i);
  });

  it("overwrites an EXISTING SBML value, converted into the model's unit", async () => {
    // Distinct from the placeholder case above, which takes the
    // add-the-attribute branch. This one takes the replace-the-attribute
    // branch, and a mutation writing the raw mM value survived every
    // other test here: the resolve fixture had no value attribute, and
    // the fixture that did have one used mM, where converted and raw are
    // identical. uM with an existing value is the case that can tell them
    // apart.
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      SBML(
        '<parameter id="Km_hex" value="999" constant="true"/>',
        '<!-- caterva: km parameter="Km_hex" enzyme="hexokinase" unit="uM" resolve -->',
      ),
      { format: "sbml" },
    );
    expect(report.blocking).toEqual([]);
    expect(report.groundedSource).toContain('value="120"');
    expect(report.groundedSource).not.toContain('value="0.12"');
    expect(report.groundedSource).not.toContain('value="999"');
  });

  it("binds an SBML id exactly, even when a longer id comes first", async () => {
    // A prefix match would bind `Km_hex` to `Km_hex_long`, which appears
    // FIRST here. The earlier ordering hid this: declaring the longer id
    // made a prefix match land correctly by accident.
    vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
    const report = await groundAnnotatedModel(
      SBML(
        '<parameter id="Km_hex_long" value="777" constant="true"/>\n      <parameter id="Km_hex" value="0.9" constant="true"/>',
        '<!-- caterva: km parameter="Km_hex" enzyme="hexokinase" unit="mM" resolve -->',
      ),
      { format: "sbml" },
    );
    expect(report.blocking).toEqual([]);
    expect(report.groundedSource).toContain('<parameter id="Km_hex_long" value="777"');
    expect(report.groundedSource).toContain('<parameter id="Km_hex" value="0.12"');
  });

  describe("a Ki is looked up under its inhibitor, by the stated mechanism", () => {
    // What the runner answers on the recorded rabbit hexokinase page
    // (Tests/fixtures/recorded/brenda_2.7.1.1.html.gz, CATERVA_BRENDA_RECORDED
    // and CATERVA_HTTP_RECORDED as vitest.config.ts sets them), run
    // 2026-09-30 for MgADP- with modelSubstrate "glucose": both Ki rows (ref
    // 640206) state mixed inhibition, so a noncompetitive rate law takes the
    // one measured versus glucose and a competitive one is refused.
    const MGADP_NONCOMPETITIVE = {
      found: true,
      ki: 7.8,
      unit: "mM",
      organism: "Oryctolagus cuniculus",
      source: "brenda_exact",
      crossSpecies: false,
      citation: {
        source: "BRENDA",
        referenceId: "640206",
        url: "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
      },
      rowScope: { isoform: null, inhibitionMode: "mixed", versus: "glucose", kitzWilson: false },
      literatureCandidates: [],
      logs: [],
    };
    const MGADP_COMPETITIVE = {
      found: false,
      source: "mode_withheld",
      modesAvailable: ["mixed inhibition versus MgATP2-", "mixed inhibition versus glucose"],
      literatureCandidates: [],
      logs: [],
    };
    const kiModel = (annotation: string, assignment: string) =>
      [
        "model hexokinase_adp",
        "  S -> P; Vmax * S / (Km + S) / (1 + I / Ki_adp);",
        `  ${annotation}`,
        `  ${assignment}`,
        "  Km = 0.1; Vmax = 0.5; S = 10; I = 1;",
        "end",
      ].join("\n");
    const IDENTITY = 'ec="2.7.1.1" organism="Oryctolagus cuniculus" unit="mM"';

    it("looks nothing up without an inhibitor, and resolve then refuses", async () => {
      vi.mocked(resolveKineticValue).mockClear();
      const report = await groundAnnotatedModel(
        kiModel(`// caterva: ki ${IDENTITY} substrate="glucose" resolve`, "Ki_adp = ?;"),
      );
      // The defect was this lookup, under substrate "glucose".
      expect(resolveKineticValue).not.toHaveBeenCalled();
      const entry = report.entries[0]!;
      expect(entry.status).toBe("not_found");
      expect(entry.note).toMatch(/^No Ki was looked up: a Ki belongs to its inhibitor/);
      expect(entry.note).toContain('substrate="glucose" on a ki annotation names the model\'s substrate');
      expect(report.blocking).toHaveLength(1);
      expect(report.groundedSource).toBeUndefined();
    });

    it("sends the inhibitor as the compound, with the mechanism and the model substrate", async () => {
      vi.mocked(resolveKineticValue).mockResolvedValue(MGADP_NONCOMPETITIVE as never);
      const report = await groundAnnotatedModel(
        kiModel(
          `// caterva: ki ${IDENTITY} inhibitor="MgADP-" inhibition="noncompetitive" substrate="glucose" resolve`,
          "Ki_adp = ?;",
        ),
      );

      expect(vi.mocked(resolveKineticValue).mock.calls[0]![0]).toMatchObject({
        quantity: "ki",
        ecNumber: "2.7.1.1",
        organism: "Oryctolagus cuniculus",
        substrate: "MgADP-",
        inhibitionMode: "noncompetitive",
        modelSubstrate: "glucose",
      });
      expect(report.blocking).toEqual([]);
      expect(report.groundedSource).toContain("Ki_adp = 7.8;");
      const entry = report.entries[0]!;
      expect(entry).toMatchObject({ inhibitor: "MgADP-", inhibitionMode: "noncompetitive" });
      // The row's own mode reaches the note, in the query path's words.
      expect(entry.note).toContain("BRENDA (ref 640206)");
      expect(entry.note).toContain(
        "KI: the source row measured mixed inhibition versus glucose; a Ki is specific to that mode and assay.",
      );
    });

    it("sends no mechanism when none was stated, and no model substrate either", async () => {
      vi.mocked(resolveKineticValue).mockResolvedValue(MGADP_NONCOMPETITIVE as never);
      await groundAnnotatedModel(
        kiModel(`// caterva: ki ${IDENTITY} inhibitor="MgADP-" substrate="glucose"`, "Ki_adp = 7.8;"),
      );
      const sent = vi.mocked(resolveKineticValue).mock.calls[0]![0];
      expect(sent.substrate).toBe("MgADP-");
      expect(sent).not.toHaveProperty("inhibitionMode");
      expect(sent).not.toHaveProperty("modelSubstrate");
    });

    it("refuses a Ki of another mechanism, naming what BRENDA holds", async () => {
      vi.mocked(resolveKineticValue).mockResolvedValue(MGADP_COMPETITIVE as never);
      const report = await groundAnnotatedModel(
        kiModel(
          `// caterva: ki ${IDENTITY} inhibitor="MgADP-" inhibition="competitive" substrate="glucose" resolve`,
          "Ki_adp = ?;",
        ),
      );
      expect(report.groundedSource).toBeUndefined();
      expect(report.blocking).toHaveLength(1);
      expect(report.blocking[0]).toContain(
        "(mixed inhibition versus MgATP2-; mixed inhibition versus glucose)",
      );
      expect(report.blocking[0]).toContain("none was used");
      // Not the literature-has-nothing sentence: constants exist.
      expect(report.blocking[0]).not.toMatch(/hold no KI/);
    });

    it("leaves a Km's lookup as it was: under its substrate, with no mode", async () => {
      vi.mocked(resolveKineticValue).mockResolvedValue(CITED as never);
      await groundAnnotatedModel(
        model('// caterva: km enzyme="hexokinase" substrate="glucose" unit="mM"', "Km_hex = 0.15;"),
      );
      const sent = vi.mocked(resolveKineticValue).mock.calls[0]![0];
      expect(sent.substrate).toBe("glucose");
      expect(sent).not.toHaveProperty("inhibitionMode");
    });
  });
});

/**
 * Declarations about a caller's own model.
 *
 * The refusals below matter more than the happy paths, for the reason
 * they always do here: a missed annotation is visible (the parameter is
 * simply not checked), and a WRONG one attaches a real citation to a
 * number it does not describe. A Km resolved against the wrong enzyme is
 * more convincing than no citation at all, which makes it worse than no
 * citation at all.
 */
import { describe, expect, it } from "vitest";

import { parseModelAnnotations } from "../lib/modelAnnotations";

const parse = parseModelAnnotations;
const only = (source: string) => {
  const { annotations, problems } = parse(source);
  expect(problems).toEqual([]);
  expect(annotations).toHaveLength(1);
  return annotations[0]!;
};

describe("parseModelAnnotations", () => {
  it("reads a declaration on the line above its parameter", () => {
    const a = only(`
      model hexokinase_assay
        // caterva: km enzyme="hexokinase" substrate="glucose" unit="mM"
        Km_hex = 0.15;
      end
    `);
    expect(a.parameter).toBe("Km_hex");
    expect(a.quantity).toBe("km");
    expect(a.enzymeName).toBe("hexokinase");
    expect(a.substrate).toBe("glucose");
    expect(a.unit).toBe("mM");
    expect(a.value).toBe(0.15);
    expect(a.mode).toBe("check");
  });

  it("reads a declaration trailing its parameter on one line", () => {
    const a = only(
      `Km_hex = 0.15;  // caterva: km enzyme="hexokinase" unit="mM"`,
    );
    expect(a.parameter).toBe("Km_hex");
    expect(a.value).toBe(0.15);
  });

  it("points at the parameter's line, not the comment's", () => {
    // The message has to send the reader to the number, which is what
    // they will edit.
    const a = only(
      ['// caterva: km enzyme="hexokinase" unit="mM"', "Km_hex = 0.15;"].join(
        "\n",
      ),
    );
    expect(a.line).toBe(2);
  });

  it("accepts an EC number instead of a name, and an organism", () => {
    const a = only(
      `// caterva: ki ec="1.1.1.27" organism="Oryctolagus cuniculus" unit="uM"\n` +
        `Ki_ldh = 40;`,
    );
    expect(a.ecNumber).toBe("1.1.1.27");
    expect(a.organism).toBe("Oryctolagus cuniculus");
    expect(a.quantity).toBe("ki");
  });

  it("reads scientific notation and hash comments", () => {
    const a = only(`# caterva: kcat enzyme="catalase" unit="1/s"\nkcat_cat = 4.1e4;`);
    expect(a.value).toBe(41000);
    expect(a.quantity).toBe("kcat");
  });

  it("reads the resolve mode and its placeholder", () => {
    // The caller writes the structure and leaves the constant to Caterva.
    const a = only(
      `// caterva: km enzyme="hexokinase" substrate="glucose" unit="mM" resolve\n` +
        `Km_hex = ?;`,
    );
    expect(a.mode).toBe("resolve");
    expect(a.parameter).toBe("Km_hex");
    expect(a.value).toBeUndefined();
  });

  it("allows resolve to overwrite a value the caller already wrote", () => {
    // "Use the literature's number instead of mine" is a legitimate ask,
    // and distinct from having no number at all.
    const a = only(
      `Km_hex = 0.15; // caterva: km enzyme="hexokinase" unit="mM" resolve`,
    );
    expect(a.mode).toBe("resolve");
    expect(a.value).toBe(0.15);
  });

  // ---- the refusals -----------------------------------------------------

  it("refuses to guess which enzyme a parameter belongs to", () => {
    // THE central rule. `Km_hex` looks like hexokinase to a human and
    // means nothing to a resolver. Inferring it from the name is how a
    // real citation ends up attached to the wrong enzyme's constant.
    const { annotations, problems } = parse(
      `// caterva: km substrate="glucose" unit="mM"\nKm_hex = 0.15;`,
    );
    expect(annotations).toEqual([]);
    expect(problems[0]!.message).toMatch(/enzyme must be named/i);
    expect(problems[0]!.message).toMatch(/will not infer/i);
  });

  it("reports a mistyped field instead of ignoring it", () => {
    // `enzmye="hexokinase"` silently dropped would leave the caller
    // believing the parameter was literature-checked when it was skipped.
    const { annotations, problems } = parse(
      `// caterva: km enzmye="hexokinase" unit="mM"\nKm_hex = 0.15;`,
    );
    expect(annotations).toEqual([]);
    expect(problems[0]!.message).toMatch(/enzmye/);
  });

  it("reports an unknown quantity", () => {
    const { problems } = parse(
      `// caterva: vmax enzyme="hexokinase"\nV = 1;`,
    );
    expect(problems[0]!.message).toMatch(/not a quantity Caterva can resolve/i);
  });

  it("reports an annotation attached to nothing", () => {
    const { annotations, problems } = parse(
      `// caterva: km enzyme="hexokinase" unit="mM"\n// just a comment\n`,
    );
    expect(annotations).toEqual([]);
    expect(problems[0]!.message).toMatch(/not attached to a parameter/i);
  });

  it("reports a placeholder with no resolve", () => {
    // `Km = ?` in check mode has nothing to check and would silently do
    // nothing.
    const { problems } = parse(
      `// caterva: km enzyme="hexokinase" unit="mM"\nKm_hex = ?;`,
    );
    expect(problems[0]!.message).toMatch(/no value to check/);
    expect(problems[0]!.message).toMatch(/resolve/);
  });

  it("drops BOTH of two claims about one parameter, and says so", () => {
    // Keeping the first would be choosing between two claims by source
    // order -- the whichever-came-first non-decision that let domain
    // classification pick the wrong model.
    const { annotations, problems } = parse(
      `// caterva: km enzyme="hexokinase" unit="mM"\nKm_x = 0.15;\n` +
        `// caterva: km enzyme="glucokinase" unit="mM"\nKm_x = 0.20;`,
    );
    expect(annotations).toEqual([]);
    expect(problems[0]!.message).toMatch(/annotated 2 times/);
  });

  it("ignores an ordinary comment that is not a caterva directive", () => {
    // Antimony sources are full of comments. Only the tagged ones are
    // claims.
    const { annotations, problems } = parse(
      `// Km measured in-house, see lab notebook p.44\nKm_hex = 0.15;`,
    );
    expect(annotations).toEqual([]);
    expect(problems).toEqual([]);
  });

  it("does not bind to an assignment that is an expression", () => {
    // `Vmax = kcat * E0` is computed by the model, not a measured
    // constant. Reporting a citation for it would claim a source for
    // something the model derives.
    const { annotations, problems } = parse(
      `// caterva: km enzyme="hexokinase" unit="mM"\nKm_hex = kcat * E0;`,
    );
    expect(annotations).toEqual([]);
    expect(problems[0]!.message).toMatch(/not attached to a parameter/i);
  });

  it("reads several declarations in one model", () => {
    const { annotations, problems } = parse(`
      model competitive
        // caterva: km enzyme="hexokinase" substrate="glucose" unit="mM"
        Km = 0.15;
        // caterva: ki enzyme="hexokinase" substrate="glucose" unit="mM"
        Ki = 0.02;
        S = 10;  // no claim made about this one
      end
    `);
    expect(problems).toEqual([]);
    expect(annotations.map((a) => a.parameter)).toEqual(["Km", "Ki"]);
    expect(annotations.map((a) => a.quantity)).toEqual(["km", "ki"]);
  });

  describe("a ki declaration names its inhibitor and its mechanism", () => {
    // BRENDA files a Ki under its inhibitor. The grammar had no way to say
    // which one, so a ki annotation was looked up under its substrate=.

    it("reads inhibitor= and inhibition= on a ki", () => {
      const a = only(
        `// caterva: ki ec="2.7.1.1" organism="Oryctolagus cuniculus" ` +
          `inhibitor="MgADP-" inhibition="Noncompetitive" substrate="glucose" unit="mM"\n` +
          `Ki_adp = 7.8;`,
      );
      expect(a.quantity).toBe("ki");
      expect(a.inhibitor).toBe("MgADP-");
      // Normalised, so the lookup is sent one of the three it knows.
      expect(a.inhibitionMode).toBe("noncompetitive");
      // On a ki, substrate= is the model's substrate, kept as written.
      expect(a.substrate).toBe("glucose");
    });

    it("carries both in an SBML declaration, as in Antimony", () => {
      const { annotations, problems } = parse(
        [
          "<sbml><model><listOfParameters>",
          '  <parameter id="Ki_adp" value="7.8" constant="true"/>',
          "</listOfParameters>",
          '<!-- caterva: ki parameter="Ki_adp" ec="2.7.1.1" inhibitor="MgADP-" inhibition="noncompetitive" unit="mM" -->',
          "</model></sbml>",
        ].join("\n"),
        "sbml",
      );
      expect(problems).toEqual([]);
      expect(annotations[0]).toMatchObject({ inhibitor: "MgADP-", inhibitionMode: "noncompetitive" });
    });

    it("refuses inhibitor= on a km, which is filed under its substrate", () => {
      const { annotations, problems } = parse(
        `// caterva: km enzyme="hexokinase" substrate="glucose" inhibitor="MgADP-" unit="mM"\nKm_hex = 0.15;`,
      );
      expect(annotations).toEqual([]);
      expect(problems[0]!.message).toMatch(/inhibitor= describes an inhibition constant/);
    });

    it("refuses inhibition= on a kcat", () => {
      const { problems } = parse(
        `// caterva: kcat enzyme="catalase" inhibition="competitive" unit="1/s"\nkcat_cat = 4.1e4;`,
      );
      expect(problems[0]!.message).toMatch(/inhibition= describes an inhibition constant/);
    });

    it("refuses a mechanism it cannot look a Ki up by", () => {
      const { problems } = parse(
        `// caterva: ki ec="2.7.1.1" inhibitor="MgADP-" inhibition="mixed" unit="mM"\nKi = 7.8;`,
      );
      expect(problems[0]!.message).toMatch(/competitive, noncompetitive, uncompetitive/);
      expect(problems[0]!.message).toMatch(/mixed-type Ki counts as noncompetitive/);
    });

    it("points mode= at inhibition=, since mode means check or resolve here", () => {
      const { problems } = parse(
        `// caterva: ki ec="2.7.1.1" inhibitor="MgADP-" mode="competitive" unit="mM"\nKi = 7.8;`,
      );
      expect(problems[0]!.message).toMatch(/'mode' is not a field/);
      expect(problems[0]!.message).toMatch(/inhibition="competitive"/);
    });
  });
});

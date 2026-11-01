import { describe, expect, it } from "vitest";

import { SimulationParameterSchemas } from "../lib/schemas";

const VALID: Record<
  keyof typeof SimulationParameterSchemas,
  Record<string, unknown>
> = {
  mm: { km: 2, vmax: 5, s0: 10, end: 10, points: 51 },
  mm_competitive_inhibition: {
    km: 2,
    ki: 1.5,
    vmax: 5,
    s0: 10,
    i0: 0.1,
    end: 10,
    points: 51,
  },
  gillespie_ssa: { a0: 1000, k: 0.5, end: 10 },
  gillespie_ssa_bimolecular: { a0: 100, b0: 100, k: 0.005, end: 10 },
  gillespie_ssa_replicates: { a0: 100, k: 0.5, end: 10, n_replicates: 100 },
  sbml: {
    sbml_string: "model M()\n  A = 1\nend",
    start: 0,
    end: 1,
    points: 11,
  },
};

const INVALID: Record<string, Record<string, unknown>> = {
  mm: { km: "abc", vmax: 5, s0: 10 },
  mm_competitive_inhibition: { km: 2, ki: 1.5, vmax: 5, s0: 10 }, // missing i0
  gillespie_ssa: { a0: 1000, k: 0.5 }, // missing end
  gillespie_ssa_bimolecular: { a0: 100, b0: 100, k: 0.005 }, // missing end
  gillespie_ssa_replicates: { a0: 100, k: 0.5, end: 10 }, // missing n_replicates
  sbml: { start: 0, end: 1, points: 11 }, // missing sbml_string
};

describe("SimulationParameterSchemas", () => {
  for (const domain of Object.keys(SimulationParameterSchemas) as Array<
    keyof typeof SimulationParameterSchemas
  >) {
    it(`accepts valid ${domain} parameters`, () => {
      const parse = SimulationParameterSchemas[domain].safeParse(VALID[domain]);
      expect(parse.success).toBe(true);
    });

    it(`rejects structurally invalid ${domain} parameters`, () => {
      const parse = SimulationParameterSchemas[domain].safeParse(
        INVALID[domain],
      );
      expect(parse.success).toBe(false);
    });
  }


  it("rejects NaN parameters rather than passing them to the engine", () => {
    const parse = SimulationParameterSchemas.mm.safeParse({
      km: Number.NaN,
      vmax: 5,
      s0: 10,
    });
    expect(parse.success).toBe(false);
  });

});

describe("mm accepts Vmax either directly or as kcat x [E]0 (ADR 0013)", () => {
  const base = { km: 0.1, s0: 1.0, end: 10, points: 51 };

  it("accepts an explicit vmax with no kcat", () => {
    const parse = SimulationParameterSchemas.mm.safeParse({ ...base, vmax: 5 });
    expect(parse.success).toBe(true);
  });

  it("accepts kcat and enzyme_conc together with no vmax", () => {
    // The real captured golden: 118 s^-1, 6-monoacetylmorphine,
    // Homo sapiens, pH 7.4, 37 C, BRENDA ref 750291.
    const parse = SimulationParameterSchemas.mm.safeParse({
      ...base,
      kcat: 118,
      enzyme_conc: 1e-5,
    });
    expect(parse.success).toBe(true);
  });

  it("rejects kcat without enzyme_conc", () => {
    // A turnover number alone cannot produce a Vmax -- it is a per-molecule
    // property, and Vmax is a property of an assay containing some amount of
    // enzyme. Accepting this would silently fall back to the default Vmax
    // and run a simulation nobody asked for.
    const parse = SimulationParameterSchemas.mm.safeParse({
      ...base,
      kcat: 118,
    });
    expect(parse.success).toBe(false);
  });

  it("rejects enzyme_conc without kcat", () => {
    const parse = SimulationParameterSchemas.mm.safeParse({
      ...base,
      enzyme_conc: 1e-5,
    });
    expect(parse.success).toBe(false);
  });

  it("rejects a request with no route to a Vmax at all", () => {
    const parse = SimulationParameterSchemas.mm.safeParse(base);
    expect(parse.success).toBe(false);
  });

  it("accepts an explicit vmax alongside kcat and enzyme_conc", () => {
    // Not a contradiction to reject: vmax is what the engine integrates, so
    // the runner honours it and ignores the derivable value. The schema's
    // job is to ensure SOME route exists, not to arbitrate between them.
    const parse = SimulationParameterSchemas.mm.safeParse({
      ...base,
      vmax: 7,
      kcat: 118,
      enzyme_conc: 1e-5,
    });
    expect(parse.success).toBe(true);
  });
});

import { describe, expect, it } from "vitest";

import { SimulationParameterSchemas } from "../lib/schemas";

const VALID: Record<keyof typeof SimulationParameterSchemas, Record<string, unknown>> = {
  mm: { km: 2, vmax: 5, s0: 10, end: 10, points: 51 },
  sir: { beta: 0.3, gamma: 0.1, s0: 990, i0: 10, end: 100, points: 101 },
  seir: { beta: 0.3, sigma: 0.2, gamma: 0.1, s0: 990, e0: 10, i0: 0, end: 100, points: 101 },
  pcr: { n0: 100, efficiency: 0.95, cycles: 30 },
  monte_carlo_pi: { n_samples: 10_000, seed: 42 },
  wright_fisher: {
    population_size: 100,
    starting_frequency: 0.5,
    generations: 100,
    replicate_runs: 100,
    mutation_rate: 0,
    selection_coefficient: 0,
  },
  two_locus_wright_fisher: {
    population_size: 100,
    generations: 20,
    recombination_rate: 0.1,
    starting_frequencies: [0.5, 0, 0, 0.5],
    replicate_runs: 50,
  },
  molecular_dynamics: {
    n_particles: 108,
    temperature: 0.4,
    timestep: 0.005,
    n_steps: 1000,
    density: 0.85,
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
  sir: { beta: 0.3, gamma: 0.1 }, // missing s0, i0
  seir: { beta: 0.3, sigma: 0.2, gamma: 0.1, s0: 990 }, // missing e0, i0
  pcr: { n0: 100, efficiency: 0.95 }, // missing cycles
  monte_carlo_pi: { n_samples: 0.5 }, // not an integer
  wright_fisher: { population_size: 50.5, starting_frequency: 0.5, generations: 10 },
  two_locus_wright_fisher: {
    population_size: 100,
    generations: 20,
    recombination_rate: 0.1,
    starting_frequencies: [0.5, 0.5], // must be 4 entries
    replicate_runs: 50,
  },
  molecular_dynamics: { n_particles: 10, temperature: 0.4 }, // missing timestep, n_steps
  gillespie_ssa: { a0: 1000, k: 0.5 }, // missing end
  gillespie_ssa_bimolecular: { a0: 100, b0: 100, k: 0.005 }, // missing end
  gillespie_ssa_replicates: { a0: 100, k: 0.5, end: 10 }, // missing n_replicates
  sbml: { start: 0, end: 1, points: 11 }, // missing sbml_string
};

describe("SimulationParameterSchemas", () => {
  for (const domain of Object.keys(SimulationParameterSchemas) as Array<keyof typeof SimulationParameterSchemas>) {
    it(`accepts valid ${domain} parameters`, () => {
      const parse = SimulationParameterSchemas[domain].safeParse(VALID[domain]);
      expect(parse.success).toBe(true);
    });

    it(`rejects structurally invalid ${domain} parameters`, () => {
      const parse = SimulationParameterSchemas[domain].safeParse(INVALID[domain]);
      expect(parse.success).toBe(false);
    });
  }

  it("accepts engine-defaulted optional parameters omitted", () => {
    const parse = SimulationParameterSchemas.wright_fisher.safeParse({
      population_size: 100,
      starting_frequency: 0.5,
      generations: 100,
      replicate_runs: 100,
    });
    expect(parse.success).toBe(true);
  });

  it("rejects NaN parameters rather than passing them to the engine", () => {
    const parse = SimulationParameterSchemas.mm.safeParse({
      km: Number.NaN,
      vmax: 5,
      s0: 10,
    });
    expect(parse.success).toBe(false);
  });

  it("rejects malformed Monte Carlo seed", () => {
    const parse = SimulationParameterSchemas.monte_carlo_pi.safeParse({
      n_samples: 10_000,
      seed: "42",
    });
    expect(parse.success).toBe(false);
  });

  it("rejects malformed molecular-dynamics density", () => {
    for (const density of ["0.85", null]) {
      const parse = SimulationParameterSchemas.molecular_dynamics.safeParse({
        n_particles: 108,
        temperature: 0.4,
        timestep: 0.005,
        n_steps: 1000,
        density,
      });
      expect(parse.success).toBe(false);
    }
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
    const parse = SimulationParameterSchemas.mm.safeParse({ ...base, kcat: 118 });
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

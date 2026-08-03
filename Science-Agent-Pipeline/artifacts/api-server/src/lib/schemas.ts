import { z } from "zod";

import type { SimulationDomain } from "./telluriumRunner";

export const WaitlistBody = z.object({
  email: z.string().email("Invalid email address").trim().toLowerCase(),
});

export const ResolveBody = z.object({
  query: z
    .string()
    .min(1, "query is required")
    .max(500, "query must be 500 characters or fewer")
    .transform((s) => s.trim()),
});

export const CancelJobParams = z.object({
  jobId: z.coerce.string().min(1),
});

export const ExportJobParams = z.object({
  jobId: z.coerce.string().min(1),
});

/**
 * Structural validation for simulation parameters at the HTTP boundary.
 *
 * This is deliberately limited to shape: parameters must be present and
 * numeric, counts must be integers, and the two-locus haplotype array must
 * have exactly four entries. Scientific plausibility bounds (km > 0,
 * efficiency in [0, 1], temperature < 1, ...) live in the engine only --
 * duplicating them here would let the two layers drift, the exact failure
 * ADR 0003 exists to prevent.
 *
 * Optional entries are parameters the engine itself defaults when omitted;
 * the runner fills them in before calling the engine.
 */
const numeric = z.number();
const integer = z.number().int();
const optionalNumeric = z.number().nullish();

export const SimulationParameterSchemas: Record<
  SimulationDomain,
  z.ZodType<Record<string, unknown>>
> = {
  mm: z.object({
    km: numeric,
    // Optional because Vmax can instead be derived from kcat * enzyme_conc
    // (ADR 0013). Exactly one route must be available; the runner rejects a
    // request that supplies neither, and prefers an explicit vmax when both
    // are present.
    vmax: optionalNumeric,
    /** Turnover number, s^-1. Requires enzyme_conc. */
    kcat: optionalNumeric,
    /** Total enzyme concentration [E]0, mM. Requires kcat.
     *  Never resolved from literature -- it is a property of an experiment,
     *  not of an enzyme. */
    enzyme_conc: optionalNumeric,
    s0: numeric,
    end: optionalNumeric,
    points: integer.nullish(),
  }).refine(
    (p) => {
      const has = (v: unknown) => v !== undefined && v !== null;
      // An explicit vmax is always sufficient -- it is what the engine
      // integrates, and the runner prefers it over any derivable value.
      if (has(p.vmax)) return true;
      // Otherwise BOTH halves of the derivation are required. Two distinct
      // failures collapse into this one rule:
      //   - exactly one supplied: a turnover number alone is a per-molecule
      //     property with nothing to multiply, and a concentration alone has
      //     no rate
      //   - neither supplied: there is no route to a Vmax at all
      //
      // That second case is why this is not simply a "supplied together"
      // check. The first version of this refine() compared the two
      // presence flags for EQUALITY, so `{km, s0}` with no vmax, no kcat
      // and no enzyme_conc passed -- false === false. It was caught by
      // writing the test before trusting the schema.
      return has(p.kcat) && has(p.enzyme_conc);
    },
    {
      message:
        "mm needs a Vmax: supply vmax directly, or supply BOTH kcat and " +
        "enzyme_conc (Vmax = kcat * [E]0)",
    },
  ),
  sir: z.object({
    beta: numeric,
    gamma: numeric,
    s0: numeric,
    i0: numeric,
    r0_recovered: optionalNumeric,
    end: optionalNumeric,
    points: integer.nullish(),
  }),
  seir: z.object({
    beta: numeric,
    sigma: numeric,
    gamma: numeric,
    s0: numeric,
    e0: numeric,
    i0: numeric,
    r0_recovered: optionalNumeric,
    end: optionalNumeric,
    points: integer.nullish(),
  }),
  pcr: z.object({
    n0: numeric,
    efficiency: numeric,
    cycles: integer,
  }),
  monte_carlo_pi: z.object({
    n_samples: integer,
    seed: integer.nullish(),
  }),
  wright_fisher: z.object({
    population_size: integer,
    starting_frequency: numeric,
    generations: integer,
    replicate_runs: integer,
    mutation_rate: optionalNumeric,
    selection_coefficient: optionalNumeric,
    dominance: optionalNumeric,
    seed: integer.nullish(),
  }),
  two_locus_wright_fisher: z.object({
    population_size: integer,
    generations: integer,
    recombination_rate: numeric,
    starting_frequencies: z.array(numeric).length(4),
    replicate_runs: integer,
    mutation_rate: optionalNumeric,
    seed: integer.nullish(),
  }),
  molecular_dynamics: z.object({
    n_particles: integer,
    temperature: numeric,
    timestep: numeric,
    n_steps: integer,
    density: numeric.optional(),
    seed: integer.nullish(),
  }),
  gillespie_ssa: z.object({
    a0: integer,
    k: numeric,
    end: numeric,
    seed: integer.nullish(),
  }),
  gillespie_ssa_bimolecular: z.object({
    a0: integer,
    b0: integer,
    k: numeric,
    end: numeric,
    seed: integer.nullish(),
  }),
  gillespie_ssa_replicates: z.object({
    a0: integer,
    b0: integer.nullish(),
    k: numeric,
    end: numeric,
    n_replicates: z.number().int().min(1).max(1000),
    seed: integer.nullish(),
  }),
  sbml: z.object({
    sbml_string: z.string(),
    start: optionalNumeric,
    end: optionalNumeric,
    points: integer.nullish(),
  }),
};

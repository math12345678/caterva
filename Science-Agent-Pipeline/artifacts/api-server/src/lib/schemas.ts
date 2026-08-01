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
    vmax: numeric,
    s0: numeric,
    end: optionalNumeric,
    points: integer.nullish(),
  }),
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
    seed: integer.nullish(),
  }),
};

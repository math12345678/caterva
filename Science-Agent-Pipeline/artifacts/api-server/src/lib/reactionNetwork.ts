/**
 * A model the caller CONSTRUCTS, instead of one of sixteen names.
 *
 * WHAT THIS REPLACES
 *
 * Caterva's domain set is a closed catalogue, and it is written down four
 * times: `SimulationDomain` here in catervaRunner.ts (16 members),
 * `SUPPORTED_DOMAINS` in llmResolver.ts (13, which TypeScript never checks
 * against the union), `DOMAIN_DEFAULTS` in queryResolver.ts (15), and
 * `DISPATCH` in caterva_runner.py -- kept in agreement by a test rather than
 * by derivation. `SimulationParameterSchemas` is a Record total over the
 * union, so every domain also needs a hand-written Zod schema.
 *
 * A new system therefore costs five coordinated edits, which is why the
 * language model's whole job was picking a name from a list.
 *
 * ONE SCHEMA INSTEAD OF SIXTEEN
 *
 * The schema below validates the SHAPE of any reaction network -- species,
 * parameters, reactions, rate rules -- rather than the parameter list of a
 * particular system. It does not need to know what is being modelled, so it
 * does not grow when the modelling does.
 *
 * WHAT IT DELIBERATELY DOES NOT CHECK
 *
 * Whether the rate laws refer to symbols that exist, whether the
 * stoichiometry is coherent, and whether every quantity is sourced. Those
 * are checked ONCE, in `caterva/core/network.py` and
 * `caterva/core/network_provenance.py`, at the engine boundary.
 *
 * That is deliberate. Re-implementing them here would create a second
 * enforcer of the same rules in a different language, and two enforcers of
 * one rule drift into two rules -- the exact defect the four duplicate
 * domain lists above already demonstrate. This layer's job is to reject
 * malformed JSON early and cheaply; the scientific checks belong where they
 * cannot be bypassed by a caller that reaches the engine another way.
 */

import { z } from "zod";

/**
 * An Antimony identifier, as `caterva/core/network.py` defines one.
 *
 * Kept deliberately strict and in step with the engine: this is the
 * alphabet a rate law is tokenised against there, so a laxer rule here
 * would accept models the engine then refuses, and the caller would get the
 * refusal from the wrong layer with the wrong message.
 */
const Identifier = z
  .string()
  .min(1)
  .max(64)
  .regex(
    /^[A-Za-z_][A-Za-z0-9_]*$/,
    "must be a valid identifier: a letter or underscore, then letters, digits or underscores",
  );

/**
 * Stoichiometric coefficients: species id -> whole number.
 *
 * Integers only. Antimony accepts fractional stoichiometry; Caterva does
 * not, because a fractional coefficient makes the conservation laws derived
 * from the stoichiometry matrix meaningless as counts of anything.
 */
const Stoichiometry = z.record(Identifier, z.number().int().positive());

export const SpeciesSchema = z.object({
  id: Identifier,
  initial: z.number().finite(),
});

export const ParameterSchema = z.object({
  id: Identifier,
  value: z.number().finite(),
});

export const ReactionSchema = z.object({
  id: Identifier,
  reactants: Stoichiometry.default({}),
  products: Stoichiometry.default({}),
  rateLaw: z.string().min(1).max(1_000),
});

export const RateRuleSchema = z.object({
  target: Identifier,
  expression: z.string().min(1).max(1_000),
});

export const AssignmentRuleSchema = z.object({
  target: Identifier,
  expression: z.string().min(1).max(1_000),
});

/**
 * Ceilings mirror the engine's MAX_API_SBML_* limits, which bound the same
 * resource: how much work roadrunner is asked to do. A second set of
 * numbers for the same thing is how two limits drift apart.
 */
export const MAX_NETWORK_SPECIES = 200;
export const MAX_NETWORK_REACTIONS = 200;

export const ReactionNetworkSchema = z
  .object({
    name: Identifier,
    species: z.array(SpeciesSchema).min(1).max(MAX_NETWORK_SPECIES),
    parameters: z.array(ParameterSchema).max(MAX_NETWORK_SPECIES).default([]),
    reactions: z.array(ReactionSchema).max(MAX_NETWORK_REACTIONS).default([]),
    rateRules: z.array(RateRuleSchema).max(MAX_NETWORK_REACTIONS).default([]),
    assignmentRules: z.array(AssignmentRuleSchema).max(64).default([]),
  })
  .refine(
    (n) => n.reactions.length > 0 || n.rateRules.length > 0,
    {
      message:
        "a model needs at least one reaction or rate rule, or nothing can change",
    },
  )
  .refine(
    (n) => n.reactions.length + n.rateRules.length <= MAX_NETWORK_REACTIONS,
    {
      message: `a model may have at most ${MAX_NETWORK_REACTIONS} reactions and rate rules combined`,
    },
  );

/**
 * Where one number came from.
 *
 * The four origins are `provenance.ts`'s `ParameterOrigin`, spelled
 * identically on purpose: two systems enforcing one rule under different
 * vocabularies is how the rule ends up meaning two things.
 *
 * Note what is NOT rejected here: `llm` and `default` are accepted by the
 * schema and refused by the engine. That is on purpose -- a caller who
 * submits an unsourced model should be told which quantities are
 * unsourced, in one message listing all of them, rather than get a shape
 * error naming the first offending field.
 */
export const QuantitySourceSchema = z.object({
  origin: z.enum(["resolved", "user", "llm", "default"]),
  citation: z.string().max(2_000).optional(),
  note: z.string().max(2_000).optional(),
});

export const NetworkRequestSchema = z.object({
  network: ReactionNetworkSchema,
  sources: z.record(Identifier, QuantitySourceSchema).default({}),
  start: z.number().finite().default(0),
  end: z.number().finite().positive().default(10),
  points: z.number().int().positive().max(100_000).default(51),
});

/**
 * One quantity the literature is asked to supply, for `parameterize`.
 *
 * The `quantity` must be an identifier of the network; `subject` is the
 * enzyme the value belongs to. The rest narrow the lookup: which table,
 * which expected unit, which organism, which substrate, and for the
 * enzyme's EC number. None of them are required -- a request with only a
 * quantity and a subject is a legitimate one -- but each that IS present
 * must be a valid identifier-shaped value, because they become lookup
 * fields, not free text.
 */
export const ParameterRequestSchema = z.object({
  quantity: Identifier,
  subject: z.string().max(2_000).optional(),
  substrate: z.string().max(2_000).optional(),
  organism: z.string().max(2_000).optional(),
  ec_number: z.string().max(2_000).optional(),
  table: z.string().max(2_000).optional(),
  expected_unit: z.string().max(2_000).optional(),
});

/**
 * The body of `POST /api/simulate/parameterize`: a network whose constants
 * the caller does NOT already have, and the quantities to look up.
 *
 * The network's values are placeholders -- the structure is what matters,
 * and the literature fills the constants. Physical validation stays in the
 * engine, exactly as `NetworkRequestSchema` keeps it there (see that
 * schema's header: two enforcers of one rule in two languages become two
 * rules).
 */
export const ParameterizeRequestSchema = z.object({
  network: ReactionNetworkSchema,
  requests: z.array(ParameterRequestSchema).min(1, {
    message: "at least one quantity to resolve",
  }),
  sources: z.record(Identifier, QuantitySourceSchema).default({}),
  /** The organism the literature should be searched under. Optional: the
   * search explores every candidate organism when none is named. */
  organism: z.string().max(2_000).optional(),
  start: z.number().finite().default(0),
  end: z.number().finite().positive().default(10),
  points: z.number().int().positive().max(100_000).default(51),
});

export type ReactionNetwork = z.infer<typeof ReactionNetworkSchema>;
export type QuantitySource = z.infer<typeof QuantitySourceSchema>;
export type NetworkRequest = z.infer<typeof NetworkRequestSchema>;
export type ParameterRequest = z.infer<typeof ParameterRequestSchema>;
export type ParameterizeRequest = z.infer<typeof ParameterizeRequestSchema>;

/**
 * Every number a network needs, in declaration order.
 *
 * This is the set the provenance rule must be satisfied over, and it comes
 * from the model rather than from a list. That direction is the whole
 * point: under the per-domain scheme, provenance entries were created only
 * for keys already present in `DOMAIN_DEFAULTS[domain].parameters`, so a
 * parameter the catalogue had never heard of had no entry -- and a key with
 * no entry was not judged. Absence read as consent.
 *
 * The engine enforces this; the function exists here so a caller can be
 * told what is missing BEFORE paying for a subprocess.
 */
export function quantityIds(network: ReactionNetwork): string[] {
  return [
    ...network.species.map((s) => s.id),
    ...network.parameters.map((p) => p.id),
  ];
}

/**
 * Quantities with no source, in declaration order.
 *
 * A convenience for early feedback only. The authoritative refusal is the
 * engine's, and this deliberately does not duplicate its origin rules --
 * it answers "did you forget any?", not "are these acceptable?".
 */
export function unsourcedQuantityIds(
  network: ReactionNetwork,
  sources: Record<string, QuantitySource>,
): string[] {
  return quantityIds(network).filter((id) => !(id in sources));
}

/**
 * Requested quantities the network does not declare, in request order.
 *
 * A request to parameterize says "resolve these constants for me"; each
 * must name a quantity that actually exists in the network. The engine's
 * `ValueError` on `declared - available` is authoritative, but the same
 * sanity check asked here, before the subprocess and the literature search,
 * is the commonest-mistake early refusal -- exactly as
 * `unsourcedQuantityIds` is for the network route.
 */
export function unknownRequestIds(
  network: ReactionNetwork,
  requests: ParameterRequest[],
): string[] {
  const known = new Set(quantityIds(network));
  return requests
    .map((request) => request.quantity)
    .filter((quantity) => !known.has(quantity))
    .filter((quantity, index, all) => all.indexOf(quantity) === index);
}

/**
 * The model proposes STRUCTURE. It may not propose NUMBERS.
 *
 * This is the resolver for the open path: given a description of a system,
 * it asks a language model to construct a reaction network rather than to
 * pick one of thirteen domain names.
 *
 * THE RULE THAT MAKES THIS SAFE
 *
 * A language model is good at the modelling question -- what are the
 * species, what transforms into what, what functional form does the rate
 * take -- and those are choices, arguable in a paper, not measurements. It
 * is exactly the wrong thing to ask for a Km.
 *
 * So the split is enforced, not requested:
 *
 *   - STRUCTURE (species, reactions, rate laws, rate rules) comes from the
 *     model and is checked against the network that owns it by
 *     `Terium/core/network.py`.
 *   - NUMBERS come from the person asking or from literature. A value the
 *     model emits that the user did not state is dropped, and the quantity
 *     is reported as needed.
 *
 * `stripUnstatedValues` below does the dropping, and it does not rely on
 * the model's cooperation: a value is kept only if the model quoted the
 * span of the user's own text that states it, and that span is checked
 * against the query. A model that invents `"quotedFrom"` has to invent a
 * substring of a text it did not write.
 *
 * WHY REFUSAL IS THE USEFUL ANSWER
 *
 * A model with unknown constants is not a failure, it is the ordinary
 * situation at the start of an experiment. The response names the minimal
 * set of quantities that would make the system determined -- which is more
 * useful than a trajectory computed from numbers nobody measured, and is
 * the same discipline `unverifiedOriginKeys` applies to the catalogue path.
 */

import { z } from "zod";

import { logger } from "./logger";
import { requestJsonCompletion } from "./llmResolver";
import {
  ReactionNetworkSchema,
  type QuantitySource,
  type ReactionNetwork,
} from "./reactionNetwork";

/**
 * What the model is asked to return.
 *
 * `values` is separate from the network on purpose. The network the model
 * proposes carries placeholder numbers -- it has to, since the schema needs
 * a number -- and this is where a claim about where a number CAME FROM is
 * made, so that the claim can be checked instead of trusted.
 */
export const ConstructedModelSchema = z.object({
  network: ReactionNetworkSchema,
  reasoning: z.string().max(4_000).default(""),
  values: z
    .array(
      z.object({
        quantity: z.string().min(1).max(64),
        value: z.number().finite(),
        /**
         * The span of the USER's text that states this value.
         *
         * Required. The check below looks for it in the query, so a
         * fabricated attribution has to be a substring of a text the model
         * did not write -- which is a much harder thing to get right by
         * accident than a plausible-looking number.
         */
        quotedFrom: z.string().min(1).max(400),
      }),
    )
    .default([]),
});

export type ConstructedModel = z.infer<typeof ConstructedModelSchema>;

export interface ResolvedNetwork {
  network: ReactionNetwork;
  sources: Record<string, QuantitySource>;
  /** Quantities with no source: what the user must supply for this to run. */
  needed: string[];
  reasoning: string;
  /** Values the model asserted that the query does not support. */
  discarded: { quantity: string; value: number; quotedFrom: string }[];
}

/** Normalise for substring comparison: case and run-length of whitespace. */
function normalise(text: string): string {
  return text.toLowerCase().replace(/\s+/g, " ").trim();
}

/**
 * Keep only the values the user's own text supports.
 *
 * Returns the accepted sources and the discarded claims. Nothing is
 * silently dropped: a discarded value is reported, because a model that
 * repeatedly attributes numbers to text that does not contain them is a
 * fact the operator should be able to see.
 */
export function stripUnstatedValues(
  query: string,
  constructed: ConstructedModel,
): {
  sources: Record<string, QuantitySource>;
  discarded: ResolvedNetwork["discarded"];
  applied: Record<string, number>;
} {
  const haystack = normalise(query);
  const sources: Record<string, QuantitySource> = {};
  const applied: Record<string, number> = {};
  const discarded: ResolvedNetwork["discarded"] = [];

  for (const claim of constructed.values) {
    const quoted = normalise(claim.quotedFrom);
    if (quoted.length > 0 && haystack.includes(quoted)) {
      sources[claim.quantity] = {
        origin: "user",
        note: `stated in the query: "${claim.quotedFrom.trim()}"`,
      };
      applied[claim.quantity] = claim.value;
    } else {
      discarded.push(claim);
    }
  }
  return { sources, discarded, applied };
}

/**
 * The instruction. Written to make the structure/number split explicit,
 * because a model told only "return JSON" will helpfully fill in a Km.
 */
export const NETWORK_SYSTEM_PROMPT = `You construct reaction-network models for a scientific simulation engine.

Return a single JSON object, no prose and no markdown, with this shape:

{
  "network": {
    "name": "<snake_case identifier>",
    "species":    [ { "id": "<identifier>", "initial": <number> } ],
    "parameters": [ { "id": "<identifier>", "value": <number> } ],
    "reactions":  [ { "id": "<identifier>", "reactants": {"<species>": <int>},
                      "products": {"<species>": <int>},
                      "rateLaw": "<expression>" } ],
    "rateRules":  [ { "target": "<species>", "expression": "<expression>" } ],
    "assignmentRules": [ { "target": "<identifier>", "expression": "<expression>" } ]
  },
  "reasoning": "<how you mapped the description onto this network>",
  "values": [ { "quantity": "<id>", "value": <number>, "quotedFrom": "<exact words from the user's message that state this value>" } ]
}

YOUR JOB IS THE STRUCTURE, NOT THE NUMBERS.

Choose the species, the reactions, the stoichiometry and the functional
form of each rate law. Those are modelling decisions and they are what you
are for.

Do NOT supply numeric values from your own knowledge. Not rate constants,
not Michaelis constants, not initial concentrations, not populations. Put a
placeholder of 1 in the "initial"/"value" fields; they are ignored unless
the value also appears in "values".

Only list an entry in "values" when the user's message ITSELF states that
number, and set "quotedFrom" to the exact words from their message that
state it. The quote is checked against their message; a value whose quote
is not found there is discarded. Inventing a quote is worse than omitting
the value, because a value the user must supply is a normal and useful
answer, and a fabricated one is not.

RATE LAW RULES

- Every symbol in a rate law must be a species id or a parameter id you
  declared in the same network.
- Expressions only: + - * / ^ ( ) and the functions abs exp ln log log10
  pow sqrt sin cos tan. No assignment, no semicolons.
- Use a rate rule (X' = ...) when the dynamics are naturally a differential
  equation rather than a transformation of one pool into another -- Hill
  functions, predator-prey terms, and similar.
- Do NOT name a parameter "gamma": the model language reads it as the gamma
  function. Use "gamma_rate".
- A species may be changed by reactions or by a rate rule, never by both.`;

/**
 * Turn a model's reply into a network plus the sources the query supports.
 *
 * Deliberately does NOT call the language model: the caller passes the
 * parsed reply. That keeps this function pure and testable, which matters
 * because the value-stripping rule above is the security boundary of the
 * whole open path and a rule that can only be exercised through a network
 * call is a rule nobody exercises.
 */
export function resolveConstructedModel(
  query: string,
  reply: unknown,
): ResolvedNetwork | null {
  const parsed = ConstructedModelSchema.safeParse(reply);
  if (!parsed.success) {
    logger.warn(
      { issues: parsed.error.errors.slice(0, 5) },
      "constructed model did not match the expected shape",
    );
    return null;
  }

  const constructed = parsed.data;
  const { sources, discarded, applied } = stripUnstatedValues(
    query,
    constructed,
  );

  // Apply the accepted values to the network the model proposed. The
  // placeholders it emitted are overwritten; a quantity with no accepted
  // value keeps its placeholder and is reported as needed, so the number
  // never reaches a trajectory.
  const network: ReactionNetwork = {
    ...constructed.network,
    species: constructed.network.species.map((s) =>
      s.id in applied ? { ...s, initial: applied[s.id]! } : s,
    ),
    parameters: constructed.network.parameters.map((p) =>
      p.id in applied ? { ...p, value: applied[p.id]! } : p,
    ),
  };

  const needed = [
    ...network.species.map((s) => s.id),
    ...network.parameters.map((p) => p.id),
  ].filter((id) => !(id in sources));

  if (discarded.length > 0) {
    logger.warn(
      { discarded, query },
      "discarded model-asserted values whose quotation was not found in the query",
    );
  }

  return {
    network,
    sources,
    needed,
    reasoning: constructed.reasoning,
    discarded,
  };
}

/**
 * The message a user gets when their model is structurally fine and its
 * numbers are not yet known.
 *
 * Names every missing quantity. That list IS the answer: it is the minimal
 * set of measurements that would make the system determined.
 */
export function describeWhatIsNeeded(resolved: ResolvedNetwork): string {
  const { needed, network } = resolved;
  if (needed.length === 0) return "";
  return (
    `Terrium built a model of this system -- ${network.species.length} ` +
    `species, ${network.reactions.length} reaction(s) -- but will not run ` +
    `it until every number in it has a source. ` +
    `${needed.length} quantit${needed.length === 1 ? "y is" : "ies are"} ` +
    `still unknown: ${needed.join(", ")}. ` +
    `Supply them in your query, or resolve them from literature. Terrium ` +
    `does not fill them in: a value nobody measured, plotted next to values ` +
    `somebody did, is the thing this tool exists to refuse.`
  );
}


/**
 * Ask a model to construct a network for this description.
 *
 * Returns null when the model is unavailable or its reply is not a model,
 * exactly as `resolveQueryWithLLM` does: a caller treats null as "no model
 * was produced" and falls back to the catalogue rather than failing.
 *
 * The value-stripping in `resolveConstructedModel` runs on every reply, so
 * a model that ignores the prompt's instruction not to supply numbers gets
 * its numbers discarded rather than believed. That is the point of doing it
 * as a check rather than as a request.
 */
export async function constructNetworkFromQuery(
  query: string,
): Promise<ResolvedNetwork | null> {
  const reply = await requestJsonCompletion(NETWORK_SYSTEM_PROMPT, query);
  if (reply === null) {
    return null;
  }
  const resolved = resolveConstructedModel(query, reply);
  if (resolved === null) {
    logger.warn({ query }, "model reply was not a usable reaction network");
  }
  return resolved;
}

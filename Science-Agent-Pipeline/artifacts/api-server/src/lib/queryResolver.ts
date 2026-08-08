import { randomUUID } from "node:crypto";
import type { SimulationDomain } from "./telluriumRunner";
import { resolveQueryWithLLM, type EntityExtraction } from "./llmResolver";
import { resolveKineticValue } from "./scienceAgent";
import { matchEnzyme } from "./enzymes";
import {
  RESOLVABLE_FIELDS,
  RequiredParametersMissingError,
  buildResolvedKineticProvenance,
  unverifiedOriginKeys,
  isAllDefaults,
  validateParameterProvenance,
  type AssayConditions,
  type ParameterProvenance,
} from "./provenance";
import type { ScienceAgentResult } from "./scienceAgent";

/** Convert the Python runner's assay-conditions payload into the provenance
 * shape. The runner emits JSON `null` for values the source did not report;
 * `AssayConditions` uses absence for the same thing, so nulls are dropped
 * rather than passed through. A null that survived as `null` would be a
 * present-but-empty field, which `strendaStatusFor` would have to guess at.
 *
 * Nothing is defaulted here. If BRENDA did not report a pH, the result has
 * no pH, and the citation degrades to `flagged` downstream. See ADR 0010. */
function toAssayConditions(
  raw: ScienceAgentResult["assayConditions"],
): AssayConditions | undefined {
  if (!raw) return undefined;
  const conditions: AssayConditions = {};
  if (typeof raw.ph === "number" && Number.isFinite(raw.ph)) {
    conditions.ph = raw.ph;
  }
  if (
    typeof raw.temperatureC === "number" &&
    Number.isFinite(raw.temperatureC)
  ) {
    conditions.temperatureC = raw.temperatureC;
  }
  if (typeof raw.buffer === "string" && raw.buffer.trim() !== "") {
    conditions.buffer = raw.buffer;
  }
  return conditions;
}

/**
 * Apply literature resolution for kinetic constants (km, ki) from BRENDA.
 *
 * For `mm` only `km` is resolved. For `mm_competitive_inhibition` both
 * `km` and `ki` are resolved from the same literature lookup. Unresolved
 * values fall back to the defaults already in `parameters`; the provenance
 * records whether the lookup succeeded, was locatable, or failed entirely.
 */
async function applyKineticResolution(
  entities: EntityExtraction | undefined,
  overrides: Record<string, number | number[]>,
  domain: string,
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
  flags: string[],
): Promise<{
  parameters: Record<string, number | number[]>;
  parameterProvenance: Record<string, ParameterProvenance>;
  flags: string[];
}> {
  if (!entities?.ecNumber && !entities?.enzymeName) {
    return { parameters, parameterProvenance, flags };
  }

  const resolvable = RESOLVABLE_FIELDS[domain] ?? [];
  const kineticKeys = resolvable.filter((k) => !(k in overrides));
  if (kineticKeys.length === 0) {
    return { parameters, parameterProvenance, flags };
  }

  // Resolve each quantity independently: the runner reads BRENDA's KM
  // Values table for "km" and its Ki Values table for "ki", so each key
  // gets its own lookup and its own citation (ADR 0008). A cross-species
  // Ki therefore never borrows a verified Km's provenance.
  for (const key of kineticKeys) {
    const agentResult = await resolveKineticValue({
      ...entities,
      quantity: key as "km" | "ki",
    });
    if (!agentResult.found) {
      parameterProvenance = {
        ...parameterProvenance,
        [key]: {
          origin: "default",
          note: `Could not resolve a real ${key.toUpperCase()} value from BRENDA/KEGG/PubMed; using default ${key.toUpperCase()}.`,
        },
      };
      continue;
    }

    const citation = formatResolvedCitation(agentResult.citation);
    if (citation === undefined) {
      parameterProvenance = {
        ...parameterProvenance,
        [key]: {
          origin: "default",
          note: `Found a ${key.toUpperCase()} but its citation carries no locator (ref id or URL); not trusted as resolved — using default ${key.toUpperCase()}.`,
        },
      };
      flags.push(
        `Found a ${key.toUpperCase()} value but its citation was not locatable; using default ${key.toUpperCase()}.`,
      );
      continue;
    }

    const citationStatus =
      agentResult.crossSpecies === true ||
      agentResult.source === "brenda_cross_species"
        ? "flagged"
        : "verified";

    const value = key === "km" ? agentResult.km : agentResult.ki;
    if (value !== undefined) {
      parameters = { ...parameters, [key]: value };
      parameterProvenance = {
        ...parameterProvenance,
        [key]: buildResolvedKineticProvenance({
          source: agentResult.source ?? "unknown",
          citation,
          organism: agentResult.organism,
          citationStatus,
          assayConditions: toAssayConditions(agentResult.assayConditions),
        }),
      };
      flags.push(
        `Resolved ${key.toUpperCase()}=${value} ${agentResult.unit ?? "mM"} from ${agentResult.source ?? "unknown source"}.`,
      );
    } else {
      parameterProvenance = {
        ...parameterProvenance,
        [key]: {
          origin: "default",
          note: `Could not resolve a real ${key.toUpperCase()} value from BRENDA/KEGG/PubMed; using default ${key.toUpperCase()}.`,
        },
      };
    }
  }

  return { parameters, parameterProvenance, flags };
}

/**
 * Apply population genetics parameter resolution from literature.
 * Currently supports mutation_rate for Wright-Fisher domains.
 */
async function applyPopgenResolution(
  entities: EntityExtraction | undefined,
  overrides: Record<string, number | number[]>,
  domain: string,
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
  flags: string[],
): Promise<{
  parameters: Record<string, number | number[]>;
  parameterProvenance: Record<string, ParameterProvenance>;
  flags: string[];
}> {
  const resolvable = RESOLVABLE_FIELDS[domain] ?? [];
  const popgenKeys = resolvable.filter((k) => !(k in overrides));
  if (popgenKeys.length === 0) {
    return { parameters, parameterProvenance, flags };
  }

  // For now, only mutation_rate is supported
  if (popgenKeys.includes("mutation_rate") && entities?.organism) {
    const agentResult = await resolveKineticValue({
      ...entities,
      parameterType: "mutation_rate",
    });

    if (agentResult.found && agentResult.km !== undefined) {
      const value = agentResult.km;
      const citation = formatResolvedCitation(agentResult.citation);
      if (citation !== undefined) {
        parameters = { ...parameters, mutation_rate: value };
        parameterProvenance = {
          ...parameterProvenance,
          mutation_rate: buildResolvedKineticProvenance({
            source: agentResult.source ?? "unknown",
            citation,
            organism: agentResult.organism,
            citationStatus: "verified",
          }),
        };
        flags.push(
          `Resolved mutation_rate=${value} from ${agentResult.source ?? "literature"}.`,
        );
      } else {
        parameterProvenance = {
          ...parameterProvenance,
          mutation_rate: {
            origin: "default",
            note: "Found a mutation_rate value but its citation carries no locator; using default.",
          },
        };
      }
    } else {
      parameterProvenance = {
        ...parameterProvenance,
        mutation_rate: {
          origin: "default",
          note: "Could not resolve a real mutation_rate value from literature; using default.",
        },
      };
    }
  }

  return { parameters, parameterProvenance, flags };
}

export interface ResolvedSimulation {
  runId: string;
  domain: SimulationDomain;
  parameters: Record<string, number | number[]>;
  provenance: {
    reasoning: string;
    modelCitations: string[];
    flags: string[];
  };
  parameterProvenance: Record<string, ParameterProvenance>;
}

interface DomainDefaults {
  domain: SimulationDomain;
  parameters: Record<string, number | number[]>;
  keywords: string[];
  reasoning: string;
  modelCitations: string[];
}

const DOMAIN_DEFAULTS: DomainDefaults[] = [
  {
    domain: "mm_competitive_inhibition",
    parameters: {
      km: 2,
      ki: 1.0,
      vmax: 5,
      s0: 10,
      i0: 0.1,
      end: 10,
      points: 51,
    },
    keywords: [
      "competitive inhibition",
      "competitive",
      "inhibition",
      "inhibitor",
    ],
    reasoning:
      "Keywords related to enzyme kinetics with competitive inhibition were found; defaulting to a Michaelis-Menten competitive inhibition simulation.",
    modelCitations: [
      "BRENDA — The Comprehensive Enzyme Information System, https://www.brenda-enzymes.org/",
    ],
  },
  {
    domain: "mm",
    parameters: { km: 2, vmax: 5, s0: 10, end: 10, points: 51 },
    keywords: [
      "enzyme",
      "michaelis",
      "km",
      "vmax",
      "substrate",
      "ldh",
      "pyruvate",
      "lactate",
      "hexokinase",
      "catalase",
      "alcohol dehydrogenase",
      "trypsin",
      "rubisco",
      "kinase",
    ],
    reasoning:
      "Keywords related to enzyme kinetics were found; defaulting to a Michaelis-Menten simulation.",
    modelCitations: [
      "BRENDA — The Comprehensive Enzyme Information System, https://www.brenda-enzymes.org/",
    ],
  },
  {
    domain: "sir",
    parameters: {
      beta: 0.3,
      gamma: 0.1,
      s0: 990,
      i0: 10,
      r0_recovered: 0,
      end: 100,
      points: 101,
    },
    keywords: ["sir", "infection", "epidemic", "virus", "disease", "outbreak"],
    reasoning:
      "Keywords related to infectious disease spread were found; defaulting to an SIR epidemic simulation.",
    modelCitations: [
      "Kermack W.O., McKendrick A.G. (1927) A contribution to the mathematical theory of epidemics. Proceedings of the Royal Society A 115(772), 700-721.",
    ],
  },
  {
    domain: "seir",
    parameters: {
      beta: 0.3,
      sigma: 0.2,
      gamma: 0.1,
      s0: 990,
      e0: 10,
      i0: 0,
      r0_recovered: 0,
      end: 100,
      points: 101,
    },
    keywords: ["seir", "exposed", "latent", "incubation"],
    reasoning:
      "Keywords related to latent-period epidemiology were found; defaulting to an SEIR simulation.",
    modelCitations: [
      "Kermack W.O., McKendrick A.G. (1927) A contribution to the mathematical theory of epidemics. Proceedings of the Royal Society A 115(772), 700-721.",
    ],
  },
  {
    domain: "pcr",
    parameters: { n0: 100, efficiency: 0.95, cycles: 30 },
    keywords: [
      "pcr",
      "polymerase chain",
      "amplification",
      "template",
      "cycles",
    ],
    reasoning:
      "PCR amplification keywords were found; defaulting to a discrete PCR simulation.",
    modelCitations: [
      "Mullis K., Faloona F., Scharf S., Saiki R., Horn G., Erlich H. (1986) Specific enzymatic amplification of DNA in vitro: the polymerase chain reaction. Cold Spring Harbor Symposia on Quantitative Biology 51, 263-273.",
    ],
  },
  {
    domain: "monte_carlo_pi",
    parameters: { n_samples: 10_000 },
    keywords: ["monte carlo", "estimate pi", "pi estimate", "random points"],
    reasoning:
      "Monte Carlo estimation keywords were found; defaulting to pi estimation.",
    modelCitations: [
      "Metropolis N., Ulam S. (1949) The Monte Carlo method. Journal of the American Statistical Association 44(247), 335-341.",
    ],
  },
  {
    domain: "wright_fisher",
    parameters: {
      population_size: 100,
      starting_frequency: 0.5,
      generations: 100,
      replicate_runs: 100,
      mutation_rate: 0,
      selection_coefficient: 0,
    },
    keywords: [
      "wright-fisher",
      "genetic drift",
      "allele frequency",
      "population genetics",
      "fixation",
    ],
    reasoning:
      "Population-genetics keywords were found; defaulting to a Wright-Fisher simulation.",
    // The model carries both names; citing only Fisher attributes half of it.
    modelCitations: [
      "Fisher R.A. (1930) The Genetical Theory of Natural Selection. Oxford: Clarendon Press.",
      "Wright S. (1931) Evolution in Mendelian populations. Genetics 16(2), 97-159.",
    ],
  },
  {
    domain: "two_locus_wright_fisher",
    parameters: {
      population_size: 100,
      generations: 20,
      recombination_rate: 0.1,
      starting_frequencies: [0.5, 0, 0, 0.5],
      mutation_rate: 0,
      replicate_runs: 50,
    },
    keywords: [
      "linkage disequilibrium",
      "two locus",
      "two-locus",
      "recombination",
      "haplotype",
    ],
    reasoning:
      "Linkage and recombination keywords were found; defaulting to a two-locus Wright-Fisher simulation.",
    modelCitations: [
      "Lewontin R.C. (1964) The interaction of selection and linkage. I. General considerations; heterotic models. Genetics 49(1), 49-67.",
    ],
  },
  {
    domain: "molecular_dynamics",
    parameters: {
      n_particles: 108,
      temperature: 0.4,
      timestep: 0.005,
      n_steps: 1000,
      density: 0.85,
    },
    keywords: [
      "molecular dynamics",
      "lennard-jones",
      "lennard jones",
      "lj cluster",
      "particles",
    ],
    reasoning:
      "Molecular-dynamics keywords were found; defaulting to a Lennard-Jones simulation.",
    modelCitations: [
      "Hoare M.R., Pal P. (1971) Physical cluster mechanics: statics and energy surfaces for monatomic systems. Advances in Physics 20(84), 161-196.",
    ],
  },
  {
    domain: "gillespie_ssa_replicates",
    parameters: { a0: 100, k: 0.5, end: 10, n_replicates: 100 },
    keywords: ["replicates", "many seeds", "multiple runs", "ensemble"],
    reasoning:
      "Keywords related to repeated independent runs were found; defaulting to a Gillespie SSA ensemble view over n_replicates seeded trajectories.",
    modelCitations: [
      "Gillespie D.T. (1977) Exact stochastic simulation of coupled chemical reactions. The Journal of Physical Chemistry 81(25), 2340-2361.",
    ],
  },
  {
    domain: "gillespie_ssa_bimolecular",
    parameters: { a0: 100, b0: 100, k: 0.005, end: 10 },
    keywords: [
      "bimolecular",
      "second order",
      "second-order",
      "association",
      "two reactants",
      "a + b",
      "a plus b",
      "binding",
    ],
    reasoning:
      "Keywords related to a two-reactant association were found; defaulting to a Gillespie SSA simulation of the bimolecular reaction A + B -> C.",
    modelCitations: [
      "Gillespie D.T. (1977) Exact stochastic simulation of coupled chemical reactions. The Journal of Physical Chemistry 81(25), 2340-2361.",
    ],
  },
  {
    domain: "gillespie_ssa",
    parameters: { a0: 1000, k: 0.5, end: 10 },
    keywords: [
      "gillespie",
      "stochastic",
      "ssa",
      "chemical master equation",
      "decay",
      "reaction",
      "random walk",
      "birth-death",
    ],
    reasoning:
      "Keywords related to stochastic chemical kinetics were found; defaulting to a Gillespie SSA simulation of a single first-order decay reaction.",
    modelCitations: [
      "Gillespie D.T. (1977) Exact stochastic simulation of coupled chemical reactions. The Journal of Physical Chemistry 81(25), 2340-2361.",
    ],
  },
];

const PARAMETER_NAMES =
  "km|ki|vmax|kcat|enzyme_conc|s0|beta|gamma|sigma|e0|i0|r0|r0_recovered|end|points|n0|efficiency|cycles|n_samples|population_size|starting_frequency|starting_frequencies|generations|replicate_runs|mutation_rate|selection_coefficient|recombination_rate|n_particles|temperature|timestep|n_steps|density|a0|b0|k|n_replicates|seed";

/**
 * Matches a parameter token: the key name, an optional `=` or `:`
 * delimiter, and the value portion (which may be a scalar or a
 * comma-separated array).
 */
const PARAMETER_TOKEN_PATTERN = new RegExp(
  `^(${PARAMETER_NAMES})\\s*[=:]\\s*(.+)$`,
  "i",
);

/** Scalar: km=5, vmax 10, beta = 0.4 */
const PARAMETER_PATTERN = new RegExp(
  `(${PARAMETER_NAMES})\\s*[=:]?\\s*([0-9]+(?:\\.[0-9]+)?(?:e[+-]?[0-9]+)?)`,
  "i",
);

/**
 * Validation errors for malformed array overrides.
 */
export class ArrayOverrideValidationError extends Error {
  constructor(
    public readonly key: string,
    message: string,
  ) {
    super(message);
    this.name = "ArrayOverrideValidationError";
  }
}

/**
 * Parse a single comma-separated value string into a number array.
 * Returns undefined if the string contains no commas (meaning it should
 * be treated as a scalar, not an array).
 *
 * For array parameters, validation happens in `validateArrayOverride()`
 * after parsing — this function only extracts the raw numbers.
 */
function parseArrayValue(raw: string): number[] | undefined {
  const trimmed = raw.replace(/^\[|\]$/g, "").trim();
  if (!trimmed.includes(",")) return undefined;
  const parts = trimmed.split(",").map((s) => s.trim());
  if (parts.length === 0 || parts.some((s) => s === "")) return undefined;
  const nums = parts.map((s) => Number.parseFloat(s));
  if (!nums.every((n) => Number.isFinite(n))) return undefined;
  return nums;
}

/**
 * Known array-valued parameters and their validation constraints.
 *
 * Each entry specifies:
 *  - `length`: exact number of elements required
 *  - `sumTo`: if set, the elements must sum to this value within tolerance
 *  - `tolerance`: float tolerance for the sum check (default 1e-6)
 *
 * Mutation-test note (Rule 6): the sum tolerance is guarded by the array
 * override suite. Mutating `1e-6` -> `1e6` is caught by 4 tests across
 * arrayOverride.test.ts, provenance.test.ts, and queryOverrides.test.ts
 * ("rejects ... that sum to 0.9" / "do not sum to 1" / "rejects array that
 * doesn't sum to 1" / "rejects sum!=1"); the mutation was run and reverted.
 */
const ARRAY_VALIDATORS: Record<
  string,
  { length: number; sumTo?: number; tolerance?: number }
> = {
  starting_frequencies: { length: 4, sumTo: 1, tolerance: 1e-6 },
};

/**
 * Validate an array override against its declared constraints.
 * Throws `ArrayOverrideValidationError` with a clear, actionable message
 * if validation fails.
 */
function validateArrayOverride(key: string, arr: number[]): void {
  const spec = ARRAY_VALIDATORS[key];
  if (!spec) {
    throw new ArrayOverrideValidationError(
      key,
      `'${key}' is not an array-valued parameter. ` +
        `Remove the commas or use a valid array parameter.`,
    );
  }

  if (arr.length !== spec.length) {
    throw new ArrayOverrideValidationError(
      key,
      `${key} must have exactly ${spec.length} values (${arr.length} provided). ` +
        `Example: ${key}=${Array(spec.length).fill("0.25").join(",")}`,
    );
  }

  if (spec.sumTo !== undefined) {
    const sum = arr.reduce((a, b) => a + b, 0);
    const tolerance = spec.tolerance ?? 1e-6;
    if (Math.abs(sum - spec.sumTo) > tolerance) {
      throw new ArrayOverrideValidationError(
        key,
        `${key} values must sum to ${spec.sumTo} (got ${sum.toPrecision(6)}). ` +
          `Haplotype frequencies must sum to 1.0.`,
      );
    }
  }
}

/**
 * Extract numeric overrides from the query string.
 *
 * Supports both scalar and array-valued parameters:
 *   - Scalar: "km=5", "vmax 10", "beta = 0.4"
 *   - Array:  "starting_frequencies=0.5,0,0,0.5"
 *            "starting_frequencies=[0.5,0,0,0.5]"
 *
 * Array syntax requires `=` or `:` so it cannot be confused with a scalar
 * followed by unrelated text.
 */
export function extractParameterOverrides(
  query: string,
): Record<string, number | number[]> {
  const overrides: Record<string, number | number[]> = {};

  // --- Array overrides: scan the RAW query first -------------------------
  //
  // Tokenization splits on whitespace, which breaks `key=a, b, c, d` apart
  // into `key=a,` `b,` `c,` `d`. Scanning the raw query with a dedicated
  // pattern captures the full comma-separated group regardless of spaces.
  const arrayKeys = new Set<string>();
  for (const [key, spec] of Object.entries(ARRAY_VALIDATORS)) {
    const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
    const arrayRe = new RegExp(
      `${escapedKey}\\s*[=:]\\s*\\[?([0-9]+(?:\\.[0-9]+)?(?:e[+-]?[0-9]+)?(?:\\s*,\\s*[0-9]+(?:\\.[0-9]+)?(?:e[+-]?[0-9]+)?)+)\\]?`,
      "i",
    );
    const m = arrayRe.exec(query);
    if (m) {
      const arr = parseArrayValue(m[1]!);
      if (arr !== undefined) {
        validateArrayOverride(key, arr);
        overrides[key] = arr;
        arrayKeys.add(key);
      }
    }
  }

  // --- Scalar / token-based extraction ----------------------------------
  //
  // Keys already captured as arrays are skipped so a partial token
  // (e.g. `starting_frequencies=0.5,` from a space-split list) cannot
  // overwrite the validated array with a scalar.
  for (const token of query.split(/\s+/)) {
    // Try key=value or key:value pattern first
    const kvMatch = PARAMETER_TOKEN_PATTERN.exec(token);
    if (kvMatch) {
      const key = kvMatch[1]!.toLowerCase();
      if (arrayKeys.has(key)) continue;

      const rawValue = kvMatch[2]!;

      // If the value contains commas or brackets, it MUST be an array.
      // Do not fall back to scalar — a malformed array is rejected.
      if (rawValue.includes(",") || /\[/.test(rawValue)) {
        const arr = parseArrayValue(rawValue);
        if (arr !== undefined) {
          validateArrayOverride(key, arr);
          overrides[key] = arr;
        } else {
          throw new ArrayOverrideValidationError(
            key,
            `'${key}' value '${rawValue}' is not a valid comma-separated number list. ` +
              `Example: ${key}=0.5,0,0,0.5`,
          );
        }
        continue;
      }

      // Scalar parse — but only if this key is not an array parameter.
      // An array parameter supplied without commas (e.g. starting_frequencies=0.5)
      // is malformed and must be rejected, not silently accepted as a scalar.
      if (ARRAY_VALIDATORS[key] === undefined) {
        const value = Number.parseFloat(rawValue);
        if (Number.isFinite(value)) {
          overrides[key] = value;
          continue;
        }
      } else {
        // Array parameter supplied as scalar — reject with actionable message.
        throw new ArrayOverrideValidationError(
          key,
          `'${key}' requires a comma-separated list (e.g. ${key}=0.5,0,0,0.5), ` +
            `not a single number.`,
        );
      }
    }

    // Fallback: try scalar match without explicit delimiter (e.g. "km 5")
    const scalarMatch = PARAMETER_PATTERN.exec(token);
    if (scalarMatch) {
      const key = scalarMatch[1]!.toLowerCase();
      if (arrayKeys.has(key)) continue;
      const value = Number.parseFloat(scalarMatch[2]!);
      if (Number.isFinite(value)) {
        overrides[key] = value;
      }
    }
  }

  return overrides;
}

/**
 * Words that are never themselves the name of the enzyme being asked
 * about -- either generic query scaffolding, or (derived below) one of the
 * single words making up a DOMAIN_DEFAULTS keyword phrase (e.g.
 * "competitive"/"inhibition" from "competitive inhibition").
 */
const QUERY_CONNECTOR_WORDS = new Set([
  "simulate", "run", "the", "a", "an", "of", "for", "please", "with",
  "and", "to", "in", "on", "model", "reaction", "compute", "calculate",
  "show", "me", "kinetics", "kinetic", "using", "via", "estimate", "study",
  "analyze", "analyse", "dynamics", "system", "process",
]);

let cachedDomainKeywordWords: Set<string> | undefined;
function domainKeywordWords(): Set<string> {
  if (!cachedDomainKeywordWords) {
    cachedDomainKeywordWords = new Set(
      DOMAIN_DEFAULTS.flatMap((d) => d.keywords.flatMap((k) => k.split(/\s+/))),
    );
  }
  return cachedDomainKeywordWords;
}

/**
 * Best-effort enzyme-name guess from free text, used only when the
 * hardcoded `enzymes.ts` pattern list doesn't match anything.
 *
 * This is NOT a real named-entity extractor -- it strips known query
 * scaffolding and domain-routing keywords and returns whatever text is
 * left. It can guess wrong (e.g. it will mis-extract a genuinely novel
 * enzyme name that happens to share a word with a domain keyword, like
 * "kinase"). That is an acceptable failure mode here specifically because
 * the guess is never treated as ground truth: it is handed to a live
 * UniProt name search (science_agent_runner.py), which either resolves a
 * real EC number or comes back honestly empty. A wrong guess costs one
 * failed lookup; it never fabricates a parameter value.
 */
function guessEnzymeNameFromQuery(query: string): string | undefined {
  const domainWords = domainKeywordWords();
  const words = query
    .split(/\s+/)
    .filter((token) => !PARAMETER_TOKEN_PATTERN.test(token) && !PARAMETER_PATTERN.test(token))
    .join(" ")
    .toLowerCase()
    .replace(/[^a-z0-9\s-]/g, " ")
    .split(/\s+/)
    .filter((w) => w && !QUERY_CONNECTOR_WORDS.has(w) && !domainWords.has(w));
  if (words.length === 0) return undefined;
  return words.join(" ");
}

/**
 * Fallback entity extraction when no LLM is configured (or the LLM path
 * didn't run).
 *
 * First tries the hardcoded `enzymes.ts` pattern list -- fast, and already
 * carries a verified EC number/substrate/organism with no network round
 * trip. If that list doesn't match, this used to give up entirely, which
 * meant only those ~30 enzymes could ever reach a real BRENDA lookup.
 * Instead it now falls through to a best-effort name guess with no EC
 * number; `resolveKineticValue` (scienceAgent.ts) passes that name to the
 * Python bridge, which resolves an EC number for it live via UniProt
 * before attempting BRENDA -- see science_agent_runner.py::resolve_ec_number.
 */
function extractEntitiesFromQuery(query: string): EntityExtraction | undefined {
  const matched = matchEnzyme(query);
  if (matched) {
    const lower = query.toLowerCase();
    const substrate =
      matched.substrates.find((s) => lower.includes(s)) ?? matched.substrates[0]!;
    return {
      enzymeName: matched.enzymeName,
      substrate,
      organism: matched.organism,
      ecNumber: matched.ecNumber,
    };
  }

  const guess = guessEnzymeNameFromQuery(query);
  if (!guess) return undefined;
  return {
    enzymeName: guess,
    substrate: "",
    organism: "Homo sapiens",
    ecNumber: undefined,
  };
}

/**
 * Per-parameter provenance for a fully merged parameter set.
 *
 * - Keys explicitly supplied in the query text -> origin "user".
 * - Keys supplied by the LLM resolver -> origin "default" with a note that
 *   they were not verified against literature.
 * - Everything else -> origin "default". In a domain that HAS
 *   literature-resolvable fields (RESOLVABLE_FIELDS), a default whose key
 *   is not among them states the narrowness explicitly (Stage 5 Part 5):
 *   it is a teaching default by decision, not by a failed lookup.
 */
function buildParameterProvenance(
  parameters: Record<string, number | number[]>,
  overrides: Record<string, number | number[]>,
  llmSupplied: Record<string, number | number[]>,
  domain: string,
): Record<string, ParameterProvenance> {
  const resolvable = RESOLVABLE_FIELDS[domain] ?? [];
  const provenance: Record<string, ParameterProvenance> = {};
  for (const key of Object.keys(parameters)) {
    if (key in overrides) {
      provenance[key] = { origin: "user" };
    } else if (key in llmSupplied) {
      // Not `default`: a default is a value this project chose and
      // documented, whereas this is a number a language model produced from
      // a prompt. Labelling the two the same way overstates the second and
      // understates nothing -- see ADR 0011.
      provenance[key] = {
        origin: "llm",
        note: "Value supplied by the LLM resolver; not verified against literature.",
      };
    } else if (resolvable.length > 0 && !resolvable.includes(key)) {
      provenance[key] = {
        origin: "default",
        note: `No literature lookup exists for ${key}; only ${resolvable.join(", ")} is resolved from literature in this domain.`,
      };
    } else {
      provenance[key] = { origin: "default" };
    }
  }
  return provenance;
}

function provenanceViolations(
  parameters: Record<string, number | number[]>,
  parameterProvenance: Record<string, ParameterProvenance>,
): string[] {
  return validateParameterProvenance(
    parameters as Record<string, unknown>,
    parameterProvenance,
  );
}

/**
 * Resolve a natural-language query to a simulation domain and parameters.
 *
 * The resolver tries an LLM first (if an API key is configured). If the LLM
 * is unavailable or returns bad output, it falls back to deterministic keyword
 * matching, regex parameter extraction, and a small hardcoded enzyme map. This
 * makes the pipeline robust whether or not an LLM provider is configured.
 *
 * For Michaelis-Menten queries, the resolver can also call the real science
 * agent (BRENDA/KEGG/PubMed) to fetch literature-backed Km values when an EC
 * number is available.
 */
/**
 * Build the citation string attached to a resolved parameter value.
 *
 * Stage 5 Part 1 strictness: a resolved citation must be locatable — a ref id
 * (other than the "n/a" placeholder) or a URL. Returns undefined when the
 * citation is missing or carries no locator, so the caller degrades honestly
 * instead of emitting a locator-shaped string like "BRENDA (ref n/a)" that
 * locates nothing.
 */
function formatResolvedCitation(citation?: {
  source?: string;
  referenceId?: string | null;
  url?: string | null;
}): string | undefined {
  if (!citation?.source) return undefined;
  const hasRef =
    citation.referenceId !== undefined && citation.referenceId !== null;
  const hasUrl = citation.url !== undefined && citation.url !== null;
  if (!hasRef && !hasUrl) return undefined;
  const refPart = hasRef ? ` (ref ${citation.referenceId})` : "";
  const urlPart = hasUrl ? ` — ${citation.url}` : "";
  return `${citation.source}${refPart}${urlPart}`;
}

export async function resolveQuery(query: string): Promise<ResolvedSimulation> {
  const overrides = extractParameterOverrides(query);

  // Try the LLM first. If it fails or is not configured, we fall through to
  // the deterministic resolver below.
  const llmResult = await resolveQueryWithLLM(query);

  if (llmResult) {
    const domainDefaults =
      DOMAIN_DEFAULTS.find((d) => d.domain === llmResult.domain) ||
      DOMAIN_DEFAULTS[0]!;
    let parameters = {
      ...domainDefaults.parameters,
      ...llmResult.parameters,
      ...overrides,
    };
    let flags: string[] = [];
    const modelCitations = [...llmResult.modelCitations];
    let parameterProvenance = buildParameterProvenance(
      parameters,
      overrides,
      llmResult.parameters,
      llmResult.domain,
    );

    const resolvableForDomain = RESOLVABLE_FIELDS[llmResult.domain] ?? [];
    const hasUnoverriddenKinetic = resolvableForDomain.some(
      (k) => !(k in overrides),
    );
    if (
      (llmResult.domain === "mm" ||
        llmResult.domain === "mm_competitive_inhibition") &&
      (llmResult.entities?.ecNumber || llmResult.entities?.enzymeName) &&
      hasUnoverriddenKinetic
    ) {
      const result = await applyKineticResolution(
        llmResult.entities,
        overrides,
        llmResult.domain,
        parameters,
        parameterProvenance,
        flags,
      );
      parameters = result.parameters;
      parameterProvenance = result.parameterProvenance;
      flags = result.flags;
    }

    // Population genetics parameter resolution for LLM path
    if (llmResult.domain === "wright_fisher" || llmResult.domain === "two_locus_wright_fisher") {
      const popgenResult = await applyPopgenResolution(
        llmResult.entities,
        overrides,
        llmResult.domain,
        parameters,
        parameterProvenance,
        flags,
      );
      parameters = popgenResult.parameters;
      parameterProvenance = popgenResult.parameterProvenance;
      flags = popgenResult.flags;
    }

    if (
      Object.keys(overrides).length === 0 &&
      Object.keys(llmResult.parameters).length === 0
    ) {
      flags.push(
        "No parameters were extracted from the query; using defaults.",
      );
    }
    if (Object.keys(overrides).length > 0) {
      flags.push("Applied parameter overrides found in the query string.");
    }
    const violations = provenanceViolations(parameters, parameterProvenance);
    if (violations.length > 0) {
      throw new Error(
        `Internal error: invalid parameter provenance: ${violations.join("; ")}`,
      );
    }

    if (isAllDefaults(parameterProvenance)) {
      flags.push(
        "No parameter values were resolved from literature; all values are defaults.",
      );
    }

    const missing = unverifiedOriginKeys(parameterProvenance);
    if (missing.length > 0) {
      throw new RequiredParametersMissingError(llmResult.domain, missing);
    }

    return {
      runId: randomUUID(),
      domain: llmResult.domain,
      parameters,
      provenance: {
        reasoning: llmResult.reasoning,
        modelCitations,
        flags,
      },
      parameterProvenance,
    };
  }

  const lower = query.toLowerCase();

  let best: DomainDefaults | undefined;
  for (const candidate of DOMAIN_DEFAULTS) {
    if (candidate.keywords.some((keyword) => lower.includes(keyword))) {
      best = candidate;
      break;
    }
  }

  if (!best) {
    best =
      DOMAIN_DEFAULTS.find((d) => d.domain === "mm") ?? DOMAIN_DEFAULTS[0]!;
  }

  let parameters = { ...best.parameters, ...overrides };
  let flags: string[] = [];
  let parameterProvenance = buildParameterProvenance(
    parameters,
    overrides,
    {},
    best.domain,
  );

  // If this looks like an enzyme query and no LLM is available, try the
  // hardcoded entity map and the science agent.
  const fallbackEntities = extractEntitiesFromQuery(query);
  const resolvableForDomain = RESOLVABLE_FIELDS[best.domain] ?? [];
  const hasUnoverriddenKinetic = resolvableForDomain.some(
    (k) => !(k in overrides),
  );
  if (
    (best.domain === "mm" || best.domain === "mm_competitive_inhibition") &&
    (fallbackEntities?.ecNumber || fallbackEntities?.enzymeName) &&
    hasUnoverriddenKinetic
  ) {
    const result = await applyKineticResolution(
      fallbackEntities,
      overrides,
      best.domain,
      parameters,
      parameterProvenance,
      flags,
    );
    parameters = result.parameters;
    parameterProvenance = result.parameterProvenance;
    flags = result.flags;
  }

  // Population genetics parameter resolution (e.g., mutation_rate for Wright-Fisher)
  if (best.domain === "wright_fisher" || best.domain === "two_locus_wright_fisher") {
    const popgenResult = await applyPopgenResolution(
      fallbackEntities,
      overrides,
      best.domain,
      parameters,
      parameterProvenance,
      flags,
    );
    parameters = popgenResult.parameters;
    parameterProvenance = popgenResult.parameterProvenance;
    flags = popgenResult.flags;
  }

  if (Object.keys(overrides).length === 0) {
    flags.push("No parameters were extracted from the query; using defaults.");
  }
  if (Object.keys(overrides).length > 0) {
    flags.push("Applied parameter overrides found in the query string.");
  }
  const violations = provenanceViolations(parameters, parameterProvenance);
  if (violations.length > 0) {
    throw new Error(
      `Internal error: invalid parameter provenance: ${violations.join("; ")}`,
    );
  }

  if (isAllDefaults(parameterProvenance)) {
    flags.push(
      "No parameter values were resolved from literature; all values are defaults.",
    );
  }

  // Hard-block: no default- or llm-origin parameter may reach the simulation engine.
  const missing = unverifiedOriginKeys(parameterProvenance);
  if (missing.length > 0) {
    throw new RequiredParametersMissingError(best.domain, missing);
  }

  return {
    runId: randomUUID(),
    domain: best.domain,
    parameters,
    provenance: {
      reasoning: best.reasoning,
      modelCitations: best.modelCitations,
      flags,
    },
    parameterProvenance,
  };
}

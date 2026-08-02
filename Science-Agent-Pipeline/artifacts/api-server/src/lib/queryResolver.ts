import { randomUUID } from "node:crypto";
import type { SimulationDomain } from "./telluriumRunner";
import { resolveQueryWithLLM, type EntityExtraction } from "./llmResolver";
import { resolveKineticValue } from "./scienceAgent";
import { matchEnzyme } from "./enzymes";
import {
  RESOLVABLE_FIELDS,
  isAllDefaults,
  validateParameterProvenance,
  type ParameterProvenance,
} from "./provenance";

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
    domain: "mm",
    parameters: { km: 2, vmax: 5, s0: 10, end: 10, points: 51 },
    keywords: ["enzyme", "michaelis", "km", "vmax", "substrate", "ldh", "pyruvate", "lactate",
      "hexokinase", "catalase", "alcohol dehydrogenase", "trypsin", "rubisco", "kinase"],
    reasoning:
      "Keywords related to enzyme kinetics were found; defaulting to a Michaelis-Menten simulation.",
    modelCitations: [
      "BRENDA — The Comprehensive Enzyme Information System, https://www.brenda-enzymes.org/",
    ],
  },
  {
    domain: "sir",
    parameters: { beta: 0.3, gamma: 0.1, s0: 990, i0: 10, r0_recovered: 0, end: 100, points: 101 },
    keywords: ["sir", "infection", "epidemic", "virus", "disease", "outbreak"],
    reasoning:
      "Keywords related to infectious disease spread were found; defaulting to an SIR epidemic simulation.",
    modelCitations: [
      "Kermack W.O., McKendrick A.G. (1927) A contribution to the mathematical theory of epidemics. Proceedings of the Royal Society A 115(772), 700-721.",
    ],
  },
  {
    domain: "seir",
    parameters: { beta: 0.3, sigma: 0.2, gamma: 0.1, s0: 990, e0: 10, i0: 0, r0_recovered: 0, end: 100, points: 101 },
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
    keywords: ["pcr", "polymerase chain", "amplification", "template", "cycles"],
    reasoning: "PCR amplification keywords were found; defaulting to a discrete PCR simulation.",
    modelCitations: [
      "Mullis K., Faloona F., Scharf S., Saiki R., Horn G., Erlich H. (1986) Specific enzymatic amplification of DNA in vitro: the polymerase chain reaction. Cold Spring Harbor Symposia on Quantitative Biology 51, 263-273.",
    ],
  },
  {
    domain: "monte_carlo_pi",
    parameters: { n_samples: 10_000 },
    keywords: ["monte carlo", "estimate pi", "pi estimate", "random points"],
    reasoning: "Monte Carlo estimation keywords were found; defaulting to pi estimation.",
    modelCitations: [
      "Metropolis N., Ulam S. (1949) The Monte Carlo method. Journal of the American Statistical Association 44(247), 335-341.",
    ],
  },
  {
    domain: "wright_fisher",
    parameters: { population_size: 100, starting_frequency: 0.5, generations: 100, replicate_runs: 100, mutation_rate: 0, selection_coefficient: 0 },
    keywords: ["wright-fisher", "genetic drift", "allele frequency", "population genetics", "fixation"],
    reasoning: "Population-genetics keywords were found; defaulting to a Wright-Fisher simulation.",
    // The model carries both names; citing only Fisher attributes half of it.
    modelCitations: [
      "Fisher R.A. (1930) The Genetical Theory of Natural Selection. Oxford: Clarendon Press.",
      "Wright S. (1931) Evolution in Mendelian populations. Genetics 16(2), 97-159.",
    ],
  },
  {
    domain: "two_locus_wright_fisher",
    parameters: { population_size: 100, generations: 20, recombination_rate: 0.1, starting_frequencies: [0.5, 0, 0, 0.5], mutation_rate: 0, replicate_runs: 50 },
    keywords: ["linkage disequilibrium", "two locus", "two-locus", "recombination", "haplotype"],
    reasoning: "Linkage and recombination keywords were found; defaulting to a two-locus Wright-Fisher simulation.",
    modelCitations: [
      "Lewontin R.C. (1964) The interaction of selection and linkage. I. General considerations; heterotic models. Genetics 49(1), 49-67.",
    ],
  },
  {
    domain: "molecular_dynamics",
    parameters: { n_particles: 108, temperature: 0.4, timestep: 0.005, n_steps: 1000, density: 0.85 },
    keywords: ["molecular dynamics", "lennard-jones", "lennard jones", "lj cluster", "particles"],
    reasoning: "Molecular-dynamics keywords were found; defaulting to a Lennard-Jones simulation.",
    modelCitations: [
      "Hoare M.R., Pal P. (1971) Physical cluster mechanics: statics and energy surfaces for monatomic systems. Advances in Physics 20(84), 161-196.",
    ],
  },
];

const PARAMETER_PATTERN = /(km|vmax|s0|beta|gamma|sigma|e0|i0|r0|end|points|n0|efficiency|cycles|n_samples|population_size|starting_frequency|generations|replicate_runs|mutation_rate|selection_coefficient|recombination_rate|n_particles|temperature|timestep|n_steps|density)\s*[=:]?\s*([0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?)/i;

/**
 * Extract numeric overrides from the query string.
 *
 * Looks for patterns like "km=5", "vmax 10", "beta = 0.4" and returns them
 * as a record. This is intentionally simple; OpenCode can later replace it
 * with an LLM-based extractor.
 */
function extractParameterOverrides(query: string): Record<string, number> {
  const overrides: Record<string, number> = {};

  for (const token of query.split(/\s+/)) {
    const match = PARAMETER_PATTERN.exec(token);
    if (match) {
      const key = match[1]!.toLowerCase();
      const value = Number.parseFloat(match[2]!);
      overrides[key] = value;
    }
  }

  return overrides;
}

/**
 * Fallback entity extraction for common enzymes. This keeps the pipeline
 * useful when no LLM is configured.
 */
function extractEntitiesFromQuery(query: string): EntityExtraction | undefined {
  const matched = matchEnzyme(query);
  if (!matched) return undefined;

  const lower = query.toLowerCase();
  const substrate = matched.substrates.find((s) => lower.includes(s)) ?? matched.substrates[0]!;
  return {
    enzymeName: matched.enzymeName,
    substrate,
    organism: matched.organism,
    ecNumber: matched.ecNumber,
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
  overrides: Record<string, number>,
  llmSupplied: Record<string, number | number[]>,
  domain: string,
): Record<string, ParameterProvenance> {
  const resolvable = RESOLVABLE_FIELDS[domain] ?? [];
  const provenance: Record<string, ParameterProvenance> = {};
  for (const key of Object.keys(parameters)) {
    if (key in overrides) {
      provenance[key] = { origin: "user" };
    } else if (key in llmSupplied) {
      provenance[key] = {
        origin: "default",
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
  const hasRef = citation.referenceId !== undefined && citation.referenceId !== null;
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
      DOMAIN_DEFAULTS.find((d) => d.domain === llmResult.domain) || DOMAIN_DEFAULTS[0]!;
    let parameters = { ...domainDefaults.parameters, ...llmResult.parameters, ...overrides };
    const flags: string[] = [];
    const modelCitations = [...llmResult.modelCitations];
    let parameterProvenance = buildParameterProvenance(
      parameters,
      overrides,
      llmResult.parameters,
      llmResult.domain,
    );

    if (
      llmResult.domain === "mm" &&
      llmResult.entities?.ecNumber &&
      !("km" in overrides)
    ) {
      const agentResult = await resolveKineticValue(llmResult.entities);
      if (agentResult.found && agentResult.km !== undefined) {
        const citation = formatResolvedCitation(agentResult.citation);
        if (citation !== undefined) {
          parameters = { ...parameters, km: agentResult.km };
          parameterProvenance = {
            ...parameterProvenance,
            km: {
              origin: "resolved",
              source: agentResult.source,
              citation,
              organism: agentResult.organism,
              citationStatus:
                agentResult.crossSpecies === true || agentResult.source === "brenda_cross_species"
                  ? "flagged"
                  : "verified",
            },
          };
          flags.push(
            `Resolved Km=${agentResult.km} ${agentResult.unit ?? "mM"} from ${agentResult.source ?? "unknown source"}.`
          );
        } else {
          parameterProvenance = {
            ...parameterProvenance,
            km: {
              origin: "default",
              note:
                "Found a Km but its citation carries no locator (ref id or URL); not trusted as resolved — using default Km.",
            },
          };
          flags.push("Found a Km but its citation was not locatable; using default Km.");
        }
      } else {
        parameterProvenance = {
          ...parameterProvenance,
          km: {
            origin: "default",
            note:
              "Could not resolve a real Km value from BRENDA/KEGG/PubMed; using default Km.",
          },
        };
      }
    }

    if (Object.keys(overrides).length === 0 && Object.keys(llmResult.parameters).length === 0) {
      flags.push("No parameters were extracted from the query; using defaults.");
    }
    if (Object.keys(overrides).length > 0) {
      flags.push("Applied parameter overrides found in the query string.");
    }
    if (isAllDefaults(parameterProvenance)) {
      flags.push("No parameter values were resolved from literature; all values are defaults.");
    }

    const violations = provenanceViolations(parameters, parameterProvenance);
    if (violations.length > 0) {
      throw new Error(`Internal error: invalid parameter provenance: ${violations.join("; ")}`);
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
    best = DOMAIN_DEFAULTS[0]!;
  }

  let parameters = { ...best.parameters, ...overrides };
  const flags: string[] = [];
  let parameterProvenance = buildParameterProvenance(parameters, overrides, {}, best.domain);

  // If this looks like an enzyme query and no LLM is available, try the
  // hardcoded entity map and the science agent.
  const fallbackEntities = extractEntitiesFromQuery(query);
  if (best.domain === "mm" && fallbackEntities?.ecNumber && !("km" in overrides)) {
    const agentResult = await resolveKineticValue(fallbackEntities);
    if (agentResult.found && agentResult.km !== undefined) {
      const citation = formatResolvedCitation(agentResult.citation);
      if (citation !== undefined) {
        parameters = { ...parameters, km: agentResult.km };
        parameterProvenance = {
          ...parameterProvenance,
          km: {
            origin: "resolved",
            source: agentResult.source,
            citation,
            organism: agentResult.organism,
            citationStatus:
              agentResult.crossSpecies === true || agentResult.source === "brenda_cross_species"
                ? "flagged"
                : "verified",
          },
        };
        flags.push(
          `Resolved Km=${agentResult.km} ${agentResult.unit ?? "mM"} from ${agentResult.source ?? "unknown source"}.`
        );
      } else {
        parameterProvenance = {
          ...parameterProvenance,
          km: {
            origin: "default",
            note:
              "Found a Km but its citation carries no locator (ref id or URL); not trusted as resolved — using default Km.",
          },
        };
        flags.push("Found a Km but its citation was not locatable; using default Km.");
      }
    } else {
      parameterProvenance = {
        ...parameterProvenance,
        km: {
          origin: "default",
          note: "Could not resolve a real Km value from BRENDA/KEGG/PubMed; using default Km.",
        },
      };
    }
  }

  if (Object.keys(overrides).length === 0) {
    flags.push("No parameters were extracted from the query; using defaults.");
  }
  if (Object.keys(overrides).length > 0) {
    flags.push("Applied parameter overrides found in the query string.");
  }
  if (isAllDefaults(parameterProvenance)) {
    flags.push("No parameter values were resolved from literature; all values are defaults.");
  }

  const violations = provenanceViolations(parameters, parameterProvenance);
  if (violations.length > 0) {
    throw new Error(`Internal error: invalid parameter provenance: ${violations.join("; ")}`);
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

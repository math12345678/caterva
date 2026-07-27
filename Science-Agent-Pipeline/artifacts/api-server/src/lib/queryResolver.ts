import { randomUUID } from "node:crypto";
import type { SimulationDomain } from "./telluriumRunner";
import { resolveQueryWithLLM, type EntityExtraction } from "./llmResolver";
import { resolveKineticValue } from "./scienceAgent";
import { matchEnzyme } from "./enzymes";

export interface ResolvedSimulation {
  runId: string;
  domain: SimulationDomain;
  parameters: Record<string, number>;
  provenance: {
    reasoning: string;
    citations: string[];
    flags: string[];
  };
}

interface DomainDefaults {
  domain: SimulationDomain;
  parameters: Record<string, number>;
  keywords: string[];
  reasoning: string;
  citations: string[];
}

const DOMAIN_DEFAULTS: DomainDefaults[] = [
  {
    domain: "mm",
    parameters: { km: 2, vmax: 5, s0: 10, end: 10, points: 51 },
    keywords: ["enzyme", "michaelis", "km", "vmax", "substrate", "ldh", "pyruvate", "lactate",
      "hexokinase", "catalase", "alcohol dehydrogenase", "trypsin", "rubisco", "kinase"],
    reasoning:
      "Keywords related to enzyme kinetics were found; defaulting to a Michaelis-Menten simulation.",
    citations: [
      "BRENDA — The Comprehensive Enzyme Information System, https://www.brenda-enzymes.org/",
    ],
  },
  {
    domain: "sir",
    parameters: { beta: 0.3, gamma: 0.1, s0: 990, i0: 10, r0_recovered: 0, end: 100, points: 101 },
    keywords: ["sir", "infection", "epidemic", "virus", "disease", "outbreak"],
    reasoning:
      "Keywords related to infectious disease spread were found; defaulting to an SIR epidemic simulation.",
    citations: [
      "Kermack W.O., McKendrick A.G. (1927) A Contribution to the Mathematical Theory of Epidemics.",
    ],
  },
  {
    domain: "seir",
    parameters: { beta: 0.3, sigma: 0.2, gamma: 0.1, s0: 990, e0: 10, i0: 0, r0_recovered: 0, end: 100, points: 101 },
    keywords: ["seir", "exposed", "latent", "incubation"],
    reasoning:
      "Keywords related to latent-period epidemiology were found; defaulting to an SEIR simulation.",
    citations: [
      "Kermack W.O., McKendrick A.G. (1927) A Contribution to the Mathematical Theory of Epidemics.",
    ],
  },
];

const PARAMETER_PATTERN = /(km|vmax|s0|beta|gamma|sigma|e0|i0|r0|end|points)\s*[=:]?\s*([0-9]+(?:\.[0-9]+)?(?:e[+-]?[0-9]+)?)/i;

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
    const citations = [...llmResult.citations];

    if (
      llmResult.domain === "mm" &&
      llmResult.entities?.ecNumber
    ) {
      const agentResult = await resolveKineticValue(llmResult.entities);
      if (agentResult.found && agentResult.km !== undefined) {
        parameters = { ...parameters, km: agentResult.km };
        flags.push(
          `Resolved Km=${agentResult.km} ${agentResult.unit ?? "mM"} from ${agentResult.source ?? "unknown source"}.`
        );
        if (agentResult.citation) {
          citations.push(
            `${agentResult.citation.source} (ref ${agentResult.citation.referenceId ?? "n/a"})` +
              (agentResult.citation.url ? ` — ${agentResult.citation.url}` : ""),
          );
        }
      } else {
        flags.push(
          "Could not resolve a real Km value from BRENDA/KEGG/PubMed; using default Km."
        );
      }
    }

    if (Object.keys(overrides).length === 0 && Object.keys(llmResult.parameters).length === 0) {
      flags.push("No parameters were extracted from the query; using defaults.");
    }
    if (Object.keys(overrides).length > 0) {
      flags.push("Applied parameter overrides found in the query string.");
    }

    return {
      runId: randomUUID(),
      domain: llmResult.domain,
      parameters,
      provenance: {
        reasoning: llmResult.reasoning,
        citations,
        flags,
      },
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

  // If this looks like an enzyme query and no LLM is available, try the
  // hardcoded entity map and the science agent.
  const fallbackEntities = extractEntitiesFromQuery(query);
  if (best.domain === "mm" && fallbackEntities?.ecNumber) {
    const agentResult = await resolveKineticValue(fallbackEntities);
    if (agentResult.found && agentResult.km !== undefined) {
      parameters = { ...parameters, km: agentResult.km };
      flags.push(
        `Resolved Km=${agentResult.km} ${agentResult.unit ?? "mM"} from ${agentResult.source ?? "unknown source"}.`
      );
    } else {
      flags.push("Could not resolve a real Km value from BRENDA/KEGG/PubMed; using default Km.");
    }
  }

  if (Object.keys(overrides).length === 0) {
    flags.push("No parameters were extracted from the query; using defaults.");
  }

  return {
    runId: randomUUID(),
    domain: best.domain,
    parameters,
    provenance: {
      reasoning: best.reasoning,
      citations: best.citations,
      flags,
    },
  };
}

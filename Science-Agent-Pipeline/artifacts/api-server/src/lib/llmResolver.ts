import { logger } from "./logger";
import type { SimulationDomain } from "./telluriumRunner";

export interface EntityExtraction {
  enzymeName?: string;
  substrate?: string;
  organism: string;
  ecNumber?: string;
}

export interface LLMResolvedSimulation {
  domain: SimulationDomain;
  parameters: Record<string, number | number[]>;
  reasoning: string;
  modelCitations: string[];
  entities?: EntityExtraction;
}

interface OpenAIMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

interface OpenAIResponse {
  choices?: {
    message?: {
      content?: string;
    };
  }[];
}

// `sbml` is intentionally absent here: it is the internal raw-SBML escape
// hatch, not a natural-language domain offered by the resolver. It remains
// part of the runner/API dispatch contract and is validated separately.
const SYSTEM_PROMPT = `You are the "science agent" resolver for a computational biology simulation pipeline.

Given a natural-language query, return a single JSON object (no markdown, no prose) with this exact shape:

{
  "domain": "mm" | "sir" | "seir" | "pcr" | "monte_carlo_pi" | "wright_fisher" | "two_locus_wright_fisher" | "molecular_dynamics" | "gillespie_ssa" | "gillespie_ssa_bimolecular",
  "parameters": { ...numeric parameters... },
  "reasoning": "short explanation of how you mapped the query",
  "modelCitations": ["optional literature reference"],
  "entities": {
    "enzymeName": "full enzyme name if mentioned",
    "substrate": "specific substrate if mentioned",
    "organism": "organism if mentioned, else Homo sapiens",
    "ecNumber": "EC number if known or inferable"
  }
}

Domain meanings:
- "mm": Michaelis-Menten enzyme kinetics.
- "sir": SIR epidemiology.
- "seir": SEIR epidemiology.
- "pcr": discrete PCR amplification.
- "monte_carlo_pi": Monte Carlo estimation of pi.
- "wright_fisher": Wright-Fisher population genetics.
- "two_locus_wright_fisher": two-locus linkage disequilibrium.
- "molecular_dynamics": Lennard-Jones molecular dynamics.
- "gillespie_ssa": Gillespie stochastic simulation of a first-order decay reaction (A -> B), parameters a0 (initial molecules), k (per-molecule decay rate), end (simulation time).
- "gillespie_ssa_bimolecular": Gillespie stochastic simulation of a bimolecular association reaction (A + B -> C), parameters a0, b0 (initial molecules), k (per-molecule-pair rate), end (simulation time).

Rules:
1. Infer sensible defaults for any missing numeric parameters.
2. Return only the JSON object. Do not wrap it in markdown code fences.
3. If the query is ambiguous, choose the most likely domain and explain in "reasoning".
4. Populate "entities" with any enzyme information you can extract from the query; omit or set to null if none is present.`;

function getApiKey(): string | undefined {
  return process.env.OPENAI_API_KEY || process.env.LLM_API_KEY;
}

function getApiUrl(): string {
  return (
    process.env.OPENAI_API_URL ||
    process.env.LLM_API_URL ||
    "https://api.openai.com/v1/chat/completions"
  );
}

function getModel(): string {
  return process.env.OPENAI_MODEL || process.env.LLM_MODEL || "gpt-4o-mini";
}

/**
 * Not every OpenAI-compatible provider supports `response_format`. Only force
 * JSON mode when we are clearly talking to OpenAI, or when the operator has
 * explicitly opted in via LLM_FORCE_JSON=true.
 */
function supportsJsonResponseFormat(url: string): boolean {
  const forced = process.env.LLM_FORCE_JSON;
  if (forced === "true") return true;
  if (forced === "false") return false;
  return url.includes("api.openai.com");
}

/**
 * Attempt to resolve a query using an OpenAI-compatible LLM.
 *
 * Returns `null` when no API key is configured, so callers can fall back to
 * the deterministic regex/keyword resolver. This keeps the pipeline runnable
 * locally without requiring LLM credentials.
 */
export async function resolveQueryWithLLM(
  query: string,
): Promise<LLMResolvedSimulation | null> {
  const apiKey = getApiKey();
  if (!apiKey) {
    return null;
  }

  const url = getApiUrl();
  const model = getModel();

  const messages: OpenAIMessage[] = [
    { role: "system", content: SYSTEM_PROMPT },
    { role: "user", content: query },
  ];

  try {
    const requestBody: Record<string, unknown> = {
      model,
      messages,
      temperature: 0.2,
    };

    if (supportsJsonResponseFormat(url)) {
      requestBody.response_format = { type: "json_object" };
    }

    const response = await fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${apiKey}`,
      },
      body: JSON.stringify(requestBody),
    });

    if (!response.ok) {
      const text = await response.text();
      logger.warn({ status: response.status, body: text }, "LLM resolver returned non-2xx response");
      return null;
    }

    const data = (await response.json()) as OpenAIResponse;
    const content = data.choices?.[0]?.message?.content;
    if (!content) {
      logger.warn("LLM resolver returned empty content");
      return null;
    }

    const parsed = JSON.parse(content) as Partial<LLMResolvedSimulation>;

    if (
      !parsed.domain ||
      !["mm", "sir", "seir", "pcr", "monte_carlo_pi", "wright_fisher", "two_locus_wright_fisher", "molecular_dynamics", "gillespie_ssa", "gillespie_ssa_bimolecular"].includes(parsed.domain)
    ) {
      logger.warn({ parsed }, "LLM resolver returned invalid domain");
      return null;
    }

    if (!parsed.parameters || typeof parsed.parameters !== "object") {
      logger.warn({ parsed }, "LLM resolver returned invalid parameters");
      return null;
    }

    return {
      domain: parsed.domain,
      parameters: normalizeParameters(parsed.parameters),
      reasoning: parsed.reasoning || "Resolved via LLM.",
      modelCitations: Array.isArray(parsed.modelCitations) ? parsed.modelCitations : [],
      entities: normalizeEntities(parsed.entities),
    };
  } catch (err) {
    logger.warn({ err }, "LLM resolver failed; falling back to keyword resolver");
    return null;
  }
}

function normalizeParameters(input: Record<string, unknown>): Record<string, number> {
  const out: Record<string, number> = {};
  for (const [key, value] of Object.entries(input)) {
    if (typeof value === "number") {
      out[key] = value;
    } else if (typeof value === "string") {
      const parsed = Number.parseFloat(value);
      if (!Number.isNaN(parsed)) {
        out[key] = parsed;
      }
    }
  }
  return out;
}

function normalizeEntities(input: unknown): EntityExtraction | undefined {
  if (!input || typeof input !== "object") return undefined;
  const raw = input as Record<string, unknown>;
  return {
    enzymeName: typeof raw.enzymeName === "string" ? raw.enzymeName : undefined,
    substrate: typeof raw.substrate === "string" ? raw.substrate : undefined,
    organism: typeof raw.organism === "string" ? raw.organism : "Homo sapiens",
    ecNumber: typeof raw.ecNumber === "string" ? raw.ecNumber : undefined,
  };
}

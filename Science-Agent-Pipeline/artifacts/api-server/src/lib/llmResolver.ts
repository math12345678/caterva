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
  "domain": "mm" | "sir" | "seir" | "pcr" | "monte_carlo_pi" | "wright_fisher" | "two_locus_wright_fisher" | "molecular_dynamics" | "gillespie_ssa" | "gillespie_ssa_bimolecular" | "gillespie_ssa_replicates",
  "parameters": { ...numeric parameters the query explicitly states; omit anything else ... },
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
- "gillespie_ssa_replicates": Gillespie SSA ensemble view, parameters a0 (initial molecules), k (rate), end (simulation time), n_replicates (independent seeded runs; optional b0 for the bimolecular A + B -> C form).

Rules:
1. Return numeric values only for parameters the query explicitly states. The pipeline hard-blocks any value that is not user-supplied or literature-backed, so never invent numbers: omit a parameter entirely rather than guessing a value. Return an empty "parameters" object when the query states no numbers.
2. Return only the JSON object. Do not wrap it in markdown code fences.
3. If the query is ambiguous, choose the most likely domain and explain in "reasoning".
4. Populate "entities" with any enzyme information you can extract from the query; omit or set to null if none is present.`;

/**
 * Known OpenAI-compatible providers, selected via LLM_PROVIDER. This is
 * purely a convenience layer over the generic LLM_API_KEY/LLM_API_URL/
 * LLM_MODEL override that already existed -- every entry here resolves to
 * exactly the same request shape (POST {url}, Authorization: Bearer
 * {key}, an OpenAI-style chat/completions body). Nothing about the
 * resolver's *trust* semantics changes: every value this path returns is
 * still origin "llm" (see ADR 0011), never "resolved" -- adding more
 * providers is about which vendor answers the request, not about
 * upgrading an LLM guess into a literature citation.
 *
 * Each provider's API key is read from its own PROVIDER_API_KEY variable
 * (e.g. GROQ_API_KEY) rather than overloading LLM_API_KEY, so more than
 * one can be configured at once without one silently shadowing another.
 */
interface LLMProviderConfig {
  apiUrl: string;
  apiKeyEnvVar: string;
  defaultModel: string;
  /** Whether this provider is known to support response_format:
   * json_object. Unknown/unlisted providers default to false (see
   * supportsJsonResponseFormat) -- forcing JSON mode on a provider that
   * doesn't support it fails the request outright, so the safe default
   * is to only opt in providers this has been checked against. */
  supportsJsonMode: boolean;
}

const LLM_PROVIDERS: Record<string, LLMProviderConfig> = {
  openai: {
    apiUrl: "https://api.openai.com/v1/chat/completions",
    apiKeyEnvVar: "OPENAI_API_KEY",
    defaultModel: "gpt-4o-mini",
    supportsJsonMode: true,
  },
  groq: {
    apiUrl: "https://api.groq.com/openai/v1/chat/completions",
    apiKeyEnvVar: "GROQ_API_KEY",
    defaultModel: "llama-3.3-70b-versatile",
    supportsJsonMode: true,
  },
  openrouter: {
    apiUrl: "https://openrouter.ai/api/v1/chat/completions",
    apiKeyEnvVar: "OPENROUTER_API_KEY",
    defaultModel: "openai/gpt-4o-mini",
    supportsJsonMode: true,
  },
  mistral: {
    apiUrl: "https://api.mistral.ai/v1/chat/completions",
    apiKeyEnvVar: "MISTRAL_API_KEY",
    defaultModel: "mistral-small-latest",
    supportsJsonMode: true,
  },
  siliconflow: {
    apiUrl: "https://api.siliconflow.com/v1/chat/completions",
    apiKeyEnvVar: "SILICONFLOW_API_KEY",
    defaultModel: "Qwen/Qwen2.5-7B-Instruct",
    supportsJsonMode: false,
  },
  tokenrouter: {
    apiUrl: "https://api.tokenrouter.io/v1/chat/completions",
    apiKeyEnvVar: "TOKENROUTER_API_KEY",
    defaultModel: "gpt-4o-mini",
    supportsJsonMode: true,
  },
};

/**
 * Resolve which provider config is active. LLM_PROVIDER selects by name
 * from LLM_PROVIDERS above; when unset (or set to an unrecognised name),
 * this falls back to the original generic OPENAI_API_KEY/LLM_API_KEY /
 * OPENAI_API_URL/LLM_API_URL override path -- so existing deployments
 * that never set LLM_PROVIDER keep working unchanged.
 */
function activeProvider(): LLMProviderConfig | null {
  const name = process.env.LLM_PROVIDER?.toLowerCase();
  if (name && LLM_PROVIDERS[name]) {
    return LLM_PROVIDERS[name];
  }
  return null;
}

function getApiKey(): string | undefined {
  const provider = activeProvider();
  if (provider) {
    return process.env[provider.apiKeyEnvVar] || process.env.LLM_API_KEY;
  }
  return process.env.OPENAI_API_KEY || process.env.LLM_API_KEY;
}

function getApiUrl(): string {
  const provider = activeProvider();
  return (
    process.env.OPENAI_API_URL ||
    process.env.LLM_API_URL ||
    provider?.apiUrl ||
    "https://api.openai.com/v1/chat/completions"
  );
}

function getModel(): string {
  const provider = activeProvider();
  return (
    process.env.OPENAI_MODEL ||
    process.env.LLM_MODEL ||
    provider?.defaultModel ||
    "gpt-4o-mini"
  );
}

/**
 * Not every OpenAI-compatible provider supports `response_format`. An
 * explicit LLM_FORCE_JSON always wins; otherwise a recognised
 * LLM_PROVIDER's own supportsJsonMode flag is authoritative (this is what
 * lets SiliconFlow -- known not to support it -- correctly opt out even
 * though its URL doesn't contain "api.openai.com"); falling back to the
 * original OpenAI-URL heuristic only when no provider is selected at all,
 * so the generic LLM_API_URL override path is unchanged.
 */
function supportsJsonResponseFormat(url: string): boolean {
  const forced = process.env.LLM_FORCE_JSON;
  if (forced === "true") return true;
  if (forced === "false") return false;
  const provider = activeProvider();
  if (provider) return provider.supportsJsonMode;
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
      logger.warn(
        { status: response.status, body: text },
        "LLM resolver returned non-2xx response",
      );
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
      ![
        "mm",
        "sir",
        "seir",
        "pcr",
        "monte_carlo_pi",
        "wright_fisher",
        "two_locus_wright_fisher",
        "molecular_dynamics",
        "gillespie_ssa",
        "gillespie_ssa_bimolecular",
        "gillespie_ssa_replicates",
      ].includes(parsed.domain)
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
      modelCitations: Array.isArray(parsed.modelCitations)
        ? parsed.modelCitations
        : [],
      entities: normalizeEntities(parsed.entities),
    };
  } catch (err) {
    logger.warn(
      { err },
      "LLM resolver failed; falling back to keyword resolver",
    );
    return null;
  }
}

function normalizeParameters(
  input: Record<string, unknown>,
): Record<string, number> {
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

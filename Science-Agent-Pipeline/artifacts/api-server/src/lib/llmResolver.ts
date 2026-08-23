import { logger } from "./logger";
import type { SimulationDomain } from "./teriumRunner";

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
/**
 * What each simulation domain means, in one line.
 *
 * These lines were embedded directly in SYSTEM_PROMPT. They are lifted out
 * because a second consumer now needs them -- the benchmark's query
 * generator describes a domain to an LLM in order to get queries written in
 * somebody else's words. Two hand-maintained copies of "what `seir` means"
 * would drift, and the drift would silently change what the benchmark is
 * measuring relative to what the resolver is told.
 */
export const DOMAIN_MEANINGS: Record<string, string> = {
  mm: "Michaelis-Menten enzyme kinetics (no inhibitor).",
  mm_competitive_inhibition:
    "Michaelis-Menten with competitive inhibitor (requires ki parameter).",
  sir: "SIR epidemiology (Kermack & McKendrick 1927).",
  seir: "SEIR epidemiology with exposed period (Anderson & May 1991).",
  wright_fisher: "Wright-Fisher population genetics.",
  gillespie_ssa:
    "Gillespie stochastic simulation of first-order decay (A -> B).",
  pcr: "discrete PCR amplification.",
  molecular_dynamics: "Lennard-Jones molecular dynamics.",
  gillespie_ssa_bimolecular:
    "Gillespie SSA for bimolecular reactions (A + B -> C).",
  two_locus_wright_fisher:
    "two-locus Wright-Fisher with recombination and linkage disequilibrium.",
  lotka_volterra:
    "predator-prey population dynamics (Lotka 1925, Volterra 1926).",
  cell_cycle_oscillator:
    "molecular cell cycle via cyclin-CDK regulation (Tyson 1991).",
  repressilator:
    "synthetic genetic oscillator with three repressive genes (Elowitz & Leibler 2000).",
};

const DOMAIN_MEANING_LINES = Object.entries(DOMAIN_MEANINGS)
  .map(([domain, meaning]) => `- "${domain}": ${meaning}`)
  .join("\n");

const SYSTEM_PROMPT = `You are the "science agent" resolver for a computational biology simulation pipeline.

Given a natural-language query, return a single JSON object (no markdown, no prose) with this exact shape:

{
  "domain": "mm" | "mm_competitive_inhibition" | "sir" | "seir" | "wright_fisher" | "gillespie_ssa" | "pcr" | "molecular_dynamics" | "gillespie_ssa_bimolecular" | "two_locus_wright_fisher" | "lotka_volterra" | "cell_cycle_oscillator" | "repressilator",
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
${DOMAIN_MEANING_LINES}

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

/**
 * List of simulation domains exposed to the LLM resolver.
 * Engine-internal domains (monte_carlo_pi, gillespie_ssa_replicates) are excluded.
 * Must match SYSTEM_PROMPT's domain enum.
 */
const SUPPORTED_DOMAINS = [
  "mm",
  "mm_competitive_inhibition",
  "sir",
  "seir",
  "wright_fisher",
  "gillespie_ssa",
  "pcr",
  "molecular_dynamics",
  "gillespie_ssa_bimolecular",
  "two_locus_wright_fisher",
  "lotka_volterra",
  "cell_cycle_oscillator",
  "repressilator",
] as const;

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
    // Was "llama-3.3-70b-versatile" until Groq retired it. That default
    // returned HTTP 404 "model does not exist or you do not have access",
    // which `resolveQueryWithLLM` turns into null -- so the resolver fell
    // back to the keyword table on every query and never said why. Checked
    // against Groq's /v1/models on 2026-08-23: this id is present, the old
    // one is not. A default that 404s is worse than no default, because it
    // fails as a silent downgrade rather than as an error.
    defaultModel: "openai/gpt-oss-120b",
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
 * LLM API request timeout in milliseconds. Prevents hanging on
 * unresponsive endpoints.
 */
const LLM_REQUEST_TIMEOUT_MS = 30_000;

/** Why the LLM resolver is or is not usable, as three states rather than a
 *  boolean. "Keys are present but unreachable" is the state that was
 *  previously indistinguishable from "no keys at all". */
export type LLMConfigState =
  | { state: "configured"; provider: string; model: string }
  | { state: "unconfigured"; detail: string }
  | { state: "misconfigured"; detail: string };

/**
 * Report whether an LLM would actually be called, and if not, why.
 *
 * The case this exists for: an operator sets GROQ_API_KEY (and four other
 * provider keys) but never sets LLM_PROVIDER. `getApiKey` only consults a
 * provider's own env var once LLM_PROVIDER selects that provider, so every
 * key is ignored, `resolveQueryWithLLM` returns null, and the pipeline
 * silently classifies with the keyword table forever. Nothing logged it and
 * `/pipeline/status` reported "Not set", which is not what is wrong -- the
 * keys are set; the selector is missing. Telling an operator "not set" when
 * five keys are present sends them to look in the wrong place.
 */
export function describeLLMConfig(): LLMConfigState {
  const selector = process.env.LLM_PROVIDER?.toLowerCase();
  const generic = process.env.LLM_API_KEY || process.env.OPENAI_API_KEY;

  if (selector && !LLM_PROVIDERS[selector]) {
    return {
      state: "misconfigured",
      detail:
        `LLM_PROVIDER="${selector}" is not a known provider. Known: ` +
        `${Object.keys(LLM_PROVIDERS).join(", ")}.`,
    };
  }

  if (getApiKey()) {
    return {
      state: "configured",
      provider: selector ?? "generic (LLM_API_KEY/OPENAI_API_KEY)",
      model: getModel(),
    };
  }

  // No key resolved. Distinguish "nothing configured" from "keys present
  // but none selected", because only the second is a one-line fix.
  const present = Object.entries(LLM_PROVIDERS)
    .filter(([, cfg]) => !!process.env[cfg.apiKeyEnvVar])
    .map(([name]) => name);

  if (present.length > 0 && !selector && !generic) {
    return {
      state: "misconfigured",
      detail:
        `Provider key(s) present for: ${present.join(", ")}, but ` +
        "LLM_PROVIDER is unset, so none of them is used and every query " +
        `falls back to keyword matching. Set LLM_PROVIDER to one of: ` +
        `${present.join(", ")}.`,
    };
  }

  return {
    state: "unconfigured",
    detail:
      "No LLM API key found. Set LLM_PROVIDER plus that provider's key, " +
      "or LLM_API_KEY with LLM_API_URL. Queries use keyword matching.",
  };
}

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

/**
 * Helper to resolve configuration values with fallback chain.
 * Checks env vars in order: override1, override2, provider-specific, fallback.
 */
function resolveConfigValue<T>(
  overrides: Array<T | undefined>,
  providerValue?: T,
  fallback?: T,
): T | undefined {
  for (const override of overrides) {
    if (override !== undefined) return override;
  }
  if (providerValue !== undefined) return providerValue;
  return fallback;
}

function getApiKey(): string | undefined {
  const provider = activeProvider();
  return resolveConfigValue(
    [
      provider ? process.env[provider.apiKeyEnvVar] : undefined,
      process.env.LLM_API_KEY,
      process.env.OPENAI_API_KEY,
    ],
    undefined,
  );
}

function getApiUrl(): string {
  const provider = activeProvider();
  return (
    resolveConfigValue(
      [process.env.OPENAI_API_URL, process.env.LLM_API_URL],
      provider?.apiUrl,
      "https://api.openai.com/v1/chat/completions",
    ) || "https://api.openai.com/v1/chat/completions"
  );
}

function getModel(): string {
  const provider = activeProvider();
  return (
    resolveConfigValue(
      [process.env.OPENAI_MODEL, process.env.LLM_MODEL],
      provider?.defaultModel,
      "gpt-4o-mini",
    ) || "gpt-4o-mini"
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

    // Abort after timeout to prevent hanging on unresponsive API endpoints
    const abortController = new AbortController();
    const timeoutId = setTimeout(() => abortController.abort(), LLM_REQUEST_TIMEOUT_MS);

    let response;
    try {
      response = await fetch(url, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${apiKey}`,
        },
        body: JSON.stringify(requestBody),
        signal: abortController.signal,
      });
    } finally {
      clearTimeout(timeoutId);
    }

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

    // Validate domain is in the supported list
    if (
      !parsed.domain ||
      !SUPPORTED_DOMAINS.includes(parsed.domain as (typeof SUPPORTED_DOMAINS)[number])
    ) {
      logger.warn(
        { parsed, supported: SUPPORTED_DOMAINS },
        "LLM resolver returned unsupported domain",
      );
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

/**
 * Helper to extract optional string fields from an object.
 * Returns the value if it's a string, otherwise undefined.
 */
function extractString(value: unknown): string | undefined {
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

function normalizeEntities(input: unknown): EntityExtraction | undefined {
  if (!input || typeof input !== "object") return undefined;
  const raw = input as Record<string, unknown>;
  return {
    enzymeName: extractString(raw.enzymeName),
    substrate: extractString(raw.substrate),
    organism: extractString(raw.organism) || "Homo sapiens",
    ecNumber: extractString(raw.ecNumber),
  };
}

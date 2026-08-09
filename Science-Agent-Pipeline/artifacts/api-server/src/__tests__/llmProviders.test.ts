/**
 * Multi-provider LLM_PROVIDER selection (llmResolver.ts).
 *
 * The LLM entity-extraction path already accepted any OpenAI-compatible
 * endpoint via the generic LLM_API_KEY/LLM_API_URL/LLM_MODEL override --
 * LLM_PROVIDERS is a convenience layer on top of that, letting an operator
 * write LLM_PROVIDER=groq + GROQ_API_KEY instead of hand-copying Groq's
 * base URL into LLM_API_URL. This does not change what the resolved value
 * IS: every parameter this path returns is still origin "llm" (ADR 0011),
 * never "resolved" -- see llmOrigin.test.ts for that contract. These tests
 * only check that provider selection actually reaches the network request
 * correctly, since a wrong URL or a silently-dropped key would make a
 * "configured" provider fail every call.
 */

import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { resolveQueryWithLLM } from "../lib/llmResolver";

const ENV_KEYS = [
  "LLM_PROVIDER",
  "LLM_API_KEY",
  "LLM_API_URL",
  "LLM_MODEL",
  "LLM_FORCE_JSON",
  "OPENAI_API_KEY",
  "OPENAI_API_URL",
  "OPENAI_MODEL",
  "GROQ_API_KEY",
  "OPENROUTER_API_KEY",
  "MISTRAL_API_KEY",
  "SILICONFLOW_API_KEY",
  "TOKENROUTER_API_KEY",
] as const;

let savedEnv: Record<string, string | undefined>;

beforeEach(() => {
  savedEnv = {};
  for (const k of ENV_KEYS) {
    savedEnv[k] = process.env[k];
    delete process.env[k];
  }
});

afterEach(() => {
  for (const k of ENV_KEYS) {
    if (savedEnv[k] === undefined) delete process.env[k];
    else process.env[k] = savedEnv[k];
  }
  vi.restoreAllMocks();
});

function mockFetchOnce(body: unknown) {
  return vi.spyOn(global, "fetch").mockResolvedValueOnce({
    ok: true,
    json: async () => body,
  } as Response);
}

const VALID_LLM_RESPONSE = {
  choices: [
    {
      message: {
        content: JSON.stringify({
          domain: "mm",
          parameters: {},
          reasoning: "test",
          modelCitations: [],
        }),
      },
    },
  ],
};

// Every domain the resolver prompt offers. `sbml` is intentionally excluded
// (it is the internal raw-SBML escape hatch, not a natural-language domain).
// This list must match the LLM allowlist inside resolveQueryWithLLM exactly;
// the test below fails if a resolvable domain is rejected there.
const RESOLVABLE_DOMAINS = [
  "mm",
  "mm_competitive_inhibition",
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
] as const;


describe("LLM_PROVIDER selection reaches the actual HTTP request", () => {
  it("with no provider or key configured, returns null without calling fetch", async () => {
    const fetchSpy = vi.spyOn(global, "fetch");
    const result = await resolveQueryWithLLM("simulate something");
    expect(result).toBeNull();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it("groq: uses Groq's URL, default model, and GROQ_API_KEY as the bearer token", async () => {
    process.env.LLM_PROVIDER = "groq";
    process.env.GROQ_API_KEY = "fake-groq-key";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    expect(fetchSpy).toHaveBeenCalledTimes(1);
    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://api.groq.com/openai/v1/chat/completions");
    const headers = init!.headers as Record<string, string>;
    expect(headers.Authorization).toBe("Bearer fake-groq-key");
    const body = JSON.parse(init!.body as string);
    expect(body.model).toBe("llama-3.3-70b-versatile");
  });

  it("openrouter: uses OpenRouter's URL and OPENROUTER_API_KEY", async () => {
    process.env.LLM_PROVIDER = "openrouter";
    process.env.OPENROUTER_API_KEY = "fake-openrouter-key";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://openrouter.ai/api/v1/chat/completions");
    expect((init!.headers as Record<string, string>).Authorization).toBe(
      "Bearer fake-openrouter-key",
    );
  });

  it("mistral: uses Mistral's URL and MISTRAL_API_KEY", async () => {
    process.env.LLM_PROVIDER = "mistral";
    process.env.MISTRAL_API_KEY = "fake-mistral-key";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://api.mistral.ai/v1/chat/completions");
    expect((init!.headers as Record<string, string>).Authorization).toBe(
      "Bearer fake-mistral-key",
    );
  });

  it("siliconflow: uses SiliconFlow's URL/key and does NOT force JSON mode", async () => {
    process.env.LLM_PROVIDER = "siliconflow";
    process.env.SILICONFLOW_API_KEY = "fake-siliconflow-key";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://api.siliconflow.com/v1/chat/completions");
    const body = JSON.parse(init!.body as string);
    // SiliconFlow is marked supportsJsonMode: false -- a request that
    // forced response_format on a provider that doesn't support it would
    // fail outright, so this must be the one provider NOT setting it.
    expect(body.response_format).toBeUndefined();
  });

  it("tokenrouter: uses TokenRouter's URL and TOKENROUTER_API_KEY", async () => {
    process.env.LLM_PROVIDER = "tokenrouter";
    process.env.TOKENROUTER_API_KEY = "fake-tokenrouter-key";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://api.tokenrouter.io/v1/chat/completions");
    expect((init!.headers as Record<string, string>).Authorization).toBe(
      "Bearer fake-tokenrouter-key",
    );
  });

  it("an explicit LLM_API_URL still overrides the selected provider's URL", async () => {
    // The generic override must remain authoritative -- an operator
    // pointing at a self-hosted proxy in front of a known provider must
    // not have that silently replaced by the provider's default URL.
    process.env.LLM_PROVIDER = "groq";
    process.env.GROQ_API_KEY = "fake-groq-key";
    process.env.LLM_API_URL = "https://my-proxy.internal/v1/chat/completions";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [url] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://my-proxy.internal/v1/chat/completions");
  });

  it("an unrecognised LLM_PROVIDER name falls back to the generic override path unchanged", async () => {
    process.env.LLM_PROVIDER = "some-provider-not-in-the-registry";
    process.env.LLM_API_KEY = "fake-generic-key";
    process.env.LLM_API_URL = "https://example.com/v1/chat/completions";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://example.com/v1/chat/completions");
    expect((init!.headers as Record<string, string>).Authorization).toBe(
      "Bearer fake-generic-key",
    );
  });

  it("LLM_FORCE_JSON=true overrides a provider's supportsJsonMode:false", async () => {
    process.env.LLM_PROVIDER = "siliconflow";
    process.env.SILICONFLOW_API_KEY = "fake-siliconflow-key";
    process.env.LLM_FORCE_JSON = "true";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [, init] = fetchSpy.mock.calls[0]!;
    const body = JSON.parse(init!.body as string);
    expect(body.response_format).toEqual({ type: "json_object" });
  });

  it("existing OPENAI_API_KEY-only deployments are unaffected by LLM_PROVIDER being unset", async () => {
    process.env.OPENAI_API_KEY = "fake-openai-key";
    const fetchSpy = mockFetchOnce(VALID_LLM_RESPONSE);

    await resolveQueryWithLLM("simulate something");

    const [url, init] = fetchSpy.mock.calls[0]!;
    expect(url).toBe("https://api.openai.com/v1/chat/completions");
    const body = JSON.parse(init!.body as string);
    expect(body.model).toBe("gpt-4o-mini");
    expect((init!.headers as Record<string, string>).Authorization).toBe(
      "Bearer fake-openai-key",
    );
  });
});

describe("the LLM resolver accepts every resolvable domain it advertises", () => {
  it("returns a non-null result for each RESOLVABLE_DOMAINS entry, including mm_competitive_inhibition", async () => {
    // The allowlist inside resolveQueryWithLLM and the prompt listing a
    // domain must never drift apart: a domain advertised in the prompt but
    // missing from the allowlist would be silently rejected (null) every
    // time the model names it. This pins that list to the full resolvable
    // set. Regression for the mm_competitive_inhibition allowlist gap.
    process.env.OPENAI_API_KEY = "fake-openai-key";
    for (const domain of RESOLVABLE_DOMAINS) {
      vi.spyOn(global, "fetch").mockResolvedValueOnce({
        ok: true,
        json: async () => ({
          choices: [
            {
              message: {
                content: JSON.stringify({
                  domain,
                  parameters: {},
                  reasoning: "test",
                  modelCitations: [],
                }),
              },
            },
          ],
        }),
      } as Response);

      const result = await resolveQueryWithLLM("simulate something");
      expect(result, `domain "${domain}" must not be rejected`).not.toBeNull();
      expect(result!.domain).toBe(domain);
    }
  });
});

/**
 * "No LLM key" and "five LLM keys, none selected" are different facts.
 *
 * The second is what a real deployment was in: GROQ_API_KEY,
 * OPENROUTER_API_KEY, MISTRAL_API_KEY, SILICONFLOW_API_KEY and
 * TOKENROUTER_API_KEY were all set, LLM_PROVIDER was not, and
 * `getApiKey` therefore resolved nothing -- because a provider's own env var
 * is only consulted once LLM_PROVIDER names that provider. Every query fell
 * back to keyword matching, and `/pipeline/status` said "Not set", pointing
 * the operator at the one thing that was not the problem.
 *
 * These tests pin the distinction, because a boolean here is exactly the
 * "could not check became it is fine" shape: the pipeline kept answering,
 * just worse, and nothing said so.
 */

import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { describeLLMConfig } from "../lib/llmResolver";

const LLM_VARS = [
  "LLM_PROVIDER",
  "LLM_API_KEY",
  "LLM_API_URL",
  "LLM_MODEL",
  "OPENAI_API_KEY",
  "OPENAI_API_URL",
  "OPENAI_MODEL",
  "GROQ_API_KEY",
  "OPENROUTER_API_KEY",
  "MISTRAL_API_KEY",
  "SILICONFLOW_API_KEY",
  "TOKENROUTER_API_KEY",
];

let saved: Record<string, string | undefined>;

beforeEach(() => {
  saved = {};
  for (const v of LLM_VARS) {
    saved[v] = process.env[v];
    delete process.env[v];
  }
});

afterEach(() => {
  for (const v of LLM_VARS) {
    if (saved[v] === undefined) delete process.env[v];
    else process.env[v] = saved[v];
  }
});

describe("describeLLMConfig", () => {
  it("reports unconfigured when genuinely nothing is set", () => {
    const result = describeLLMConfig();
    expect(result.state).toBe("unconfigured");
  });

  it("reports configured, with provider and model, when a provider is selected", () => {
    process.env.LLM_PROVIDER = "groq";
    process.env.GROQ_API_KEY = "test-key";
    const result = describeLLMConfig();
    expect(result.state).toBe("configured");
    if (result.state !== "configured") throw new Error("unreachable");
    expect(result.provider).toBe("groq");
    // The model must be reported, not merely known: an operator debugging a
    // 404 needs to see which model id is actually being requested.
    expect(result.model.length).toBeGreaterThan(0);
  });

  it("reports misconfigured — not 'not set' — when keys exist but LLM_PROVIDER does not", () => {
    // The exact real-world state this was written for.
    process.env.GROQ_API_KEY = "test-key";
    process.env.MISTRAL_API_KEY = "test-key";

    const result = describeLLMConfig();

    expect(result.state).toBe("misconfigured");
    if (result.state !== "misconfigured") throw new Error("unreachable");
    // Assert on what the operator is told to do, not on an incidental
    // substring: the message has to name the missing selector and list the
    // providers whose keys are actually present.
    expect(result.detail).toContain("LLM_PROVIDER is unset");
    expect(result.detail).toContain("groq");
    expect(result.detail).toContain("mistral");
    // And it must not name a provider whose key is absent.
    expect(result.detail).not.toContain("openrouter");
  });

  it("reports misconfigured when LLM_PROVIDER names a provider that does not exist", () => {
    process.env.LLM_PROVIDER = "not-a-real-provider";
    process.env.GROQ_API_KEY = "test-key";
    const result = describeLLMConfig();
    expect(result.state).toBe("misconfigured");
    if (result.state !== "misconfigured") throw new Error("unreachable");
    expect(result.detail).toContain("not a known provider");
  });

  it("still reports configured via the generic key path, with no provider selected", () => {
    // The pre-existing deployment shape, which must keep working.
    process.env.LLM_API_KEY = "test-key";
    const result = describeLLMConfig();
    expect(result.state).toBe("configured");
  });

  it("does not claim keys are missing when a provider key is present", () => {
    // Regression on the specific misreport: the old status line said
    // "Not set" in this state.
    process.env.TOKENROUTER_API_KEY = "test-key";
    const result = describeLLMConfig();
    expect(result.state).not.toBe("unconfigured");
  });
});

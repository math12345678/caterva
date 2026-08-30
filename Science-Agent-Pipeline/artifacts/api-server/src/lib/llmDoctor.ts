/**
 * Check whether each configured LLM provider actually works.
 *
 * This exists because "is the AI pipeline working?" took an afternoon to
 * answer by hand, and the answer was three separate configuration failures
 * that nothing reported:
 *
 * - Groq's default model `llama-3.3-70b-versatile` had been retired and
 *   returned HTTP 404 (ADR 0190).
 * - SiliconFlow's key was valid and its account balance was empty, so every
 *   request failed with a 200-shaped error body (ADR 0170).
 * - TokenRouter's key was malformed -- the API wants a `tr_` prefix -- so it
 *   rejected every request as an invalid key.
 *
 * Each looked identical from inside Terrium, because `resolveQueryWithLLM`
 * flattens every failure into `null` and falls through to keyword matching.
 * The pipeline kept answering; it just stopped using the LLM, and said so
 * nowhere. That flattening is correct in production -- a student's
 * simulation should not fail because a vendor is down -- which is exactly
 * why the diagnosis has to live somewhere else.
 *
 * ## Four states, not two
 *
 * `ok`          the provider answered and returned a usable completion
 * `unconfigured` no API key for it; not a fault, just absent
 * `broken`      it answered, and the answer was a refusal (bad key, dead
 *               model, no balance) -- the state that previously looked like
 *               "the LLM is off"
 * `unreachable` the request itself failed: DNS, timeout, connection refused.
 *               Distinct from `broken` because one is the provider's answer
 *               and the other is the absence of one, and only the second
 *               might be the checking machine's fault.
 *
 * Nothing here reads or writes anything Terrium uses. It makes one request
 * per provider and reports.
 */

import { LLM_PROVIDERS, type LLMProviderConfig } from "./llmResolver";

export type ProviderState = "ok" | "unconfigured" | "broken" | "unreachable";

export interface ProviderReport {
  provider: string;
  state: ProviderState;
  model: string;
  /** One line a person can act on. Never a raw stack. */
  detail: string;
  /** HTTP status, when the provider answered at all. */
  status?: number;
  latencyMs?: number;
}

const PROBE_TIMEOUT_MS = 20_000;

/**
 * The smallest completion that proves the whole path works.
 *
 * A `/v1/models` listing is cheaper but proves less: SiliconFlow listed its
 * models perfectly while refusing every completion for lack of balance, and
 * Groq listed models while the *configured* one was absent. Only a real
 * completion with the model Terrium would actually send exercises key,
 * endpoint, model id and quota together, which is the combination that broke.
 */
function probeBody(model: string): string {
  return JSON.stringify({
    model,
    messages: [{ role: "user", content: "Reply with the single word: ok" }],
    // Generous on purpose. The first version asked for 8 and reported Groq
    // BROKEN, which was wrong: `openai/gpt-oss-120b` is a reasoning model
    // and spent the whole budget on reasoning tokens, returning
    // finish_reason "length" with empty content. A check that condemns a
    // working provider is worse than no check, because somebody acts on it.
    max_tokens: 256,
    temperature: 0,
  });
}

/**
 * Turn a provider's answer into something a person can act on.
 *
 * Providers disagree about how to say "no". Some use HTTP status, some
 * return 200 with an error body. Both are `broken`; the text differs.
 */
function explain(status: number, body: string): string {
  const lower = body.toLowerCase();
  if (lower.includes("balance") || lower.includes("quota") || lower.includes("credit")) {
    return "account balance or quota exhausted -- the key is valid, there is nothing to spend";
  }
  if (lower.includes("does not exist") || lower.includes("model_not_found")) {
    return "the configured model does not exist or this account cannot access it";
  }
  if (status === 401 || status === 403 || lower.includes("invalid_api_key") || lower.includes("malformed")) {
    return "the API key was rejected (check for a required prefix or a stale key)";
  }
  if (status === 429) {
    return "rate limited -- the key works; this check is not a capacity test";
  }
  const firstLine = body.trim().split("\n")[0] ?? "";
  return `HTTP ${status}: ${firstLine.slice(0, 160)}`;
}

export interface ProbeDeps {
  fetch: typeof globalThis.fetch;
  now: () => number;
  env: Record<string, string | undefined>;
}

export async function probeProvider(
  name: string,
  config: LLMProviderConfig,
  deps: ProbeDeps,
): Promise<ProviderReport> {
  const key = deps.env[config.apiKeyEnvVar];
  const model = deps.env.LLM_MODEL ?? config.defaultModel;

  if (!key || key.trim().length === 0) {
    return {
      provider: name,
      state: "unconfigured",
      model,
      detail: `no ${config.apiKeyEnvVar} set`,
    };
  }

  const started = deps.now();
  const controller = new AbortController();
  // Cleared in `finally`. Without that the timer keeps the event loop alive
  // for the full timeout after every probe, so a run over six providers sat
  // for two minutes doing nothing before exiting.
  const timer = setTimeout(() => controller.abort(), PROBE_TIMEOUT_MS);

  try {
    const response = await deps.fetch(config.apiUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${key}`,
      },
      body: probeBody(model),
      signal: controller.signal,
    });
    const latencyMs = deps.now() - started;
    const body = await response.text();

    if (!response.ok) {
      return {
        provider: name,
        state: "broken",
        model,
        status: response.status,
        latencyMs,
        detail: explain(response.status, body),
      };
    }

    // A 200 is not a success. SiliconFlow returns 200 with an error body,
    // and treating status alone as the verdict is how "your account balance
    // is insufficient" reads as a working provider.
    let parsed: unknown;
    try {
      parsed = JSON.parse(body);
    } catch {
      return {
        provider: name,
        state: "broken",
        model,
        status: response.status,
        latencyMs,
        detail: "answered 200 with a body that is not JSON",
      };
    }

    const asRecord = parsed as {
      choices?: { message?: { content?: string }; finish_reason?: string }[];
      error?: { message?: string };
      message?: string;
    };

    if (asRecord.error || (!asRecord.choices && asRecord.message)) {
      const text = asRecord.error?.message ?? asRecord.message ?? body;
      return {
        provider: name,
        state: "broken",
        model,
        status: response.status,
        latencyMs,
        detail: explain(response.status, text),
      };
    }

    const choice = asRecord.choices?.[0];
    const content = choice?.message?.content;

    if (typeof content !== "string" || content.trim().length === 0) {
      // Empty content with finish_reason "length" is this probe running out
      // of budget, not the provider failing. The key authenticated, the
      // model exists and it generated tokens -- everything Terrium needs.
      // Reporting it as BROKEN would send somebody to fix a working
      // provider, which is how the first version of this file scored Groq.
      if (choice?.finish_reason === "length") {
        return {
          provider: name,
          state: "ok",
          model,
          status: response.status,
          latencyMs,
          detail:
            `answered in ${latencyMs} ms (reasoning used the probe's token ` +
            "budget; the provider is fine)",
        };
      }
      return {
        provider: name,
        state: "broken",
        model,
        status: response.status,
        latencyMs,
        detail: "answered 200 with no completion content",
      };
    }

    return {
      provider: name,
      state: "ok",
      model,
      status: response.status,
      latencyMs,
      detail: `answered in ${latencyMs} ms`,
    };
  } catch (err) {
    // The request never got an answer. Distinct from a refusal: this one
    // might be the checking machine's network rather than the provider.
    const latencyMs = deps.now() - started;
    const reason =
      err instanceof Error && err.name === "AbortError"
        ? `no response within ${PROBE_TIMEOUT_MS} ms`
        : err instanceof Error
          ? err.message
          : String(err);
    return {
      provider: name,
      state: "unreachable",
      model,
      latencyMs,
      detail: reason,
    };
  } finally {
    clearTimeout(timer);
  }
}

export async function probeAllProviders(deps: ProbeDeps): Promise<ProviderReport[]> {
  const reports: ProviderReport[] = [];
  for (const [name, config] of Object.entries(LLM_PROVIDERS)) {
    reports.push(await probeProvider(name, config, deps));
  }
  return reports;
}

/**
 * Exit code for the whole run, as three states rather than pass/fail.
 *
 * 0  at least one provider works
 * 1  a provider is configured and broken -- somebody should fix it
 * 3  nothing is configured at all: could not determine, not "all healthy"
 *
 * The 3 matters most. A machine with no keys would otherwise report zero
 * failures and read as a clean bill of health, which is the same shape of
 * lie as an empty test suite passing.
 */
export function exitCodeFor(reports: ProviderReport[]): 0 | 1 | 3 {
  if (reports.some((r) => r.state === "ok")) return 0;
  if (reports.some((r) => r.state === "broken" || r.state === "unreachable")) return 1;
  return 3;
}

export function formatReports(reports: ProviderReport[]): string {
  const width = Math.max(...reports.map((r) => r.provider.length));
  const mark: Record<ProviderState, string> = {
    ok: "OK          ",
    broken: "BROKEN      ",
    unreachable: "UNREACHABLE ",
    unconfigured: "not set     ",
  };

  const lines = reports.map(
    (r) => `  ${mark[r.state]}${r.provider.padEnd(width)}  ${r.detail}` +
      (r.state === "ok" || r.state === "broken" ? `\n  ${" ".repeat(12 + width)}  model: ${r.model}` : ""),
  );

  const working = reports.filter((r) => r.state === "ok");
  const broken = reports.filter((r) => r.state === "broken" || r.state === "unreachable");

  lines.push("");
  if (working.length > 0) {
    lines.push(
      `  ${working.length} provider(s) usable. Set LLM_PROVIDER to one of: ` +
        `${working.map((r) => r.provider).join(", ")}.`,
    );
  } else if (broken.length > 0) {
    lines.push(
      "  NO usable provider. Every configured one refused or could not be reached.",
      "  Terrium will keep answering -- it falls back to keyword classification --",
      "  so this will not surface as an error anywhere else.",
    );
  } else {
    lines.push(
      "  NOT DETERMINED: no provider is configured, so nothing was checked.",
      "  This is not a clean bill of health. Set a provider key to check one.",
    );
  }
  return lines.join("\n");
}

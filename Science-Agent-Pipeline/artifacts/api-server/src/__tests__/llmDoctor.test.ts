/**
 * The provider check, against every way a provider says no.
 *
 * Each case below is a real failure this session hit by hand. They are here
 * because they are indistinguishable from inside Terrium -- `resolveQueryWithLLM`
 * turns all of them into `null` and falls through to keyword matching -- so
 * the only place the difference can be asserted is here.
 *
 * The most important test is the last group: a reasoning model that spends
 * its token budget thinking is NOT a broken provider, and the first version
 * of this checker said it was. A check that condemns something working is
 * worse than no check, because somebody acts on it.
 */

import { describe, expect, it } from "vitest";
import {
  exitCodeFor,
  formatReports,
  probeProvider,
  type ProbeDeps,
  type ProviderReport,
} from "../lib/llmDoctor";

const CONFIG = {
  apiUrl: "https://example.test/v1/chat/completions",
  apiKeyEnvVar: "TEST_API_KEY",
  defaultModel: "test-model",
  supportsJsonMode: true,
};

function deps(
  responder: () => Response | Promise<Response> | never,
  env: Record<string, string | undefined> = { TEST_API_KEY: "k" },
): ProbeDeps {
  return {
    fetch: (async () => responder()) as unknown as typeof globalThis.fetch,
    now: () => 1000,
    env,
  };
}

const json = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status });

const completion = (content: string, finishReason = "stop") =>
  json({ choices: [{ message: { content }, finish_reason: finishReason }] });

describe("a provider that works", () => {
  it("reports ok", async () => {
    const r = await probeProvider("t", CONFIG, deps(() => completion("ok")));
    expect(r.state).toBe("ok");
    expect(r.model).toBe("test-model");
  });

  it("reports the model it actually probed, not the default", async () => {
    // An operator debugging a 404 needs to see which id was sent.
    const r = await probeProvider(
      "t",
      CONFIG,
      deps(() => completion("ok"), { TEST_API_KEY: "k", LLM_MODEL: "override-model" }),
    );
    expect(r.model).toBe("override-model");
  });
});

describe("a provider with no key", () => {
  it("is unconfigured, not broken", async () => {
    // Absence is not a fault, and conflating them would send somebody to
    // debug a provider they never intended to use.
    const r = await probeProvider("t", CONFIG, deps(() => completion("ok"), {}));
    expect(r.state).toBe("unconfigured");
    expect(r.detail).toContain("TEST_API_KEY");
  });

  it("treats a whitespace-only key as absent", async () => {
    const r = await probeProvider(
      "t",
      CONFIG,
      deps(() => completion("ok"), { TEST_API_KEY: "   " }),
    );
    expect(r.state).toBe("unconfigured");
  });
});

describe("every way a provider says no", () => {
  it("names a retired model (the Groq failure from ADR 0166)", async () => {
    const r = await probeProvider(
      "t",
      CONFIG,
      deps(() =>
        json({ error: { message: "The model `x` does not exist or you do not have access to it." } }, 404),
      ),
    );
    expect(r.state).toBe("broken");
    expect(r.detail).toContain("does not exist");
  });

  it("names an exhausted balance behind a 200 (the SiliconFlow failure)", async () => {
    // The nastiest of the three: HTTP 200, error in the body. Judging on
    // status alone reports this provider as healthy.
    const r = await probeProvider(
      "t",
      CONFIG,
      deps(() => json({ code: 30001, message: "Sorry, your account balance is insufficient" })),
    );
    expect(r.state).toBe("broken");
    expect(r.detail).toContain("balance");
  });

  it("names a rejected key (the TokenRouter failure)", async () => {
    const r = await probeProvider(
      "t",
      CONFIG,
      deps(() => json({ error: { message: "Missing or malformed API key", code: "invalid_api_key" } }, 401)),
    );
    expect(r.state).toBe("broken");
    expect(r.detail).toContain("key was rejected");
  });

  it("says a rate limit is not a broken key", async () => {
    const r = await probeProvider("t", CONFIG, deps(() => json({ error: { message: "rate" } }, 429)));
    expect(r.state).toBe("broken");
    expect(r.detail).toContain("the key works");
  });

  it("reports a non-JSON 200 rather than crashing on it", async () => {
    const r = await probeProvider(
      "t",
      CONFIG,
      deps(() => new Response("<html>gateway</html>", { status: 200 })),
    );
    expect(r.state).toBe("broken");
    expect(r.detail).toContain("not JSON");
  });
});

describe("a request that never gets an answer", () => {
  it("is unreachable, not broken", async () => {
    // One is the provider's answer; the other is the absence of one, and
    // only the second might be this machine's network.
    const r = await probeProvider(
      "t",
      CONFIG,
      deps(() => {
        throw new Error("getaddrinfo ENOTFOUND example.test");
      }),
    );
    expect(r.state).toBe("unreachable");
    expect(r.detail).toContain("ENOTFOUND");
  });
});

describe("a reasoning model that spends its budget thinking", () => {
  it("is ok, not broken", async () => {
    // The false positive the first version of this file produced. Groq's
    // openai/gpt-oss-120b returned finish_reason "length" with empty content
    // because the probe asked for 8 tokens and reasoning consumed them. The
    // key authenticated, the model existed, tokens were generated -- the
    // provider is fine and the probe was wrong.
    const r = await probeProvider("t", CONFIG, deps(() => completion("", "length")));
    expect(r.state).toBe("ok");
    expect(r.detail).toContain("token budget");
  });

  it("is still broken when content is empty for any other reason", async () => {
    // The half that stops the fix meaning "accept every empty answer".
    const r = await probeProvider("t", CONFIG, deps(() => completion("", "stop")));
    expect(r.state).toBe("broken");
    expect(r.detail).toContain("no completion content");
  });
});

describe("the exit code", () => {
  const report = (state: ProviderReport["state"]): ProviderReport => ({
    provider: "p",
    state,
    model: "m",
    detail: "d",
  });

  it("is 0 when at least one provider works", () => {
    expect(exitCodeFor([report("broken"), report("ok")])).toBe(0);
  });

  it("is 1 when everything configured is broken", () => {
    expect(exitCodeFor([report("broken"), report("unreachable")])).toBe(1);
  });

  it("is 3 when nothing is configured at all", () => {
    // The one that matters. Zero failures over zero providers is not a clean
    // bill of health -- it is the same shape as an empty suite passing.
    expect(exitCodeFor([report("unconfigured"), report("unconfigured")])).toBe(3);
  });
});

describe("the report", () => {
  it("says nothing was determined when nothing is configured", () => {
    const text = formatReports([
      { provider: "a", state: "unconfigured", model: "m", detail: "no key" },
    ]);
    expect(text).toContain("NOT DETERMINED");
    expect(text).toContain("not a clean bill of health");
  });

  it("warns that a total failure will not surface anywhere else", () => {
    // Because it will not: the pipeline keeps answering by keyword.
    const text = formatReports([
      { provider: "a", state: "broken", model: "m", detail: "bad key" },
    ]);
    expect(text).toContain("NO usable provider");
    expect(text).toContain("keyword classification");
  });

  it("names which providers to choose between when several work", () => {
    const text = formatReports([
      { provider: "a", state: "ok", model: "m", detail: "fine" },
      { provider: "b", state: "ok", model: "m", detail: "fine" },
    ]);
    expect(text).toContain("LLM_PROVIDER");
    expect(text).toContain("a, b");
  });
});

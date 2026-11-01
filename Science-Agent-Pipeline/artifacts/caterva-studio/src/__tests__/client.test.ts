import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import capabilities from "./fixtures/api/capabilities.json";
import createSim from "./fixtures/api/create_sim.json";
import health from "./fixtures/api/health.json";
import noToken from "./fixtures/api/no_token.json";
import runMissing from "./fixtures/api/run_missing.json";
import settings from "./fixtures/api/settings.json";
import settingsBad from "./fixtures/api/settings_bad.json";
import wrongHost from "./fixtures/api/wrong_host.json";
import {
  ApiRequestError,
  apiJson,
  apiPost,
  apiPut,
  discardSessionToken,
  resetSessionTokenForTests,
  sessionToken,
} from "@/api/client";
import { createRun, getRun } from "@/api/runs";
import type { Capabilities, Health, Settings } from "@/api/types";
import { describeError } from "@/lib/errors";
import { CapabilitiesSchema, HealthSchema, SettingsSchema } from "@/lib/schemas";

import { mockServer, setSessionToken } from "./helpers";

const TOKEN = "t0k3n_from-the-meta-tag";

beforeEach(() => setSessionToken(TOKEN));
afterEach(() => vi.unstubAllGlobals());

describe("the session token", () => {
  it("is the one the test gave the page", () => {
    expect(sessionToken()).toBe(TOKEN);
  });

  it("is read from the URL fragment, which is removed from the address at once", () => {
    const real = "A".repeat(43);
    window.history.replaceState(null, "", `/runs#token=${real}`);
    resetSessionTokenForTests();
    expect(sessionToken()).toBe(real);
    expect(window.location.hash).toBe("");
    expect(window.location.pathname).toBe("/runs");
    // A reload of the same tab has no fragment and still has the token.
    resetSessionTokenForTests();
    expect(sessionToken()).toBe(real);
    discardSessionToken();
    resetSessionTokenForTests();
    expect(sessionToken()).toBeNull();
  });

  it("keeps other fragment parameters and drops an unusable token", () => {
    window.history.replaceState(null, "", "/#token=short&section=about");
    resetSessionTokenForTests();
    expect(sessionToken()).toBeNull();
    expect(window.location.hash).toBe("#section=about");
    window.history.replaceState(null, "", "/");
  });

  it("is never read from a meta tag in a build, nor written in by the server", () => {
    const meta = document.createElement("meta");
    meta.name = "caterva-session";
    meta.content = "B".repeat(43);
    document.head.appendChild(meta);
    resetSessionTokenForTests();
    expect(sessionToken()).toBeNull();
    meta.remove();
  });

  it("is absent when the page was opened without one, and no request is made", async () => {
    setSessionToken(null);
    expect(sessionToken()).toBeNull();
    const { fetchMock } = mockServer(() => health);
    const e = await apiJson("/api/health").catch((x: unknown) => x);
    expect(e).toBeInstanceOf(ApiRequestError);
    expect((e as ApiRequestError).kind).toBe("session");
    expect(fetchMock).not.toHaveBeenCalled();
    expect(describeError(e).title).toBe("This page was not opened by the studio server");
  });

  it("rides in the X-Caterva-Session header on every request, never in the URL", async () => {
    const { seen } = mockServer(() => health);
    await apiJson<Health>("/api/health", {}, HealthSchema);
    await apiPost("/api/runs", { kind: "sim", request: { seed: 7 } }).catch(() => undefined);
    for (const req of seen) {
      expect(req.headers.get("X-Caterva-Session")).toBe(TOKEN);
      expect(req.url).not.toContain(TOKEN);
    }
    expect(seen[1].headers.get("Content-Type")).toBe("application/json");
  });
});

describe("answers, checked against the contract", () => {
  it("accepts the real health, capabilities and settings answers", async () => {
    mockServer((req) =>
      req.url === "/api/health" ? health : req.url === "/api/capabilities" ? capabilities : req.url === "/api/settings" ? settings : undefined,
    );
    const h = await apiJson<Health>("/api/health", {}, HealthSchema);
    expect(h.api_version).toBe(1);
    const c = await apiJson<Capabilities>("/api/capabilities", {}, CapabilitiesSchema);
    expect(c.kinds.compose.reason).toBe("not built yet in this version of Caterva Studio");
    // A key the page does not know yet (core stores more settings) is kept, never dropped.
    const s = await apiJson<Settings>("/api/settings", {}, SettingsSchema);
    expect(s).toEqual(settings.body);
  });

  it("names the first field where an answer differs from the contract", async () => {
    const renamed = { ...health.body, api_version: undefined, apiVersion: 1 };
    mockServer(() => ({ status: 200, body: renamed }));
    const e = (await apiJson("/api/health", {}, HealthSchema).catch((x: unknown) => x)) as ApiRequestError;
    expect(e.kind).toBe("contract");
    expect(e.error.field).toBe("api_version");
    expect(describeError(e).title).toBe("The server's answer did not match this page");
  });
});

describe("refusals become readable states, in the server's words", () => {
  it.each([
    ["no_token", noToken, "unauthorized", "The server refused this page's session"],
    ["wrong_host", wrongHost, "forbidden", "The server refused this page"],
    ["run_missing", runMissing, "not_found", "Not found"],
    ["create_sim", createSim, "unavailable", "Not available in this installation"],
  ] as const)("%s", async (_name, recorded, code, title) => {
    mockServer(() => recorded);
    const e = (await apiJson("/api/anything").catch((x: unknown) => x)) as ApiRequestError;
    expect(e.status).toBe(recorded.status);
    expect(e.error.code).toBe(code);
    const r = describeError(e);
    expect(r.title).toBe(title);
    expect(r.message).toBe(recorded.body.error.message);
  });

  it("keeps the field a 400 names, so the form can put the message under it", async () => {
    mockServer(() => settingsBad);
    const e = (await apiPut("/api/settings", { theme: "sepia" }).catch((x: unknown) => x)) as ApiRequestError;
    expect(describeError(e).field).toBe("theme");
    expect(describeError(e).message).toBe("theme must be one of system, light, dark");
  });

  it("tells a server that is not answering apart from one that refused", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    );
    const e = (await getRun("20260930-141502-sim-3f9a0c1d").catch((x: unknown) => x)) as ApiRequestError;
    expect(e.kind).toBe("network");
    expect(describeError(e).title).toBe("The studio server is not answering");
  });

  it("does not invent a body for an error answer without one", async () => {
    mockServer(() => new Response("<html>proxy error</html>", { status: 502 }));
    const e = (await createRun("sim", { seed: 7 }).catch((x: unknown) => x)) as ApiRequestError;
    expect(e.status).toBe(502);
    expect(e.error.message).toBe("The server answered HTTP 502 without an error body.");
  });
});

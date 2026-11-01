/**
 * Settings sends core's two optional keys (offline, gromacs_path) with the
 * rest, over the real recorded answers in fixtures/api. The PUT is answered
 * with what was sent, as the server answers a valid one.
 */
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import capabilities from "./fixtures/api/capabilities.json";
import health from "./fixtures/api/health.json";
import runsEmpty from "./fixtures/api/runs_empty.json";
import settings from "./fixtures/api/settings.json";
import App from "@/App";

import { json, mockServer, setSessionToken } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

describe("Settings", () => {
  it("saves offline mode and the GROMACS path with the stored keys", async () => {
    setSessionToken("token");
    window.history.replaceState(null, "", "/settings");
    const { seen } = mockServer((req) => {
      if (req.url === "/api/health") return health;
      if (req.url.startsWith("/api/capabilities")) return capabilities;
      if (req.url === "/api/settings" && req.method === "PUT") return json(200, req.body);
      if (req.url === "/api/settings") return settings;
      if (req.url.startsWith("/api/runs")) return runsEmpty;
      return undefined;
    });
    render(<App />);
    const offline = await screen.findByRole("switch", { name: /Offline mode/ });
    await userEvent.click(offline);
    await userEvent.type(screen.getByRole("textbox", { name: /GROMACS/ }), "/opt/homebrew/bin/gmx");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const put = await vi.waitFor(() => {
      const p = seen.find((r) => r.method === "PUT" && r.url === "/api/settings");
      if (!p) throw new Error("no PUT yet");
      return p;
    });
    expect(put.body).toEqual({
      ...settings.body,
      offline: true,
      gromacs_path: "/opt/homebrew/bin/gmx",
    });
  });

  it("keeps the runs kept setting only when it is changed, and checks GROMACS only when asked", async () => {
    setSessionToken("token");
    window.history.replaceState(null, "", "/settings");
    const { seen } = mockServer((req) => {
      if (req.url === "/api/health") return health;
      if (req.url === "/api/capabilities/refresh" && req.method === "POST") return capabilities;
      if (req.url.startsWith("/api/capabilities")) return capabilities;
      if (req.url === "/api/settings" && req.method === "PUT") return json(200, req.body);
      if (req.url === "/api/settings") return settings;
      if (req.url.startsWith("/api/runs")) return runsEmpty;
      return undefined;
    });
    render(<App />);
    await screen.findByRole("switch", { name: /Offline mode/ });
    expect(seen.some((r) => r.url === "/api/capabilities/refresh")).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Check GROMACS" }));
    await vi.waitFor(() => expect(seen.some((r) => r.url === "/api/capabilities/refresh" && r.method === "POST")).toBe(true));
    expect(seen.find((r) => r.url === "/api/capabilities/refresh")!.body).toEqual({});
    await userEvent.selectOptions(screen.getByRole("combobox", { name: /Runs kept/ }), "500");
    await userEvent.click(screen.getByRole("button", { name: "Save" }));
    const put = await vi.waitFor(() => {
      const p = seen.find((r) => r.method === "PUT" && r.url === "/api/settings");
      if (!p) throw new Error("no PUT yet");
      return p;
    });
    expect(put.body).toEqual({ ...settings.body, keep_runs: 500 });
  });
});


describe("Settings, Updates", () => {
  const status = {
    enabled: true,
    reason: null,
    version: "0.5.1",
    build: "412",
    lastCheck: "2026-10-04T12:00:00Z",
    automatic: true,
    prereleases: false,
    checking: false,
    note: null,
  };

  function openSettings() {
    setSessionToken("token");
    window.history.replaceState(null, "", "/settings");
    mockServer((req) => {
      if (req.url === "/api/health") return health;
      if (req.url.startsWith("/api/capabilities")) return capabilities;
      if (req.url === "/api/settings") return settings;
      if (req.url.startsWith("/api/runs")) return runsEmpty;
      return undefined;
    });
    render(<App />);
  }

  function stubShell(answer: unknown) {
    const postMessage = vi.fn(async (message: { action: string }) => (message.action === "updateStatus" ? answer : null));
    vi.stubGlobal("webkit", { messageHandlers: { caterva: { postMessage } } });
    return postMessage;
  }

  it("says updates are the app's business when the page runs in a browser", async () => {
    openSettings();
    expect(await screen.findByRole("heading", { name: "Updates" })).toBeTruthy();
    expect(screen.getByText(/open in a browser, not in the app/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Check now" })).toBeNull();
    expect(screen.queryByRole("switch", { name: /Include prereleases/ })).toBeNull();
  });

  it("shows the installed version and asks the shell to check, in the app", async () => {
    const post = stubShell(status);
    openSettings();
    expect(await screen.findByText(/0\.5\.1 \(build 412\)/)).toBeTruthy();
    await userEvent.click(screen.getByRole("button", { name: "Check now" }));
    await vi.waitFor(() => expect(post).toHaveBeenCalledWith({ action: "checkForUpdates" }));
  });

  it("sends each switch to the shell on its own and never claims an Apple signature", async () => {
    const post = stubShell(status);
    openSettings();
    await userEvent.click(await screen.findByRole("switch", { name: /Include prereleases/ }));
    await vi.waitFor(() => expect(post).toHaveBeenCalledWith({ action: "setUpdateOptions", prereleases: true }));
    await userEvent.click(screen.getByRole("switch", { name: /Check automatically/ }));
    await vi.waitFor(() => expect(post).toHaveBeenCalledWith({ action: "setUpdateOptions", automatic: false }));
    expect(screen.getByText(/not signed with an Apple Developer ID and not notarised/)).toBeTruthy();
  });

  it("gives the reason when this build does not update itself", async () => {
    stubShell({ ...status, enabled: false, reason: "A development build runs from a checkout and does not update itself." });
    openSettings();
    expect(await screen.findByText(/development build runs from a checkout/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Check now" })).toBeNull();
  });
});

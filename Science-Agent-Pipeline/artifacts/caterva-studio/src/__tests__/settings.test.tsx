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
});

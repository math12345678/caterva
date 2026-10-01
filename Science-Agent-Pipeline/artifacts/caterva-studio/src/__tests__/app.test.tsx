/**
 * The shell over the real recorded answers of an installation with no runs
 * and no science kinds registered yet (fixtures/api, from core's dispatch).
 */
import { render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import capabilities from "./fixtures/api/capabilities.json";
import health from "./fixtures/api/health.json";
import runsEmpty from "./fixtures/api/runs_empty.json";
import settings from "./fixtures/api/settings.json";
import App from "@/App";

import { mockServer, setSessionToken } from "./helpers";

afterEach(() => {
  vi.unstubAllGlobals();
  window.history.replaceState(null, "", "/");
});

function serve() {
  return mockServer((req) => {
    if (req.url === "/api/health") return health;
    if (req.url === "/api/capabilities") return capabilities;
    if (req.url === "/api/settings") return settings;
    if (req.url.startsWith("/api/runs")) return runsEmpty;
    return undefined;
  });
}

describe("the shell", () => {
  it("refuses to start without a session token, and says how to open the page", () => {
    setSessionToken(null);
    const { fetchMock } = serve();
    render(<App />);
    expect(screen.getByRole("alert")).toHaveTextContent("This page was not opened by the studio server");
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("draws the rail in its three groups, the status line from capabilities, and Home's first questions", async () => {
    setSessionToken("token");
    serve();
    render(<App />);
    const nav = await screen.findByRole("navigation", { name: "Studio" });
    for (const group of ["Kinetics", "Structure & dynamics", "Workspace"]) {
      expect(within(nav).getByRole("group", { name: group })).toBeInTheDocument();
    }
    expect(within(nav).queryByRole("link", { name: "Rates" })).toBeNull();
    expect(within(nav).getByRole("link", { name: "Home" })).toHaveAttribute("aria-current", "page");

    const status = screen.getByRole("contentinfo", { name: "What this installation can reach" });
    expect(await within(status).findByText(`GROMACS ${capabilities.body.gromacs.version}`)).toBeInTheDocument();
    expect(within(status).getByText("network not checked")).toBeInTheDocument();

    expect(await screen.findByText("Nothing has run here yet")).toBeInTheDocument();
    expect(screen.getAllByText(/caterva compose/).length).toBeGreaterThan(0);
    // Every kind is listed with the server's reason it cannot run yet.
    expect((await screen.findAllByText("not built yet in this version of Caterva Studio")).length).toBeGreaterThan(5);
  });

  it("says why a reserved screen is missing, in the server's words, and retitles the tab", async () => {
    setSessionToken("token");
    serve();
    window.history.replaceState(null, "", "/rates");
    render(<App />);
    expect(await screen.findByText("Rates is not in this installation")).toBeInTheDocument();
    expect(
      await screen.findByText("The caterva.rates module is not in this installation; no adapter registered the rates kind."),
    ).toBeInTheDocument();
    expect(document.title).toBe("Rates · Caterva Studio");
  });

  it("says an unknown address names no screen", async () => {
    setSessionToken("token");
    serve();
    window.history.replaceState(null, "", "/nowhere");
    render(<App />);
    expect(await screen.findByText("There is no screen at this address")).toBeInTheDocument();
    expect(document.title).toBe("No screen · Caterva Studio");
  });
});

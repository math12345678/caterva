import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import capabilities from "./fixtures/api/capabilities.json";
import createSim from "./fixtures/api/create_sim.json";
import runsEmpty from "./fixtures/api/runs_empty.json";
import type { Capabilities } from "@/api/types";
import { CommandPalette, orderSections, paletteFilter } from "@/components/palette/CommandPalette";
import { CommandProvider, useCommand } from "@/components/palette/commands";
import { JobsProvider } from "@/lib/jobs";

import { json, mockServer, setSessionToken } from "./helpers";

const caps = capabilities.body as unknown as Capabilities;

function ScreenAction({ run }: { run: () => void }) {
  useCommand({ id: "test.primary", title: "Look up the constants", run });
  return null;
}

function mount(c: Capabilities = caps, extra?: ReactNode) {
  const memory = memoryLocation({ path: "/", record: true });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <Router hook={memory.hook}>
        <CommandProvider>
          <JobsProvider>
            {extra}
            <CommandPalette capabilities={c} />
          </JobsProvider>
        </CommandProvider>
      </Router>
    </QueryClientProvider>,
  );
  return memory;
}

const openWithKeys = () => fireEvent.keyDown(window, { key: "k", ctrlKey: true, metaKey: true });

beforeEach(() => setSessionToken("token"));
afterEach(() => vi.unstubAllGlobals());

describe("the command palette", () => {
  it("opens on Cmd-K (Ctrl-K elsewhere) and lists every visible route by group", async () => {
    mockServer((req) => (req.url.startsWith("/api/runs") ? runsEmpty : undefined));
    mount();
    expect(screen.queryByRole("combobox")).toBeNull();
    // jsdom reports no platform, so the page treats it as not macOS: Ctrl is the modifier.
    act(() => openWithKeys());
    expect(await screen.findByRole("combobox")).toHaveFocus();
    for (const title of ["Home", "Compose", "Constants", "Stochastic", "Structures", "History", "About"]) {
      expect(screen.getByRole("option", { name: new RegExp(`^${title}`) })).toBeInTheDocument();
    }
    // `caterva rates` is not in this installation (capabilities.rates.available is false).
    expect(screen.queryByRole("option", { name: /^Rates/ })).toBeNull();
  });

  it("navigates to the chosen screen and closes", async () => {
    mockServer((req) => (req.url.startsWith("/api/runs") ? runsEmpty : undefined));
    const memory = mount();
    act(() => openWithKeys());
    const input = await screen.findByRole("combobox");
    await userEvent.type(input, "History");
    await userEvent.keyboard("{Enter}");
    expect(memory.history).toContain("/history");
    await waitFor(() => expect(screen.queryByRole("combobox")).toBeNull());
  });

  it("offers a screen's registered primary action", async () => {
    mockServer((req) => (req.url.startsWith("/api/runs") ? runsEmpty : undefined));
    const run = vi.fn();
    mount(caps, <ScreenAction run={run} />);
    act(() => openWithKeys());
    await userEvent.click(await screen.findByRole("option", { name: /Look up the constants/ }));
    expect(run).toHaveBeenCalledOnce();
  });

  it("says compose cannot start, with the server's reason, when this installation cannot run it", async () => {
    mockServer((req) => (req.url.startsWith("/api/runs") ? runsEmpty : undefined));
    mount();
    act(() => openWithKeys());
    await userEvent.type(await screen.findByRole("combobox"), "Michaelis Menten");
    const item = screen.getByRole("option", { name: /Compose “Michaelis Menten”/ });
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("Not available: not built yet in this version of Caterva Studio");
  });

  it("starts a compose run from the typed text and opens it; a refusal is shown in the palette", async () => {
    const withCompose = { ...caps, kinds: { ...caps.kinds, compose: { ...caps.kinds.compose, available: true, reason: null } } };
    const { seen } = mockServer((req) => {
      if (req.method === "POST" && req.url === "/api/runs") return createSim;
      if (req.url.startsWith("/api/runs")) return json(200, runsEmpty.body);
      return undefined;
    });
    mount(withCompose);
    act(() => openWithKeys());
    await userEvent.type(await screen.findByRole("combobox"), "Michaelis Menten");
    await userEvent.click(screen.getByRole("option", { name: /Compose “Michaelis Menten”/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(createSim.body.error.message);
    const post = seen.find((r) => r.method === "POST");
    expect(post?.body).toEqual({ kind: "compose", request: { description: "Michaelis Menten" } });
    // The palette stays open, so the reader can change the text.
    expect(screen.getByRole("combobox")).toBeInTheDocument();
  });

  it("ranks a screen's title above a passing match in another screen's description", () => {
    const sections = [
      { key: "go", items: [["Home /", ["what this installation can do and the runs opened last"]]] as [string, string[]?][], node: null },
      { key: "workspace", items: [["History /history", ["every run"]]] as [string, string[]?][], node: null },
    ];
    expect(orderSections(sections, "History").map((s) => s.key)).toEqual(["workspace", "go"]);
    expect(orderSections(sections, "").map((s) => s.key)).toEqual(["go", "workspace"]);
    expect(paletteFilter("palette:compose-from-text", "History")).toBeLessThan(paletteFilter("History /history", "History"));
  });
});

/**
 * Home, History and About in the whole app, over real answers of a server
 * with five runs (src/__fixtures__/api/workspace, captured through the
 * dispatch layer; README there). No number here is typed by hand.
 */
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import dataSources from "../../../../../../docs/data-sources.json";
import capabilities from "@/__fixtures__/api/workspace/capabilities.json";
import compose from "@/__fixtures__/api/workspace/compose.json";
import health from "@/__fixtures__/api/workspace/health.json";
import negative from "@/__fixtures__/api/workspace/negative.json";
import runs from "@/__fixtures__/api/workspace/runs.json";
import settings from "@/__fixtures__/api/workspace/settings.json";
import shapes from "@/__fixtures__/api/workspace/shapes.json";
import App from "@/App";
import { type Handler, json, mockServer, runTitle, setSessionToken } from "@/__tests__/helpers";
import { resetRunStreamsForTests } from "@/api/runs";
import type { Capabilities, RunRecord, RunSummary } from "@/api/types";
import { plain } from "@/lib/copy";
import { resetToastsForTests } from "@/lib/toast";

import { citeCaterva } from "../About";
import { matchesSearch } from "../History";
import { machineSentences } from "../Home";
import { resetTrashForTests, UNDO_MS } from "./trash";

const RUNS = runs.runs as RunSummary[];
const RECORDS: Record<string, RunRecord> = Object.fromEntries(
  [compose, negative].map((f) => [(f.run as RunRecord).id, f.run as RunRecord]),
);

type Extra = (req: Parameters<Handler>[0]) => Response | undefined;

function serve(extra: Extra = () => undefined, list = runs) {
  return mockServer((req) => {
    const answer = extra(req);
    if (answer !== undefined) return answer;
    if (req.url === "/api/health") return json(200, health);
    if (req.url.startsWith("/api/capabilities")) return json(200, capabilities);
    if (req.url === "/api/settings") return json(200, settings);
    if (req.url === "/api/compose/shapes") return json(200, shapes);
    if (req.url.startsWith("/api/runs?")) return json(200, list);
    const id = /^\/api\/runs\/([^/]+)$/.exec(req.url)?.[1];
    if (id && req.method === "GET" && RECORDS[id]) return json(200, RECORDS[id]);
    return undefined;
  });
}

/** The stacked layout of a 1024 px window: jsdom gives the split's handles no box to hit-test. */
function stacked(on: boolean) {
  (window as unknown as { __setMedia?: (q: string, v: boolean) => void }).__setMedia?.("(max-width: 1099px)", on);
}

function at(path: string) {
  window.history.replaceState(null, "", path);
}

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  resetRunStreamsForTests();
  resetTrashForTests();
  resetToastsForTests();
  stacked(false);
  at("/");
});

describe("Home", () => {
  it("offers the one-line ask with the server's shapes, the recent runs and what this machine can do", async () => {
    setSessionToken("t0k");
    serve();
    at("/");
    render(<App />);
    const ask = await screen.findByRole("textbox", { name: "Write one line." });
    expect(ask).toHaveFocus();
    const suggestions = await screen.findByRole("list", { name: "Suggestions: shapes the grammar recognises" });
    const first = shapes.shapes[0].split(": ")[1];
    await userEvent.click(within(suggestions).getByRole("button", { name: first }));
    expect(ask).toHaveValue(first);
    for (const r of RUNS) expect(screen.getAllByText(runTitle(r.title)).length).toBeGreaterThan(0);
    for (const s of machineSentences(capabilities as Capabilities, settings.offline)) {
      expect(screen.getByText(s.text)).toBeInTheDocument();
    }
  });

  it("starts the line as caterva compose and opens it on Compose", async () => {
    setSessionToken("t0k");
    const run = compose.run as RunRecord;
    const { seen } = serve((req) => (req.method === "POST" && req.url === "/api/runs" ? json(202, { run }) : undefined));
    at("/");
    render(<App />);
    await userEvent.type(await screen.findByRole("textbox", { name: "Write one line." }), `${run.request.description}{Enter}`);
    await waitFor(() => expect(window.location.pathname + window.location.search).toBe(`/compose?run=${run.id}`));
    expect(seen.find((r) => r.method === "POST")!.body).toEqual({ kind: "compose", request: { description: run.request.description } });
  });

  it("says why a line was refused, under the line", async () => {
    setSessionToken("t0k");
    const error = { code: "malformed", message: "caterva compose: error: the description is empty", field: "description" };
    serve((req) => (req.method === "POST" ? json(400, { error }) : undefined));
    at("/");
    render(<App />);
    await userEvent.type(await screen.findByRole("textbox", { name: "Write one line." }), "x{Enter}");
    expect(await screen.findByRole("alert")).toHaveTextContent(error.message);
  });

  it("teaches the marks and three first questions on an installation with no runs", async () => {
    setSessionToken("t0k");
    serve(undefined, { runs: [], next_cursor: null });
    at("/");
    render(<App />);
    expect(await screen.findByRole("region", { name: "Nothing has run here yet" })).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "What the marks mean" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /A model of hexokinase, every constant cited/ })).toHaveAttribute(
      "href",
      "/compose?description=Michaelis%20Menten&subject=2.7.1.1&organism=human&substrate=glucose",
    );
  });
});

describe("History", () => {
  beforeEach(() => stacked(true));

  it("finds runs by what the list shows of them", () => {
    const refused = RUNS.find((r) => r.outcome?.meaning === "refused")!;
    const reasonWord = refused.outcome!.reason!.split(/\s+/).find((w) => w.length > 8)!;
    expect(RUNS.filter((r) => matchesSearch(r, reasonWord))).toContainEqual(refused);
    const sim = RUNS.find((r) => r.kind === "sim")!;
    expect(RUNS.filter((r) => matchesSearch(r, sim.id))).toEqual([sim]);
    expect(RUNS.filter((r) => matchesSearch(r, `${sim.kind} ${sim.id.slice(-8).toUpperCase()}`))).toEqual([sim]);
    expect(RUNS.filter((r) => matchesSearch(r, ""))).toHaveLength(RUNS.length);
  });

  it("filters the list as you type, after / puts the cursor in the search", async () => {
    setSessionToken("t0k");
    serve();
    at("/history");
    render(<App />);
    const list = await screen.findByRole("list", { name: "Runs, newest first" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(RUNS.length);
    await userEvent.keyboard("/");
    const search = screen.getByRole("searchbox", { name: "Search the runs" });
    expect(search).toHaveFocus();
    const negativeRun = RUNS.find((r) => r.outcome?.meaning === "negative")!;
    await userEvent.type(search, "disagrees");
    expect(within(list).getAllByRole("listitem")).toHaveLength(RUNS.filter((r) => matchesSearch(r, "disagrees")).length);
    expect(within(list).getByText(runTitle(negativeRun.title))).toBeInTheDocument();
  });

  it("deletes with an undo: nothing is sent while Undo is offered, and Undo sends nothing at all", async () => {
    setSessionToken("t0k");
    const target = compose.run as RunRecord;
    const { seen } = serve((req) => (req.method === "DELETE" ? json(200, RUNS.find((r) => r.id === target.id)) : undefined));
    // Settings fixture asks before deleting; the confirmation is in place.
    at(`/history?run=${target.id}`);
    render(<App />);
    const detail = await screen.findByRole("article", { name: target.title });
    await userEvent.click(within(detail).getByRole("button", { name: "Delete" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Confirm deleting this run" })).getByRole("button", { name: "Delete" }));
    const list = screen.getByRole("list", { name: "Runs, newest first" });
    expect(within(list).queryByText(runTitle(target.title))).toBeNull();
    expect(seen.some((r) => r.method === "DELETE")).toBe(false);
    await userEvent.click(await screen.findByRole("button", { name: "Undo" }));
    expect(await within(list).findByText(runTitle(target.title))).toBeInTheDocument();
    expect(seen.some((r) => r.method === "DELETE")).toBe(false);
  });

  it("sends the delete once Undo is no longer offered", async () => {
    setSessionToken("t0k");
    const target = negative.run as RunRecord;
    const { seen } = serve((req) => (req.method === "DELETE" ? json(200, RUNS.find((r) => r.id === target.id)) : undefined));
    at(`/history?run=${target.id}`);
    render(<App />);
    const detail = await screen.findByRole("article", { name: target.title });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await userEvent.click(within(detail).getByRole("button", { name: "Delete" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Confirm deleting this run" })).getByRole("button", { name: "Delete" }));
    await act(async () => {
      vi.advanceTimersByTime(UNDO_MS + 1500);
    });
    await waitFor(() => expect(seen.filter((r) => r.method === "DELETE").map((r) => r.url)).toEqual([`/api/runs/${target.id}`]));
    expect(seen.find((r) => r.method === "DELETE")!.headers.get("X-Caterva-Session")).toBe("t0k");
  });
});

describe("History's undo", () => {
  beforeEach(() => stacked(true));

  it("keeps holding the delete while the reader is on the Undo note", async () => {
    setSessionToken("t0k");
    const target = negative.run as RunRecord;
    const { seen } = serve((req) => (req.method === "DELETE" ? json(200, RUNS.find((r) => r.id === target.id)) : undefined));
    at(`/history?run=${target.id}`);
    render(<App />);
    const detail = await screen.findByRole("article", { name: target.title });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    await userEvent.click(within(detail).getByRole("button", { name: "Delete" }));
    await userEvent.click(within(screen.getByRole("group", { name: "Confirm deleting this run" })).getByRole("button", { name: "Delete" }));
    const note = screen.getByText(`Moved to the trash: ${target.title}`).closest(".toast") as HTMLElement;
    await userEvent.hover(note);
    await act(async () => {
      vi.advanceTimersByTime(UNDO_MS * 3);
    });
    expect(seen.some((r) => r.method === "DELETE")).toBe(false);
    await userEvent.click(within(note).getByRole("button", { name: "Undo" }));
    await act(async () => {
      vi.advanceTimersByTime(UNDO_MS * 2);
    });
    expect(seen.some((r) => r.method === "DELETE")).toBe(false);
  });
});

describe("About", () => {
  it("names each data source from the attribution table the exports use, and how to cite Caterva", async () => {
    setSessionToken("t0k");
    serve();
    at("/about");
    render(<App />);
    expect(await screen.findByText(citeCaterva(health.version))).toBeInTheDocument();
    for (const s of dataSources.sources) {
      expect(screen.getByText(plain(s.creator))).toBeInTheDocument();
      if (s.citation_request) expect(screen.getByText(`How to cite it: ${plain(s.citation_request)}`)).toBeInTheDocument();
    }
    const docs = screen.getByRole("link", { name: /How every parameter gets its origin/ });
    expect(docs).toHaveAttribute("href", expect.stringContaining("docs/adr/0008-parameter-provenance.md"));
  });

  it("checks the network only when asked", async () => {
    setSessionToken("t0k");
    const { seen } = serve();
    at("/about");
    render(<App />);
    await screen.findByRole("button", { name: "Check the network" });
    expect(seen.some((r) => r.url.includes("probe=network"))).toBe(false);
    await userEvent.click(screen.getByRole("button", { name: "Check the network" }));
    await waitFor(() => expect(seen.some((r) => r.url === "/api/capabilities?probe=network")).toBe(true));
  });
});

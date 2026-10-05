/**
 * The assistant on a Rates run.
 *
 * The run and its result are the REAL captured Rates fixtures the Rates screen's own tests use
 * (src/__fixtures__/api/rates). The server's answers are the recorded compose ones from the assistant's fixtures
 * (the server answers the same shapes for every kind of run; its handling of a Rates result is tested in
 * caterva/tests/test_assistant_rates.py), so these tests prove only what the PAGE does for a Rates run: which tools
 * it offers, and what it asks the server to read.
 */
import { QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";

import type { RunRecord } from "@/api/types";
import { ASSISTANT_KINDS, RunAssistant } from "@/components/assistant/RunAssistant";
import { makeQueryClient } from "@/lib/queries";

import answerExplain from "@/__fixtures__/api/assistant/answer-explain-accepted.json";
import prepareExplain from "@/__fixtures__/api/assistant/prepare-explain-accepted.json";
import statusReady from "@/__fixtures__/api/assistant/status-ready.json";
import ratesRun from "@/__fixtures__/api/rates/run-puromycin-replicates.json";
import ratesNever from "@/__fixtures__/api/rates/run-never-saturates.json";

import { json, mockServer, type SeenRequest, setSessionToken } from "./helpers";

const run = ratesRun.run as unknown as RunRecord;
const result = ratesRun.result as unknown;

function wrap(node: React.ReactNode) {
  return <QueryClientProvider client={makeQueryClient()}>{node}</QueryClientProvider>;
}

beforeEach(() => setSessionToken("token"));

const posts = (seen: SeenRequest[], path: string) => seen.filter((r) => r.method === "POST" && r.url === path);

describe("the assistant on a Rates run", () => {
  it("reads Rates results", () => {
    expect(ASSISTANT_KINDS).toContain("rates");
    expect(run.kind).toBe("rates");
  });

  it("offers explain, methods and ask, and not 'what to measure next', which Rates does not rank", async () => {
    // statusReady switches every tool on, so the absence below is the page's own decision.
    expect(Object.values(statusReady.body.features).every((f) => (f as { on: boolean }).on)).toBe(true);
    mockServer((req) => (req.url === "/api/assistant/status" ? json(200, statusReady.body) : undefined));
    render(wrap(<RunAssistant run={run} result={result} />));
    expect(await screen.findByRole("button", { name: "Explain this result" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Draft my methods" })).toBeInTheDocument();
    expect(screen.getByLabelText("Ask this run")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /What should I measure next/ })).toBeNull();
  });

  it("offers the same tools on a run whose constant is only bounded on one side", async () => {
    mockServer((req) => (req.url === "/api/assistant/status" ? json(200, statusReady.body) : undefined));
    render(wrap(<RunAssistant run={ratesNever.run as unknown as RunRecord} result={ratesNever.result as unknown} />));
    expect(await screen.findByRole("button", { name: "Explain this result" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /What should I measure next/ })).toBeNull();
  });

  it("asks the server to read the run by its id, never sending the result or the person's table", async () => {
    const { seen } = mockServer((req) => {
      const key = `${req.method} ${req.url}`;
      if (key === "GET /api/assistant/status") return json(200, statusReady.body);
      if (key === "POST /api/assistant/prepare") return json(200, prepareExplain.body);
      if (key === "POST /api/assistant/send") return json(200, answerExplain.body);
      return undefined;
    });
    render(wrap(<RunAssistant run={run} result={result} />));
    await userEvent.click(await screen.findByRole("button", { name: "Explain this result" }));
    await screen.findByText("Assistant text, not a measurement");
    expect(posts(seen, "/api/assistant/prepare")[0].body).toEqual({ feature: "explain", run_id: run.id });
    const sent = JSON.stringify(seen.map((r) => r.body ?? null));
    expect(sent).not.toContain("201.67400350707237");
    expect(sent).not.toContain("puromycin.csv");
  });
});

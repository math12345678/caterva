/**
 * The job runner: useRun's life of a run over the event stream, the shared
 * stream's reconnect with Last-Event-ID, cancel, and the notification when
 * a run finishes out of sight.
 *
 * The run records and event frames below follow docs/studio/CONTRACT.md
 * 8.2 to 8.4 field for field; they carry no science (the result is the
 * committed `caterva sim ssa` CSV), because what is under test is the
 * protocol, and the refusal reason is a real one from the recorded 503.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, renderHook, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import csv from "./fixtures/sim-ssa-a0-200-k-0.5-end-10-seed-7.csv?raw";
import createSim from "./fixtures/api/create_sim.json";
import { parseEventBlock, resetRunStreamsForTests } from "@/api/runs";
import type { RunRecord, RunStatus } from "@/api/types";
import { useRun } from "@/api/useRun";
import { Toaster } from "@/components/toast/Toaster";
import { JobsProvider, useJobs } from "@/lib/jobs";
import { resetToastsForTests } from "@/lib/toast";

import { frame, json, mockServer, parseCsv, type SeenRequest, setSessionToken, sseResponse } from "./helpers";

const ID = "20260930-141502-sim-3f9a0c1d";
const AT = "2026-09-30T14:15:02Z";
const SSA = parseCsv(csv);

function record(status: RunStatus, extra: Partial<RunRecord> = {}): RunRecord {
  return {
    schema: "caterva.studio.run/1",
    id: ID,
    kind: "sim",
    title: "caterva sim ssa --seed 7",
    status,
    created_at: AT,
    started_at: status === "queued" ? null : AT,
    finished_at: ["done", "failed", "cancelled", "interrupted"].includes(status) ? AT : null,
    caterva_version: "0.4.0",
    cli: ["caterva", "sim", "ssa", "--a0", "200", "--k", "0.5", "--end", "10", "--seed", "7"],
    request: { seed: 7, a0: 200, k: 0.5, end: 10 },
    outcome: null,
    error: null,
    artifacts: [],
    progress: null,
    ...extra,
  };
}

const base = { run_id: ID, at: AT };
const produced = { exit_code: 0, meaning: "produced", summary: `${SSA.series.time.length - 1} events`, reason: null };

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <JobsProvider>{children}</JobsProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  setSessionToken("token");
  resetRunStreamsForTests();
  resetToastsForTests();
});
afterEach(() => vi.unstubAllGlobals());

describe("parseEventBlock", () => {
  it("reads the contract's frame and checks its shape", () => {
    const e = parseEventBlock(frame("stage", 3, { ...base, stage: "simulate", label: "Simulating", fraction: null }).trim());
    expect(e).toEqual({ event: "stage", data: { ...base, seq: 3, stage: "simulate", label: "Simulating", fraction: null } });
    expect(parseEventBlock(": keep-alive")).toBeNull();
  });

  it("refuses a frame that does not match the contract, rather than drawing it", () => {
    expect(() => parseEventBlock(`event: stage\ndata: ${JSON.stringify({ ...base, seq: 1, label: "x" })}`)).toThrow(/did not match/);
  });
});

describe("useRun", () => {
  it("submits, follows every stage, and reads the result once the run ends", async () => {
    const full = [
      frame("status", 1, { ...base, status: "queued" }),
      frame("status", 2, { ...base, status: "running" }),
      frame("stage", 3, { ...base, stage: "simulate", label: "Simulating 200 molecules", fraction: null }),
      frame("log", 4, { ...base, line: "wrote the table" }),
      frame("result", 5, { ...base, outcome: produced }),
      frame("status", 6, { ...base, status: "done", outcome: produced }),
      frame("end", 7, { ...base, status: "done" }),
    ].join("");
    // Split mid-frame, as TCP may deliver it.
    const cut = Math.floor(full.length / 2) + 3;
    const { seen } = mockServer((req) => {
      if (req.method === "POST" && req.url === "/api/runs") return json(202, { run: record("queued") });
      if (req.url === `/api/runs/${ID}/events`) return sseResponse([full.slice(0, cut), full.slice(cut)]);
      if (req.url === `/api/runs/${ID}/result`) return json(200, { columns: SSA.columns, series: SSA.series });
      if (req.url === `/api/runs/${ID}`) return json(200, record("done", { outcome: produced as RunRecord["outcome"] }));
      if (req.url.startsWith("/api/runs?")) return json(200, { runs: [], next_cursor: null });
      return undefined;
    });
    const { result } = renderHook(() => useRun("sim"), { wrapper });
    await act(async () => {
      await result.current.submit({ seed: 7, a0: 200, k: 0.5, end: 10 });
    });
    await waitFor(() => expect(result.current.settled).toBe(true));
    expect(result.current.status).toBe("done");
    expect(result.current.stages.map((s) => s.label)).toEqual(["Simulating 200 molecules"]);
    expect(result.current.log).toEqual(["wrote the table"]);
    expect(result.current.outcome?.meaning).toBe("produced");
    expect((result.current.result as unknown as { columns: string[] }).columns).toEqual(["time", "a", "b"]);
    const post = seen.find((r: SeenRequest) => r.method === "POST");
    expect(post?.body).toEqual({ kind: "sim", request: { seed: 7, a0: 200, k: 0.5, end: 10 } });
  });

  it("reconnects a dropped stream from the last event it saw", async () => {
    let calls = 0;
    const { seen } = mockServer((req) => {
      if (req.url === `/api/runs/${ID}/events`) {
        calls += 1;
        if (calls === 1) {
          return sseResponse([frame("status", 1, { ...base, status: "queued" }), frame("status", 2, { ...base, status: "running" })]);
        }
        return sseResponse([
          frame("result", 3, { ...base, outcome: produced }),
          frame("status", 4, { ...base, status: "done", outcome: produced }),
          frame("end", 5, { ...base, status: "done" }),
        ]);
      }
      if (req.url === `/api/runs/${ID}/result`) return json(200, { columns: SSA.columns });
      if (req.url === `/api/runs/${ID}`) return json(200, calls === 0 ? record("running") : record("done", { outcome: produced as RunRecord["outcome"] }));
      if (req.url.startsWith("/api/runs?")) return json(200, { runs: [], next_cursor: null });
      return undefined;
    });
    const { result } = renderHook(() => useRun("sim", ID), { wrapper });
    await waitFor(() => expect(result.current.settled).toBe(true), { timeout: 4000 });
    const streams = seen.filter((r) => r.url.endsWith("/events"));
    expect(streams).toHaveLength(2);
    expect(streams[0].headers.get("Last-Event-ID")).toBeNull();
    expect(streams[1].headers.get("Last-Event-ID")).toBe("2");
    expect(result.current.status).toBe("done");
  });

  it("keeps a request the server refused apart from a run, in the server's words", async () => {
    mockServer((req) => {
      if (req.method === "POST") return createSim;
      if (req.url.startsWith("/api/runs?")) return json(200, { runs: [], next_cursor: null });
      return undefined;
    });
    const { result } = renderHook(() => useRun("sim"), { wrapper });
    await act(async () => {
      await result.current.submit({ seed: 7 });
    });
    expect(result.current.run).toBeNull();
    expect(result.current.status).toBe("idle");
    expect(result.current.requestError).toEqual(createSim.body.error);
  });

  it("asks to cancel, says so until the cancelled status arrives, and keeps no result", async () => {
    let cancelled = false;
    const gate: { release?: () => void } = {};
    const { seen } = mockServer((req) => {
      if (req.method === "POST" && req.url === "/api/runs") return json(202, { run: record("queued") });
      if (req.method === "POST" && req.url === `/api/runs/${ID}/cancel`) {
        cancelled = true;
        gate.release?.();
        return json(202, record("running"));
      }
      if (req.url === `/api/runs/${ID}/events`) {
        const encoder = new TextEncoder();
        return new Response(
          new ReadableStream<Uint8Array>({
            start(controller) {
              controller.enqueue(encoder.encode(frame("status", 1, { ...base, status: "running" })));
              gate.release = () => {
                controller.enqueue(encoder.encode(frame("status", 2, { ...base, status: "cancelled" }) + frame("end", 3, { ...base, status: "cancelled" })));
                controller.close();
              };
            },
          }),
          { status: 200 },
        );
      }
      if (req.url === `/api/runs/${ID}`) return json(200, record(cancelled ? "cancelled" : "running"));
      if (req.url.startsWith("/api/runs?")) return json(200, { runs: [], next_cursor: null });
      return undefined;
    });
    const { result } = renderHook(() => useRun("sim"), { wrapper });
    await act(async () => {
      await result.current.submit({ seed: 7 });
    });
    await waitFor(() => expect(result.current.status).toBe("running"));
    await act(async () => {
      await result.current.cancel();
    });
    await waitFor(() => expect(result.current.settled).toBe(true));
    expect(seen.some((r) => r.url.endsWith("/cancel") && r.method === "POST")).toBe(true);
    expect(result.current.status).toBe("cancelled");
    expect(result.current.cancelling).toBe(false);
    expect(result.current.result).toBeNull();
    expect(seen.some((r) => r.url.endsWith("/result"))).toBe(false);
  });
});

describe("job activity", () => {
  it("announces a run that ends out of sight, in its own words", async () => {
    const refused = { exit_code: 3, meaning: "refused", summary: "", reason: createSim.body.error.message };
    mockServer((req) => {
      if (req.url === `/api/runs/${ID}/events`) {
        return sseResponse([
          frame("status", 1, { ...base, status: "running" }),
          frame("result", 2, { ...base, outcome: refused }),
          frame("status", 3, { ...base, status: "done", outcome: refused }),
          frame("end", 4, { ...base, status: "done" }),
        ]);
      }
      if (req.url.startsWith("/api/runs?")) return json(200, { runs: [], next_cursor: null });
      return undefined;
    });
    function Starter() {
      const jobs = useJobs();
      return (
        <>
          <button type="button" onClick={() => jobs.track(record("running"), "found")}>
            track
          </button>
          <span data-testid="active">{jobs.active.length}</span>
        </>
      );
    }
    render(
      <>
        <Starter />
        <Toaster />
      </>,
      { wrapper },
    );
    act(() => screen.getByText("track").click());
    expect(await screen.findByText(`Refused: ${record("running").title}`)).toBeInTheDocument();
    expect(screen.getByText(createSim.body.error.message)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open" })).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId("active").textContent).toBe("0"));
  });
});

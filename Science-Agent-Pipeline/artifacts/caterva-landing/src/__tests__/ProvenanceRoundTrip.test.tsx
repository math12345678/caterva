/**
 * A resolved value must reach the run as RESOLVED, with its citation.
 *
 * Measured 2026-11-02 on the web path: "hexokinase glucose human" resolved
 * BRENDA's Km 6 mM (ref 641068) and refused Vmax, correctly, for want of an
 * enzyme concentration (ADR 0013). The page then:
 *
 *   - replaced the server's explanation with its own sentence, "vmax is
 *     yours to choose, not something the literature reports" -- the
 *     opposite of what the server said (state [E]0 and Vmax is derived from
 *     the cited kcat);
 *   - on "run", re-sent every field as `key=value`
 *     ("... km=6 vmax=5 s0=10 end=10 points=51"), which the resolver reads
 *     as the person typing it, so the run reported km origin "user" with no
 *     citation, and the illustrative s0/end/points as the student's own.
 *
 * These tests drive the component the way a person does and check what it
 * SENDS, because the laundering happened in the request, not the display.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";

const runSimulation = vi.fn();
const listSimulationJobs = vi.fn();

vi.mock("@workspace/api-client-react", async (importOriginal) => {
  const original =
    await importOriginal<typeof import("@workspace/api-client-react")>();
  return {
    ...original,
    runSimulation: (...args: unknown[]) => runSimulation(...args),
    listSimulationJobs: (...args: unknown[]) => listSimulationJobs(...args),
  };
});

import AgentSimulator from "../cli/AgentSimulator";
import RecentRuns from "../cli/RecentRuns";
import KineticsPlayground from "../cli/KineticsPlayground";

const KM_CITATION =
  "BRENDA (ref 641068) — https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1";

const ENZYME_CONC_DETAIL =
  "Vmax is not a property of the enzyme on its own — it is kcat × [E]0, so " +
  "it depends on how much enzyme is in YOUR assay. State the enzyme " +
  'concentration — e.g. "with 50 nM enzyme" — and Vmax is derived and cited for you.';

/** The 422 /api/resolve really returns for "hexokinase glucose human". */
function refusal(vmaxReason: string, vmaxDetail: string) {
  return {
    error: "RequiredParametersMissingError",
    message: `Cannot simulate 'mm': vmax is unresolved. vmax: ${vmaxDetail}`,
    missingKeys: ["vmax"],
    domain: "mm",
    resolvedParameters: { km: 6, s0: 10, end: 10, points: 51 },
    details: { vmax: vmaxDetail },
    parameterProvenance: {
      km: {
        origin: "resolved",
        source: "brenda_exact",
        citation: KM_CITATION,
        organism: "Homo sapiens",
        citationStatus: "verified",
      },
      vmax: { origin: "default", unresolvedReason: vmaxReason, note: vmaxDetail },
      s0: { origin: "default", note: "No literature lookup exists for s0." },
      end: { origin: "default" },
      points: { origin: "default" },
    },
  };
}

function mockFetch(resolveBody: unknown, status = 422) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      if (url === "/api/enzymes") {
        return new Response("[]", { status: 200 });
      }
      if (url === "/api/resolve") {
        return new Response(JSON.stringify(resolveBody), { status });
      }
      return new Response("{}", { status: 404 });
    }),
  );
}

/** A completed run, shaped as /api/simulate returns it. */
const COMPLETED_JOB = {
  jobId: "job-1",
  status: "completed",
  query: "hexokinase glucose human with 50 nM enzyme",
  progress: 100,
  createdAt: "2026-11-02T00:00:00Z",
  updatedAt: "2026-11-02T00:00:01Z",
  result: {
    runId: "job-1",
    domain: "mm",
    parameters: { km: 6, vmax: 0.002005, s0: 10, end: 10, points: 51 },
    trajectory: [
      { t: 0, S: 10, P: 0 },
      { t: 10, S: 9.98, P: 0.02 },
    ],
    provenance: { reasoning: "keyword", modelCitations: [], flags: [] },
    parameterProvenance: {
      km: {
        origin: "resolved",
        citation: KM_CITATION,
        organism: "Homo sapiens",
      },
      vmax: {
        origin: "resolved",
        citation:
          "BRENDA (ref 739603) — https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
        organism: "Homo sapiens",
        note: "Vmax = kcat (40.1 1/s, cited below) × enzyme_conc (0.00005 mM).",
      },
      s0: { origin: "default" },
      end: { origin: "default" },
      points: { origin: "default" },
    },
    completedAt: "2026-11-02T00:00:01Z",
  },
};

async function resolve(query: string) {
  render(<AgentSimulator />);
  fireEvent.change(screen.getByPlaceholderText(/simulate/i), {
    target: { value: query },
  });
  fireEvent.click(screen.getByRole("button", { name: /^resolve$/i }));
  await screen.findByTestId("server-refusal");
}

function sentQuery(): string {
  expect(runSimulation).toHaveBeenCalledTimes(1);
  return (runSimulation.mock.calls[0]![0] as { query: string }).query;
}

beforeEach(() => {
  runSimulation.mockReset();
  listSimulationJobs.mockReset();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("the resolve -> run round trip keeps provenance", () => {
  it("shows the server's refusal, not a paraphrase that contradicts it", async () => {
    mockFetch(refusal("enzyme_conc_not_supplied", ENZYME_CONC_DETAIL));
    await resolve("hexokinase glucose human");
    const box = screen.getByTestId("server-refusal");
    expect(box).toHaveTextContent("kcat × [E]0");
    expect(box).toHaveTextContent("with 50 nM enzyme");
    expect(screen.queryByText(/yours to choose/i)).toBeNull();
  });

  it("shows where the resolved Km came from before the run", async () => {
    mockFetch(refusal("enzyme_conc_not_supplied", ENZYME_CONC_DETAIL));
    await resolve("hexokinase glucose human");
    expect(screen.getByTestId("origin-km")).toHaveTextContent(
      "resolved · BRENDA (ref 641068)",
    );
    expect(screen.getByTestId("origin-km")).toHaveTextContent("Homo sapiens");
    expect(screen.getByTestId("origin-s0")).toHaveTextContent(/default/);
  });

  it("sends the enzyme concentration as the phrase the resolver reads, and no resolved value", async () => {
    mockFetch(refusal("enzyme_conc_not_supplied", ENZYME_CONC_DETAIL));
    runSimulation.mockResolvedValue(COMPLETED_JOB);
    await resolve("hexokinase glucose human");

    const run = screen.getByRole("button", { name: /run pipeline|fix parameter/i });
    // Vmax is missing and no [E]0 yet: nothing to run on.
    expect(run).toBeDisabled();

    fireEvent.change(screen.getByLabelText("enzyme concentration (nM)"), {
      target: { value: "50" },
    });
    expect(run).not.toBeDisabled();
    fireEvent.click(run);

    await waitFor(() => expect(runSimulation).toHaveBeenCalled());
    const q = sentQuery();
    expect(q).toBe("hexokinase glucose human with 50 nM enzyme");
    // The resolved Km and the illustrative defaults are NOT echoed back as
    // if the person had typed them.
    expect(q).not.toMatch(/\bkm=|\bs0=|\bend=|\bpoints=|\bvmax=/);
  });

  it("renders each parameter's citation and organism in the result", async () => {
    mockFetch(refusal("enzyme_conc_not_supplied", ENZYME_CONC_DETAIL));
    runSimulation.mockResolvedValue(COMPLETED_JOB);
    await resolve("hexokinase glucose human");
    fireEvent.change(screen.getByLabelText("enzyme concentration (nM)"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByRole("button", { name: /run pipeline/i }));

    const list = await screen.findByTestId("parameter-provenance");
    expect(list).toHaveTextContent(
      "km 6 mM — resolved · BRENDA (ref 641068) — https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1 · Homo sapiens",
    );
    expect(list).toHaveTextContent("vmax 0.002005 mM/s — resolved · BRENDA (ref 739603)");
    expect(list).toHaveTextContent("s0 10 mM — default (illustrative, not literature)");
  });

  it("sends a value the person EDITED, and only that one", async () => {
    mockFetch(refusal("enzyme_conc_not_supplied", ENZYME_CONC_DETAIL));
    runSimulation.mockResolvedValue(COMPLETED_JOB);
    await resolve("hexokinase glucose human");
    const s0 = screen
      .getByTestId("origin-s0")
      .parentElement!.querySelector("input")!;
    fireEvent.change(s0, { target: { value: "2" } });
    expect(screen.getByTestId("origin-s0")).toHaveTextContent(/yours/);
    fireEvent.change(screen.getByLabelText("enzyme concentration (nM)"), {
      target: { value: "50" },
    });
    fireEvent.click(screen.getByRole("button", { name: /run pipeline/i }));
    await waitFor(() => expect(runSimulation).toHaveBeenCalled());
    expect(sentQuery()).toBe("hexokinase glucose human with 50 nM enzyme s0=2");
  });

  it("when no kcat exists, asks for a Vmax the person measured, labelled as theirs", async () => {
    const noKcat =
      "Vmax = kcat × [E]0, and your enzyme concentration was read. BRENDA " +
      "holds a kcat for this enzyme from Oryctolagus cuniculus, but none " +
      "measured in Homo sapiens.";
    mockFetch(refusal("not_found", noKcat));
    runSimulation.mockResolvedValue(COMPLETED_JOB);
    await resolve("lactate dehydrogenase with pyruvate in humans with 50 nM enzyme");

    expect(screen.getByTestId("server-refusal")).toHaveTextContent(
      "none measured in Homo sapiens",
    );
    // No enzyme-concentration field: there is no kcat to multiply it by.
    expect(screen.queryByLabelText("enzyme concentration (nM)")).toBeNull();
    expect(
      screen.getByText("Vmax you measured (mM/s) — no kcat to derive it"),
    ).toBeInTheDocument();

    const vmax = screen
      .getByTestId("origin-vmax")
      .parentElement!.querySelector("input")!;
    fireEvent.change(vmax, { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /run pipeline/i }));
    await waitFor(() => expect(runSimulation).toHaveBeenCalled());
    expect(sentQuery()).toBe(
      "lactate dehydrogenase with pyruvate in humans with 50 nM enzyme vmax=3",
    );
  });

  it("refuses a malformed enzyme concentration instead of sending it", async () => {
    mockFetch(refusal("enzyme_conc_not_supplied", ENZYME_CONC_DETAIL));
    await resolve("hexokinase glucose human");
    fireEvent.change(screen.getByLabelText("enzyme concentration (nM)"), {
      target: { value: "5e-2" },
    });
    expect(screen.getByText("A positive number in nM")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /fix parameter errors/i }),
    ).toBeDisabled();
  });
});

describe("Recent Runs says when it is showing a cached list", () => {
  it("labels the localStorage fallback 'cached, API unreachable'", async () => {
    localStorage.setItem(
      "caterva:recent-runs",
      JSON.stringify([{ ...COMPLETED_JOB, jobId: "cached-1" }]),
    );
    listSimulationJobs.mockRejectedValue(new Error("Failed to fetch"));
    render(<RecentRuns pollInterval={60_000} />);
    expect(await screen.findByTestId("runs-cached-label")).toHaveTextContent(
      "cached, API unreachable",
    );
    localStorage.removeItem("caterva:recent-runs");
  });

  it("labels a list that was live until the API went away", async () => {
    // No saved copy at all: the first fetch answers, the next one fails.
    // What stays on screen is no longer current and must say so.
    localStorage.removeItem("caterva:recent-runs");
    listSimulationJobs
      .mockResolvedValueOnce([COMPLETED_JOB])
      .mockRejectedValue(new Error("Failed to fetch"));
    render(<RecentRuns pollInterval={50} />);
    await waitFor(() => expect(listSimulationJobs).toHaveBeenCalledTimes(1));
    expect(screen.queryByTestId("runs-cached-label")).toBeNull();
    expect(
      await screen.findByTestId("runs-cached-label", {}, { timeout: 2000 }),
    ).toHaveTextContent("cached, API unreachable");
    localStorage.removeItem("caterva:recent-runs");
  });

  it("drops the label once the API answers", async () => {
    localStorage.setItem(
      "caterva:recent-runs",
      JSON.stringify([{ ...COMPLETED_JOB, jobId: "cached-1" }]),
    );
    listSimulationJobs.mockResolvedValue([COMPLETED_JOB]);
    render(<RecentRuns pollInterval={60_000} />);
    await waitFor(() => expect(listSimulationJobs).toHaveBeenCalled());
    await waitFor(() =>
      expect(screen.queryByTestId("runs-cached-label")).toBeNull(),
    );
    localStorage.removeItem("caterva:recent-runs");
  });
});

describe("the kinetics playground preset", () => {
  it("labels Vmax and s0 as illustrative next to the cited Km", () => {
    render(<KineticsPlayground />);
    const note = screen.getByTestId("preset-provenance");
    expect(note).toHaveTextContent("Hexokinase: Km 6 mM — BRENDA ref 641068");
    expect(note).toHaveTextContent(
      "are illustrative experimental choices, not literature values",
    );
    expect(screen.queryByRole("button", { name: "LDH" })).toBeNull();
    expect(screen.queryByRole("button", { name: "AChE" })).toBeNull();
  });
});

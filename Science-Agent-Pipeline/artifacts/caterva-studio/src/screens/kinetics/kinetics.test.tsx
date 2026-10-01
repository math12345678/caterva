/**
 * The kinetics screens over real API responses (src/__fixtures__/api/kinetics,
 * captured from the studio server's dispatch on real inputs; README there).
 * No number in these tests is typed by hand: each expectation is read from
 * the fixture it renders.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import bindDisagrees from "@/__fixtures__/api/kinetics/bind-quinoline-disagrees.json";
import bindList from "@/__fixtures__/api/kinetics/bind-list.json";
import bindNoRows from "@/__fixtures__/api/kinetics/bind-no-rows.json";
import bindSurvey from "@/__fixtures__/api/kinetics/bind-survey.json";
import analyses from "@/__fixtures__/api/kinetics/compose-binding-analyses.json";
import charts from "@/__fixtures__/api/kinetics/compose-binding-charts.json";
import gossypol from "@/__fixtures__/api/kinetics/compose-ldh-gossypol.json";
import noncompetitive from "@/__fixtures__/api/kinetics/compose-ldh-noncompetitive.json";
import malformed from "@/__fixtures__/api/kinetics/compose-malformed.json";
import shapes from "@/__fixtures__/api/kinetics/compose-shapes.json";
import unrecognised from "@/__fixtures__/api/kinetics/compose-unrecognised.json";
import constants from "@/__fixtures__/api/kinetics/constants-hexokinase.json";
import simAssociation from "@/__fixtures__/api/kinetics/sim-association.json";
import simDecay from "@/__fixtures__/api/kinetics/sim-decay.json";
import capabilities from "@/__fixtures__/api/workspace/capabilities.json";
import { frame, json, mockServer, setSessionToken, sseResponse } from "@/__tests__/helpers";
import { resetRunStreamsForTests } from "@/api/runs";
import type { ApiError, BindResult, ComposeResult, ConstantsResult, RunKind, RunRecord, SimResult, SourcedValue } from "@/api/types";
import type { RunState } from "@/api/useRun";
import { fieldError } from "@/components/forms/Field";
import { shellQuote } from "@/components/report/Report";
import { formatValue } from "@/lib/format";

import BindScreen, { bindForm, bindRequest } from "../Bind";
import ComposeScreen, { composeForm, composeRequest, EMPTY_COMPOSE } from "../Compose";
import { simForm, simRequest } from "../Sim";
import { BindResultView } from "./BindResult";
import { composeExports, ComposeResultView } from "./ComposeResult";
import { composeHref, ConstantsResultView } from "./ConstantsResult";
import { KineticsRun } from "./kit";
import { designGains, perturbationEffects, robustnessSamples, stochasticRun, sweepSeries } from "./sections";
import { parseShapes, ShapeCatalogue } from "./ShapeCatalogue";
import { SimResultView } from "./SimResult";

type Captured = {
  captured: { request: Record<string, unknown> } | { kind: string; request: Record<string, unknown> };
  run: unknown;
  result: unknown;
  events: { event: string; data: Record<string, unknown> }[];
};

const cap = <T,>(x: unknown) => x as T;

function finished<K extends RunKind>(fixture: Captured): RunState<K> & { cancel: () => Promise<void> } {
  const run = fixture.run as RunRecord;
  return {
    run,
    status: run.status,
    stage: null,
    stages: [],
    log: [],
    outcome: run.outcome,
    result: fixture.result as RunState<K>["result"],
    requestError: null,
    runError: run.error,
    submitting: false,
    cancelling: false,
    settled: true,
    cancel: async () => {},
  };
}

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function param(result: ComposeResult, id: string): SourcedValue {
  return result.model.parameters.find((p) => p.id === id)!;
}

function requestOf(fixture: Captured): Record<string, unknown> {
  const c = fixture.captured as { request: Record<string, unknown> };
  return ("kind" in c.request ? (c.request.request as Record<string, unknown>) : c.request) as Record<string, unknown>;
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetRunStreamsForTests();
});

describe("Compose result", () => {
  const result = cap<ComposeResult>(gossypol.result);
  const run = cap<RunRecord>(gossypol.run);

  it("says the verdict first, with the worst concern the library named", () => {
    render(<ComposeResultView result={result} run={run} />);
    const verdict = screen.getByRole("region", { name: result.verdict!.verdict });
    expect(within(verdict).getByText(result.verdict!.licence)).toBeInTheDocument();
    const worst = result.verdict!.concerns[0];
    expect(within(verdict).getByText("The worst thing wrong with it")).toBeInTheDocument();
    expect(within(verdict).getByText(worst.detail)).toBeInTheDocument();
    expect(within(verdict).getByText(worst.remedy)).toBeInTheDocument();
    // The verdict precedes the table of where the numbers come from.
    const table = screen.getByRole("region", { name: "Where the numbers come from" });
    expect(verdict.compareDocumentPosition(table) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("puts the gossypol Ki one click from its BRENDA reference, with the row's words and scope inline", async () => {
    const ki = param(result, "reaction_Ki");
    expect(ki.provenance.kind).toBe("measured");
    render(<ComposeResultView result={result} run={run} />);
    const table = screen.getByRole("region", { name: "Where the numbers come from" });
    // Inline in the ledger: the row's commentary and every scope concern, verbatim.
    expect(within(table).getByText(ki.provenance.commentary!)).toBeInTheDocument();
    for (const s of ki.provenance.scope!) expect(within(table).getByText(s)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: new RegExp(`^${ki.label}, ${formatValue(ki)} `) }));
    const popover = await screen.findByRole("dialog");
    const link = within(popover).getByRole("link", { name: new RegExp(`^${escape(ki.provenance.citation!.text)}(,|$)`) });
    expect(link).toHaveAttribute("href", ki.provenance.citation!.url);
  });

  it("shows a placeholder's reason in the resolver's words", async () => {
    const kcat = param(result, "reaction_kcat");
    expect(kcat.provenance.kind).toBe("placeholder");
    render(<ComposeResultView result={result} run={run} />);
    const table = screen.getByRole("region", { name: "Where the numbers come from" });
    expect(within(table).getByText(kcat.provenance.reason!)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /^kcat, .*placeholder, not measured$/ }));
    const popover = await screen.findByRole("dialog");
    expect(within(popover).getByText(kcat.provenance.reason!)).toBeInTheDocument();
  });

  it("says why a noncompetitive model carries the noncompetitive row", () => {
    const r = cap<ComposeResult>(noncompetitive.result);
    const ki = param(r, "reaction_Ki");
    expect(ki.provenance.chosen_because).toBeTruthy();
    render(<ComposeResultView result={r} run={cap<RunRecord>(noncompetitive.run)} />);
    expect(screen.getByRole("button", { name: new RegExp(`^Ki, ${formatValue(ki)} mM, measured, cited$`) })).toBeInTheDocument();
    expect(screen.getByText(ki.provenance.chosen_because!)).toBeInTheDocument();
  });

  it("draws every section under its heading, a refused one with the engine's reason and a link from the verdict", () => {
    const r = cap<ComposeResult>(analyses.result);
    const record = cap<RunRecord>(analyses.run);
    render(<ComposeResultView result={r} run={record} />);
    for (const section of r.sections) {
      const region = screen.getByRole("region", { name: section.title });
      expect(within(region).getByText(section.status === "answered" ? "answered" : section.status === "refused" ? "refused" : "partly refused")).toBeInTheDocument();
    }
    const refused = r.sections.find((s) => s.status === "refused")!;
    const region = screen.getByRole("region", { name: refused.title });
    expect(within(region).getByRole("region", { name: "Refused, and why" })).toHaveTextContent(refused.refusals[0].slice(0, 60));
    expect(screen.getByRole("link", { name: refused.title })).toHaveAttribute("href", `#k-section-${refused.key}`);
    expect(screen.getByText(record.outcome!.reason!)).toBeInTheDocument();
  });

  it("draws a figure for each analysis that has one, from the section's own data", () => {
    const r = cap<ComposeResult>(charts.result);
    render(<ComposeResultView result={r} run={cap<RunRecord>(charts.run)} />);
    const robustness = robustnessSamples(r.sections.find((s) => s.key === "robustness")!.data)!;
    expect(screen.getByRole("heading", { name: `Did "${robustness.conclusion}" hold in each draw?` })).toBeInTheDocument();
    const effects = perturbationEffects(r.sections.find((s) => s.key === "perturbations")!.data)!;
    expect(screen.getByRole("heading", { name: `What each perturbation does to ${effects.readout}` })).toBeInTheDocument();
    expect(designGains(r.sections.find((s) => s.key === "design")!.data)!.length).toBeGreaterThan(0);
    expect(screen.getByRole("heading", { name: "What each measurement would add" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "How many directions a measurement can pin down" })).toBeInTheDocument();
    const ssa = stochasticRun(r.sections.find((s) => s.key === "stochastic")!.data)!;
    expect(ssa.times.length).toBe(Object.values(ssa.counts)[0].length);
    expect(screen.getByRole("heading", { name: "One exact stochastic trajectory" })).toBeInTheDocument();
    const sweep = sweepSeries(r.sweeps[0])!;
    expect(screen.getByRole("heading", { name: `Stable steady states as ${sweep.parameter} is swept` })).toBeInTheDocument();
    expect(sweep.rows.length).toBe((r.sweeps[0].points as unknown[]).length);
  });

  it("reads the robustness draws exactly as the library returned them", () => {
    const r = cap<ComposeResult>(charts.result);
    const data = r.sections.find((s) => s.key === "robustness")!.data as { report: { evaluated: { values: Record<string, number>; held: boolean }[]; varied: string[] } };
    const parsed = robustnessSamples(data)!;
    expect(parsed.samples.map((s) => s.values)).toEqual(data.report.evaluated.map((e) => e.values));
    expect(parsed.samples.map((s) => s.held)).toEqual(data.report.evaluated.map((e) => e.held));
  });

  it("offers each export the run wrote, and the result as JSON", () => {
    const r = cap<ComposeResult>(gossypol.result);
    const exports = composeExports(r, run);
    expect(exports.map((e) => e.label)).toEqual(["Methods", "CSV", "SBML", "Antimony", "JSON"]);
    for (const e of exports.slice(0, 4)) expect(run.artifacts.map((a) => a.name)).toContain(e.artifact);
  });
});

describe("A kinetics run", () => {
  it("downloads an export with the session header and links to the saved run", async () => {
    setSessionToken("t0k");
    const state = finished<"compose">(gossypol as Captured);
    const { seen } = mockServer(() => new Response("<sbml/>", { status: 200, headers: { "Content-Disposition": 'attachment; filename="model.xml"' } }));
    const created = vi.fn(() => "blob:x");
    vi.stubGlobal("URL", Object.assign(Object.create(URL), { createObjectURL: created, revokeObjectURL: () => {} }));
    // jsdom cannot follow a download link; the click itself is what the page does.
    const clicked = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
    render(
      <KineticsRun<"compose"> state={state} path="/compose" idle={null} exports={composeExports}>
        {(r, record) => <ComposeResultView result={r} run={record} />}
      </KineticsRun>,
    );
    const toolbar = screen.getByRole("toolbar", { name: "This run" });
    expect(within(toolbar).getByRole("button", { name: "Copy link" })).toHaveAttribute("title", expect.stringContaining(`/compose?run=${state.run!.id}`));
    await userEvent.click(within(toolbar).getByRole("button", { name: "SBML" }));
    await waitFor(() => expect(created).toHaveBeenCalled());
    expect(clicked).toHaveBeenCalled();
    clicked.mockRestore();
    expect(seen[0].url).toBe(`/api/runs/${state.run!.id}/artifacts/model.xml`);
    expect(seen[0].headers.get("X-Caterva-Session")).toBe("t0k");
    // The command that reproduces it, as the server recorded it.
    await userEvent.click(screen.getByRole("button", { name: "The same run in a terminal" }));
    expect(document.querySelector(".slab-body")?.textContent).toBe(`$ ${state.run!.cli.map(shellQuote).join(" ")}`);
  });

  it("shows a refusal with no result as the command's reason", () => {
    const state = finished<"compose">(unrecognised as Captured);
    expect(state.result).toBeNull();
    render(
      <KineticsRun<"compose"> state={state} path="/compose" idle={null}>
        {(r, record) => <ComposeResultView result={r} run={record} />}
      </KineticsRun>,
    );
    expect(screen.getByText(state.outcome!.reason!.replace(/\s+/g, " ").trim(), { normalizer: (t) => t.replace(/\s+/g, " ").trim() })).toBeInTheDocument();
  });

  it("shows a running compose as each stage the server reported, the constants it looks up among them", () => {
    const stages = (gossypol as Captured).events
      .filter((e) => e.event === "stage")
      .slice(0, 6)
      .map((e) => ({ stage: String(e.data.stage), label: String(e.data.label), fraction: null, at: String(e.data.at) }));
    const last = stages[stages.length - 1];
    const state = { ...finished<"compose">(gossypol as Captured), status: "running" as const, result: null, settled: false, stage: last, stages };
    render(
      <KineticsRun<"compose"> state={state} path="/compose" idle={null}>
        {() => null}
      </KineticsRun>,
    );
    expect(screen.getAllByText(last.label).length).toBeGreaterThan(0);
    const list = screen.getByRole("list", { name: "Stages so far" });
    for (const s of stages) expect(within(list).getByText(s.label)).toBeInTheDocument();
    expect(stages.some((s) => s.label.startsWith("Looking up "))).toBe(true);
  });

});

describe("Compose form", () => {
  it("maps the form to the request the CLI's flags expect", () => {
    const request = composeRequest({
      ...EMPTY_COMPOSE,
      description: " Michaelis Menten ",
      subject: "1.1.1.27",
      substrate: "pyruvate",
      any_mode: true,
      analyses: { crnt: true, validate: false },
      robustness: true,
      knockout: "E, S",
    });
    expect(request).toEqual({
      description: "Michaelis Menten",
      subject: "1.1.1.27",
      substrate: "pyruvate",
      any_mode: true,
      analyses: { crnt: true, robustness: { samples: null }, knockout: ["E", "S"] },
    });
  });

  it("fills the form back from a stored request, so a reopened run shows its question", () => {
    for (const fixture of [gossypol, analyses, charts] as Captured[]) {
      const stored = (fixture.run as RunRecord).request;
      expect(composeRequest(composeForm(stored))).toEqual(stored);
    }
  });

  it("puts a 400 under the field it names, and nowhere else", () => {
    const error = malformed.body.error as ApiError;
    expect(fieldError(error, "description")).toBeNull();
    const named: ApiError = { ...error, field: "analyses.robustness.samples" };
    expect(fieldError(named, "analyses.robustness")).toBe(error.message);
    expect(fieldError(named, "subject")).toBeNull();
  });

  it("offers the shapes the grammar recognises and writes the chosen one into the field", async () => {
    const onPick = vi.fn();
    const parsed = parseShapes(shapes.shapes);
    render(<ShapeCatalogue shapes={shapes.shapes} onPick={onPick} />);
    await userEvent.click(screen.getByRole("button", { name: `Browse the ${parsed.length} shapes it recognises` }));
    const list = screen.getByRole("list", { name: "Recognised shapes" });
    expect(within(list).getAllByRole("button")).toHaveLength(parsed.length);
    await userEvent.type(screen.getByRole("searchbox", { name: "Filter the shapes" }), parsed[0].name);
    await userEvent.click(within(list).getAllByRole("button")[0]);
    expect(onPick).toHaveBeenCalledWith(parsed[0].description);
  });
});

/**
 * The panes stacked, as in a 1024 px window: react-resizable-panels hit-tests
 * pointer events against its handles' boxes, which jsdom gives no size, so
 * in the side-by-side layout a simulated click never reaches a field.
 */
function stacked(on: boolean) {
  (window as unknown as { __setMedia?: (q: string, v: boolean) => void }).__setMedia?.("(max-width: 1099px)", on);
}

afterEach(() => stacked(false));

function withApp(path: string, children: ReactNode) {
  const memory = memoryLocation({ path });
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <Router hook={memory.hook} searchHook={memory.searchHook}>
        {children}
      </Router>
    </QueryClientProvider>
  );
}

function replay(fixture: Captured): Response {
  return sseResponse(fixture.events.map((e, i) => frame(e.event, i + 1, e.data)));
}

describe("Compose screen", () => {
  it("reopens a saved run with its question in the form and its verdict beside it", async () => {
    setSessionToken("t0k");
    const fixture = gossypol as Captured;
    const run = fixture.run as RunRecord;
    mockServer((req) => {
      if (req.url === `/api/runs/${run.id}`) return json(200, run);
      if (req.url === `/api/runs/${run.id}/result`) return json(200, fixture.result);
      if (req.url === `/api/runs/${run.id}/events`) return replay(fixture);
      if (req.url === "/api/compose/shapes") return json(200, shapes);
      return undefined;
    });
    render(withApp(`/compose?run=${run.id}`, <ComposeScreen />));
    const result = cap<ComposeResult>(fixture.result);
    expect(await screen.findByRole("region", { name: result.verdict!.verdict })).toBeInTheDocument();
    expect(screen.getByLabelText("Mechanism")).toHaveValue(String(run.request.description));
    expect(screen.getByLabelText(/^Enzyme/)).toHaveValue(String(run.request.subject));
    expect(screen.getByLabelText(/^Inhibitor/)).toHaveValue(String(run.request.inhibitor));
  });

  it("fills the form from a linked question and runs nothing until asked", async () => {
    setSessionToken("t0k");
    const { seen } = mockServer((req) => (req.url === "/api/compose/shapes" ? json(200, shapes) : undefined));
    render(withApp("/compose?description=Michaelis-Menten&subject=2.7.1.1&organism=human&substrate=glucose", <ComposeScreen />));
    await waitFor(() => expect(screen.getByLabelText("Mechanism")).toHaveValue("Michaelis-Menten"));
    expect(screen.getByLabelText(/^Organism/)).toHaveValue("human");
    expect(seen.some((r) => r.method === "POST")).toBe(false);
  });

  it("submits on Cmd-Enter and shows the server's 400 under the field it names", async () => {
    setSessionToken("t0k");
    const error = { ...(malformed.body.error as ApiError), field: "analyses.robustness" };
    const { seen } = mockServer((req) => {
      if (req.url === "/api/compose/shapes") return json(200, shapes);
      if (req.method === "POST" && req.url === "/api/runs") return json(400, { error });
      return undefined;
    });
    stacked(true);
    render(withApp("/compose", <ComposeScreen />));
    await userEvent.type(screen.getByLabelText("Mechanism"), "reversible binding");
    await userEvent.click(screen.getByRole("checkbox", { name: /Robustness to the placeholders/ }));
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(seen.some((r) => r.method === "POST")).toBe(true));
    expect(await screen.findAllByText(error.message)).not.toHaveLength(0);
    const post = seen.find((r) => r.method === "POST")!;
    expect(post.body).toEqual({ kind: "compose", request: { description: "reversible binding", analyses: { robustness: { samples: null } } } });
  });
});

describe("Constants", () => {
  const result = cap<ConstantsResult>(constants.result);
  const request = requestOf(constants as Captured);

  it("lists every row the resolver read, each with the paper that measured it", () => {
    render(<ConstantsResultView result={result} request={request} />);
    const km = result.constants[0];
    const table = screen.getByRole("table", { name: /Every Km row the resolver read/ });
    for (const v of [km.value!, ...km.alternatives]) {
      expect(within(table).getByRole("button", { name: new RegExp(`${escape(formatValue(v))} ${v.unit}, measured, cited`) })).toBeInTheDocument();
    }
    expect(within(table).getAllByText(km.value!.provenance.citation!.text).length).toBeGreaterThan(0);
    expect(within(table).getAllByText(km.value!.provenance.commentary!).length).toBeGreaterThan(0);
  });

  it("sends a constant to Compose by filling its form with the same enzyme, organism and substrate", () => {
    render(withApp("/constants", <ConstantsResultView result={result} request={request} />));
    const link = screen.getByRole("link", { name: "Use in Compose" });
    expect(link).toHaveAttribute("href", composeHref(request, "km"));
    const params = new URLSearchParams(composeHref(request, "km").split("?")[1]);
    expect(params.get("subject")).toBe(request.ec);
    expect(params.get("organism")).toBe(request.organism);
    expect(params.get("substrate")).toBe(request.substrate);
  });

  it("marks the values cite.py supplied as its defaults, and says what it declined", () => {
    render(<ConstantsResultView result={result} request={request} />);
    for (const v of result.supplied) {
      expect(v.provenance.by).toBe("default");
      expect(screen.getByRole("button", { name: new RegExp(`^${v.id}, .*a stated default$`) })).toBeInTheDocument();
    }
    for (const r of result.refusals) expect(screen.getByText(r)).toBeInTheDocument();
  });
});

describe("Stochastic", () => {
  it("shows the final counts and the ODE expectation, each with its mark", () => {
    const result = cap<SimResult>(simDecay.result);
    render(<SimResultView result={result} />);
    for (const v of Object.values(result.final)) {
      expect(screen.getAllByRole("button", { name: new RegExp(`${escape(formatValue(v))}.*computed by Caterva`) }).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("button", { name: new RegExp(`^${escape(result.expected.label!)}`) })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Molecule counts, one step per event" })).toBeInTheDocument();
  });

  it("marks each input as yours", () => {
    const result = cap<SimResult>(simAssociation.result);
    render(<SimResultView result={result} />);
    for (const [name, v] of Object.entries(result.parameters)) {
      expect(screen.getByRole("button", { name: new RegExp(`^${name}, ${escape(formatValue(v))} .*chosen by you$`) })).toBeInTheDocument();
    }
  });

  it("sends the seed and never leaves k to the default, and reads a stored request back", () => {
    const form = { reaction: "association" as const, seed: "7", a0: "", b0: "80", k: "0.005", end: "" };
    expect(simRequest(form)).toEqual({ seed: 7, bimolecular: true, k: 0.005, b0: 80 });
    const stored = (simAssociation.run as RunRecord).request;
    expect(simRequest(simForm(stored))).toEqual(stored);
  });
});

describe("Binding", () => {
  it("draws a disagreement as a negative finding with its arithmetic", () => {
    const result = cap<BindResult>(bindDisagrees.result);
    const run = cap<RunRecord>(bindDisagrees.run);
    render(<BindResultView result={result} run={run} />);
    const verdict = screen.getByRole("region", { name: `The computed value ${result.verdict!.word}` });
    expect(within(verdict).getByText(run.outcome!.reason!)).toBeInTheDocument();
    for (const v of [result.verdict!.gap_kcal, result.verdict!.ki_fold]) {
      expect(within(verdict).getByRole("button", { name: new RegExp(escape(formatValue(v))) })).toBeInTheDocument();
      expect(within(verdict).getByText(v.provenance.method!)).toBeInTheDocument();
    }
    // Each cited Ki beside the ΔG°bind computed from it, with the library's method once.
    const method = result.target!.used[0].dg.provenance.method!;
    expect(screen.getByText(method)).toBeInTheDocument();
    for (const row of result.target!.used) {
      expect(screen.getAllByRole("button", { name: new RegExp(`^Ki, ${escape(formatValue(row.ki))} mM`) }).length).toBeGreaterThan(0);
      expect(screen.getAllByRole("button", { name: new RegExp(`^ΔG°bind, ${escape(formatValue(row.dg))} kcal/mol, computed by Caterva`) }).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("img", { name: /ΔG°bind of 2 Ki row/ })).toBeInTheDocument();
  });

  it("lists the survey with the band where there is one", () => {
    const result = cap<BindResult>(bindSurvey.result);
    render(<BindResultView result={result} run={cap<RunRecord>(bindSurvey.run)} />);
    expect(screen.getAllByRole("row")).toHaveLength(result.survey.length + 1);
  });

  it("asks for a listed compound's target in one click", async () => {
    const result = cap<BindResult>(bindList.result);
    const onPick = vi.fn();
    render(<BindResultView result={result} run={cap<RunRecord>(bindList.run)} onPick={onPick} />);
    await userEvent.click(screen.getByRole("button", { name: result.compounds[0] }));
    expect(onPick).toHaveBeenCalledWith(result.compounds[0]);
  });

  it("shows no Ki row as a refusal naming the compounds that have one", () => {
    const state = finished<"bind">(bindNoRows as Captured);
    render(
      <KineticsRun<"bind"> state={state} path="/bind" idle={null}>
        {(r, record) => <BindResultView result={r} run={record} />}
      </KineticsRun>,
    );
    expect(screen.getByRole("region", { name: state.outcome!.summary })).toHaveTextContent("Compounds that do have one");
  });

  it("sends a computed value with its unit and σ, and reads a stored request back", () => {
    expect(
      bindRequest({ mode: "inhibitor", ec: "1.1.1.27", organism: "human", inhibitor: "gossypol", state: "free", isoform: "", computed: "-7.9", error: "0.4", unit: "kcal" }),
    ).toEqual({ ec: "1.1.1.27", mode: "inhibitor", organism: "human", inhibitor: "gossypol", computed: { value: -7.9, unit: "kcal", error: 0.4 } });
    const stored = (bindDisagrees.run as RunRecord).request;
    expect(bindRequest(bindForm(stored))).toMatchObject(stored);
  });

  it("reopens a run on the screen with its question filled in", async () => {
    setSessionToken("t0k");
    const fixture = bindDisagrees as Captured;
    const run = fixture.run as RunRecord;
    mockServer((req) => {
      if (req.url === `/api/runs/${run.id}`) return json(200, run);
      if (req.url === `/api/runs/${run.id}/result`) return json(200, fixture.result);
      if (req.url === `/api/runs/${run.id}/events`) return replay(fixture);
      if (req.url === "/api/capabilities") return json(200, capabilities);
      return undefined;
    });
    render(withApp(`/bind?run=${run.id}`, <BindScreen />));
    expect(await screen.findByRole("region", { name: /^The computed value / })).toBeInTheDocument();
    expect(screen.getByLabelText("EC number")).toHaveValue(String(run.request.ec));
    expect(screen.getByRole("button", { name: "Judge" })).toBeInTheDocument();
  });
});

/**
 * The kinetics screens over real API responses (src/__fixtures__/api/kinetics,
 * captured from the studio server's dispatch on real inputs; README there).
 * No number in these tests is typed by hand: each expectation is read from
 * the fixture it renders.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import bindDisagrees from "@/__fixtures__/api/kinetics/bind-quinoline-disagrees.json";
import bindList from "@/__fixtures__/api/kinetics/bind-list.json";
import bindNoRows from "@/__fixtures__/api/kinetics/bind-no-rows.json";
import bindSurvey from "@/__fixtures__/api/kinetics/bind-survey.json";
import analyses from "@/__fixtures__/api/kinetics/compose-binding-analyses.json";
import gossypol from "@/__fixtures__/api/kinetics/compose-ldh-gossypol.json";
import noncompetitive from "@/__fixtures__/api/kinetics/compose-ldh-noncompetitive.json";
import malformed from "@/__fixtures__/api/kinetics/compose-malformed.json";
import unrecognised from "@/__fixtures__/api/kinetics/compose-unrecognised.json";
import constants from "@/__fixtures__/api/kinetics/constants-hexokinase.json";
import simDecay from "@/__fixtures__/api/kinetics/sim-decay.json";
import type {
  ApiError,
  BindResult,
  ComposeResult,
  ConstantsResult,
  RunKind,
  RunRecord,
  SimResult,
  SourcedValue,
} from "@/api/types";
import type { RunState } from "@/api/useRun";
import { formatValue } from "@/lib/format";

import { BindResultView } from "./BindResult";
import { ComposeResultView } from "./ComposeResult";
import { ConstantsResultView } from "./ConstantsResult";
import { fieldError } from "./form";
import { RunView, shellQuote } from "./RunView";
import { SimResultView } from "./SimResult";
import { bindRequest } from "../Bind";
import { composeRequest } from "../Compose";
import { simRequest } from "../Sim";

// jsdom has no ResizeObserver; recharts' ResponsiveContainer asks for one.
// The charts draw nothing at zero size here, which these tests do not read.
if (!("ResizeObserver" in globalThis)) {
  (globalThis as unknown as { ResizeObserver: unknown }).ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
}

type Captured = { run: unknown; result: unknown; events: { event: string; data: Record<string, unknown> }[] };

function finished<K extends RunKind>(fixture: Captured): RunState<K> {
  const run = fixture.run as RunRecord;
  return {
    run,
    status: run.status,
    stage: null,
    log: [],
    outcome: run.outcome,
    result: fixture.result as RunState<K>["result"],
    requestError: null,
    runError: run.error,
  };
}

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function param(result: ComposeResult, id: string): SourcedValue {
  return result.model.parameters.find((p) => p.id === id)!;
}

describe("Compose", () => {
  const result = gossypol.result as unknown as ComposeResult;

  it("says the verdict first, in the library's word", () => {
    render(<ComposeResultView result={result} />);
    const verdict = screen.getByRole("region", { name: "Verdict" });
    expect(within(verdict).getByText(result.verdict!.verdict)).toBeInTheDocument();
    expect(within(verdict).getByText(result.verdict!.licence)).toBeInTheDocument();
  });

  it("puts the README's gossypol Ki one click from its BRENDA reference", async () => {
    const ki = param(result, "reaction_Ki");
    expect(ki.provenance.kind).toBe("measured");
    render(<ComposeResultView result={result} />);
    await userEvent.click(screen.getByRole("button", { name: new RegExp(`^${ki.label} ${formatValue(ki)} `) }));
    const link = await screen.findByRole("link", { name: ki.provenance.citation!.text });
    expect(link).toHaveAttribute("href", ki.provenance.citation!.url);
    expect(screen.getByText(ki.provenance.commentary!)).toBeInTheDocument();
  });

  it("shows a placeholder's reason in the resolver's words", async () => {
    const kcat = param(result, "reaction_kcat");
    expect(kcat.provenance.kind).toBe("placeholder");
    render(<ComposeResultView result={result} />);
    await userEvent.click(screen.getByRole("button", { name: /^kcat .*placeholder, not measured$/ }));
    const popover = await screen.findByRole("dialog");
    expect(within(popover).getByText(kcat.provenance.reason!)).toBeInTheDocument();
  });

  it("says why a noncompetitive model carries the noncompetitive row", () => {
    const r = noncompetitive.result as unknown as ComposeResult;
    const ki = param(r, "reaction_Ki");
    expect(ki.provenance.chosen_because).toBeTruthy();
    render(<ComposeResultView result={r} />);
    expect(screen.getByRole("button", { name: new RegExp(`^Ki ${formatValue(ki)} mM, measured, cited$`) })).toBeInTheDocument();
  });

  it("draws every section under its heading, a refused one marked refused", () => {
    const r = analyses.result as unknown as ComposeResult;
    render(<ComposeResultView result={r} />);
    for (const section of r.sections) {
      const region = screen.getByRole("region", { name: section.title });
      expect(within(region).getByText(section.status === "answered" ? "answered" : section.status === "refused" ? "refused" : "partly refused")).toBeInTheDocument();
    }
    expect(r.sections.some((s) => s.status === "refused")).toBe(true);
  });

  it("shows a refusal with no result as the command's reason, and the command", () => {
    const state = finished<"compose">(unrecognised as Captured);
    expect(state.result).toBeNull();
    render(
      <RunView<"compose"> state={state} empty={null}>
        {(r) => <ComposeResultView result={r} />}
      </RunView>,
    );
    expect(screen.getByRole("region", { name: "Refused, and why" })).toHaveTextContent(
      state.outcome!.reason!.replace(/\s+/g, " ").slice(0, 60),
    );
    expect(screen.getByText(state.run!.cli.map(shellQuote).join(" "))).toBeInTheDocument();
  });

  it("shows a running run as the stage the server reported", () => {
    const stage = (analyses as Captured).events.find((e) => e.event === "stage")!.data;
    const state = { ...finished<"compose">(analyses as Captured), status: "running" as const, result: null, stage: { label: String(stage.label), fraction: null } };
    render(
      <RunView<"compose"> state={state} empty={null}>
        {() => null}
      </RunView>,
    );
    expect(screen.getByRole("status")).toHaveTextContent(String(stage.label));
  });

  it("maps the form to the request the CLI's flags expect", () => {
    const request = composeRequest({
      description: " Michaelis Menten ",
      subject: "1.1.1.27",
      organism: "",
      substrate: "pyruvate",
      inhibitor: "",
      isoform: "",
      any_mode: true,
      analyses: { crnt: true, validate: false },
      robustness: true,
      samples: "",
      stochastic: false,
      volume: "",
      stochasticEnd: "",
      stochasticSeed: "",
      knockout: "E, S",
      overexpress: "",
      sweep: "",
      sweepLow: "",
      sweepHigh: "",
      sweepSteps: "",
      no_simulate: false,
      no_analysis: false,
      no_ranking: false,
    });
    expect(request).toEqual({
      description: "Michaelis Menten",
      subject: "1.1.1.27",
      substrate: "pyruvate",
      any_mode: true,
      analyses: { crnt: true, robustness: { samples: null }, knockout: ["E", "S"] },
    });
  });

  it("puts a 400 under the field it names, and nowhere else", () => {
    const error = malformed.body.error as ApiError;
    expect(fieldError(error, "description")).toBeNull();
    const named: ApiError = { ...error, field: "analyses.robustness.samples" };
    expect(fieldError(named, "analyses.robustness")).toBe(error.message);
    expect(fieldError(named, "subject")).toBeNull();
  });
});

describe("Constants", () => {
  const result = constants.result as unknown as ConstantsResult;

  it("shows each constant with the paper that measured it", async () => {
    const km = result.constants[0].value!;
    render(<ConstantsResultView result={result} />);
    const links = screen.getAllByRole("link", { name: km.provenance.citation!.text });
    expect(links[0]).toHaveAttribute("href", km.provenance.citation!.url);
    expect(screen.getByText(`BRENDA's row: ${km.provenance.commentary}`)).toBeInTheDocument();
  });

  it("lists the rows the resolver read and did not carry, each measured", () => {
    render(<ConstantsResultView result={result} />);
    const alternatives = result.constants[0].alternatives;
    for (const a of alternatives) {
      expect(screen.getByRole("button", { name: new RegExp(`${formatValue(a)} ${a.unit}, measured, cited`) })).toBeInTheDocument();
    }
  });

  it("marks the values cite.py supplied as its defaults", () => {
    render(<ConstantsResultView result={result} />);
    for (const v of result.supplied) {
      expect(v.provenance.by).toBe("default");
      expect(screen.getByRole("button", { name: new RegExp(`^${v.id} .*a stated default$`) })).toBeInTheDocument();
    }
  });
});

describe("Stochastic", () => {
  const result = simDecay.result as unknown as SimResult;

  it("shows the final counts and the ODE expectation, each with its mark", () => {
    render(<SimResultView result={result} />);
    for (const v of Object.values(result.final)) {
      expect(screen.getAllByRole("button", { name: new RegExp(`${formatValue(v)}.*computed by Caterva`) }).length).toBeGreaterThan(0);
    }
    expect(screen.getByRole("button", { name: new RegExp(`^${escape(result.expected.label!)}`) })).toBeInTheDocument();
    expect(screen.getByText(`${result.rows} rows in the event table, every one drawn.`)).toBeInTheDocument();
  });

  it("sends the seed and never leaves k to the default", () => {
    expect(simRequest({ reaction: "association", seed: "7", a0: "", b0: "80", k: "0.005", end: "" })).toEqual({
      seed: 7,
      bimolecular: true,
      k: 0.005,
      b0: 80,
    });
  });
});

describe("Binding", () => {
  it("draws a disagreement as a verdict with the gap and the Ki fold", () => {
    const result = bindDisagrees.result as unknown as BindResult;
    render(<BindResultView result={result} />);
    const verdict = screen.getByRole("region", { name: "Verdict" });
    expect(within(verdict).getByText(result.verdict!.word)).toBeInTheDocument();
    expect(within(verdict).getByRole("button", { name: new RegExp(formatValue(result.verdict!.gap_kcal)) })).toBeInTheDocument();
    expect(within(verdict).getByRole("button", { name: new RegExp(formatValue(result.verdict!.ki_fold)) })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: /ΔG°bind of each Ki row/ })).toBeInTheDocument();
    for (const row of result.target!.used) {
      expect(screen.getAllByRole("button", { name: new RegExp(`^Ki ${formatValue(row.ki)} mM`) }).length).toBeGreaterThan(0);
    }
  });

  it("lists the survey with the band where there is one", () => {
    const result = bindSurvey.result as unknown as BindResult;
    render(<BindResultView result={result} />);
    expect(screen.getAllByRole("row")).toHaveLength(result.survey.length + 1);
  });

  it("asks for a listed compound's target in one click", async () => {
    const result = bindList.result as unknown as BindResult;
    const onPick = vi.fn();
    render(<BindResultView result={result} onPick={onPick} />);
    await userEvent.click(screen.getByRole("button", { name: result.compounds[0] }));
    expect(onPick).toHaveBeenCalledWith(result.compounds[0]);
  });

  it("shows no Ki row as a refusal naming the compounds that have one", () => {
    const state = finished<"bind">(bindNoRows as Captured);
    render(
      <RunView<"bind"> state={state} empty={null}>
        {(r) => <BindResultView result={r} />}
      </RunView>,
    );
    expect(screen.getByRole("region", { name: "Refused, and why" })).toHaveTextContent("Compounds that do have one");
  });

  it("sends a computed value with its unit and σ", () => {
    expect(
      bindRequest({ mode: "inhibitor", ec: "1.1.1.27", organism: "human", inhibitor: "gossypol", state: "free", isoform: "", computed: "-7.9", error: "0.4", unit: "kcal" }),
    ).toEqual({ ec: "1.1.1.27", mode: "inhibitor", organism: "human", inhibitor: "gossypol", computed: { value: -7.9, unit: "kcal", error: 0.4 } });
  });
});

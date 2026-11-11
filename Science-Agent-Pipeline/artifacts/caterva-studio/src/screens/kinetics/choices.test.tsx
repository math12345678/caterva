/**
 * What Caterva chose, and switching it in one click (ADR 0182).
 *
 * A compose request that names an enzyme and leaves the substrate, the
 * inhibitor or the organism blank runs with the best-measured real option
 * BRENDA has; the result's `search.choices` says what was chosen, why, and
 * what else there was with BRENDA's row counts. These tests render the real
 * recorded hexokinase run (src/__fixtures__/api/enzymes, captured from the
 * studio server) with a `choices` list in the contract's shape added to its
 * search: the engine side of the contract (caterva/compose/defaults.py) was
 * written in parallel, so no run with choices had been recorded yet. The
 * alternatives' names and row counts below are that stand-in's; every other
 * number is read from the fixture. Re-record a run once the engine has
 * landed and swap it in.
 *
 * Also here: an old result without `choices` still renders (and says how many
 * constants are measured), a field that contradicts the description is a
 * warning at the top with the run the description asked for, and the
 * Substrate and Inhibitor fields say that blank is a question Caterva answers.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import composeHexokinase from "@/__fixtures__/api/enzymes/compose-hexokinase-human-glucose.json";
import hexokinaseDetail from "@/__fixtures__/api/enzymes/detail-2.7.1.1-human.json";
import gossypol from "@/__fixtures__/api/kinetics/compose-ldh-gossypol.json";
import shapes from "@/__fixtures__/api/kinetics/compose-shapes.json";
import { frame, json, mockServer, setSessionToken, sseResponse } from "@/__tests__/helpers";
import { choicesOf, mismatchOf, rerunPatch, rowsLine, type SearchChoice } from "@/api/choices";
import { resetRunStreamsForTests } from "@/api/runs";
import type { ComposeResult, RunRecord } from "@/api/types";

import ComposeScreen, { composeForm, composeRequest, INHIBITOR_HINT, rerunForm, SUBSTRATE_HINT } from "../Compose";
import { compoundOf, ComposeResultView, measuredTally } from "./ComposeResult";

type Captured = { run: unknown; result: unknown; events: { event: string; data: Record<string, unknown> }[] };
const cap = <T,>(x: unknown) => x as T;

const recorded = composeHexokinase as unknown as Captured;
const baseResult = cap<ComposeResult>(recorded.result);
const baseRun = cap<RunRecord>(recorded.run);

/** The contract-shaped stand-in: the substrate the recorded run used, as the engine would report having chosen it. */
const SUBSTRATE_CHOICE: SearchChoice = {
  role: "substrate",
  chosen: baseResult.search.substrate!,
  why: `It has the most Km and kcat rows for EC ${baseResult.search.ec} in ${baseResult.search.organism} in BRENDA.`,
  alternatives: [
    { name: "D-mannose", rows: { km: 9, kcat: 4 } },
    { name: "D-fructose", rows: { km: 6 } },
  ],
  considered: 5,
};
const ORGANISM_CHOICE: SearchChoice = {
  role: "organism",
  chosen: baseResult.search.organism!,
  why: "It has the most measured rows for this enzyme in BRENDA.",
  alternatives: [{ name: "Saccharomyces cerevisiae", rows: { km: 31, kcat: 12 } }],
  considered: 2,
};

function withChoices(choices: SearchChoice[], notes: string[] = baseResult.notes): ComposeResult {
  return { ...baseResult, notes, search: { ...baseResult.search, choices } as ComposeResult["search"] };
}

/** The recorded request with the substrate left blank, as a request the engine chose a substrate for would be. */
function blankSubstrateRun(): RunRecord {
  const { substrate: _dropped, ...request } = baseRun.request;
  return { ...baseRun, request };
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetRunStreamsForTests();
});

describe("reading the choices a result carries", () => {
  it("reads each choice in the order the engine made it, and nothing from a result that has none", () => {
    expect(choicesOf(withChoices([ORGANISM_CHOICE, SUBSTRATE_CHOICE])).map((c) => c.role)).toEqual(["organism", "substrate"]);
    // Every run recorded before the engine chose: no key at all.
    expect("choices" in baseResult.search).toBe(false);
    expect(choicesOf(baseResult)).toEqual([]);
  });

  it("drops a malformed choice rather than drawing a chip that would run with nothing set", () => {
    const broken = withChoices([{ ...SUBSTRATE_CHOICE, chosen: "" }, { ...SUBSTRATE_CHOICE, role: "cofactor" as never }, SUBSTRATE_CHOICE]);
    expect(choicesOf(broken)).toHaveLength(1);
  });

  it("says a chip's rows as the constants are written", () => {
    expect(rowsLine({ km: 9, kcat: 4 })).toBe("9 Km, 4 kcat");
    expect(rowsLine({ ki: 7 })).toBe("7 Ki");
    expect(rowsLine({})).toBe("");
  });

  it("keeps every choice made before the one switched, and leaves the later ones to the engine", () => {
    const choices = [ORGANISM_CHOICE, SUBSTRATE_CHOICE];
    // A substrate's row counts were counted in the organism chosen first, so that organism is kept.
    expect(rerunPatch(choices, 1, "D-mannose")).toEqual({ organism: ORGANISM_CHOICE.chosen, substrate: "D-mannose" });
    // Switching the organism lets the engine choose the substrate again, for the new organism.
    expect(rerunPatch(choices, 0, "Saccharomyces cerevisiae")).toEqual({ organism: "Saccharomyces cerevisiae" });
    expect(rerunPatch([{ ...SUBSTRATE_CHOICE, role: "enzyme" }], 0, "2.7.1.2")).toEqual({ subject: "2.7.1.2" });
  });

  it("re-runs the run's own request with the field set, and clears an isoform when the enzyme or organism moves", () => {
    const request = { description: "Michaelis Menten", subject: "2.7.1.1", organism: "human", isoform: "HK1" };
    expect(composeRequest(rerunForm(request, { substrate: "D-mannose" }))).toEqual({ ...request, substrate: "D-mannose" });
    expect(composeRequest(rerunForm(request, { organism: "Saccharomyces cerevisiae" }))).toEqual({
      description: "Michaelis Menten",
      subject: "2.7.1.1",
      organism: "Saccharomyces cerevisiae",
    });
    const moved = rerunForm(request, { subject: "3.4.21.79" });
    expect(moved).toMatchObject({ subject: "3.4.21.79", subjectSeed: "", isoform: "" });
    expect(composeForm(request).isoform).toBe("HK1");
  });
});

describe("the choices panel", () => {
  it("says what Caterva chose, why, and offers each alternative with its BRENDA row counts", () => {
    render(<ComposeResultView result={withChoices([SUBSTRATE_CHOICE])} run={blankSubstrateRun()} onRerun={vi.fn()} />);
    const panel = screen.getByRole("region", { name: "Caterva chose the substrate" });
    expect(panel).toHaveTextContent(SUBSTRATE_CHOICE.chosen);
    expect(panel).toHaveTextContent(SUBSTRATE_CHOICE.why);
    expect(within(panel).getByRole("button", { name: /Run again with the substrate D-mannose \(9 Km, 4 kcat rows in BRENDA\)/ })).toHaveTextContent(
      "D-mannose · 9 Km, 4 kcat",
    );
    expect(within(panel).getByRole("button", { name: /D-fructose/ })).toHaveTextContent("D-fructose · 6 Km");
    // Five weighed: the chosen one, two listed, two more not listed.
    expect(panel).toHaveTextContent("2 more options weighed and not listed");
  });

  it("runs again with the alternative a chip names", async () => {
    const onRerun = vi.fn();
    render(<ComposeResultView result={withChoices([ORGANISM_CHOICE, SUBSTRATE_CHOICE])} run={blankSubstrateRun()} onRerun={onRerun} />);
    await userEvent.click(screen.getByRole("button", { name: /Run again with the substrate D-mannose/ }));
    expect(onRerun).toHaveBeenCalledWith({ organism: ORGANISM_CHOICE.chosen, substrate: "D-mannose" });
  });

  it("lists the alternatives without offering them on a screen that cannot run compose", () => {
    render(<ComposeResultView result={withChoices([SUBSTRATE_CHOICE])} run={blankSubstrateRun()} />);
    const panel = screen.getByRole("region", { name: "Caterva chose the substrate" });
    expect(within(panel).queryByRole("button")).toBeNull();
    expect(panel).toHaveTextContent("D-mannose · 9 Km, 4 kcat");
  });

  it("is absent, and the page still renders, for an old result with no choices", () => {
    render(<ComposeResultView result={baseResult} run={baseRun} onRerun={vi.fn()} />);
    expect(screen.queryByTestId("choices")).toBeNull();
    expect(screen.queryByText(/Caterva chose/)).toBeNull();
    expect(screen.getByRole("region", { name: baseResult.verdict!.verdict })).toBeInTheDocument();
  });
});

describe("measured or placeholder, at a glance", () => {
  it("counts the constants measured from BRENDA in a badge at the top", () => {
    const tally = measuredTally(baseResult);
    expect(tally).toMatchObject({ measured: baseResult.model.parameters.length, placeholders: 0, brenda: true });
    render(<ComposeResultView result={baseResult} run={baseRun} />);
    const badge = screen.getByTestId("measured-badge");
    expect(badge).toHaveTextContent(`${tally.measured} of ${tally.total} constants measured from BRENDA`);
    expect(badge).toHaveAttribute("data-tone", "signal");
  });

  it("says how many are placeholders, and links to where each says why", () => {
    const result = cap<ComposeResult>(gossypol.result);
    const tally = measuredTally(result);
    expect(tally.placeholders).toBeGreaterThan(0);
    render(<ComposeResultView result={result} run={cap<RunRecord>(gossypol.run)} />);
    const badge = screen.getByTestId("measured-badge");
    expect(badge).toHaveTextContent(`${tally.measured} of ${tally.total} constants measured from BRENDA`);
    expect(badge).toHaveAttribute("data-tone", "caution");
    expect(within(badge).getByRole("link", { name: /placeholder/ })).toHaveAttribute("href", "#k-numbers");
  });

  it("leads a measured row with its organism, the compound it was measured for, and its citation", () => {
    const result = cap<ComposeResult>(gossypol.result);
    render(<ComposeResultView result={result} run={cap<RunRecord>(gossypol.run)} />);
    const ledger = screen.getAllByRole("table")[0];
    for (const p of result.model.parameters.filter((v) => v.provenance.kind === "measured")) {
      const row = within(ledger).getByRole("row", { name: new RegExp(p.id!) });
      const compound = compoundOf(p, result)!;
      expect(compound).toBe(p.label === "Ki" ? `inhibitor ${result.search.compounds["@inhibitor"]}` : `substrate ${result.search.substrate}`);
      const line = row.querySelector(".k-origin-line")!;
      expect(line.textContent!.indexOf(p.provenance.organism!)).toBeLessThan(line.textContent!.indexOf(compound));
      expect(line.textContent!.indexOf(compound)).toBeLessThan(line.textContent!.indexOf(p.provenance.citation!.text));
    }
  });

  it("names no compound where the row does not say whose it is", () => {
    const result = cap<ComposeResult>(gossypol.result);
    const placeholder = result.model.parameters.find((p) => p.provenance.kind === "placeholder")!;
    expect(compoundOf(placeholder, result)).toBeNull();
  });
});

describe("a field that contradicts the description", () => {
  const NOTE = "Your description names 'granzyme B' (EC 3.4.21.79); --subject 1.14.19.48 was used, because a flag wins over the description.";

  it("reads the engine's note, either quote, for the enzyme and for the organism", () => {
    expect(mismatchOf(NOTE)).toMatchObject({ field: "subject", named: "granzyme B", readAs: "3.4.21.79", used: "1.14.19.48" });
    expect(mismatchOf(`Your description names "Bloom's enzyme" (EC 3.6.4.12); --subject 1.1.1.1 was used, because a flag wins over the description.`)).toMatchObject({
      named: "Bloom's enzyme",
      readAs: "3.6.4.12",
    });
    expect(
      mismatchOf("Your description names 'yeast' (Saccharomyces cerevisiae); --organism Homo sapiens was used, because a flag wins over the description."),
    ).toMatchObject({ field: "organism", readAs: "Saccharomyces cerevisiae", used: "Homo sapiens" });
    expect(mismatchOf("Read --organism 'human' as Homo sapiens.")).toBeNull();
  });

  it("is a warning at the top with the run the description asked for", async () => {
    const onRerun = vi.fn();
    render(<ComposeResultView result={withChoices([], [...baseResult.notes, NOTE])} run={baseRun} onRerun={onRerun} />);
    const warning = screen.getByRole("alert");
    expect(warning).toHaveTextContent("Your description names granzyme B (EC 3.4.21.79), but this run used EC 1.14.19.48");
    await userEvent.click(within(warning).getByRole("button", { name: "Use EC 3.4.21.79 (granzyme B) instead" }));
    expect(onRerun).toHaveBeenCalledWith({ subject: "3.4.21.79" });
  });

  it("is not shown on a run whose fields agree with the description", () => {
    render(<ComposeResultView result={baseResult} run={baseRun} onRerun={vi.fn()} />);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

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

/** The panes stacked (see kinetics.test.tsx): jsdom gives the resize handles no size. */
function stacked(on: boolean) {
  (window as unknown as { __setMedia?: (q: string, v: boolean) => void }).__setMedia?.("(max-width: 1099px)", on);
}
afterEach(() => stacked(false));

describe("the Compose screen", () => {
  it("says under Substrate and Inhibitor that blank is answered by Caterva", () => {
    setSessionToken("t0k");
    mockServer((req) => (req.url === "/api/compose/shapes" ? json(200, shapes) : undefined));
    render(withApp("/compose", <ComposeScreen />));
    expect(screen.getByLabelText(/^Substrate/)).toHaveAccessibleDescription(SUBSTRATE_HINT);
    expect(screen.getByLabelText(/^Inhibitor/)).toHaveAccessibleDescription(INHIBITOR_HINT);
    expect(SUBSTRATE_HINT).toMatch(/^Leave blank: Caterva picks the best-measured one from BRENDA and tells you/);
  });

  it("submits a new run at once when a chip is clicked, with that field set and the rest of the request kept", async () => {
    setSessionToken("t0k");
    const run = blankSubstrateRun();
    const result = withChoices([SUBSTRATE_CHOICE]);
    const { seen } = mockServer((req) => {
      if (req.url === `/api/runs/${run.id}`) return json(200, run);
      if (req.url === `/api/runs/${run.id}/result`) return json(200, result);
      if (req.url === `/api/runs/${run.id}/events`) return sseResponse(recorded.events.map((e, i) => frame(e.event, i + 1, e.data)));
      if (req.url === "/api/compose/shapes") return json(200, shapes);
      if (req.url.startsWith(`/api/enzymes/${String(run.request.subject)}`)) return json(200, hexokinaseDetail.body);
      if (req.method === "POST" && req.url === "/api/runs") return json(400, { error: { code: "malformed", message: "stop here" } });
      return undefined;
    });
    stacked(true);
    render(withApp(`/compose?run=${run.id}`, <ComposeScreen />));
    await userEvent.click(await screen.findByRole("button", { name: /Run again with the substrate D-mannose/ }));
    await waitFor(() => expect(seen.some((r) => r.method === "POST")).toBe(true));
    const post = seen.find((r) => r.method === "POST")!;
    expect(post.body).toEqual({ kind: "compose", request: { ...run.request, substrate: "D-mannose" } });
    // The form shows the request that was sent.
    expect(screen.getByLabelText(/^Substrate/)).toHaveValue("D-mannose");
  });
});

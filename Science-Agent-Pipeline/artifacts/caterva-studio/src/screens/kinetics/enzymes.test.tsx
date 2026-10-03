/**
 * The enzyme finder's effects on the kinetics screens, over real responses
 * (src/__fixtures__/api/enzymes, captured from the dispatch layer):
 *
 * - the request carries an EC number the person chose, never typed text;
 * - the engine's isozyme notice (the verdict's "Qualified" line and the
 *   [isozymes] concern) is on the page when the engine wrote it, and gone
 *   when an isoform was given;
 * - the Steady states table lists physical states only, says once how many
 *   non-physical solutions the search also found and why they are excluded,
 *   and keeps them behind a disclosure with the engine's own labels;
 * - a refused name offers each candidate it named;
 * - the status bar's network item is honest about what is known, and its
 *   popover asks again on request.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import composeHexokinase from "@/__fixtures__/api/enzymes/compose-hexokinase-human-glucose.json";
import composeHxk1 from "@/__fixtures__/api/enzymes/compose-hexokinase-human-glucose-hxk1.json";
import composeLdh from "@/__fixtures__/api/enzymes/compose-ldh-human-pyruvate.json";
import composeNames from "@/__fixtures__/api/enzymes/compose-name-several-enzymes.json";
import constantsNames from "@/__fixtures__/api/enzymes/constants-name-several-enzymes.json";
import capsAfterLookup from "@/__fixtures__/api/enzymes/capabilities-after-a-lookup.json";
import capsNothingYet from "@/__fixtures__/api/enzymes/capabilities-nothing-yet.json";
import { json, mockServer, setSessionToken } from "@/__tests__/helpers";
import type { Capabilities, ComposeResult, NameRefusal, RunRecord } from "@/api/types";
import type { RunState } from "@/api/useRun";
import { RunPanel } from "@/components/run/RunPanel";
import { StatusLine } from "@/components/shell/StatusLine";
import { readNetwork } from "@/lib/network";

import { composeRequest, EMPTY_COMPOSE } from "../Compose";
import { constantsRequest, EMPTY_CONSTANTS } from "../Constants";
import { ComposeResultView } from "./ComposeResult";

type Captured = { run: unknown; result: unknown };
const cap = <T,>(x: unknown) => x as T;

afterEach(() => vi.unstubAllGlobals());

describe("what the engine is sent", () => {
  it("is the chosen EC number, and never the text that was typed", () => {
    expect(composeRequest({ ...EMPTY_COMPOSE, description: "Michaelis Menten", subject: "1.1.1.27", subjectSeed: "" })).toMatchObject({ subject: "1.1.1.27" });
    // A name that only seeded the search is not a choice.
    const seeded = composeRequest({ ...EMPTY_COMPOSE, description: "Michaelis Menten", subject: "", subjectSeed: "lactate dehydrogenase" });
    expect(seeded).not.toHaveProperty("subject");
    // Text in the subject that is not a complete EC number is not sent either.
    expect(composeRequest({ ...EMPTY_COMPOSE, description: "x", subject: "hexokinase" })).not.toHaveProperty("subject");
    expect(constantsRequest({ ...EMPTY_CONSTANTS, ec: "2.7.1.1", substrate: "glucose" })).toMatchObject({ ec: "2.7.1.1" });
    expect(constantsRequest({ ...EMPTY_CONSTANTS, ec: "", ecSeed: "hexokinase", substrate: "glucose" })).not.toHaveProperty("enzyme");
  });
});

describe("the isozyme notice in a Compose result", () => {
  const withNotice = composeHexokinase as unknown as Captured;
  const result = cap<ComposeResult>(withNotice.result);
  const run = cap<RunRecord>(withNotice.run);

  it("shows the engine's Qualified line and the isozymes concern, from the verdict's own words", () => {
    const concern = result.verdict!.concerns.find((c) => c.source === "isozymes")!;
    expect(concern.qualifier).toMatch(/is 5 proteins in human and no --isoform was given/);
    render(<ComposeResultView result={result} run={run} />);
    const verdict = screen.getByRole("region", { name: result.verdict!.verdict });
    expect(within(verdict).getByText("Qualified")).toBeInTheDocument();
    expect(within(verdict).getByText(`${concern.qualifier}.`, { exact: false })).toBeInTheDocument();
    // The verdict word is still the engine's: the notice qualifies it, it does not change it.
    expect(result.verdict!.text).toContain(`Qualified: ${concern.qualifier}.`);
    expect(within(verdict).getByText(concern.detail)).toBeInTheDocument();
    expect(within(verdict).getByText(concern.remedy)).toBeInTheDocument();
  });

  it("is gone when an isoform was given", () => {
    const given = composeHxk1 as unknown as Captured;
    const r = cap<ComposeResult>(given.result);
    expect(r.verdict!.concerns.some((c) => c.source === "isozymes")).toBe(false);
    render(<ComposeResultView result={r} run={cap<RunRecord>(given.run)} />);
    expect(screen.queryByText("Qualified")).toBeNull();
    expect(screen.queryByText("Which isozyme")).toBeNull();
  });
});

describe("Steady states", () => {
  const fixture = composeLdh as unknown as Captured;
  const result = cap<ComposeResult>(fixture.result);
  const run = cap<RunRecord>(fixture.run);
  const found = result.stability!.fixed_points;
  const physical = found.filter((p) => p.physical);
  const unphysical = found.filter((p) => !p.physical);

  it("starts from a real run in which the search also found solutions at negative amounts", () => {
    expect(physical.length).toBeGreaterThan(0);
    expect(unphysical.length).toBeGreaterThan(1);
    expect(unphysical.some((p) => Object.values(p.state).some((v) => v !== null && v < -1e6))).toBe(true);
  });

  it("lists the physical states only", () => {
    render(<ComposeResultView result={result} run={run} />);
    const section = screen.getByRole("region", { name: "Steady states" });
    const rows = within(section).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(physical.length);
    expect(within(section).getByText(`${physical.length} found from ${result.stability!.starts_tried} starts`)).toBeInTheDocument();
    // No value near -3.4e6 sits in the table before anyone opens the disclosure.
    expect(section.textContent).not.toMatch(/-3\.39e\+?6|−3\.39e\+?6|3394495/);
  });

  it("says once how many solutions it excluded and why, in the report's words", () => {
    render(<ComposeResultView result={result} run={run} />);
    const sentence = screen.getAllByTestId("nonphysical-sentence");
    expect(sentence).toHaveLength(1);
    expect(sentence[0]).toHaveTextContent(
      `${unphysical.length} more solutions are at negative concentrations, which the equations have and the system cannot reach.`,
    );
    expect(result.stability!.text).toContain(`${unphysical.length} more at negative concentrations, which the equations have and the system cannot reach`);
  });

  it("keeps them behind a disclosure with the engine's own labels", async () => {
    render(<ComposeResultView result={result} run={run} />);
    const section = screen.getByRole("region", { name: "Steady states" });
    expect(within(section).queryByText(unphysical[0].description!)).toBeNull();
    await userEvent.click(within(section).getByRole("button", { name: new RegExp(`The ${unphysical.length} solutions at negative concentrations`) }));
    for (const p of unphysical) expect(within(section).getByText(p.description!)).toBeInTheDocument();
    expect(unphysical[0].description).toMatch(/NEGATIVE concentrations -- not physically reachable/);
    const tables = within(section).getAllByRole("table");
    expect(tables).toHaveLength(2);
    expect(within(tables[1]).getAllByRole("row").slice(1)).toHaveLength(unphysical.length);
  });
});

describe("a refused name", () => {
  const refusal = cap<RunRecord>(composeNames.run).outcome!.name_refusal as NameRefusal;

  it("offers each candidate by name in a Compose result, and choosing one sets the form's enzyme", async () => {
    const fixture = composeNames as unknown as Captured;
    const onChoose = vi.fn();
    render(<ComposeResultView result={cap<ComposeResult>(fixture.result)} run={cap<RunRecord>(fixture.run)} onChooseEnzyme={onChoose} />);
    for (const c of refusal.named_candidates.slice(0, 3)) expect(screen.getByText(c.name)).toBeInTheDocument();
    const suggested = screen.getByText("suggested").closest("li")!;
    expect(within(suggested).getByText(`EC ${refusal.recommended}`)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: `Use EC ${refusal.recommended}` }));
    expect(onChoose).toHaveBeenCalledWith(refusal.recommended);
  });

  it("is offered by the run panel when the refusal came with no result (constants)", async () => {
    const run = cap<RunRecord>((constantsNames as unknown as Captured).run);
    const named = run.outcome!.name_refusal as NameRefusal;
    expect(run.outcome!.meaning).toBe("refused");
    const state = {
      run, status: "done", stage: null, stages: [], log: [], outcome: run.outcome, result: null, requestError: null,
      runError: null, submitting: false, cancelling: false, settled: true,
    } as unknown as RunState<"constants">;
    const onChoose = vi.fn();
    render(
      <RunPanel state={state} onChooseEnzyme={onChoose}>
        {() => null}
      </RunPanel>,
    );
    expect(screen.getByRole("heading", { name: "Which enzyme did you mean?" })).toBeInTheDocument();
    expect(named.rerun_flag).toBe("--ec {ec}");
    await userEvent.click(screen.getByRole("button", { name: `Use EC ${named.named_candidates[1].ec}` }));
    expect(onChoose).toHaveBeenCalledWith(named.named_candidates[1].ec);
  });
});

describe("the network in the status bar", () => {
  const nothing = capsNothingYet.body as unknown as Capabilities;
  const used = capsAfterLookup.body as unknown as Capabilities;

  function bar(caps: Capabilities) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return render(
      <QueryClientProvider client={client}>
        <StatusLine health={undefined} healthError={null} capabilities={caps} capabilitiesError={null} />
      </QueryClientProvider>,
    );
  }

  it("says not checked only when nothing has happened", () => {
    expect(nothing.network.checked).toBe(false);
    expect(nothing.network.source).toBeNull();
    bar(nothing);
    expect(screen.getByRole("button", { name: /^network not checked/ })).toBeInTheDocument();
  });

  it("says reachable, from which request and when, after a lookup that worked", () => {
    expect(used.network.source).toBe("use");
    expect(used.network.reachable).toBe(true);
    bar(used);
    expect(screen.queryByText("network not checked")).toBeNull();
    const trigger = screen.getByRole("button", { name: /^network reachable/ });
    expect(trigger).toHaveAccessibleName(/UniProt answered the last real request/);
    expect(readNetwork(used.network).sentence).toMatch(/That was a lookup you ran, not a check of every host/);
  });

  it("offers an explicit re-check in its popover and shows the server's new answer", async () => {
    setSessionToken("t0k");
    const { seen } = mockServer((req) => (req.url === "/api/capabilities?probe=network" ? json(200, used) : undefined));
    bar(nothing);
    await userEvent.click(screen.getByRole("button", { name: /^network not checked/ }));
    const panel = await screen.findByRole("dialog", { name: "The network" });
    expect(within(panel).getByText(/Nothing has contacted a database/)).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Check the network" }));
    await waitFor(() => expect(seen.some((r) => r.url === "/api/capabilities?probe=network")).toBe(true));
    expect(seen.find((r) => r.url.includes("probe=network"))!.method).toBe("GET");
  });

  it("reads an unreachable host from a failed request, with the server's reason", () => {
    const failed: Capabilities["network"] = {
      ...used.network,
      reachable: false,
      hosts: { ...used.network.hosts, "www.brenda-enzymes.org": false },
      reason: "www.brenda-enzymes.org could not be reached: name resolution failed",
    };
    const reading = readNetwork(failed);
    expect(reading.state).toBe("off");
    expect(reading.label).toBe("network unreachable");
    expect(reading.sentence).toContain("www.brenda-enzymes.org could not be reached: name resolution failed");
  });
});

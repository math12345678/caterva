/**
 * The enzyme finder's effects on the kinetics screens, over real responses
 * (src/__fixtures__/api/enzymes, captured from the dispatch layer):
 *
 * - the request carries an EC number the person chose, never typed text;
 * - the engine's isozyme notice (the verdict's "Qualified" line and the
 *   [isozymes] concern) is on the page when the engine wrote it, stays when
 *   an isoform was given and a cited constant's row names no isozyme, and
 *   says which constant;
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
import composeGck from "@/__fixtures__/api/enzymes/compose-hexokinase-human-glucose-gck.json";
import composeHk2 from "@/__fixtures__/api/enzymes/compose-hexokinase-human-glucose-hk2.json";
import composeHxk1 from "@/__fixtures__/api/enzymes/compose-hexokinase-human-glucose-hxk1.json";
import composeTwoEnzymes from "@/__fixtures__/api/enzymes/compose-two-enzymes-competing.json";
import composeUnused from "@/__fixtures__/api/enzymes/compose-michaelis-menten-unused-inhibitor.json";
import constantsHexokinase from "@/__fixtures__/api/enzymes/constants-hexokinase-human-glucose.json";
import composeLdh from "@/__fixtures__/api/enzymes/compose-ldh-human-pyruvate.json";
import composeNames from "@/__fixtures__/api/enzymes/compose-name-several-enzymes.json";
import constantsNames from "@/__fixtures__/api/enzymes/constants-name-several-enzymes.json";
import capsAfterLookup from "@/__fixtures__/api/enzymes/capabilities-after-a-lookup.json";
import capsNothingYet from "@/__fixtures__/api/enzymes/capabilities-nothing-yet.json";
import { json, mockServer, setSessionToken } from "@/__tests__/helpers";
import type { Capabilities, ComposeResult, ConstantsResult, NameRefusal, RunRecord } from "@/api/types";
import type { RunState } from "@/api/useRun";
import { RunPanel } from "@/components/run/RunPanel";
import { resetLaunchCheck, StatusLine } from "@/components/shell/StatusLine";
import { plain } from "@/lib/copy";
import { readNetwork } from "@/lib/network";

import { composeRequest, EMPTY_COMPOSE } from "../Compose";
import { constantsRequest, EMPTY_CONSTANTS } from "../Constants";
import { ComposeResultView } from "./ComposeResult";
import { ConstantsResultView } from "./ConstantsResult";

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
    expect(within(verdict).getByText(`${plain(concern.qualifier ?? "")}.`, { exact: false })).toBeInTheDocument();
    // The verdict word is still the engine's: the notice qualifies it, it does not change it.
    expect(result.verdict!.text).toContain(`Qualified: ${concern.qualifier}.`);
    expect(within(verdict).getByText(plain(concern.detail))).toBeInTheDocument();
    expect(within(verdict).getByText(plain(concern.remedy ?? ""))).toBeInTheDocument();
  });

  it("stays when an isoform was given and a cited constant's row names no isozyme, and says which constant", () => {
    const given = composeHxk1 as unknown as Captured;
    const r = cap<ComposeResult>(given.result);
    const concern = r.verdict!.concerns.find((c) => c.source === "isozymes")!;
    expect(concern).toBeDefined();
    expect(concern.qualifier).toMatch(/HXK1 was asked for, but the row for `reaction_kcat` does not state which isozyme/);
    expect(concern.detail).toMatch(/--isoform HXK1 was given for EC 2\.7\.1\.1/);
    render(<ComposeResultView result={r} run={cap<RunRecord>(given.run)} />);
    const verdict = screen.getByRole("region", { name: r.verdict!.verdict });
    expect(within(verdict).getByText("Qualified")).toBeInTheDocument();
    // The Km did come from the row that says hexokinase I; the kcat's row says nothing about which one.
    const km = r.model.parameters.find((p) => p.id === "reaction_Km")!;
    expect(km.provenance.chosen_because).toMatch(/the row for HXK1, as --isoform asked/);
  });

  it("names the isozyme no Km row states, visibly, instead of going quiet", () => {
    const given = composeGck as unknown as Captured;
    const r = cap<ComposeResult>(given.result);
    const km = r.model.parameters.find((p) => p.id === "reaction_Km")!;
    expect(km.provenance.scope).toContain("the row names no isoform, so whether it measured GCK, the one asked for, is unknown");
    const concern = r.verdict!.concerns.find((c) => c.source === "isozymes")!;
    expect(concern.qualifier).toMatch(/GCK was asked for, but the row for `reaction_Km` does not state which isozyme/);
  });

  it("takes the row that says hexokinase II for HK2, and still names the kcat whose row says nothing", () => {
    const given = composeHk2 as unknown as Captured;
    const r = cap<ComposeResult>(given.result);
    const km = r.model.parameters.find((p) => p.id === "reaction_Km")!;
    expect(km.value).toBe(0.37);
    expect(km.provenance.citation?.reference_id).toBe("702867");
    expect(km.provenance.commentary).toMatch(/hexokinase II/);
    expect(r.notes.some((n) => /--isoform 'HK2' was read as HK2, human protein HXK2_HUMAN \(UniProt P52789\)/.test(n))).toBe(true);
  });

  it("does not echo an inhibitor the mechanism has no step for as searched", () => {
    const given = composeUnused as unknown as Captured;
    const r = cap<ComposeResult>(given.result);
    expect(r.search.compounds).toEqual({});
    expect(r.search.unused_compounds).toEqual({ "@inhibitor": "gossypol" });
    render(<ComposeResultView result={r} run={cap<RunRecord>(given.run)} />);
    const note = screen.getByTestId("unused-compounds");
    expect(note).toHaveTextContent("Not used: inhibitor gossypol");
    expect(note).toHaveTextContent("so no constant was looked up for it");
    expect(screen.queryByText(/, inhibitor gossypol\./)).toBeNull();
  });
});

describe("a constants lookup carries what the engine said", () => {
  const fixture = constantsHexokinase as unknown as Captured;
  const result = cap<ConstantsResult>(fixture.result);

  it("shows the tie explanation, the spread and the scope concern on the chosen row", () => {
    render(<ConstantsResultView result={result} request={{ ec: "2.7.1.1", organism: "human", substrate: "glucose" }} />);
    const account = screen.getByTestId("engine-account");
    const prov = result.constants[0].value!.provenance;
    expect(account).toHaveTextContent("3 rows were equally well evidenced");
    expect(account).toHaveTextContent("taking the lowest, which the evidence does not justify");
    expect(prov.spread!.sentence).toBeTruthy();
    expect(within(account).getByText(prov.spread!.sentence)).toBeInTheDocument();
    for (const s of prov.scope!) expect(within(account).getByText(s)).toBeInTheDocument();
  });

  it("shows the isozyme notice for an EC number with several proteins in the organism", () => {
    render(<ConstantsResultView result={result} request={{ ec: "2.7.1.1", organism: "human", substrate: "glucose" }} />);
    const notice = screen.getByTestId("isozyme-notice");
    expect(notice).toHaveTextContent("EC 2.7.1.1 has 5 human isozymes");
    expect(notice).toHaveTextContent("HKDC1, HK1, HK2, HK3, GCK");
    expect(notice.textContent).not.toMatch(/no --isoform was given/);
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

describe("the steady-state numbers", () => {
  it("writes an amount that is negative only by rounding as 0, with what was reported", () => {
    const fixture = composeHexokinase as unknown as Captured;
    const r = cap<ComposeResult>(fixture.result);
    const point = r.stability!.fixed_points.find((p) => p.physical && (p.state.reaction_S as number) < 0)!;
    expect(point.state.reaction_S).toBeLessThan(0);
    expect(Math.abs(point.state.reaction_S as number)).toBeLessThan(r.stability!.rounding_tolerance);
    render(<ComposeResultView result={r} run={cap<RunRecord>(fixture.run)} />);
    const zero = document.querySelector("[data-rounded-to-zero='true']") as HTMLElement;
    expect(zero).toHaveTextContent("0");
    expect(zero.getAttribute("title")).toMatch(/^Reported as -4\.\d+e-18: rounds to zero within the search's tolerance \(1e-6\)$/);
    expect(screen.getByTestId("rounded-to-zero")).toHaveTextContent("rounding within the search's tolerance");
    expect(screen.queryByText(/-4\.\d+e-18/)).toBeNull();
  });

  it("says the count of steady states on a line of equilibria is an artefact of where the starts fell, in the headline", () => {
    const fixture = composeTwoEnzymes as unknown as Captured;
    const r = cap<ComposeResult>(fixture.result);
    expect(r.stability!.count_caveat).toBe(
      "How many points land on the line is an artefact of where the starts fell, not a property of the model.",
    );
    render(<ComposeResultView result={r} run={cap<RunRecord>(fixture.run)} />);
    const section = screen.getByRole("region", { name: "Steady states" });
    const physical = r.stability!.fixed_points.filter((p) => p.physical).length;
    expect(within(section).getByText(`${physical} found from ${r.stability!.starts_tried} starts: the count depends on where the starts fell`)).toBeInTheDocument();
    expect(within(section).getByTestId("count-caveat")).toHaveTextContent(r.stability!.count_caveat!);
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

  beforeEach(() => resetLaunchCheck());

  it("checks once when the page opens and nothing has used the network yet, and not again on a re-render", async () => {
    setSessionToken("t0k");
    const { seen } = mockServer((req) => (req.url === "/api/capabilities?probe=network" ? json(200, used) : undefined));
    const view = bar(nothing);
    await waitFor(() => expect(seen.filter((r) => r.url === "/api/capabilities?probe=network")).toHaveLength(1));
    view.rerender(
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <StatusLine health={undefined} healthError={null} capabilities={nothing} capabilitiesError={null} />
      </QueryClientProvider>,
    );
    expect(seen.filter((r) => r.url === "/api/capabilities?probe=network")).toHaveLength(1);
  });

  it("does not check when a lookup has already told the server what the network is", async () => {
    setSessionToken("t0k");
    const { seen } = mockServer(() => undefined);
    bar(used);
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(seen.some((r) => r.url.includes("probe=network"))).toBe(false);
  });

  it("says not checked only when nothing has happened", () => {
    expect(nothing.network.checked).toBe(false);
    expect(nothing.network.source).toBeNull();
    bar(nothing);
    expect(screen.getByRole("button", { name: /^network not checked/ })).toBeInTheDocument();
  });

  it("says which host answered, from which request and when, after a lookup that worked", () => {
    expect(used.network.source).toBe("use");
    expect(used.network.reachable).toBe(true);
    expect(used.network.hosts["pubchem.ncbi.nlm.nih.gov"]).toBe(true);
    expect(used.network.hosts["rest.uniprot.org"]).toBeNull();
    bar(used);
    expect(screen.queryByText("network not checked")).toBeNull();
    const trigger = screen.getByRole("button", { name: /^some hosts reachable/ });
    expect(trigger).toHaveAccessibleName(/PubChem answered/);
    const sentence = readNetwork(used.network).sentence;
    expect(sentence).toMatch(/BRENDA, UniProt, the RCSB search, the RCSB files, NCBI not checked yet/);
    expect(sentence).toMatch(/check to test every host/);
    expect(sentence).not.toMatch(/Every database host answered/);
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

  it("reads an unreachable host from a failed request, with the server's reason, and does not blame the others", () => {
    const failed: Capabilities["network"] = {
      ...used.network,
      reachable: false,
      hosts: { ...used.network.hosts, "www.brenda-enzymes.org": false },
      reason: "www.brenda-enzymes.org could not be reached: name resolution failed",
    };
    const reading = readNetwork(failed);
    expect(reading.state).toBe("off");
    expect(reading.label).toBe("some hosts unreachable");
    expect(reading.sentence).toContain("PubChem answered");
    expect(reading.sentence).toContain("BRENDA did not answer");
    expect(reading.sentence).not.toContain("UniProt did not answer");
    // A host that did not answer is said by its name; the server's own reason is kept for a disclosure.
    expect(reading.sentence).not.toContain("www.brenda-enzymes.org");
    expect(reading.detail).toBe("www.brenda-enzymes.org could not be reached: name resolution failed");
  });

  it("says every host answered a check only when every host did, in a check", () => {
    const hosts = Object.fromEntries(Object.keys(used.network.hosts).map((h) => [h, true]));
    const status = Object.fromEntries(
      Object.keys(hosts).map((h) => [h, { reachable: true, checked_at: "2026-10-03T12:00:00.000Z", source: "probe", reason: null }]),
    );
    const checked: Capabilities["network"] = { ...used.network, source: "probe", hosts, host_status: status, reachable: true, reason: null };
    expect(readNetwork(checked).sentence).toMatch(/^Every database host answered a check/);
    expect(readNetwork(checked).label).toBe("network reachable");
    const partly: Capabilities["network"] = { ...checked, hosts: { ...hosts, "rest.uniprot.org": null } };
    expect(readNetwork(partly).sentence).not.toMatch(/Every database host/);
    expect(readNetwork(partly).sentence).toMatch(/UniProt not checked yet/);
  });
});

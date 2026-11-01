/**
 * The structure screens over real responses: the adapters' output for real
 * inputs, captured as src/__fixtures__/api/structure/README.md says. No
 * number below is typed by hand; every expectation is read from a fixture
 * or from the page.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import analyzeFixture from "@/__fixtures__/api/structure/analyze-lysozyme-native.json";
import scriptOnlyFixture from "@/__fixtures__/api/structure/analyze-lysozyme-script-only.json";
import coordinatesFixture from "@/__fixtures__/api/structure/coordinates-1L63.json";
import fepRefusedFixture from "@/__fixtures__/api/structure/fep-status-not-fep.json";
import setupFixture from "@/__fixtures__/api/structure/md-setup-1AKI.json";
import chosenSetupFixture from "@/__fixtures__/api/structure/md-setup-1I10-chosen.json";
import prepare1I10 from "@/__fixtures__/api/structure/prepare-1I10-ph7.4.json";
import prepare1L63 from "@/__fixtures__/api/structure/prepare-1L63.json";
import byNameFixture from "@/__fixtures__/api/structure/structure-by-name-ldha.json";
import severalFixture from "@/__fixtures__/api/structure/structure-ldh-several-proteins.json";
import structureFixture from "@/__fixtures__/api/structure/structure-ldha-oxamate.json";
import namesFixture from "@/__fixtures__/api/structure/structure-name-several-enzymes.json";
import type {
  AnalyzeResult,
  CoordinatesResponse,
  FindingRow,
  MdSetupResult,
  NameRefusal,
  Outcome,
  PrepareResult,
  RunKind,
  StructureResult,
} from "@/api/types";
import type { RunState } from "@/api/useRun";
import { mockServer, setSessionToken } from "@/__tests__/helpers";

import { NameRefusalChoices } from "@/components/enzyme/NameRefusal";

import { AnalyzeResultView } from "../Analyze";
import { SetupResultView, tabOfRun } from "../Md";
import { PrepareResultView } from "../Prepare";
import { StructureResultView } from "../Structure";
import { Entry } from "./EntryView";
import { ExtraSections } from "./Extra";
import { RunScreen } from "./kit";
import { findingFocus, knownAbout, rankFindings } from "./residues";
import { runs } from "./RmsfChart";
import type { FlexibilityView } from "./views";

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

function finished<K extends RunKind>(outcome: Outcome, result: RunState<K>["result"]): RunState<K> & { cancel: () => Promise<void> } {
  return {
    run: null,
    status: "done",
    stage: null,
    stages: [],
    log: [],
    outcome,
    result,
    requestError: null,
    runError: null,
    submitting: false,
    cancelling: false,
    settled: true,
    cancel: async () => {},
  };
}

afterEach(() => {
  vi.unstubAllGlobals();
});

const coords = coordinatesFixture as unknown as CoordinatesResponse;

describe("what the tools know about a residue", () => {
  it("finds the audit's findings at a residue, and points an unmodelled stretch at its flanks", () => {
    const findings = coords.findings!;
    const thr = findings.find((f) => f.residues[0] === "54")!;
    const known = knownAbout({ chain: "A", resseq: 54 }, { catalytic: coords.catalytic, findings });
    expect(known.findings).toEqual([thr]);
    expect(known.catalytic).toBeNull();
    const asp = coords.catalytic![0];
    expect(knownAbout({ chain: asp.chain, resseq: Number(asp.resseq) }, { catalytic: coords.catalytic, findings }).catalytic).toBe(asp);

    const gap = findings.find((f) => f.residues[0].includes("-"))!;
    const [a, b] = gap.residues[0].split("-").map(Number);
    expect(findingFocus(gap)).toEqual({ refs: [{ chain: "A", resseq: a - 1 }, { chain: "A", resseq: b + 1 }], flanking: true });
  });

  it("ranks findings as the report does: severity, then nearest the active site", () => {
    const r = prepare1I10.result as unknown as PrepareResult;
    const ranked = rankFindings(r.findings);
    const order = ["blocks", "decide", "note"];
    for (let i = 1; i < ranked.length; i++) {
      const [p, q] = [ranked[i - 1], ranked[i]];
      const bySeverity = order.indexOf(p.severity) - order.indexOf(q.severity);
      expect(bySeverity).toBeLessThanOrEqual(0);
      if (bySeverity === 0 && p.distance && q.distance) expect(p.distance.value!).toBeLessThanOrEqual(q.distance.value!);
    }
  });
});

describe("an entry in 3D", () => {
  it("lists the catalytic residues, and choosing one says what caterva prepare placed there", async () => {
    wrap(<Entry coords={coords} findings={coords.findings!} />);
    expect(screen.getByRole("application", { name: new RegExp(`^${coords.pdb_id}:`) })).toBeInTheDocument();
    const site = coords.catalytic![0];
    await userEvent.click(screen.getByRole("button", { name: new RegExp(`${site.chain} Asp${site.resseq}`) }));
    const panel = screen.getByRole("region", { name: "What the tools know about this residue" });
    expect(within(panel).getByText(`Catalytic: ${site.roles}`)).toBeInTheDocument();
    expect(within(panel).getByText(new RegExp(site.reference))).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: "Clear" }));
    expect(screen.queryByRole("region", { name: "What the tools know about this residue" })).toBeNull();
  });

  it("shows a finding's residue chosen, with the audit's words and its distance one click from its method", async () => {
    const f = coords.findings!.find((x) => x.residues[0] === "54")!;
    const focus = { ...findingFocus(f), what: f.what };
    wrap(<Entry coords={coords} findings={coords.findings!} focus={focus} />);
    const panel = screen.getByRole("region", { name: "What the tools know about this residue" });
    expect(within(panel).getByRole("heading", { name: /54 \(chain A\)/ })).toBeInTheDocument();
    await userEvent.click(within(panel).getByRole("button", { name: /to the active site/ }));
    expect(await screen.findByText(f.distance!.provenance.method!)).toBeInTheDocument();
  });
});

describe("Structures", () => {
  const result = structureFixture.result as unknown as StructureResult;

  it("lists the chosen protein's entries best first, and Enter on one opens it in 3D", async () => {
    setSessionToken("test-token");
    const seen: string[] = [];
    mockServer((req) => {
      seen.push(req.url);
      return new Promise<Response>(() => {});
    });
    wrap(<StructureResultView result={result} runId={null} />);
    const entries = screen.getByRole("table", { name: /PDB entries/ });
    const rows = within(entries).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(result.entries.length);
    expect(within(rows[0]).getByText(result.entries[0].pdb_id)).toBeInTheDocument();
    await userEvent.click(within(rows[0]).getByRole("button", { name: /resolution/ }));
    expect(await screen.findByText(result.entries[0].resolution!.provenance.citation!.text)).toBeInTheDocument();

    const second = result.entries[1].pdb_id;
    rows[1].focus();
    await userEvent.keyboard("{Enter}");
    expect(screen.getByRole("heading", { name: `PDB ${second}` })).toBeInTheDocument();
    expect(await screen.findByRole("status", { name: new RegExp(`Reading PDB ${second}`) })).toBeInTheDocument();
    expect(seen.some((u) => u.endsWith(`/api/structure/${second}/coordinates`))).toBe(true);
    expect(screen.getByRole("link", { name: "Audit this entry" })).toHaveAttribute("href", `/prepare?entry=${second}`);
  });

  it("shows a several-proteins refusal in the command's words, with a choice per protein", async () => {
    const outcome = severalFixture.outcome as Outcome;
    const several = severalFixture.result as unknown as StructureResult;
    const chosen: string[] = [];
    wrap(
      <RunScreen
        kind="structure"
        id="t"
        formLabel="form"
        action="Search"
        canSubmit
        onSubmit={() => {}}
        run={finished<"structure">(outcome, several)}
        form={null}
        idle={null}
      >
        {(r) => <StructureResultView result={r} runId={null} onChoose={(p) => chosen.push(p.accession)} />}
      </RunScreen>,
    );
    expect(within(screen.getByRole("region", { name: outcome.summary })).getByText(outcome.reason!)).toBeInTheDocument();
    const withEntries = several.proteins.filter((p) => p.entries > 0);
    const buttons = screen.getAllByRole("button", { name: /^Choose / });
    expect(buttons).toHaveLength(withEntries.length);
    await userEvent.click(buttons[0]);
    expect(chosen).toEqual([withEntries[0].accession]);
    expect(screen.queryByRole("table", { name: /PDB entries/ })).toBeNull();
  });

  it("offers each enzyme a refused name could be, by name, and sends nothing until one is chosen", async () => {
    expect(namesFixture.outcome.meaning).toBe("refused");
    expect(namesFixture.result).toBeNull();
    const refusal = namesFixture.outcome.name_refusal as unknown as NameRefusal;
    const chosen: string[] = [];
    wrap(<NameRefusalChoices refusal={refusal} onChoose={(ec) => chosen.push(ec)} />);
    for (const c of refusal.named_candidates) {
      expect(screen.getByText(c.name)).toBeInTheDocument();
      expect(screen.getByText(`EC ${c.ec}`)).toBeInTheDocument();
    }
    const second = refusal.named_candidates[1];
    await userEvent.click(screen.getByRole("button", { name: `Use EC ${second.ec}` }));
    expect(chosen).toEqual([second.ec]);
  });

  it("says which EC number a name was resolved to, and offers the ChimeraX script the run kept", () => {
    const r = byNameFixture.result as unknown as StructureResult;
    mockServer(() => new Promise<Response>(() => {}));
    wrap(<StructureResultView result={r} runId="20260930-120000-structure-0badc0de" />);
    expect(r.subject_notes?.length).toBeGreaterThan(0);
    expect(screen.getByText(r.subject_notes![0])).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Download the ChimeraX script" })).toBeInTheDocument();
  });
});

describe("Prepare", () => {
  it("leads with the blocking findings, nearest the active site first", () => {
    const r = prepare1L63.result as unknown as PrepareResult;
    expect(prepare1L63.outcome.meaning).toBe("negative");
    mockServer(() => new Promise<Response>(() => {}));
    wrap(<PrepareResultView result={r} entry="1L63" />);
    expect(screen.getByRole("heading", { name: /every chain has at least one blocking defect/ })).toBeInTheDocument();
    const blocks = screen.getByRole("table", { name: "Blocks a faithful setup" });
    const rows = within(blocks).getAllByRole("row").slice(1);
    const expected = r.findings.filter((f) => f.severity === "blocks").sort((a, b) => a.distance!.value! - b.distance!.value!);
    expect(rows).toHaveLength(expected.length);
    expected.forEach((f, i) => expect(within(rows[i]).getByText(f.what, { exact: false })).toBeInTheDocument());
  });

  it("shows a chosen finding in the viewer with what the audit found there", async () => {
    setSessionToken("test-token");
    mockServer((req) => (req.url.endsWith("/api/structure/1L63/coordinates") ? { status: 200, body: coordinatesFixture } : undefined));
    const r = prepare1L63.result as unknown as PrepareResult;
    wrap(<PrepareResultView result={r} entry="1L63" />);
    const blocks = screen.getByRole("table", { name: "Blocks a faithful setup" });
    const first = within(blocks).getAllByRole("row")[1];
    await userEvent.click(first);
    const finding = rankFindings(r.findings)[0] as FindingRow;
    const look = await screen.findByRole("region", { name: "The finding being looked at" });
    expect(within(look).getByText(new RegExp(finding.what.slice(0, 20).replace(/[()>-]/g, ".")))).toBeInTheDocument();
    const panel = screen.getByRole("region", { name: "What the tools know about this residue" });
    expect(within(panel).getByText(finding.what, { exact: false })).toBeInTheDocument();
  });

  it("judges protonation at the assay pH with the survey's pKa one click away", async () => {
    const r = prepare1I10.result as unknown as PrepareResult;
    mockServer(() => new Promise<Response>(() => {}));
    wrap(<PrepareResultView result={r} entry="1I10" />);
    const table = screen.getByRole("table", { name: "Protonation" });
    const pka = within(table).getAllByRole("button", { name: /typical pKa/ });
    expect(pka.length).toBeGreaterThan(0);
    await userEvent.click(pka[0]);
    expect(within(await screen.findByRole("dialog")).getByText(/Grimsley/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Write an MD setup for chain A/ })).toHaveAttribute("href", "/md?pdb=1I10&chain=A");
  });
});

describe("Dynamics", () => {
  it("lists every parameter with its origin, each cited method linked to its paper", async () => {
    const r = setupFixture.result as unknown as MdSetupResult;
    wrap(<SetupResultView result={r} />);
    const table = screen.getByRole("table", { name: "Parameters" });
    expect(within(table).getAllByRole("row")).toHaveLength(r.parameters.length + 1);
    const methods = r.parameters.filter((p) => p.origin === "method");
    expect(within(table).getAllByText("cited method")).toHaveLength(methods.length);
    for (const m of methods) {
      expect(within(table).getByRole("link", { name: new RegExp(m.citation!.text.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")) })).toHaveAttribute(
        "href",
        m.citation!.url!,
      );
    }
    const chosen = r.parameters.filter((p) => p.origin === "chosen");
    expect(within(table).getAllByText("a stated default")).toHaveLength(chosen.filter((p) => p.by === "default").length);
    expect(within(table).getAllByText("chosen by you")).toHaveLength(chosen.filter((p) => p.by === "user").length);
    await userEvent.click(within(table).getByRole("button", { name: /^temperature/ }));
    expect(within(await screen.findByRole("dialog")).getByText(r.temperature.provenance.reason!)).toBeInTheDocument();
    expect(screen.getByText(`${r.out_dir}/run.sh`, { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Analyze it here once it has run" })).toHaveAttribute(
      "href",
      `/analyze?directory=${encodeURIComponent(r.out_dir)}`,
    );
  });

  it("marks what the person chose as theirs", () => {
    const r = chosenSetupFixture.result as unknown as MdSetupResult;
    wrap(<SetupResultView result={r} />);
    const table = screen.getByRole("table", { name: "Parameters" });
    const yours = r.parameters.filter((p) => p.by === "user").length + (r.ph ? 1 : 0);
    expect(within(table).getAllByText("chosen by you")).toHaveLength(yours);
  });

  it("reopens a run from History on the tab of its kind", () => {
    expect(tabOfRun("20260930-120000-md-setup-0badc0de")).toBe("setup");
    expect(tabOfRun("20260930-120000-md-summarise-0badc0de")).toBe("convergence");
    expect(tabOfRun("20260930-120000-fep-status-0badc0de")).toBe("fep");
    expect(tabOfRun("20260930-120000-complex-check-0badc0de")).toBe("complex");
    expect(tabOfRun("20260930-120000-analyze-0badc0de")).toBeNull();
  });

  it("shows a free-energy refusal as a refusal, not an error", () => {
    const outcome = fepRefusedFixture.outcome as Outcome;
    wrap(
      <RunScreen kind="fep.status" id="t" formLabel="form" action="Read" canSubmit onSubmit={() => {}} run={finished<"fep.status">(outcome, null)} form={null} idle={null}>
        {() => null}
      </RunScreen>,
    );
    expect(within(screen.getByRole("region", { name: outcome.summary })).getAllByText(outcome.reason!).length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Analyze", () => {
  const r = analyzeFixture.result as unknown as AnalyzeResult;

  it("draws every catalytic distance per replica, with its verdict and the threshold it was judged against", async () => {
    wrap(<AnalyzeResultView result={r} />);
    expect(screen.getAllByText("not yet a result").length).toBeGreaterThan(0);
    const table = screen.getByRole("table", { name: "Catalytic distances" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(r.distances.length);
    r.distances.forEach((d, i) => expect(within(rows[i]).getByText(d.label)).toBeInTheDocument());
    const reps = r.replicas!;
    for (const name of reps) expect(within(table).getByRole("columnheader", { name })).toBeInTheDocument();
    await userEvent.click(within(rows[0]).getByRole("button", { name: new RegExp(`${r.distances[0].label}, mean`) }));
    expect(await screen.findByText(r.distances[0].mean.provenance.method!)).toBeInTheDocument();
    const moved = r.thresholds!.distances[0];
    expect(screen.getAllByRole("button", { name: new RegExp(`^${moved.label}`) }).length).toBeGreaterThan(0);
    expect(screen.getAllByRole("figure", { name: /each replica's mean and error/ }).length).toBe(2);
  });

  it("puts the RMSF along the chain beside the flexibility means, every value with its provenance", async () => {
    wrap(<AnalyzeResultView result={r} />);
    const flex = r.flexibility as unknown as FlexibilityView;
    const profile = flex.rmsf!;
    expect(screen.getByRole("heading", { name: "C-alpha RMSF along the chain" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "The numbers as a table" }));
    const table = screen.getByRole("table", { name: `C-alpha RMSF of ${profile.residues.length} residues` });
    expect(within(table).getAllByRole("row")).toHaveLength(profile.residues.length + 1);
    const first = Object.keys(profile.replicas)[0];
    expect(within(table).getAllByRole("button", { name: new RegExp(`RMSF, ${first}`) }).length).toBe(
      profile.replicas[first].filter((v) => v !== null).length,
    );
    expect(runs(profile.pocket).flat().every((n) => profile.pocket.includes(n))).toBe(true);
  });

  it("compares the occupancies replica by replica", () => {
    wrap(<AnalyzeResultView result={r} />);
    for (const name of ["Water", "Hydrogen bonds", "Rotamers", "Faces"]) {
      const table = screen.getByRole("table", { name });
      for (const rep of r.replicas!) expect(within(table).getAllByRole("columnheader", { name: new RegExp(rep) }).length).toBeGreaterThan(0);
    }
  });

  it("says when a run only wrote its script", () => {
    wrap(<AnalyzeResultView result={scriptOnlyFixture.result as unknown as AnalyzeResult} />);
    expect(screen.getByText("script written, nothing measured")).toBeInTheDocument();
  });

  it("draws a section it has no drawing for by its shape, keeping every value's mark", () => {
    // Rows shaped like a section a newer engine adds: this fixture's own distance rows, under a name the page does not know.
    const rows = r.distances.slice(0, 2).map((d) => ({ label: d.label, mean: d.mean, verdict: d.verdict }));
    wrap(<ExtraSections extra={{ rows_from_this_fixture: rows }} />);
    expect(screen.getByRole("heading", { name: "Rows from this fixture" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: /, mean,/ })).toHaveLength(2);
  });
});

describe("the form frame", () => {
  it("submits with the platform's modifier and Enter, and not while it cannot", () => {
    const submitted: number[] = [];
    const idle = { ...finished<"prepare">({ exit_code: 0, meaning: "produced", summary: "", reason: null }, null), status: "idle" as const, settled: false };
    const { rerender } = wrap(
      <RunScreen kind="prepare" id="t" formLabel="Audit an entry" action="Audit" canSubmit={false} onSubmit={() => submitted.push(1)} run={idle} form={null} idle={<p>idle</p>}>
        {() => null}
      </RunScreen>,
    );
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(submitted).toHaveLength(0);
    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <RunScreen kind="prepare" id="t" formLabel="Audit an entry" action="Audit" canSubmit onSubmit={() => submitted.push(1)} run={idle} form={null} idle={<p>idle</p>}>
          {() => null}
        </RunScreen>
      </QueryClientProvider>,
    );
    fireEvent.keyDown(window, { key: "Enter", ctrlKey: true });
    expect(submitted).toHaveLength(1);
    fireEvent.submit(screen.getByRole("form", { name: "Audit an entry" }));
    expect(submitted).toHaveLength(2);
  });
});

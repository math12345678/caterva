/**
 * The structure screens over real responses: the adapters' output for real
 * inputs, captured as src/__fixtures__/api/structure/README.md says. No
 * number below is typed by hand; every expectation is read from a fixture
 * or from the page.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it } from "vitest";

import analyzeFixture from "@/__fixtures__/api/structure/analyze-lysozyme-native.json";
import coordinatesFixture from "@/__fixtures__/api/structure/coordinates-1L63.json";
import fepRefusedFixture from "@/__fixtures__/api/structure/fep-status-not-fep.json";
import setupFixture from "@/__fixtures__/api/structure/md-setup-1AKI.json";
import prepare1I10 from "@/__fixtures__/api/structure/prepare-1I10-ph7.4.json";
import prepare1L63 from "@/__fixtures__/api/structure/prepare-1L63.json";
import severalFixture from "@/__fixtures__/api/structure/structure-ldh-several-proteins.json";
import structureFixture from "@/__fixtures__/api/structure/structure-ldha-oxamate.json";
import type {
  AnalyzeResult,
  CoordinatesResponse,
  MdSetupResult,
  Outcome,
  PrepareResult,
  StructureResult,
} from "@/api/types";

import { AnalyzeResultView } from "../Analyze";
import { SetupResultView, tabOfRun } from "../Md";
import { PrepareResultView } from "../Prepare";
import { StructureResultView } from "../Structure";
import { RunArea } from "./kit";
import { MoleculeView } from "./MoleculeView";
import { buildModel, oklchToSrgb, siteKey } from "./model";

function wrap(node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{node}</QueryClientProvider>);
}

const coords = coordinatesFixture as unknown as CoordinatesResponse;

describe("the viewer's model", () => {
  it("keeps every atom of the file, centred, and finds each catalytic residue's atoms", () => {
    const m = buildModel(coords);
    expect(m.roles.length + m.hiddenWater).toBe(coords.count);
    const n = m.roles.length;
    const mean = [0, 1, 2].map((d) => {
      let s = 0;
      for (let k = 0; k < n; k++) s += m.positions[k * 3 + d];
      return s / n;
    });
    for (const v of mean) expect(Math.abs(v)).toBeLessThan(1e-3);
    // Centring subtracts one vector: distances between atoms are the file's.
    const [i, j] = [0, n - 1];
    const fileDistance = Math.hypot(
      coords.atoms.x[m.source[i]] - coords.atoms.x[m.source[j]],
      coords.atoms.y[m.source[i]] - coords.atoms.y[m.source[j]],
      coords.atoms.z[m.source[i]] - coords.atoms.z[m.source[j]],
    );
    const modelDistance = Math.hypot(
      m.positions[i * 3] - m.positions[j * 3],
      m.positions[i * 3 + 1] - m.positions[j * 3 + 1],
      m.positions[i * 3 + 2] - m.positions[j * 3 + 2],
    );
    expect(modelDistance).toBeCloseTo(fileDistance, 3);

    expect(m.sites.map((s) => s.key)).toEqual(coords.catalytic!.map((c) => siteKey(c.chain, c.resseq)));
    for (const site of m.sites) {
      const expected = coords.atoms.resseq.filter(
        (r, k) => String(r) === site.site.resseq && coords.atoms.chain[k] === site.site.chain && !coords.atoms.hetero[k],
      ).length;
      expect(site.atoms.length).toBe(expected);
      expect(site.atoms.length).toBeGreaterThan(0);
    }
  });

  it("converts the page's OKLCH tokens to the brand's sRGB", () => {
    // paper #FDF8EE, ink #2A2D35, signal #5D7F8D (caterva-landing DESIGN.md), as index.css writes them.
    const cases: [string, [number, number, number]][] = [
      ["oklch(0.98 0.014 84.6)", [0xfd, 0xf8, 0xee]],
      ["oklch(0.297 0.015 269.2)", [0x2a, 0x2d, 0x35]],
      ["oklch(0.576 0.044 225.3)", [0x5d, 0x7f, 0x8d]],
    ];
    for (const [css, hex] of cases) {
      const rgb = oklchToSrgb(css)!;
      rgb.forEach((c, i) => expect(Math.abs(c * 255 - hex[i])).toBeLessThan(1.5));
    }
    expect(oklchToSrgb("#fdf8ee")).toBeNull();
  });
});

describe("MoleculeView without WebGL", () => {
  it("says it cannot draw, and still lists the catalytic residues as buttons", async () => {
    let selected: string | null = null;
    render(<MoleculeView coords={coords} selected={null} onSelect={(k) => (selected = k)} />);
    expect(screen.getByText(/gives the page no WebGL/)).toBeInTheDocument();
    const first = coords.catalytic![0];
    const button = screen.getByRole("button", { name: new RegExp(`${first.chain}·Asp${first.resseq}`) });
    await userEvent.click(button);
    expect(selected).toBe(siteKey(first.chain, first.resseq));
  });
});

describe("Structures", () => {
  const result = structureFixture.result as unknown as StructureResult;

  it("lists the chosen protein's entries best first, each resolution with its citation one click away", async () => {
    wrap(<StructureResultView result={result} runId={null} />);
    const entries = screen.getByRole("table", { name: "PDB entries" });
    const rows = within(entries).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(result.top!);
    expect(within(rows[0]).getByRole("button", { name: `Open PDB ${result.entries[0].pdb_id} in 3D` })).toBeInTheDocument();
    await userEvent.click(within(rows[0]).getByRole("button", { name: /resolution/ }));
    expect(await screen.findByText(result.entries[0].resolution!.provenance.citation!.text)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: `Show all ${result.entries.length}` }));
    expect(within(entries).getAllByRole("row")).toHaveLength(result.entries.length + 1);
  });

  it("shows a several-proteins refusal in the command's words, with a choice per protein", () => {
    const outcome = severalFixture.outcome as Outcome;
    const several = severalFixture.result as unknown as StructureResult;
    const choices: string[] = [];
    wrap(
      <RunArea
        view={{ run: null, status: "done", stage: null, outcome, requestError: null, runError: null }}
        waiting=""
        hasResult
      >
        <StructureResultView result={several} runId={null} onChoose={(gene) => choices.push(gene ?? "")} />
      </RunArea>,
    );
    expect(within(screen.getByRole("region", { name: "Refused, and why" })).getByText(outcome.reason!)).toBeInTheDocument();
    const withEntries = several.proteins.filter((p) => p.entries > 0);
    expect(screen.getAllByRole("button", { name: "Choose" })).toHaveLength(withEntries.length);
    expect(screen.queryByRole("table", { name: "PDB entries" })).toBeNull();
  });
});

describe("Prepare", () => {
  it("leads with the blocking findings when every chain is blocked, nearest the active site first", () => {
    const r = prepare1L63.result as unknown as PrepareResult;
    expect(prepare1L63.outcome.meaning).toBe("negative");
    wrap(<PrepareResultView result={r} entry="1L63" />);
    expect(screen.getByText(/every chain has at least one blocking/)).toBeInTheDocument();
    const blocks = screen.getByRole("table", { name: "Blocks a faithful setup" });
    const shown = within(blocks)
      .getAllByRole("row")
      .slice(1)
      .map((row) => within(row).getByRole("button").getAttribute("aria-label"));
    const expected = r.findings
      .filter((f) => f.severity === "blocks")
      .map((f) => f.distance!.value!)
      .sort((a, b) => a - b);
    expect(shown).toHaveLength(expected.length);
    // The rows are in the report's order: the nearest first.
    const firstRow = within(blocks).getAllByRole("row")[1];
    const nearest = r.findings.find((f) => f.severity === "blocks" && f.distance!.value === expected[0])!;
    expect(within(firstRow).getByText(nearest.what, { exact: false })).toBeInTheDocument();
  });

  it("judges protonation at the assay pH with the survey's pKa one click away", async () => {
    const r = prepare1I10.result as unknown as PrepareResult;
    wrap(<PrepareResultView result={r} entry="1I10" />);
    const table = screen.getByRole("table", { name: "Protonation" });
    const pkaButtons = within(table).getAllByRole("button", { name: /typical pKa/ });
    expect(pkaButtons.length).toBeGreaterThan(0);
    await userEvent.click(pkaButtons[0]);
    expect(within(await screen.findByRole("dialog")).getByText(/Grimsley/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Write an MD setup for chain A/ })).toHaveAttribute(
      "href",
      "/md?pdb=1I10&chain=A",
    );
  });
});

describe("Dynamics", () => {
  it("lists every parameter with its origin, cited methods linked", async () => {
    const r = setupFixture.result as unknown as MdSetupResult;
    wrap(<SetupResultView result={r} />);
    const table = screen.getByRole("table", { name: "Parameters" });
    expect(within(table).getAllByRole("row")).toHaveLength(r.parameters.length + 1);
    expect(within(table).getAllByText("cited method").length).toBe(r.parameters.filter((p) => p.origin === "method").length);
    expect(within(table).getByRole("link", { name: "doi:10.1002/prot.22711" })).toHaveAttribute(
      "href",
      "https://doi.org/10.1002/prot.22711",
    );
    await userEvent.click(screen.getByRole("button", { name: /temperature/ }));
    expect(within(await screen.findByRole("dialog")).getByText(r.temperature.provenance.reason!)).toBeInTheDocument();
    expect(document.querySelector("pre.command-slab")?.textContent).toContain(`bash ${r.out_dir}/run.sh`);
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
    render(
      <RunArea
        view={{ run: null, status: "done", stage: null, outcome, requestError: null, runError: null }}
        waiting=""
        hasResult={false}
      />,
    );
    expect(screen.getByText(outcome.reason!)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });
});

describe("Analyze", () => {
  it("draws every catalytic distance with its verdict, and says it is not yet a result", async () => {
    const r = analyzeFixture.result as unknown as AnalyzeResult;
    wrap(<AnalyzeResultView result={r} />);
    expect(screen.getAllByText("not yet a result").length).toBeGreaterThan(0);
    const table = screen.getByRole("table", { name: "Catalytic distances" });
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(r.distances.length);
    r.distances.forEach((d, i) => expect(within(rows[i]).getByText(d.label)).toBeInTheDocument());
    await userEvent.click(within(rows[0]).getByRole("button", { name: new RegExp(`${r.distances[0].label}, mean`) }));
    expect(await screen.findByText(r.distances[0].mean.provenance.method!)).toBeInTheDocument();
    expect(screen.getByRole("table", { name: "Water" })).toBeInTheDocument();
  });
});

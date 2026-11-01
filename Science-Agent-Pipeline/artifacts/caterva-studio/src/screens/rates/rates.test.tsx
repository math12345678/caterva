/**
 * The Rates screen over the studio server's real answers
 * (src/__fixtures__/api/rates, captured from the dispatch layer; README
 * there). The mock server answers a preview or a run with the recording made
 * for exactly that table, and 404 for any other, so a test cannot pass on an
 * answer nobody recorded. The tables are R's Puromycin data and formats of
 * the same values; no number below is typed as an expectation, each is read
 * from the fixture it renders.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Router } from "wouter";
import { memoryLocation } from "wouter/memory-location";

import capsRates from "@/__fixtures__/api/rates/capabilities-rates.json";
import previewBinary from "@/__fixtures__/api/rates/preview-binary.json";
import previewMessy from "@/__fixtures__/api/rates/preview-messy.json";
import previewNever from "@/__fixtures__/api/rates/preview-never-saturates.json";
import previewNoUnits from "@/__fixtures__/api/rates/preview-no-units.json";
import previewNoUnitsNamed from "@/__fixtures__/api/rates/preview-no-units-named.json";
import previewNoUnitsSubstrate from "@/__fixtures__/api/rates/preview-no-units-substrate-named.json";
import previewPasted from "@/__fixtures__/api/rates/preview-pasted-decimal-comma.json";
import previewGroupOff from "@/__fixtures__/api/rates/preview-puromycin-group-off.json";
import previewPuromycin from "@/__fixtures__/api/rates/preview-puromycin.json";
import previewWide from "@/__fixtures__/api/rates/preview-wide.json";
import runLiterature from "@/__fixtures__/api/rates/run-literature-declined.json";
import runNever from "@/__fixtures__/api/rates/run-never-saturates.json";
import runResiduals from "@/__fixtures__/api/rates/run-puromycin-residuals.json";
import runRefused from "@/__fixtures__/api/rates/run-refused-law-needs-inhibitor.json";
import { frame, json, mockServer, setSessionToken, sseResponse } from "@/__tests__/helpers";
import { resetRunStreamsForTests } from "@/api/runs";
import type { RatesPreview, RatesResult, RunRecord } from "@/api/types";
import { plain } from "@/lib/copy";
import { formatNumber } from "@/lib/format";

import RatesScreen from "../Rates";
import { announcement, ratesRequest, requestState, roleOf, withRole, sigmaAllowed, defaultSigma, readFile, readPasted } from "./model";
import { PUROMYCIN_CSV } from "./puromycin";

type Recorded = { request: { method: string; path: string; body: { text: string; filename?: string; mapping?: Record<string, unknown> } }; status: number; body: RatesPreview };
type Captured = { captured: { request: Record<string, unknown> }; run: unknown; result: unknown; events: { event: string; data: Record<string, unknown> }[] };

const PREVIEWS = [previewPuromycin, previewGroupOff, previewMessy, previewNever, previewNoUnits, previewNoUnitsSubstrate, previewNoUnitsNamed, previewPasted, previewWide, previewBinary] as unknown as Recorded[];

function previewFor(body: { text: string; mapping?: unknown }): Response | undefined {
  const hit = PREVIEWS.find((p) => p.request.body.text === body.text && JSON.stringify(p.request.body.mapping ?? {}) === JSON.stringify(body.mapping ?? {}));
  if (hit) return json(hit.status, hit.body);
  // A first look at a table is a request with no mapping; a recorded one with a mapping is a follow-up.
  const first = PREVIEWS.find((p) => p.request.body.text === body.text && !p.request.body.mapping);
  return first && !body.mapping ? json(first.status, first.body) : undefined;
}

function replay(fixture: Captured): Response {
  return sseResponse(fixture.events.map((e, i) => frame(e.event, i + 1, e.data)));
}

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

function serve(extra?: (req: { url: string; method: string; body: unknown }) => Response | undefined) {
  return mockServer((req) => {
    if (req.url === "/api/capabilities") return json(200, capsRates.body);
    if (req.url === "/api/settings") return json(200, { theme: "system", max_concurrent: 2, keep_runs: 200, offline: false });
    if (req.url === "/api/rates/preview" && req.method === "POST") return previewFor(req.body as { text: string; mapping?: unknown });
    return extra?.(req);
  });
}

function serveRun(fixture: Captured) {
  const run = fixture.run as RunRecord;
  return serve((req) => {
    if (req.method === "POST" && req.url === "/api/runs") return json(202, { run });
    if (req.url === `/api/runs/${run.id}`) return json(200, run);
    if (req.url === `/api/runs/${run.id}/result`) return fixture.result ? json(200, fixture.result) : json(404, { error: { code: "not_found", message: "no result" } });
    if (req.url === `/api/runs/${run.id}/events`) return replay(fixture);
    return undefined;
  });
}

afterEach(() => {
  vi.unstubAllGlobals();
  resetRunStreamsForTests();
});

const file = (text: string, name: string) => {
  const f = new File([text], name, { type: "text/csv" });
  if (typeof f.text !== "function") Object.defineProperty(f, "text", { value: () => Promise.resolve(text) });
  return f;
};

describe("getting a table in", () => {
  it("opens the real Puromycin example, says how every part of it was read, and announces it once", async () => {
    setSessionToken("t0k");
    serve();
    render(withApp("/rates", <RatesScreen />));
    await userEvent.click(await screen.findByRole("button", { name: "Open an example" }));
    const preview = (previewPuromycin as unknown as Recorded).body;
    const table = await screen.findByRole("table", { name: /The first 23 of 23 rows/ });
    // Each column's role is a control on its heading, set as detected.
    expect(within(table).getByLabelText(/Role of column 1, substrate/)).toHaveValue("substrate");
    expect(within(table).getByLabelText(/Role of column 3, state/)).toHaveValue("group");
    expect(screen.getByText(/Example: R's datasets::Puromycin/)).toBeInTheDocument();
    for (const d of preview.decisions.slice(0, 3)) expect(screen.getByText(d)).toBeInTheDocument();
    const status = await screen.findByText(announcement(preview));
    expect(status).toHaveAttribute("aria-live", "polite");
    expect(preview.problems).toEqual([]);
    expect(screen.getByText("Measurements used").nextSibling).toHaveTextContent(String(preview.summary!.rows_used));
    // Step 2 appears with the uncertainty the table offers first, and Fit is ready.
    expect(await screen.findByRole("radio", { name: /From the scatter of my replicates \(11 replicate sets, 11 degrees of freedom\)/ })).toBeChecked();
    expect(screen.getByRole("button", { name: "Fit my data" })).toBeEnabled();
  });

  it("opens the example from the address Home links to", async () => {
    setSessionToken("t0k");
    serve();
    render(withApp("/rates?example=puromycin", <RatesScreen />));
    expect(await screen.findByRole("table", { name: /The first 23 of 23 rows/ })).toBeInTheDocument();
  });

  it("reads a file dropped on the page as text and sends the text, never a path", async () => {
    setSessionToken("t0k");
    const { seen } = serve();
    const recorded = previewMessy as unknown as Recorded;
    render(withApp("/rates", <RatesScreen />));
    const zone = (await screen.findByText("Drop a CSV, TSV or text file here")).closest(".r-drop")!;
    fireEvent.drop(zone, { dataTransfer: { files: [file(recorded.request.body.text, "treated-messy.tsv")] } });
    await screen.findByRole("table", { name: /The first/ });
    const post = seen.find((r) => r.url === "/api/rates/preview")!;
    expect(post.body).toMatchObject({ text: recorded.request.body.text, filename: "treated-messy.tsv" });
    expect(JSON.stringify(post.body)).not.toMatch(/\/(Users|home|tmp)\//);
  });

  it("locates every problem by line and column, marks the cells, and skips rows only in the open", async () => {
    setSessionToken("t0k");
    serve();
    const recorded = previewMessy as unknown as Recorded;
    render(withApp("/rates", <RatesScreen />));
    const zone = (await screen.findByText("Drop a CSV, TSV or text file here")).closest(".r-drop")!;
    fireEvent.drop(zone, { dataTransfer: { files: [file(recorded.request.body.text, "treated-messy.tsv")] } });
    await screen.findByRole("table", { name: /The first/ });
    const skipped = recorded.body.problems.filter((p) => p.severity === "skipped");
    expect(skipped.length).toBe(recorded.body.summary!.rows_skipped);
    const group = (await screen.findByText(/Skipped, and left out of the fit/)).closest(".r-problem-group")!;
    for (const p of skipped) {
      const item = within(group as HTMLElement).getByText(p.message);
      expect(item.closest("li")).toHaveTextContent(`line ${p.line}, ${p.column}`);
    }
    // The cell itself is marked, with its reason as text for a screen reader.
    const flagged = recorded.body.preview.rows.filter((r) => Object.keys(r.flags).length);
    expect(flagged.length).toBe(skipped.length);
    const marked = document.querySelectorAll('td[data-flag="true"]');
    expect(marked.length).toBe(skipped.length);
    expect(screen.getAllByText(/skipped$/).length).toBeGreaterThan(0);
  });

  it("reads a spreadsheet paste pressed with Ctrl V anywhere, but not into a field", async () => {
    setSessionToken("t0k");
    const { seen } = serve();
    const recorded = previewPasted as unknown as Recorded;
    render(withApp("/rates", <RatesScreen />));
    await screen.findByText("Drop a CSV, TSV or text file here");
    // In a field, paste means paste into it: nothing is read.
    const box = screen.getByRole("button", { name: "Choose a file" });
    box.focus();
    fireEvent.paste(document.body, { clipboardData: { getData: () => "" } });
    expect(seen.some((r) => r.url === "/api/rates/preview")).toBe(false);
    fireEvent.paste(document.body, { clipboardData: { getData: () => recorded.request.body.text } });
    const table = await screen.findByRole("table", { name: /The first 12 of 12 rows/ });
    expect(screen.getByText("Pasted text")).toBeInTheDocument();
    const header = within(table).getAllByRole("columnheader");
    expect(header.map((h) => h.textContent)).toEqual(expect.arrayContaining([expect.stringContaining("[S]")]));
    for (const d of recorded.body.decisions.slice(0, 4)) expect(screen.getByText(d)).toBeInTheDocument();
    expect(screen.getByLabelText("Substrate unit")).toHaveValue("ppm");
  });

  it("does not take a paste typed into a text box as a table until it is used", async () => {
    setSessionToken("t0k");
    const { seen } = serve();
    render(withApp("/rates", <RatesScreen />));
    await userEvent.click(await screen.findByText("Type or paste into a box instead"));
    const box = screen.getByLabelText("Table text");
    box.focus();
    fireEvent.paste(box, { clipboardData: { getData: () => "a\tb" } });
    expect(seen.some((r) => r.url === "/api/rates/preview")).toBe(false);
  });

  it("refuses a workbook by name before reading it, and a binary file with the server's reason", async () => {
    setSessionToken("t0k");
    serve();
    render(withApp("/rates", <RatesScreen />));
    const zone = (await screen.findByText("Drop a CSV, TSV or text file here")).closest(".r-drop")!;
    fireEvent.drop(zone, { dataTransfer: { files: [file("x", "gels.xlsx")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("gels.xlsx is not a text file");
    const recorded = previewBinary as unknown as Recorded;
    fireEvent.drop(zone, { dataTransfer: { files: [file(recorded.request.body.text, "workbook.csv")] } });
    expect(await screen.findByText(recorded.body.refusal!)).toBeInTheDocument();
    expect(screen.queryByRole("table", { name: /The first/ })).toBeNull();
    expect(screen.getByText(/The choices appear here once there is a table|Fix what the table above says first/)).toBeInTheDocument();
  });

  it("refuses a file over the size limit without reading it", async () => {
    const big = { name: "big.csv", size: 600_000, text: vi.fn() } as unknown as File;
    const result = await readFile(big);
    expect(result.ok).toBe(false);
    expect((result as { message: string }).message).toContain("524,288 bytes");
    expect(big.text).not.toHaveBeenCalled();
    expect((readPasted("x".repeat(600_000)) as { message: string }).message).toContain("524,288 bytes");
    expect((readPasted("   ") as { message: string }).message).toContain("no text");
  });
});

describe("reading and changing the mapping", () => {
  it("asks the server again when a column's role changes, and shows its answer", async () => {
    setSessionToken("t0k");
    const { seen } = serve();
    render(withApp("/rates", <RatesScreen />));
    await userEvent.click(await screen.findByRole("button", { name: "Open an example" }));
    const group = await screen.findByLabelText(/Role of column 3, state/);
    await userEvent.selectOptions(group, "none");
    const off = (previewGroupOff as unknown as Recorded).body;
    await waitFor(() => expect(screen.queryByText("Groups")).toBeNull());
    const second = seen.filter((r) => r.url === "/api/rates/preview")[1];
    expect((second.body as { mapping: { roles: Record<string, unknown> } }).mapping.roles.group).toBeNull();
    expect(off.group_column).toBeNull();
    expect(screen.queryByText(/Your table has groups/)).toBeNull();
  });

  it("names the units when a pasted pair of numbers has none, and fits only once they are named", async () => {
    setSessionToken("t0k");
    serve();
    const bare = previewNoUnits as unknown as Recorded;
    render(withApp("/rates", <RatesScreen />));
    await screen.findByText("Drop a CSV, TSV or text file here");
    fireEvent.paste(document.body, { clipboardData: { getData: () => bare.request.body.text } });
    expect(await screen.findByText(/Stops the fit/)).toBeInTheDocument();
    expect(screen.getAllByText(/has no unit/).length).toBeGreaterThan(0);
    expect(screen.queryByRole("button", { name: "Fit my data" })).toBeNull();
    const named = (previewNoUnitsNamed as unknown as Recorded).request.body.mapping as { units: Record<string, string> };
    expect((previewNoUnitsSubstrate as unknown as Recorded).body.ready).toBe(false);
    const sub = screen.getByLabelText("Substrate unit");
    await userEvent.type(sub, `${named.units.substrate}{Enter}`);
    const rate = screen.getByLabelText("Rate unit");
    await userEvent.type(rate, `${named.units.rate}{Enter}`);
    await waitFor(() => expect(screen.getByRole("button", { name: "Fit my data" })).toBeEnabled());
  });

  it("sets a column's role, taking it from whatever held it", () => {
    const mapping = (previewPuromycin as unknown as Recorded).body.mapping;
    expect(roleOf(mapping, 0)).toBe("substrate");
    expect(roleOf(mapping, 2)).toBe("group");
    const swapped = withRole(mapping, 2, "sigma");
    expect(roleOf(swapped, 2)).toBe("sigma");
    expect((swapped.roles as { group: unknown }).group).toBeNull();
    const wide = withRole(withRole(mapping, 1, "rate-replicate"), 2, "rate-replicate");
    expect((wide.roles as { rates: number[]; rate: unknown }).rates).toEqual([1, 2]);
    expect((wide.roles as { rate: unknown }).rate).toBeNull();
  });
});

describe("what to fit", () => {
  it("offers only the sources of uncertainty the table has, and says what each costs", () => {
    const options = (previewPuromycin as unknown as Recorded).body.sigma_options!;
    expect(defaultSigma(options)).toBe("replicates");
    expect(sigmaAllowed("column", options)).toMatch(/no standard-deviation column/);
    expect(sigmaAllowed("replicates", options)).toBeNull();
    const withColumn = { ...options, column: true };
    expect(defaultSigma(withColumn)).toBe("column");
    expect(sigmaAllowed("residuals", withColumn)).toMatch(/exactly one source/);
    expect(sigmaAllowed("replicates", { ...options, replicates: false })).toMatch(/more than once/);
    expect(defaultSigma(null)).toBe("");
  });

  it("disables the laws that do not apply and says why", async () => {
    setSessionToken("t0k");
    serve();
    render(withApp("/rates?example=puromycin", <RatesScreen />));
    const select = await screen.findByLabelText("Which law");
    expect(within(select).getByRole("option", { name: /Only Competitive inhibition \(needs an inhibitor column\)/ })).toBeDisabled();
    expect(within(select).getByRole("option", { name: "Only Hill" })).toBeEnabled();
    expect(within(select).getAllByRole("option")).toHaveLength(8);
  });

  it("says the literature comparison is unavailable, and why, when it is", async () => {
    setSessionToken("t0k");
    mockServer((req) => {
      if (req.url === "/api/capabilities") return json(200, { ...capsRates.body, literature: { available: false, reason: "the literature layer is not in this app folder" } });
      if (req.url === "/api/settings") return json(200, { theme: "system", max_concurrent: 2, keep_runs: 200, offline: false });
      if (req.url === "/api/rates/preview") return previewFor(req.body as { text: string });
      return undefined;
    });
    render(withApp("/rates?example=puromycin", <RatesScreen />));
    expect(await screen.findByText(/Comparing with BRENDA is not available now: the literature layer is not in this app folder/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Compare my Km/)).toBeNull();
  });
});

describe("running and the result", () => {
  it("fits the example on Ctrl Enter and draws the figure, the constants and the verdicts from the run", async () => {
    setSessionToken("t0k");
    const fixture = runResiduals as unknown as Captured;
    const { seen } = serveRun(fixture);
    render(withApp("/rates", <RatesScreen />));
    await userEvent.click(await screen.findByRole("button", { name: "Open an example" }));
    await userEvent.click(await screen.findByRole("radio", { name: /From the scatter about the fitted curve/ }));
    await userEvent.keyboard("{Control>}{Enter}{/Control}");
    await waitFor(() => expect(seen.some((r) => r.method === "POST" && r.url === "/api/runs")).toBe(true));
    const post = seen.find((r) => r.method === "POST" && r.url === "/api/runs")!;
    expect(post.body).toEqual({ kind: "rates", request: (fixture.captured as { request: unknown }).request });
    const result = fixture.result as RatesResult;
    // The figure: every measurement is a marker, the legend names the groups, the axes carry the data's names and units.
    const figure = await screen.findByRole("img", { name: /Initial rates and the fitted curve\. 2 series, 23 measurements/ });
    expect(figure.querySelectorAll('[data-role="point"]')).toHaveLength(23);
    expect(figure.querySelectorAll('[data-role="residual"]')).toHaveLength(23);
    expect(figure.querySelectorAll('[data-role="curve"]')).toHaveLength(2);
    expect(figure.querySelectorAll('[data-role="band"]')).toHaveLength(2);
    expect(figure.textContent).toContain("substrate (ppm)");
    expect(figure.textContent).toContain("rate (counts/min/min)");
    expect(figure.textContent).toContain("residual (counts/min/min)");
    for (const s of result.figure.series) expect(figure.textContent).toContain(s.label);
    // The constants: the fitted value of treated Vmax, marked, with its interval and the words that say where it came from.
    const params = await screen.findByRole("table", { name: /The constants of each reported law, fitted from your data/ });
    const vmax = result.parameters.find((p) => p.group === "treated" && p.constant === "Vmax")!;
    expect(within(params).getByRole("button", { name: new RegExp(`^Vmax, ${formatNumber(vmax.estimate!)} .*fitted$`) })).toBeInTheDocument();
    expect(within(params).getAllByText("fitted from your data").length).toBeGreaterThanOrEqual(result.parameters.filter((p) => p.determined).length);
    expect(params.closest(".r-params")).toHaveTextContent("Interval method: 95% profile-likelihood interval (Bates and Watts 1988)");
    // The lack-of-fit sentence, in the engine's words, with its p.
    for (const l of result.lack_of_fit) expect(screen.getAllByText(plain(l.sentence)).length).toBeGreaterThan(0);
    expect(screen.getAllByText(result.lack_of_fit[0].trust).length).toBeGreaterThan(0);
    // The laws compared, with the engine's verdict and no choice made where the data cannot choose.
    const untreated = result.comparison.find((c) => c.group === "untreated")!;
    expect(screen.getAllByText(plain(untreated.verdict[0])).length).toBeGreaterThan(0);
    expect(screen.getByRole("table", { name: "Laws fitted to untreated, with AICc" })).toBeInTheDocument();
    // Groups.
    for (const s of result.groups!.sentences) expect(screen.getAllByText(plain(s)).length).toBeGreaterThan(0);
    // The one sentence on the uncertainty and why it matters.
    expect(screen.getByText(result.sigma.why, { exact: false })).toBeInTheDocument();
  });

  it("shows the engine's real refusal for a table that cannot bound Km, and no number for it", async () => {
    setSessionToken("t0k");
    const fixture = runNever as unknown as Captured;
    serveRun(fixture);
    const run = fixture.run as RunRecord;
    render(withApp(`/rates?run=${run.id}`, <RatesScreen />));
    const result = fixture.result as RatesResult;
    const block = await screen.findByRole("region", { name: "Read before you quote these numbers" });
    const caution = result.cautions.find((c) => c.kind === "undetermined")!;
    expect(within(block).getByText(plain(caution.text))).toBeInTheDocument();
    expect(within(block).getByText(/What to change:/).parentElement).toHaveTextContent(plain(caution.change!));
    expect(caution.change).toContain("the highest is 0.06 ppm");
    expect(result.better).not.toContain(caution.change);
    // Each caution once.
    for (const c of result.cautions) expect(screen.getAllByText(plain(c.text))).toHaveLength(1);
    // The table: no value for Km or Vmax, the engine's one-sided statement instead, and the product the data do determine.
    const params = await screen.findByRole("table", { name: /The constants of each reported law/ });
    const rows = within(params).getAllByRole("row");
    const km = rows.find((r) => r.textContent?.startsWith("Km") || within(r).queryByText("Km"))!;
    expect(within(km).getByText("not determined")).toBeInTheDocument();
    expect(within(km).queryByRole("button")).toBeNull();
    const ratio = result.parameters.find((p) => p.product)!;
    expect(within(params).getByRole("button", { name: new RegExp(`^${ratio.constant.replace("/", "\\/")}, `) })).toBeInTheDocument();
    expect(screen.getByText(/Lack of fit was not tested/)).toBeInTheDocument();
  });

  it("reopens a run with its table, mapping and choices restored", async () => {
    setSessionToken("t0k");
    const fixture = runResiduals as unknown as Captured;
    serveRun(fixture);
    const run = fixture.run as RunRecord;
    render(withApp(`/rates?run=${run.id}`, <RatesScreen />));
    expect(await screen.findByText(/Restored from the run: puromycin\.csv/)).toBeInTheDocument();
    const table = await screen.findByRole("table", { name: /The first 23 of 23 rows/ });
    expect(within(table).getByLabelText(/Role of column 3, state/)).toHaveValue("group");
    expect(await screen.findByRole("radio", { name: /From the scatter about the fitted curve/ })).toBeChecked();
    const state = requestState(run.request);
    expect(state.source?.text).toBe(PUROMYCIN_CSV);
    expect(state.mapping).toEqual((previewPuromycin as unknown as Recorded).body.mapping);
    // A run made from the restored state is the same request.
    expect(ratesRequest(state.source!, (previewPuromycin as unknown as Recorded).body, state.form, state.literature)).toEqual(run.request);
  });

  it("shows a refusal in the command's words, with no result", async () => {
    setSessionToken("t0k");
    const fixture = runRefused as unknown as Captured;
    serveRun(fixture);
    const run = fixture.run as RunRecord;
    render(withApp(`/rates?run=${run.id}`, <RatesScreen />));
    const reason = plain(run.outcome!.reason!);
    expect(await screen.findAllByText(new RegExp(reason.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).not.toHaveLength(0);
    expect(screen.queryByRole("table", { name: /The constants of each reported law/ })).toBeNull();
  });

  it("keeps the report when the literature comparison is declined, and says so under the literature heading", async () => {
    setSessionToken("t0k");
    const fixture = runLiterature as unknown as Captured;
    serveRun(fixture);
    const run = fixture.run as RunRecord;
    render(withApp(`/rates?run=${run.id}`, <RatesScreen />));
    const result = fixture.result as RatesResult;
    const heading = await screen.findByRole("heading", { name: "Against the literature" });
    const section = heading.closest("section")!;
    for (const row of result.literature) expect(within(section).getAllByText(plain(row.sentence)).length).toBeGreaterThan(0);
    expect(await screen.findByRole("table", { name: /The constants of each reported law/ })).toBeInTheDocument();
  });

  it("puts the methods paragraph and the cite line on the page exactly as the run wrote them", async () => {
    setSessionToken("t0k");
    const fixture = runResiduals as unknown as Captured;
    serveRun(fixture);
    const run = fixture.run as RunRecord;
    render(withApp(`/rates?run=${run.id}`, <RatesScreen />));
    const result = fixture.result as RatesResult;
    expect((await screen.findByTestId("methods-text")).textContent).toBe(result.methods.trim());
    expect(screen.getByTestId("cite-line").textContent).toBe(result.cite);
    // The real numbers are in it: the counts of rows and conditions, the interval method, the software.
    expect(result.methods).toContain("23 measurements at 12 distinct conditions");
    expect(result.methods).toContain("profile-likelihood intervals");
    expect(result.methods).toContain(`Caterva ${(result.analysis as { caterva: string }).caterva}`);
  });
});

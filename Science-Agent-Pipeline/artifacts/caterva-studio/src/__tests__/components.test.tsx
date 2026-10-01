import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import csv from "./fixtures/sim-ssa-a0-200-k-0.5-end-10-seed-7.csv?raw";
import createSim from "./fixtures/api/create_sim.json";
import settingsBad from "./fixtures/api/settings_bad.json";
import fixture from "@/__fixtures__/api/contract/michaelis-menten-parameters.json";
import bindNoRows from "@/__fixtures__/api/kinetics/bind-no-rows.json";
import composeRefused from "@/__fixtures__/api/workspace/refused.json";
import type { ApiError, Outcome, SourcedValue } from "@/api/types";
import { intervalData, IntervalBars } from "@/components/charts/IntervalBars";
import { timeCourseRows, TimeCourseChart } from "@/components/charts/TimeCourseChart";
import { Field, fieldError, NumberInput, parseNumber } from "@/components/forms/Field";
import { Segmented } from "@/components/forms/Segmented";
import { renderMarkdown, shellQuote } from "@/components/report/Report";
import { DataTable, sortRows } from "@/components/table/DataTable";
import { outcomeLine } from "@/components/run/RunRow";
import { ErrorState, OutcomeNotice } from "@/components/states/States";
import { Loading } from "@/components/states/Loading";

import { parseCsv } from "./helpers";

const SSA = parseCsv(csv);
const badTheme = settingsBad.body.error as ApiError;
const params = fixture.searched.parameters as SourcedValue[];

describe("states", () => {
  it("draws a refusal as a finding with the command's reason, not as an error", () => {
    const outcome: Outcome = { exit_code: 3, meaning: "refused", summary: "", reason: createSim.body.error.message };
    render(<OutcomeNotice outcome={outcome} />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByText("Refused")).toBeInTheDocument();
    expect(screen.getByText(createSim.body.error.message)).toBeInTheDocument();
  });

  it("draws a negative finding as a result with its verdict", () => {
    const outcome: Outcome = { exit_code: 4, meaning: "negative", summary: "", reason: "every chain has a blocking defect" };
    render(<OutcomeNotice outcome={outcome} />);
    expect(screen.getByText("Negative finding")).toBeInTheDocument();
    expect(screen.getByText("every chain has a blocking defect")).toBeInTheDocument();
  });

  it("says a refusal's first sentence once when the reason repeats the summary (bind, recorded)", () => {
    const outcome = bindNoRows.run.outcome as Outcome;
    const first = outcome.summary;
    const rest = (outcome.reason ?? "").split("\n").slice(1).join("\n");
    render(<OutcomeNotice outcome={outcome} />);
    const notice = screen.getByRole("region", { name: first });
    expect(within(notice).getByRole("heading", { name: first })).toBeInTheDocument();
    expect(notice.textContent?.split(first).length).toBe(2);
    expect(notice).toHaveTextContent(rest);
    expect(outcomeLine(bindNoRows.run as never)).toBe(first);
  });

  it("keeps a paragraph-long summary out of the heading and still prints it once (compose, recorded)", () => {
    const outcome = composeRefused.run.outcome as Outcome;
    render(<OutcomeNotice outcome={outcome} />);
    expect(screen.getByRole("heading", { name: "Refused, and why" })).toBeInTheDocument();
    const reason = document.querySelector(".state-reason");
    expect(reason?.textContent).toBe(outcome.reason);
    expect(reason?.textContent?.split(outcome.summary).length).toBe(2);
  });

  it("shows nothing extra for a produced result", () => {
    const { container } = render(<OutcomeNotice outcome={{ exit_code: 0, meaning: "produced", summary: "ok", reason: null }} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows an error body whole, with the field it names", () => {
    render(<ErrorState error={settingsBad.body.error} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent("That question is not well formed");
    expect(alert).toHaveTextContent(settingsBad.body.error.message);
    expect(alert).toHaveTextContent("field theme");
  });

  it("loads with the mark and a sentence, and a counted stage says its count", () => {
    render(<Loading label="Sampling parameter sets" fraction={0.25} />);
    const bar = screen.getByRole("progressbar", { name: "Sampling parameter sets" });
    expect(bar).toHaveAttribute("aria-valuenow", "25");
    expect(bar.querySelector(".mark-loader")).toHaveAttribute("data-mode", "determinate");
  });
});

describe("forms", () => {
  it("puts the server's message under the field it names, and links them", () => {
    const message = fieldError(badTheme, "theme");
    expect(message).toBe(settingsBad.body.error.message);
    expect(fieldError(badTheme, "max_parallel_runs")).toBeNull();
    render(
      <Field label="Theme" error={message}>
        <NumberInput unit="mM" />
      </Field>,
    );
    const input = screen.getByRole("textbox", { name: "Theme" });
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription(settingsBad.body.error.message);
    expect(input).toHaveValue("");
  });

  it("reads a typed number exactly, or not at all", () => {
    expect(parseNumber("6.0")).toBe(6);
    expect(parseNumber("1e-3")).toBe(0.001);
    expect(parseNumber("−2")).toBe(-2);
    expect(parseNumber("")).toBeNull();
    expect(parseNumber("6 mM")).toBeNull();
  });

  it("moves a segmented control with the arrow keys", async () => {
    let value = "a";
    const { rerender } = render(
      <Segmented label="Mode" value={value} onChange={(v) => (value = v)} options={[{ value: "a", label: "A" }, { value: "b", label: "B" }]} />,
    );
    await userEvent.click(screen.getByRole("radio", { name: "A" }));
    // Radix moves roving focus on the next task and chooses the radio focused
    // while an arrow key is down, so the key is held as a person's would be.
    await userEvent.keyboard("{ArrowRight>}");
    await waitFor(() => expect(value).toBe("b"));
    await userEvent.keyboard("{/ArrowRight}");
    rerender(
      <Segmented label="Mode" value={value} onChange={(v) => (value = v)} options={[{ value: "a", label: "A" }, { value: "b", label: "B" }]} />,
    );
    expect(value).toBe("b");
    expect(screen.getByRole("radio", { name: "B" })).toBeChecked();
  });
});

describe("DataTable", () => {
  const cols = [
    { key: "id", header: "parameter", headerText: "parameter", cell: (v: SourcedValue) => v.id, sortValue: (v: SourcedValue) => v.id ?? null },
    { key: "value", header: "value", headerText: "value", numeric: true, cell: (v: SourcedValue) => String(v.value), sortValue: (v: SourcedValue) => v.value },
  ];

  it("sorts by the data, not the display, with missing values last both ways", () => {
    const withNull = [...params, { ...params[0], id: "none", value: null }];
    const up = sortRows(withNull, cols[1], "asc").map((v) => v.value);
    const down = sortRows(withNull, cols[1], "desc").map((v) => v.value);
    expect(up[up.length - 1]).toBeNull();
    expect(down[down.length - 1]).toBeNull();
    const finite = up.filter((x): x is number => x !== null);
    expect(finite).toEqual([...finite].sort((a, b) => a - b));
  });

  it("says how it is sorted, and sorts from the header", async () => {
    render(<DataTable caption="Parameters" rows={params} columns={cols} rowKey={(v) => v.id!} />);
    const th = screen.getByRole("columnheader", { name: /value/ });
    expect(th).toHaveAttribute("aria-sort", "none");
    await userEvent.click(within(th).getByRole("button", { name: "Sort by value" }));
    expect(th).toHaveAttribute("aria-sort", "ascending");
    await userEvent.click(within(th).getByRole("button", { name: "Sort by value" }));
    expect(th).toHaveAttribute("aria-sort", "descending");
    expect(screen.getByRole("table", { name: "Parameters" })).toBeInTheDocument();
  });
});

describe("charts", () => {
  it("draws the SSA trajectory as given, with its numbers one activation away", async () => {
    const series = { a: SSA.series.a, b: SSA.series.b };
    expect(timeCourseRows(SSA.series.time, series)).toHaveLength(SSA.series.time.length);
    render(
      <TimeCourseChart
        title="A to B, seed 7"
        times={SSA.series.time}
        series={series}
        timeUnit="s"
        unit="molecules"
        step
        width={640}
      />,
    );
    const figure = screen.getByRole("figure", { name: "A to B, seed 7" });
    expect(within(figure).getByRole("img", { name: "A to B, seed 7" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /The numbers as a table/ }));
    const table = screen.getByRole("table", { name: `A to B, seed 7: ${SSA.series.time.length} time points` });
    expect(within(table).getAllByRole("row")).toHaveLength(SSA.series.time.length + 1);
  });

  it("takes intervals from the server and never guesses one", () => {
    const items = params.map((v) => ({ label: v.label ?? v.id ?? "", value: v }));
    const data = intervalData(items);
    for (const d of data) {
      const item = items.find((i) => i.label === d.label)!;
      if (!item.value.interval) expect(d.err).toBeUndefined();
    }
    render(<IntervalBars title="Parameters" items={items} unit="mixed" width={640} />);
    expect(screen.getByRole("figure", { name: "Parameters" })).toBeInTheDocument();
  });
});

describe("reports", () => {
  it("renders the CLI's Markdown with raw HTML shown as text, never run", () => {
    const html = renderMarkdown("# Report\n\n<script>alert(1)</script> [a](javascript:alert(1))");
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
    expect(html).not.toContain('href="javascript:');
  });

  it("quotes a command line the way shlex.quote does", () => {
    expect(shellQuote("Michaelis Menten")).toBe("'Michaelis Menten'");
    expect(shellQuote("2.7.1.1")).toBe("2.7.1.1");
    expect(shellQuote("it's")).toBe(`'it'"'"'s'`);
    expect(shellQuote("")).toBe("''");
  });
});

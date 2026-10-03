/**
 * What the design review found, held in place: engine text that cannot widen
 * a column, an upstream outage that is not a refusal, one layout for every
 * problem, required fields named before a request, a disabled button that
 * says why, a loading state that announces its step and not its counter, and
 * the other small rules the review measured. Where a rule lives in the
 * stylesheet it is checked there, because jsdom applies no CSS.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Outcome, RunKind, RunRecord } from "@/api/types";
import type { RunState } from "@/api/useRun";
import { Field, TextInput } from "@/components/forms/Field";
import { CommandProvider } from "@/components/palette/commands";
import { RunAnnouncer, RunProgress } from "@/components/run/RunPanel";
import { Loading } from "@/components/states/Loading";
import { ErrorState, NetworkState, OutcomeNotice, RefusalState, RunFailedState } from "@/components/states/States";
import { Identified } from "@/components/run/Identified";
import { StatusLine } from "@/components/shell/StatusLine";
import { plural } from "@/lib/copy";
import { describeApiError } from "@/lib/errors";
import { nextPollDelay } from "@/lib/polling";

import { RunForm } from "../screens/kinetics/kit";
import { RunScreen } from "../screens/structure/kit";
import { allCss, css } from "./stylesheet";

const UNIPROT_TIMEOUT =
  "ReadTimeout: HTTPSConnectionPool(host='rest.uniprot.org', port=443): Read timed out. (read timeout=30)";
const UNIPROT_503 =
  "HTTPError: 503 Server Error: Service Unavailable for url: https://rest.uniprot.org/uniprotkb/search?query=ec%3A1.1.1.27%20AND%20organism_id%3A9606&format=json&size=500&fields=accession%2Cgene_names";

const refused = (reason: string, summary = reason.split("\n")[0]): Outcome => ({ exit_code: 3, meaning: "refused", summary, reason });
const outage = (reason: string): Outcome => ({
  exit_code: 3,
  meaning: "network",
  summary: reason.split(":")[0],
  reason,
  network: { host: "rest.uniprot.org", status: reason.includes("503") ? 503 : null, timed_out: reason.includes("Timeout") },
  has_result: false,
});

afterEach(() => {
  vi.useRealTimers();
});

/** The declarations of every rule whose selector list includes `selector` exactly (at any @media depth). */
function rule(source: string, selector: string): string {
  const bare = source.replace(/\/\*[\s\S]*?\*\//g, "");
  const out: string[] = [];
  for (const chunk of bare.split("}")) {
    const open = chunk.lastIndexOf("{");
    if (open < 0) continue;
    const selectors = chunk
      .slice(0, open)
      .split(",")
      .map((x) => x.trim().replace(/^.*[;{]\s*/s, ""));
    if (selectors.includes(selector)) out.push(chunk.slice(open + 1));
  }
  return out.join("\n");
}

describe("D1: engine text never widens a column", () => {
  it("wraps anywhere in every prose container that can receive it", () => {
    for (const selector of [".state-reason", ".state-body", ".k-remedy", ".k-worst-detail", ".report-text", ".run-log", ".field-error", ".net-sentence"]) {
      expect(rule(css, selector), selector).toMatch(/overflow-wrap:\s*anywhere/);
    }
  });

  it("names the host, never the request URL, in a refusal", () => {
    const url = "https://rest.uniprot.org/uniprotkb/search?query=ec%3A1.1.1.27&format=json";
    render(<RefusalState reason={`Refused: could not read ${url}`} />);
    const reason = document.querySelector(".state-reason")!;
    expect(reason.textContent).toContain("UniProt");
    expect(reason.textContent).not.toContain("https://");
    // The raw text is still one disclosure away.
    expect(document.querySelector(".state-raw pre")!.textContent).toContain(url);
  });
});

describe("D2: an outage is not a refusal", () => {
  it.each([UNIPROT_TIMEOUT, UNIPROT_503])("draws %s as UniProt not answering, with Retry and the raw text behind a disclosure", async (raw) => {
    const onRetry = vi.fn();
    render(<OutcomeNotice outcome={outage(raw)} onRetry={onRetry} again="search again" />);
    expect(screen.getByRole("heading", { name: "UniProt did not answer" })).toBeInTheDocument();
    expect(screen.getByText("UniProt did not answer. Check the network, then search again.")).toBeInTheDocument();
    expect(screen.queryByText("Refused")).toBeNull();
    const section = screen.getByRole("region", { name: "UniProt did not answer" });
    expect(within(section).queryByText(/HTTPSConnectionPool|Server Error/, { selector: "p, h2" })).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(section.querySelector(".state-raw pre")!.textContent).toBe(raw);
  });

  it("uses the same layout for a refusal, a failure and an outage", () => {
    const shapes = [
      <RefusalState key="r" reason="Refused: no structure" />,
      <ErrorState key="e" error={{ code: "malformed", message: "bad", field: "ec" }} />,
      <NetworkState key="n" failure={{ host: "rest.uniprot.org", status: null, timed_out: true }} />,
      <RunFailedState key="f" error={{ type: "KeyError", message: "x" }} />,
    ];
    for (const shape of shapes) {
      const { container, unmount } = render(shape);
      const section = container.querySelector("section.state")!;
      expect(section.querySelector(".state-kicker"), "a kicker").not.toBeNull();
      expect(section.querySelector("h2.state-title"), "a heading").not.toBeNull();
      unmount();
    }
  });

  it("classifies a 503 'could not reach' body as an outage too", () => {
    render(<ErrorState error={{ code: "unavailable", message: "could not reach the PDB (ConnectionError: HTTPSConnectionPool(host='files.rcsb.org', port=443): Max retries exceeded)" }} />);
    expect(screen.getByRole("heading", { name: "The RCSB files did not answer" })).toBeInTheDocument();
  });

  it("never puts exception text in an accessible name or a toast message", () => {
    const described = describeApiError({ code: "unavailable", message: UNIPROT_503 });
    expect(described.message).toBe("UniProt did not answer. Check the network, then try again.");
    expect(described.raw).toBe(UNIPROT_503);
    render(
      <QueryClientProvider client={new QueryClient()}>
        <StatusLine
          health={undefined}
          healthError={null}
          capabilitiesError={null}
          capabilities={
            {
              literature: { available: true, reason: null },
              gromacs: { found: false, path: null, version: null, reason: "x" },
              data_dir: { path: "/w", writable: true, runs: 1, reason: null },
              dev_origin: null,
              network: {
                checked: true,
                reachable: false,
                source: "use",
                checked_at: "2026-10-03T10:00:00Z",
                hosts: { "rest.uniprot.org": false },
                reason: `rest.uniprot.org could not be reached: ${UNIPROT_TIMEOUT}`,
              },
            } as never
          }
        />
      </QueryClientProvider>,
    );
    const trigger = screen.getByRole("button", { name: /^network unreachable/ });
    expect(trigger.getAttribute("aria-label")).toContain("UniProt did not answer");
    expect(trigger.getAttribute("aria-label")).not.toMatch(/ReadTimeout|HTTPSConnectionPool/);
  });
});

describe("D3: a required field is named before any request", () => {
  function Form({ onSubmit }: { onSubmit: () => void }) {
    return (
      <RunForm id="test.submit" label="Look up" onSubmit={onSubmit} running={false}>
        <Field label="Organism" required>
          <TextInput />
        </Field>
      </RunForm>
    );
  }
  const mount = (onSubmit: () => void) =>
    render(
      <CommandProvider>
        <Form onSubmit={onSubmit} />
      </CommandProvider>,
    );

  it("marks the control aria-required, and refuses to send it empty with an inline message", async () => {
    const onSubmit = vi.fn();
    mount(onSubmit);
    const input = screen.getByRole("textbox", { name: /Organism/ });
    expect(input).toHaveAttribute("aria-required", "true");
    expect(input).not.toHaveAttribute("aria-invalid");
    await userEvent.click(screen.getByRole("button", { name: "Look up" }));
    expect(onSubmit).not.toHaveBeenCalled();
    expect(await screen.findByText("Organism is required: fill it in to continue.")).toBeInTheDocument();
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveFocus();
    expect(input.getAttribute("aria-describedby")).toBeTruthy();
  });

  it("clears the message when the field is filled, and then sends", async () => {
    const onSubmit = vi.fn();
    mount(onSubmit);
    await userEvent.click(screen.getByRole("button", { name: "Look up" }));
    await userEvent.type(screen.getByRole("textbox", { name: /Organism/ }), "human");
    expect(screen.queryByText(/is required/)).toBeNull();
    await userEvent.click(screen.getByRole("button", { name: "Look up" }));
    expect(onSubmit).toHaveBeenCalledOnce();
  });
});

describe("D7: the primary action is reachable and the live region is one line", () => {
  it("pins the action bar to the screen's own scroller, which the panel must not clip", () => {
    expect(rule(css, ".split-pane")).toMatch(/overflow:\s*visible\s*!important/);
    expect(rule(css, ".k-form .form-bar")).toMatch(/position:\s*sticky/);
    expect(rule(css, ".k-form .form-bar")).toMatch(/bottom:\s*0/);
  });

  it("has no live region round the whole result", () => {
    const { container } = render(
      <CommandProvider>
        <RunForm id="x" label="Compose" onSubmit={() => {}} running={false}>
          <span />
        </RunForm>
      </CommandProvider>,
    );
    expect(container.querySelector("[aria-live]")).toBeNull();
  });

  function runState(over: Partial<RunState<"compose">>): RunState<"compose"> {
    return {
      run: null,
      status: "running",
      stage: null,
      stages: [],
      log: [],
      outcome: null,
      result: null,
      requestError: null,
      runError: null,
      submitting: false,
      cancelling: false,
      settled: false,
      ...over,
    };
  }

  it("announces one sentence when a run finishes, and moves focus to the result's heading", async () => {
    function Harness({ state }: { state: RunState<"compose"> }) {
      const root = { current: null as HTMLDivElement | null };
      return (
        <div ref={(el) => void (root.current = el)}>
          <RunAnnouncer state={state} root={root} />
          {state.settled ? <h2 id="result-heading">The verdict</h2> : <p>working</p>}
        </div>
      );
    }
    const { rerender } = render(<Harness state={runState({ status: "running" })} />);
    expect(screen.getByRole("status")).toHaveTextContent("");
    rerender(<Harness state={runState({ status: "done", settled: true, outcome: { exit_code: 0, meaning: "produced", summary: "ok", reason: null } })} />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent("Finished. The result is below."));
    expect(screen.getByRole("heading", { name: "The verdict" })).toHaveFocus();
  });

  it("does not move focus for a run that was only reopened", () => {
    function Harness({ state }: { state: RunState<"compose"> }) {
      const root = { current: null as HTMLDivElement | null };
      return (
        <div ref={(el) => void (root.current = el)}>
          <RunAnnouncer state={state} root={root} />
          <h2>The verdict</h2>
        </div>
      );
    }
    render(<Harness state={runState({ status: "done", settled: true, outcome: { exit_code: 0, meaning: "produced", summary: "ok", reason: null } })} />);
    expect(screen.getByRole("heading", { name: "The verdict" })).not.toHaveFocus();
    expect(screen.getByRole("status")).toHaveTextContent("");
  });

  it("says an outage in the finish sentence too", async () => {
    function Harness({ state }: { state: RunState<"compose"> }) {
      const root = { current: null as HTMLDivElement | null };
      return (
        <div ref={(el) => void (root.current = el)}>
          <RunAnnouncer state={state} root={root} />
          <h2>x</h2>
        </div>
      );
    }
    const { rerender } = render(<Harness state={runState({ status: "running" })} />);
    rerender(<Harness state={runState({ status: "done", settled: true, outcome: outage(UNIPROT_TIMEOUT) })} />);
    await waitFor(() => expect(screen.getByRole("status")).toHaveTextContent(/a database did not answer/));
  });
});

describe("D8: loading announces its step, not its counter", () => {
  it("makes only the sentence a live region", () => {
    const { container } = render(<Loading label="Searching BRENDA for EC 2.7.1.1" detail="18 s elapsed" />);
    const live = container.querySelectorAll("[role='status'], [aria-live]");
    expect(live).toHaveLength(1);
    expect(live[0]).toHaveTextContent("Searching BRENDA for EC 2.7.1.1");
    expect(container.querySelector(".loading-sub")!.closest("[role='status'], [aria-live]")).toBeNull();
  });

  it("keeps the percentage out of the live region as well", () => {
    render(<Loading label="Writing" fraction={0.4} detail="3 s elapsed" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "40");
    expect(screen.getByRole("status")).toHaveTextContent(/^Writing$/);
  });

  it("names a constant in words in the progress text", () => {
    const state: RunState<"compose"> = {
      run: null,
      status: "running",
      stage: { stage: "search", label: "Looking up reaction_kcat in BRENDA's kcat table for EC 1.1.1.27", fraction: null },
      stages: [
        { stage: "search", label: "Looking up reaction_Km in BRENDA's km table for EC 1.1.1.27", fraction: null, at: "t" },
        { stage: "search", label: "Looking up reaction_kcat in BRENDA's kcat table for EC 1.1.1.27", fraction: null, at: "t" },
      ],
      log: [],
      outcome: null,
      result: null,
      requestError: null,
      runError: null,
      submitting: false,
      cancelling: false,
      settled: false,
    };
    render(<RunProgress state={state} />);
    expect(screen.getAllByText("Looking up kcat of the reaction in BRENDA's kcat table for EC 1.1.1.27").length).toBeGreaterThan(0);
    expect(screen.queryByText(/reaction_kcat/)).toBeNull();
  });
});

describe("D12: a disabled primary action says why", () => {
  it("RunScreen points the button at its reason", () => {
    const run = { status: "idle", submitting: false } as never;
    render(
      <CommandProvider>
        <RunScreen
          kind={"structure" as RunKind}
          id="structure"
          form={<span />}
          action="Search"
          canSubmit={false}
          blockedReason="Choose an enzyme first."
          onSubmit={() => {}}
          run={run}
          idle={null}
          formLabel="Search the PDB"
        >
          {() => null}
        </RunScreen>
      </CommandProvider>,
    );
    const button = screen.getByRole("button", { name: "Search" });
    expect(button).toHaveAttribute("aria-disabled", "true");
    expect(button).toHaveAccessibleDescription("Choose an enzyme first.");
  });

  it("RunForm gives its reason while it is blocked or running", () => {
    const { rerender } = render(
      <CommandProvider>
        <RunForm id="a" label="Compose" onSubmit={() => {}} running={false} disabled disabledReason="Write a mechanism first.">
          <span />
        </RunForm>
      </CommandProvider>,
    );
    expect(screen.getByRole("button", { name: "Compose" })).toHaveAccessibleDescription("Write a mechanism first.");
    rerender(
      <CommandProvider>
        <RunForm id="a" label="Compose" onSubmit={() => {}} running>
          <span />
        </RunForm>
      </CommandProvider>,
    );
    expect(screen.getByRole("button", { name: "Compose" })).toHaveAccessibleDescription("A run is in progress.");
  });
});

describe("D11, D14: no nested card, no hero numbers", () => {
  it("draws what is worst about a verdict as a ruled passage, not a bordered box", () => {
    const body = rule(allCss["kinetics.css"], ".k-worst");
    expect(body).not.toMatch(/border:\s*1px/);
    expect(body).toMatch(/border-left:\s*3px solid/);
    expect(body).toMatch(/background:\s*none/);
  });

  it("sets the end-of-run counts as a compact list, not at headline size", () => {
    const k = allCss["kinetics.css"];
    expect(rule(k, ".k-finals dd")).not.toMatch(/--text-lg|--text-xl|--text-2xl/);
    expect(rule(k, ".k-finals")).toMatch(/display:\s*grid/);
  });
});

describe("D17: identifiers in tabular figures", () => {
  it("sets an EC number, a PDB entry and a seed in DM Mono", () => {
    const { container } = render(<Identified text="Km of EC 1.1.1.27, PDB 1AKI, seed 988813188 in human" />);
    const mono = [...container.querySelectorAll(".font-mono")].map((n) => n.textContent);
    expect(mono).toEqual(["EC 1.1.1.27", "PDB 1AKI", "seed 988813188"]);
    expect(container.textContent).toBe("Km of EC 1.1.1.27, PDB 1AKI, seed 988813188 in human");
    expect(rule(css, ".font-mono")).toMatch(/tabular-nums/);
  });
});

describe("D18, D19, D20: sizes and widths", () => {
  it("makes the small theme radios and the licence links at least 24 px", () => {
    const small = rule(css, '.segmented[data-size="sm"] .segmented-item');
    expect(small).toMatch(/min-height:\s*1\.5rem/);
    expect(small).toMatch(/min-width:\s*1\.75rem/);
    expect(rule(css, ".licence-list a")).toMatch(/min-height:\s*1\.5rem/);
  });

  it("sizes a segmented control to its content in a form", () => {
    expect(rule(css, ".field > .segmented")).toMatch(/width:\s*fit-content/);
  });

  it("centres the screen at wide widths", () => {
    expect(rule(css, ".screen")).toMatch(/margin-inline:\s*auto/);
  });
});

describe("D21: polling backs off", () => {
  it("asks nothing from a hidden tab, a quarter as often when idle, and less after failures", () => {
    const base = { base: 30_000, hidden: false, idleForMs: 0, failures: 0 };
    expect(nextPollDelay(base)).toBe(30_000);
    expect(nextPollDelay({ ...base, hidden: true })).toBe(false);
    expect(nextPollDelay({ ...base, idleForMs: 3 * 60_000 })).toBe(120_000);
    expect(nextPollDelay({ ...base, failures: 2 })).toBe(120_000);
    expect(nextPollDelay({ ...base, failures: 9 })).toBe(240_000);
  });
});

describe("D22: plurals and motion", () => {
  it("writes the count's own plural", () => {
    expect(plural(1, "run")).toBe("1 run");
    expect(plural(8, "run")).toBe("8 runs");
  });

  it("stills the mark and cuts every transition under prefers-reduced-motion", () => {
    const block = /@media \(prefers-reduced-motion: reduce\) \{([\s\S]*?)\n\}/.exec(css)?.[1] ?? "";
    expect(block).toMatch(/animation-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/transition-duration:\s*0\.01ms\s*!important/);
    expect(block).toMatch(/\.mark-loader \.ml-dot[\s\S]*animation:\s*none\s*!important/);
    expect(block).toMatch(/scroll-behavior:\s*auto\s*!important/);
  });

  it("leaves no animation outside that cut: every keyframe is for a selector the block stills or the universal rule shortens", () => {
    // The universal rule shortens every animation to an instant; the named ones stop outright.
    const names = [...css.matchAll(/@keyframes ([\w-]+)/g)].map((m) => m[1]);
    expect(names.length).toBeGreaterThan(0);
    expect(css).toMatch(/\*,\s*\*::before,\s*\*::after\s*\{[^}]*animation-duration:\s*0\.01ms/);
  });
});


// ---------------------------------------------------------------- D5, over the recorded runs

import composeLdh from "@/__fixtures__/api/kinetics/compose-ldh-gossypol.json";
import composeAnalyses from "@/__fixtures__/api/kinetics/compose-binding-analyses.json";
import constantsHexokinase from "@/__fixtures__/api/kinetics/constants-hexokinase.json";
import constantsRefused from "@/__fixtures__/api/kinetics/constants-refused.json";
import bindNoRows from "@/__fixtures__/api/kinetics/bind-no-rows.json";
import composeShapes from "@/__fixtures__/api/kinetics/compose-shapes.json";
import structureLdh from "@/__fixtures__/api/structure/structure-ldh-several-proteins.json";
import type { ComposeResult, ConstantsResult } from "@/api/types";
import { ComposeResultView } from "../screens/kinetics/ComposeResult";
import { ConstantsResultView } from "../screens/kinetics/ConstantsResult";

type Captured = { run: unknown; result: unknown };

/** The text a person reads: the whole page minus code, preformatted output and the terminal slab. */
function prose(): string {
  const clone = document.body.cloneNode(true) as HTMLElement;
  clone.querySelectorAll("pre, code, .slab, .state-raw, kbd").forEach((n) => n.remove());
  return clone.textContent ?? "";
}

function expectNoTerminalLeaks(text: string) {
  expect(text).not.toMatch(/(^|[\s(])--[a-z]/);
  expect(text).not.toContain("\u2014");
  expect(text).not.toMatch(/cite\.py/);
  expect(text.match(/.{0,40}\w\(s\).{0,20}/)?.[0] ?? "").toBe("");
}

describe("D5: no flag, script name or dash from the terminal reaches a rendered screen", () => {
  it("in a compose result (verdict, ledger, concerns, analyses)", () => {
    for (const fixture of [composeLdh, composeAnalyses] as unknown as Captured[]) {
      const { unmount } = render(
        <ComposeResultView result={fixture.result as ComposeResult} run={fixture.run as RunRecord} />,
      );
      expectNoTerminalLeaks(prose());
      unmount();
    }
  });

  it("in a constants result, including the cite.py-era refusals", () => {
    render(<ConstantsResultView result={(constantsHexokinase as unknown as Captured).result as ConstantsResult} request={{}} />);
    expectNoTerminalLeaks(prose());
  });

  it("in every recorded refusal", () => {
    for (const fixture of [constantsRefused, bindNoRows] as unknown as Captured[]) {
      const { unmount } = render(<OutcomeNotice outcome={(fixture.run as RunRecord).outcome} />);
      expectNoTerminalLeaks(prose());
      unmount();
    }
  });

  it("in a failed run's panel", () => {
    void composeShapes;
    void structureLdh;
    render(
      <RunFailedState error={{ type: "KeyError", message: "'reaction_kcat' is not a parameter; pass --sweep with a known one" }} />,
    );
    expectNoTerminalLeaks(prose());
  });
});

describe("D5: the constants refusal names the field that is missing", () => {
  it("renders the recorded refusal without its long dash", () => {
    const outcome = (constantsRefused as unknown as Captured).run as RunRecord;
    render(<OutcomeNotice outcome={outcome.outcome} />);
    expect(prose()).not.toContain("\u2014");
    expect(prose()).toContain("a name is looked up in UniProt");
  });
});

// ------------------------------------------------------------------- D6

describe("D6: the compounds with a Ki are a filtered set of buttons that fill the field", () => {
  const compounds = Array.from({ length: 32 }, (_, i) => `2-compound-${String(i).padStart(2, "0")}-(4-methylphenyl)sulfonyl-aminobenzoic acid`);
  const reason = `No Ki for 'oxamate' with EC 1.1.1.27 in Homo sapiens.\nCompounds that do have one: ${compounds.join("; ")}`;

  it("says one short sentence, caps the list, and fills Inhibitor on a click", async () => {
    const onChoose = vi.fn();
    render(<OutcomeNotice outcome={refused(reason)} onChooseCompound={onChoose} />);
    expect(screen.getByRole("heading", { name: "No Ki for 'oxamate' with EC 1.1.1.27 in Homo sapiens." })).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Compounds with a measured Ki" });
    expect(within(list).getAllByRole("button")).toHaveLength(12);
    expect(screen.getByText("Showing 12 of 32 compounds; type to narrow the list.")).toBeInTheDocument();
    const reasonText = document.querySelector(".state-reason")!.textContent!;
    expect(reasonText.length).toBeLessThan(160);
    await userEvent.click(within(list).getByRole("button", { name: compounds[3] }));
    expect(onChoose).toHaveBeenCalledWith(compounds[3]);
  });

  it("filters the whole list, not only what is shown", async () => {
    render(<OutcomeNotice outcome={refused(reason)} onChooseCompound={() => {}} />);
    await userEvent.type(screen.getByRole("searchbox", { name: "Filter the 32 compounds" }), "compound-31");
    const list = screen.getByRole("list", { name: "Compounds with a measured Ki" });
    expect(within(list).getAllByRole("button")).toHaveLength(1);
    await userEvent.clear(screen.getByRole("searchbox"));
    await userEvent.type(screen.getByRole("searchbox"), "zzz");
    expect(screen.getByText("No compound matches that.")).toBeInTheDocument();
  });

  it("keeps the engine's whole sentence behind a disclosure", () => {
    render(<OutcomeNotice outcome={refused(reason)} onChooseCompound={() => {}} />);
    expect(document.querySelector(".state-raw pre")!.textContent).toBe(reason);
  });
});

// ------------------------------------------------------------------ D10

import { NumbersLedger } from "../screens/kinetics/ComposeResult";
import { PLACEHOLDER_SHARED } from "@/lib/copy";

describe("D10: the placeholder boilerplate is said once", () => {
  const boilerplate = (where: string, table: string | null) =>
    `ILLUSTRATIVE PLACEHOLDER: Caterva's motif library value for ${where}. No publication supplies this number and nobody measured it. It is here so the structure can be checked, dimensioned and simulated${
      table ? `; the measurement that would replace it is in the ${table} table` : "; no database table serves it, so it is resolvable only from a paper"
    }.`;
  const value = (id: string, where: string, table: string | null) => ({
    value: 1,
    unit: "1/s",
    id,
    label: id,
    provenance: { kind: "placeholder", reason: boilerplate(where, table), table },
  });

  it("states the shared sentence above the table and keeps only the per-row reason in each cell", () => {
    const result = {
      model: {
        concentration_unit: "mM",
        parameters: [value("a_ks", "hill_repression.ks", null), value("b_kcat", "competitive_inhibition.kcat", "kcat")],
        species: [],
      },
    } as unknown as ComposeResult;
    render(<NumbersLedger result={result} />);
    expect(screen.getAllByText(PLACEHOLDER_SHARED)).toHaveLength(1);
    const table = screen.getByRole("table");
    expect(table.textContent).not.toMatch(/ILLUSTRATIVE|PLACEHOLDER/);
    expect(within(table).getByText("Library value for the ks of hill repression. No database table serves it; only a paper can supply it.")).toBeInTheDocument();
    expect(within(table).getByText("Library value for the kcat of competitive inhibition. A measurement would be in BRENDA's kcat table.")).toBeInTheDocument();
    expect(rule(allCss["kinetics.css"], ".k-origin-reason") + rule(css, ".k-origin-reason")).toMatch(/max-width:\s*68ch/);
  });
});

// ------------------------------------------------------------------ D15

describe("D15: the constants table hides columns that are empty for every row", () => {
  it("drops Conditions and The row says when no row has them, and says 'rows' with the count", () => {
    const base = (constantsHexokinase as unknown as Captured).result as ConstantsResult;
    const stripped = {
      ...base,
      constants: base.constants.map((row) => ({
        ...row,
        value: row.value && {
          ...row.value,
          provenance: { ...row.value.provenance, commentary: null, conditions: { ph: null, temperature_c: null, buffer: null, unreported: [] } },
        },
        alternatives: row.alternatives.map((a) => ({
          ...a,
          provenance: { ...a.provenance, commentary: null, conditions: { ph: null, temperature_c: null, buffer: null, unreported: [] } },
        })),
      })),
    } as ConstantsResult;
    render(<ConstantsResultView result={stripped} request={{}} />);
    expect(screen.queryByRole("columnheader", { name: "Conditions" })).toBeNull();
    expect(screen.queryByRole("columnheader", { name: "The row says" })).toBeNull();
    expect(screen.getAllByRole("columnheader", { name: "Value" }).length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toMatch(/row\(s\)|brenda_exact/);
  });

  it("keeps a column that has a value in any row", () => {
    const base = (constantsHexokinase as unknown as Captured).result as ConstantsResult;
    render(<ConstantsResultView result={base} request={{}} />);
    const withCommentary = base.constants.some((c) => [c.value, ...c.alternatives].some((v) => v?.provenance.commentary));
    expect(screen.queryAllByRole("columnheader", { name: "The row says" }).length > 0).toBe(withCommentary);
  });

  it("translates the resolver's source token into words", () => {
    render(<ConstantsResultView result={(constantsHexokinase as unknown as Captured).result as ConstantsResult} request={{}} />);
    expect(document.body.textContent).toContain("found in BRENDA, in the organism asked for");
  });
});

// ------------------------------------------------------------------ D21, D19

import { renderHook } from "@testing-library/react";
import type { ReactNode } from "react";

import App from "@/App";
import { resetRunStreamsForTests } from "@/api/runs";
import { useRun } from "@/api/useRun";
import { JobsProvider } from "@/lib/jobs";

import capabilities from "./fixtures/api/capabilities.json";
import health from "./fixtures/api/health.json";
import runsEmpty from "./fixtures/api/runs_empty.json";
import settings from "./fixtures/api/settings.json";
import { frame, json, mockServer, setSessionToken, sseResponse } from "./helpers";

const ID = "20261003-100000-structure-0badc0de";
const AT = "2026-10-03T10:00:00.000Z";

function structureRecord(outcome: Outcome): RunRecord {
  return {
    schema: "caterva.studio.run/1",
    id: ID,
    kind: "structure",
    title: "EC 1.1.1.27 in human",
    status: "done",
    created_at: AT,
    started_at: AT,
    finished_at: AT,
    caterva_version: "0.4.0",
    cli: ["caterva", "structure"],
    request: { subject: "1.1.1.27" },
    outcome,
    error: null,
    artifacts: [],
    progress: null,
  } as RunRecord;
}

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={client}>
      <JobsProvider>{children}</JobsProvider>
    </QueryClientProvider>
  );
}

describe("D21: a run that has no result is not asked for one", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    resetRunStreamsForTests();
  });

  function follow(outcome: Outcome) {
    setSessionToken("token");
    const done = { run_id: ID, at: AT, seq: 1 };
    const { seen } = mockServer((req) => {
      if (req.url === `/api/runs/${ID}/events`) {
        return sseResponse([frame("status", 1, { ...done, status: "done", outcome }), frame("end", 2, { ...done, status: "done" })]);
      }
      if (req.url === `/api/runs/${ID}/result`) return json(404, { error: { code: "not_found", message: "the run finished without a result" } });
      if (req.url === `/api/runs/${ID}`) return json(200, structureRecord(outcome));
      return undefined;
    });
    const hook = renderHook(() => useRun("structure", ID), { wrapper });
    return { seen, hook };
  }

  it("skips /result when the outcome says has_result is false", async () => {
    const { seen, hook } = follow(outage(UNIPROT_503));
    await waitFor(() => expect(hook.result.current.settled).toBe(true));
    expect(hook.result.current.outcome?.meaning).toBe("network");
    expect(seen.some((r) => r.url.endsWith("/result"))).toBe(false);
  });

  it("still asks for records written before the server said so, and treats the 404 as no result", async () => {
    const legacy: Outcome = { exit_code: 3, meaning: "refused", summary: "Refused", reason: "Refused: nothing" };
    const { seen, hook } = follow(legacy);
    await waitFor(() => expect(hook.result.current.settled).toBe(true));
    expect(seen.some((r) => r.url.endsWith("/result"))).toBe(true);
    expect(hook.result.current.result).toBeNull();
    expect(hook.result.current.requestError).toBeNull();
  });
});

describe("the shell's small repairs", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    window.history.replaceState(null, "", "/");
  });

  function serve() {
    setSessionToken("token");
    return mockServer((req) => {
      if (req.url === "/api/health") return health;
      if (req.url === "/api/capabilities") return capabilities;
      if (req.url === "/api/settings") return settings;
      if (req.url.startsWith("/api/runs")) return runsEmpty;
      return undefined;
    });
  }

  it("D21: the skip link moves focus and leaves the address alone", async () => {
    serve();
    render(<App />);
    const link = await screen.findByRole("link", { name: "Skip to the screen" });
    await userEvent.click(link);
    expect(window.location.hash).toBe("");
    expect(document.getElementById("main")).toHaveFocus();
  });

  it("D19: Check the network sits in the Network section of About, not in the page header", async () => {
    serve();
    window.history.replaceState(null, "", "/about");
    render(<App />);
    const section = await screen.findByRole("region", { name: "Network" });
    expect(within(section).getByRole("button", { name: "Check the network" })).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Check the network" })).toHaveLength(1);
  });

  it("D19: the Settings theme control does not stretch the column", async () => {
    serve();
    window.history.replaceState(null, "", "/settings");
    render(<App />);
    const appearance = await screen.findByRole("region", { name: "Appearance" });
    const group = within(appearance).getByRole("radiogroup", { name: "Theme" });
    expect(group.parentElement!.classList.contains("field")).toBe(true);
    expect(rule(css, ".field > .segmented")).toMatch(/justify-self:\s*start/);
  });

  it("D12: Settings says why Save is off", async () => {
    serve();
    window.history.replaceState(null, "", "/settings");
    render(<App />);
    const save = await screen.findByRole("button", { name: "Save" });
    expect(save).toBeDisabled();
    expect(save).toHaveAccessibleDescription("Change a setting first; there is nothing to save yet.");
  });
});

/**
 * The result at a glance, checked against the engine.
 *
 * The reference case is human glucokinase (GCK) with glucose. Both fixtures
 * are what engine 0.7.1 answered through the studio's dispatch layer against
 * the recorded BRENDA page (src/__fixtures__/api/enzymes/README.md). Every
 * expectation below is read from the fixture, not typed in, except where a
 * test says what it pins: the reference case's own numbers, so that a change
 * in either the engine's answer or the page's wording is noticed.
 */
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import composeGck from "@/__fixtures__/api/enzymes/compose-gck-engine-0.7.1.json";
import composeHk from "@/__fixtures__/api/enzymes/compose-hexokinase-engine-0.7.1.json";
import composeOld from "@/__fixtures__/api/enzymes/compose-ldh-human-pyruvate.json";
import type { ComposeResult, RunRecord, SourcedValue } from "@/api/types";
import { formatValue } from "@/lib/format";

import { ComposeResultView } from "./ComposeResult";
import { conditionsLine, constantName, halfSaturationOf, startsAreDefaults } from "./ResultMap";

type Captured = { run: unknown; result: unknown };
const of = (c: unknown) => ({ result: (c as Captured).result as ComposeResult, run: (c as Captured).run as RunRecord });
const param = (r: ComposeResult, id: string) => r.model.parameters.find((p) => p.id === id) as SourcedValue;

describe.each([
  ["with --isoform GCK", composeGck],
  ["with no isoform given", composeHk],
])("human hexokinase with glucose, %s", (_name, fixture) => {
  const { result, run } = of(fixture);
  const km = param(result, "reaction_Km");
  const kcat = param(result, "reaction_kcat");

  it("is the reference case the engine answered: 6.3 mM, Hill 1.8, 40.1 1/s, BRENDA ref 739603, pH 7.6, 25 C", () => {
    expect(km.value).toBe(6.3);
    expect(km.unit).toBe("mM");
    expect(kcat.value).toBe(40.1);
    expect(kcat.unit).toBe("1/s");
    for (const p of [km, kcat]) {
      expect(p.provenance.citation?.text).toBe("BRENDA ref 739603");
      expect(p.provenance.conditions?.ph).toBe(7.6);
      expect(p.provenance.conditions?.temperature_c).toBe(25);
      expect(p.provenance.organism).toBe("Homo sapiens");
    }
    expect(km.provenance.commentary).toContain("K0.5 value, Hill coefficient 1.8");
  });

  it("names the half-saturation constant K0.5, never Km, and keeps its Hill coefficient", () => {
    expect(halfSaturationOf(km)).toEqual({ hill: 1.8 });
    expect(constantName(km)).toBe("K0.5");
    expect(halfSaturationOf(kcat)).toBeNull();
    render(<ComposeResultView result={result} run={run} />);
    const card = screen.getByTestId("map-constant-reaction_Km");
    expect(card).toHaveTextContent("K0.5");
    expect(within(card).getByTestId("hill")).toHaveTextContent("Hill coefficient 1.8");
    expect(card).toHaveTextContent(formatValue(km));
    expect(card).toHaveTextContent(km.unit);
    // No label on the map or the line items reads "Km" alone for this constant.
    const lines = screen.getByTestId("result-lines");
    const row = within(lines).getByText("reaction_Km").closest("tr") as HTMLElement;
    expect(within(row).getByRole("rowheader")).toHaveTextContent("K0.5");
    expect(within(row).getByRole("rowheader")).toHaveTextContent("a K0.5 (Hill 1.8), not a Km");
    expect(screen.getByTestId("ledger-k05")).toHaveTextContent("a K0.5 (Hill coefficient 1.8), not a Km");
    // What a screen reader hears for the number, everywhere it is drawn: K0.5, not Km.
    const spoken = screen.getAllByRole("button", { name: new RegExp(`^K0\\.5, ${formatValue(km)} mM, measured, cited$`) });
    expect(spoken).toHaveLength(3);
    expect(screen.queryByRole("button", { name: /^Km, / })).toBeNull();
  });

  it("shows kcat, both units, the citation, the conditions and the range exactly as the engine sent them", () => {
    render(<ComposeResultView result={result} run={run} />);
    const kcatCard = screen.getByTestId("map-constant-reaction_kcat");
    expect(kcatCard).toHaveTextContent("kcat");
    expect(kcatCard).toHaveTextContent(formatValue(kcat));
    expect(kcatCard).toHaveTextContent(kcat.unit);
    const lines = screen.getByTestId("result-lines");
    for (const p of [km, kcat]) {
      const row = within(lines).getByText(p.id as string).closest("tr") as HTMLElement;
      expect(row).toHaveTextContent(formatValue(p));
      expect(row).toHaveTextContent(p.unit);
      expect(row).toHaveTextContent(p.provenance.citation?.text as string);
      expect(row).toHaveTextContent(conditionsLine(p) as string);
      expect(conditionsLine(p)).toBe("pH 7.6 · 25 °C");
      const sp = p.provenance.spread;
      expect(row).toHaveTextContent(`${sp?.low} to ${sp?.high} ${sp?.unit}`);
      expect(row).toHaveTextContent(`${sp?.n_values} values, ${sp?.references.length} sources`);
    }
    expect(screen.getByTestId("lines-total")).toHaveTextContent("2 / 2");
    const map = screen.getByTestId("result-map");
    expect(map).toHaveTextContent("Homo sapiens");
    expect(map).toHaveTextContent("glucose");
    expect(map).toHaveTextContent("pH 7.6 · 25 °C");
    expect(screen.getByTestId("result-map-enzyme")).toHaveTextContent("EC 2.7.1.1");
  });

  it("leaves the starting amounts unset and draws the time course as a shape, with no axis numbers", () => {
    expect(startsAreDefaults(result)).toBe(true);
    render(<ComposeResultView result={result} run={run} />);
    const starts = screen.getByTestId("map-starts");
    expect(starts).toHaveTextContent("Yours to set.");
    // The command's stand-in amounts are not printed in the summary as if they were results.
    for (const s of result.model.species) {
      expect(starts).not.toHaveTextContent(`${s.initial.value} ${s.initial.unit}`);
    }
    expect(screen.getByTestId("shape-only")).toHaveTextContent("Shape only.");
    expect(screen.getByText("The shape of every species over time")).toBeInTheDocument();
  });
});

describe("the enzyme's name", () => {
  it("is GCK when the request named the isoform", () => {
    const { result, run } = of(composeGck);
    render(<ComposeResultView result={result} run={run} />);
    expect(screen.getByTestId("result-map-enzyme")).toHaveTextContent("GCK");
  });

  it("is the EC number alone when no isoform was named: the engine's GCK sentence stays in the verdict, unparsed", () => {
    const { result, run } = of(composeHk);
    render(<ComposeResultView result={result} run={run} />);
    expect(screen.getByTestId("result-map-enzyme")).not.toHaveTextContent("GCK");
    expect(screen.getAllByText(/every cited row names GCK/).length).toBeGreaterThan(0);
  });
});

describe("a constant that is a Km", () => {
  it("stays a Km: nothing is renamed without the row saying K0.5", () => {
    const { result } = of(composeOld);
    for (const p of result.model.parameters) {
      if (p.label === "Km") {
        expect(halfSaturationOf(p)).toBeNull();
        expect(constantName(p)).toBe("Km");
      }
    }
  });
});

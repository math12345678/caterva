import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import fixture from "@/__fixtures__/api/contract/michaelis-menten-parameters.json";
import type { ProvenanceKind, SourcedValue } from "@/api/types";
import { Citation, doiUrl, pubmedUrl } from "@/components/provenance/Citation";
import { ProvenanceDetail } from "@/components/provenance/ProvenanceDetail";
import { countKinds, ProvenanceLegend } from "@/components/provenance/ProvenanceLegend";
import { PROVENANCE_LABEL, ProvenanceMark } from "@/components/provenance/ProvenanceMark";
import { Value, valueAccessibleName } from "@/components/provenance/Value";
import { placeholderRowReason, readPlaceholder } from "@/lib/copy";

const searched = fixture.searched.parameters as SourcedValue[];
const structureOnly = fixture.structure_only.parameters as SourcedValue[];
const km = searched.find((v) => v.id === "reaction_Km")!;
const kcat = searched.find((v) => v.id === "reaction_kcat")!;

describe("ProvenanceMark", () => {
  it("gives each of the five kinds its own shape and accessible name", () => {
    const kinds: ProvenanceKind[] = ["measured", "fitted", "computed", "placeholder", "chosen"];
    const shapes = new Set<string>();
    for (const kind of kinds) {
      const { container, unmount } = render(<ProvenanceMark provenance={{ kind, by: "user" }} />);
      const expected = kind === "chosen" ? "chosen by you" : PROVENANCE_LABEL[kind];
      expect(screen.getByRole("img", { name: expected })).toBeInTheDocument();
      shapes.add(container.querySelector("svg")!.innerHTML);
      unmount();
    }
    expect(shapes.size).toBe(5);
  });

  it("tells a default apart from a choice the reader made", () => {
    render(
      <>
        <ProvenanceMark provenance={{ kind: "chosen", by: "default" }} />
        <ProvenanceMark provenance={{ kind: "chosen", by: "user" }} />
      </>,
    );
    expect(screen.getByRole("img", { name: "a stated default" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "chosen by you" })).toBeInTheDocument();
  });
});

describe("Value, over the real contract fixture", () => {
  it("is one button that says the number, its unit and its kind", () => {
    render(<Value v={km} />);
    const button = screen.getByRole("button");
    expect(button).toHaveAccessibleName(valueAccessibleName(km));
    expect(button).toHaveAccessibleName("Km, 6 mM, measured, cited");
    expect(button).toHaveTextContent("6mM");
  });

  it("puts the citation, as a working link, one click from a measured number", async () => {
    render(<Value v={km} />);
    await userEvent.click(screen.getByRole("button"));
    const dialog = await screen.findByRole("dialog", { name: "Where Km came from" });
    const citation = km.provenance.citation!;
    expect(within(dialog).getByText(citation.text)).toBeInTheDocument();
    if (citation.url) {
      const link = within(dialog).getByRole("link", { name: new RegExp(citation.text) });
      expect(link).toHaveAttribute("href", citation.url);
      expect(link).toHaveAttribute("target", "_blank");
    } else {
      // This fixture's citation carries no link, and none is guessed.
      expect(within(dialog).queryByRole("link", { name: new RegExp(citation.text) })).toBeNull();
      expect(within(dialog).getByText("no link was recorded for this source")).toBeInTheDocument();
    }
    if (km.provenance.spread) expect(within(dialog).getByText(km.provenance.spread.sentence)).toBeInTheDocument();
    // The source row's own words, verbatim, and the scope concerns, as the library wrote them.
    if (km.provenance.commentary) expect(within(dialog).getByText(km.provenance.commentary)).toBeInTheDocument();
    for (const line of km.provenance.scope ?? []) expect(within(dialog).getByText(line)).toBeInTheDocument();
    // The full stored value is one hover away, and is what a copy takes.
    expect(within(dialog).getByRole("button", { name: /Copy full value/ })).toBeInTheDocument();
  });

  it("puts a placeholder's reason one click away, in the library's words", async () => {
    const placeholder = structureOnly.find((v) => v.provenance.kind === "placeholder")!;
    render(<Value v={placeholder} />);
    expect(screen.getByRole("button")).toHaveAttribute("data-kind", "placeholder");
    await userEvent.click(screen.getByRole("button"));
    // The boilerplate is read into the one reason this constant has; the rest is said once, above a table.
    const reading = readPlaceholder(placeholder.provenance.reason!);
    expect(reading).not.toBeNull();
    expect(await screen.findByText(placeholderRowReason(reading!))).toBeInTheDocument();
  });

  it("opens from the keyboard and closes with Escape", async () => {
    render(<Value v={kcat} />);
    await userEvent.tab();
    expect(screen.getByRole("button")).toHaveFocus();
    await userEvent.keyboard("{Enter}");
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});

describe("ProvenanceDetail", () => {
  it("shows the organism and conditions of a measurement, or says what was not stated", () => {
    render(<ProvenanceDetail v={km} />);
    if (km.provenance.organism) expect(screen.getByText(km.provenance.organism)).toBeInTheDocument();
    expect(screen.getByText("Conditions")).toBeInTheDocument();
  });
});

describe("Citation", () => {
  it("links only by forms known to work, never a guessed link", () => {
    expect(pubmedUrl("1911773")).toBe("https://pubmed.ncbi.nlm.nih.gov/1911773/");
    expect(pubmedUrl("PMC123")).toBeNull();
    expect(doiUrl("10.1021/bi00105a002")).toBe("https://doi.org/10.1021/bi00105a002");
    expect(doiUrl("not a doi")).toBeNull();
    render(<Citation citation={{ text: "BRENDA ref 1" }} detailed />);
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText("no link was recorded for this source")).toBeInTheDocument();
  });
});

describe("ProvenanceLegend", () => {
  it("counts the kinds a screen holds", () => {
    const counts = countKinds(searched);
    render(<ProvenanceLegend counts={counts} />);
    const legend = screen.getByRole("list", { name: "What the marks mean" });
    expect(within(legend).getByText(/measured, cited/)).toHaveTextContent(`measured, cited ${counts.measured}`);
    expect(counts.measured).toBe(searched.filter((v) => v.provenance.kind === "measured").length);
  });
});

describe("ProvenanceMark shapes, at the size they are read", () => {
  const draw = (provenance: { kind: ProvenanceKind; by?: "user" | "default" }) => {
    const { container, unmount } = render(<ProvenanceMark provenance={provenance} />);
    const svg = container.querySelector("svg")!;
    const out = { html: svg.innerHTML, width: Number(svg.getAttribute("width")), svg };
    unmount();
    return out;
  };

  it("draws every mark at 12 px or more, even when asked for less", () => {
    for (const kind of ["measured", "fitted", "computed", "placeholder", "chosen"] as ProvenanceKind[]) {
      expect(draw({ kind }).width).toBeGreaterThanOrEqual(12);
    }
    const { container } = render(<ProvenanceMark provenance={{ kind: "measured" }} size={8} />);
    expect(Number(container.querySelector("svg")!.getAttribute("width"))).toBe(12);
  });

  it("gives a choice and a default different shapes, not different colours", () => {
    const chosen = draw({ kind: "chosen", by: "user" });
    const def = draw({ kind: "chosen", by: "default" });
    // A filled diamond against an outlined diamond that carries a tick.
    expect(chosen.svg.querySelector("polygon")!.getAttribute("fill")).not.toBe("none");
    expect(chosen.svg.querySelector("path")).toBeNull();
    expect(def.svg.querySelector("polygon")!.getAttribute("fill")).toBe("none");
    expect(def.svg.querySelector("path")).not.toBeNull();
    expect(chosen.html).not.toBe(def.html);
  });

  it("tells a dashed placeholder ring from a solid fitted ring by its stroke, not its colour", () => {
    const placeholder = draw({ kind: "placeholder" }).svg.querySelector("circle")!;
    const fitted = draw({ kind: "fitted" }).svg.querySelector("circle")!;
    expect(placeholder.getAttribute("stroke-dasharray")).toBeTruthy();
    expect(fitted.getAttribute("stroke-dasharray")).toBeNull();
    // Four coarse dashes round the ring: each dash is at least 1.5 units long.
    const [dash] = placeholder.getAttribute("stroke-dasharray")!.split(" ").map(Number);
    expect(dash).toBeGreaterThanOrEqual(2.5);
  });

  it("keeps the legend naming every mark", () => {
    render(<ProvenanceLegend layout="stack" />);
    const legend = screen.getByRole("list", { name: "What the marks mean" });
    expect(within(legend).getAllByRole("listitem")).toHaveLength(5);
  });
});

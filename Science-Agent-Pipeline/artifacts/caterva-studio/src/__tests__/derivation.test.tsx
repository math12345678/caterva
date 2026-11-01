/**
 * The derivation block: a compose number's claim, drawn from the run's
 * claims bundle as the server transcribed it (CONTRACT.md 9, "The claim
 * object"). Over real captured runs (src/__fixtures__/api/kinetics, README
 * there): the hexokinase run, whose literature pages were answered too, so
 * its Km claim carries the paper; and the LDH run, whose claims carry none.
 * Every expectation is read from the fixture it renders.
 */
import { fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import contractFixture from "@/__fixtures__/api/contract/michaelis-menten-parameters.json";
import hexokinase from "@/__fixtures__/api/kinetics/compose-hexokinase-claims.json";
import gossypol from "@/__fixtures__/api/kinetics/compose-ldh-gossypol.json";
import type { ClaimInfo, ComposeResult, SourcedValue } from "@/api/types";
import { pubmedUrl } from "@/components/provenance/Citation";
import { Derivation, ProvenanceDetail, shortDigest } from "@/components/provenance/ProvenanceDetail";

const hk = hexokinase.result as unknown as ComposeResult;
const ldh = gossypol.result as unknown as ComposeResult;

function param(result: ComposeResult, id: string): SourcedValue {
  return result.model.parameters.find((p) => p.id === id)!;
}

afterEach(() => vi.unstubAllGlobals());

describe("the derivation block", () => {
  it("lays out the Km claim as the bundle holds it: the rule, the row, the pinned page, the paper and what is certified", () => {
    const km = param(hk, "reaction_Km");
    const claim = km.provenance.claim!;
    expect(claim.kind).toBe("cited");
    render(<ProvenanceDetail v={km} />);
    const block = screen.getByRole("group", { name: "Derivation" });
    expect(within(block).getByText(claim.id)).toBeInTheDocument();
    expect(within(block).getByText(claim.kind)).toBeInTheDocument();
    expect(within(block).getByText(`${claim.rule.rule_id} v${claim.rule.version}`)).toBeInTheDocument();
    expect(within(block).getByText(new RegExp(claim.rule.adr))).toBeInTheDocument();
    // The row's locator and its own words, verbatim (the words are also among the certified texts).
    expect(within(block).getByText(claim.row!.locator)).toBeInTheDocument();
    expect(within(block).getAllByText(claim.row!.commentary!).length).toBeGreaterThan(0);
    // The pinned page: its URL, date, licence and digest prefix, the whole digest one hover away.
    expect(within(block).getByText(claim.snapshot!.locator)).toBeInTheDocument();
    expect(within(block).getByText(claim.snapshot!.retrieved_at)).toBeInTheDocument();
    expect(within(block).getByText(new RegExp(claim.snapshot!.licence))).toBeInTheDocument();
    const digest = within(block).getByTitle(claim.snapshot!.id);
    expect(digest).toHaveTextContent(shortDigest(claim.snapshot!.id));
    expect(claim.snapshot!.id.startsWith(shortDigest(claim.snapshot!.id).replace(/…$/, ""))).toBe(true);
    // The paper, with PubMed linked only by the contract's known form.
    expect(within(block).getByText(claim.reference!.title)).toBeInTheDocument();
    expect(within(block).getByText(`${claim.reference!.journal}, ${claim.reference!.year}`)).toBeInTheDocument();
    const link = within(block).getByRole("link", { name: `PMID ${claim.reference!.pmid}` });
    expect(link).toHaveAttribute("href", pubmedUrl(claim.reference!.pmid!));
    expect(link).toHaveAttribute("href", claim.reference!.url);
    expect(link).toHaveAttribute("target", "_blank");
    // Every certified text, as the bundle has it.
    const certified = within(block).getByRole("list", { name: "Texts certified to be in the pinned page" });
    expect(within(certified).getAllByRole("listitem")).toHaveLength(claim.certificates.length);
    for (const c of claim.certificates) expect(within(certified).getByText(c.matched)).toBeInTheDocument();
    expect(claim.certificates.map((c) => c.matched)).toContain(claim.row!.reference);
    expect(within(block).queryByText("Refused")).toBeNull();
  });

  it("copies the claim id whole", async () => {
    const claim = param(hk, "reaction_Km").provenance.claim!;
    const writeText = vi.fn(() => Promise.resolve());
    Object.defineProperty(window.navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<Derivation claim={claim} />);
    fireEvent.click(screen.getByRole("button", { name: "Copy claim id" }));
    expect(writeText).toHaveBeenCalledWith(claim.id);
    expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  });

  it("links a paper to PubMed only by the contract's form, never by a link the bundle did not carry", () => {
    const claim = param(hk, "reaction_Km").provenance.claim!;
    const paper = claim.reference!;
    const { unmount } = render(<Derivation claim={{ ...claim, reference: { ...paper, url: null } }} />);
    expect(screen.getByText(`PMID ${paper.pmid}`)).toBeInTheDocument();
    expect(screen.queryByRole("link")).toBeNull();
    unmount();
    render(<Derivation claim={{ ...claim, reference: { ...paper, url: `https://example.org/${paper.pmid}` } }} />);
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("leaves out what the bundle does not hold: no paper for an LDH row, no row or page for a placeholder", () => {
    const ki = param(ldh, "reaction_Ki").provenance.claim!;
    expect(ki.kind).toBe("cited");
    expect(ki.reference).toBeNull();
    const first = render(<Derivation claim={ki} />);
    expect(screen.queryByText("Paper")).toBeNull();
    expect(screen.queryByRole("link")).toBeNull();
    expect(screen.getByText(ki.row!.locator)).toBeInTheDocument();
    first.unmount();
    const kcat = param(ldh, "reaction_kcat").provenance.claim!;
    expect(kcat.kind).toBe("placeholder");
    render(<Derivation claim={kcat} />);
    expect(screen.getAllByRole("term").map((t) => t.textContent)).toEqual(["Claim", "Rule"]);
    expect(screen.getByText(`${kcat.rule.rule_id} v${kcat.rule.version}`)).toBeInTheDocument();
  });

  it("names a refused claim's kind, what was asked for and the rows that were not it", () => {
    // No recorded run holds a refused claim (every recording pins the page its rows came from), so the
    // refusal is composed by hand in the contract's shape over the real Km claim; it carries no number.
    const cited = param(hk, "reaction_Km").provenance.claim!;
    const refused: ClaimInfo = {
      ...cited,
      kind: "refused",
      row: null,
      snapshot: null,
      reference: null,
      certificates: [],
      refusal: {
        kind: "row_not_found_on_pinned_page",
        requested: cited.row!.locator,
        candidates: [`row:${cited.snapshot!.id} | another organism`],
      },
    };
    render(<Derivation claim={refused} />);
    expect(screen.getByText("refused")).toBeInTheDocument();
    expect(screen.getByText(refused.refusal!.kind)).toBeInTheDocument();
    expect(screen.getByText(new RegExp(refused.refusal!.requested))).toBeInTheDocument();
    const rows = screen.getByRole("list", { name: "The rows that were not the one" });
    expect(within(rows).getByText(refused.refusal!.candidates[0])).toBeInTheDocument();
    expect(screen.queryByRole("list", { name: "Texts certified to be in the pinned page" })).toBeNull();
  });

  it("draws nothing for a number no bundle covers", () => {
    const km = (contractFixture.searched.parameters as SourcedValue[]).find((v) => v.id === "reaction_Km")!;
    expect(km.provenance.claim).toBeUndefined();
    render(<ProvenanceDetail v={km} />);
    expect(screen.queryByRole("group", { name: "Derivation" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Copy claim id" })).toBeNull();
  });

  it("shortens a digest to a prefix and leaves anything else alone", () => {
    const claim = param(hk, "reaction_Km").provenance.claim!;
    expect(shortDigest(claim.id)).toMatch(/^claim:sha256:[0-9a-f]{12}…$/);
    expect(shortDigest(claim.snapshot!.id)).toMatch(/^sha256:[0-9a-f]{12}…$/);
    expect(shortDigest("reaction_Km")).toBe("reaction_Km");
  });
});

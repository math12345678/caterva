/**
 * The enzyme finder over the studio server's real answers
 * (src/__fixtures__/api/enzymes, captured from the dispatch layer; README
 * there). The mock server serves a fixture for exactly the question a
 * fixture was captured for and says 404 for any other, so a test cannot
 * pass on an answer nobody recorded. No name, EC number or protein symbol
 * below is typed as an expectation: each is read from the fixture.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import detailHexokinase from "@/__fixtures__/api/enzymes/detail-2.7.1.1-human.json";
import detailTpi from "@/__fixtures__/api/enzymes/detail-5.3.1.1-human.json";
import findUnlisted from "@/__fixtures__/api/enzymes/find-9-9-9-9.json";
import detailLdh from "@/__fixtures__/api/enzymes/detail-1.1.1.27-human.json";
import findEc from "@/__fixtures__/api/enzymes/find-1-1-1-27-human.json";
import findNone from "@/__fixtures__/api/enzymes/find-zzqx-protein-of-no-enzyme.json";
import findHexokinase from "@/__fixtures__/api/enzymes/find-hexokinase-human.json";
import findLdhHuman from "@/__fixtures__/api/enzymes/find-lactate-dehydrogenase-human.json";
import findLdhAny from "@/__fixtures__/api/enzymes/find-lactate-dehydrogenase.json";
import findPkm from "@/__fixtures__/api/enzymes/find-pyruvate-kinase-pkm-human.json";
import findPyruvateKinase from "@/__fixtures__/api/enzymes/find-pyruvate-kinase.json";
import findTypo from "@/__fixtures__/api/enzymes/find-hexokinse-human.json";
import findTransferred from "@/__fixtures__/api/enzymes/find-transferred-1.1.1.109.json";
import findDeleted from "@/__fixtures__/api/enzymes/find-deleted-1.1.1.128.json";
import { json, mockServer, setSessionToken } from "@/__tests__/helpers";
import { isCompleteEc, organismLine, subjectFields } from "@/api/enzymes";
import type { EnzymeCandidate, EnzymeDetail, EnzymeFindResponse } from "@/api/types";
import { EnzymeFinder } from "@/components/enzyme/EnzymeFinder";
import { IsoformChooser } from "@/components/enzyme/IsoformChooser";

type Recorded<T> = { request: { path: string }; status: number; body: T };

const FINDS = [findEc, findNone, findHexokinase, findLdhHuman, findLdhAny, findPkm, findPyruvateKinase, findTypo, findTransferred, findDeleted, findUnlisted] as unknown as Recorded<EnzymeFindResponse>[];
const DETAILS = [detailHexokinase, detailLdh, detailTpi] as unknown as Recorded<EnzymeDetail>[];

function asked(path: string): { q: string; organism: string } {
  const p = new URL(path, "http://studio").searchParams;
  return { q: (p.get("q") ?? "").replace(/\s+/g, " "), organism: p.get("organism") ?? "" };
}

/** The fixture captured for this very question, else a 404 saying so. */
function serve(req: { url: string }): Response | undefined {
  if (req.url.startsWith("/api/enzymes/find")) {
    const want = asked(req.url);
    const hit = FINDS.find((f) => {
      const got = asked(f.request.path);
      return got.q.toLowerCase() === want.q.toLowerCase() && got.organism === want.organism;
    });
    return hit ? json(200, hit.body) : json(404, { error: { code: "not_found", message: `no recording for ${req.url}` } });
  }
  const detail = DETAILS.find((d) => req.url === d.request.path);
  if (detail) return json(200, detail.body);
  if (req.url.startsWith("/api/enzymes/")) return json(404, { error: { code: "not_found", message: "EC is not in the enzyme nomenclature" } });
  return undefined;
}

function client() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

/** A screen's enzyme field: holds the EC number the finder hands over. */
function Harness({ initial = "", organism = "", onChange }: { initial?: string; organism?: string; onChange?: (ec: string, chosen: unknown) => void }) {
  const [ec, setEc] = useState(initial);
  const [org, setOrg] = useState(organism);
  return (
    <>
      <EnzymeFinder
        value={ec}
        organism={org}
        onChange={(next, chosen) => {
          setEc(next);
          onChange?.(next, chosen);
        }}
      />
      <input aria-label="Organism" value={org} onChange={(e) => setOrg(e.target.value)} />
      <p aria-label="Held EC">{ec}</p>
    </>
  );
}

function mount(node: React.ReactNode) {
  return render(<QueryClientProvider client={client()}>{node}</QueryClientProvider>);
}

afterEach(() => vi.unstubAllGlobals());

function setup() {
  setSessionToken("t0k");
  return mockServer(serve);
}

const type = (text: string) => userEvent.type(screen.getByRole("combobox"), text);

describe("the finder's pure rules", () => {
  it("reads a complete EC number, preliminary ones included, and nothing else", () => {
    expect(isCompleteEc("1.1.1.27")).toBe(true);
    expect(isCompleteEc(" 3.2.1.n3 ")).toBe(true);
    for (const t of ["1.1.1", "1.1.1.-", "hexokinase", "EC 1.1.1.27", ""]) expect(isCompleteEc(t)).toBe(false);
  });

  it("holds an EC number as the choice and any other text only as a seed", () => {
    expect(subjectFields("1.1.1.27")).toEqual({ subject: "1.1.1.27", subjectSeed: "" });
    expect(subjectFields("lactate dehydrogenase")).toEqual({ subject: "", subjectSeed: "lactate dehydrogenase" });
  });

  it("says what the nomenclature lists for the organism, and says plainly when it lists none", () => {
    const c = (findLdhHuman.body as unknown as EnzymeFindResponse).candidates[0];
    const line = organismLine(c.organism_proteins, c.organism_protein_count, "human", true)!;
    expect(line.startsWith("human: ")).toBe(true);
    for (const p of c.organism_proteins.slice(0, 6)) expect(line).toContain(p.symbol);
    expect(organismLine([], 0, "human", true)).toBe("no human protein recorded in the nomenclature; BRENDA may still hold measurements");
    expect(organismLine([], 0, null, false)).toBeNull();
  });
});

describe("the type-ahead", () => {
  it("is a combobox with a listbox, and shows the candidates of a name that is several enzymes by name", async () => {
    setup();
    mount(<Harness organism="human" />);
    const box = screen.getByRole("combobox", { name: /Enzyme/ });
    expect(box).toHaveAttribute("aria-autocomplete", "list");
    expect(box).toHaveAttribute("aria-expanded", "false");
    await type("lactate dehydrogenase");
    const list = await screen.findByRole("listbox");
    expect(box).toHaveAttribute("aria-controls", list.id);
    expect(box).toHaveAttribute("aria-expanded", "true");
    const answer = findLdhHuman.body as unknown as EnzymeFindResponse;
    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(answer.candidates.length);
    answer.candidates.forEach((c, i) => {
      expect(within(options[i]).getByText(`EC ${c.ec}`)).toBeInTheDocument();
      expect(within(options[i]).getByText(c.name)).toBeInTheDocument();
      expect(within(options[i]).getByText(c.why)).toBeInTheDocument();
    });
    // The first candidate's reaction and its human proteins are on the row.
    const first = answer.candidates[0];
    expect(within(options[0]).getByText(first.reaction)).toBeInTheDocument();
    expect(within(options[0]).getByText(new RegExp(`^human: ${first.organism_proteins[0].symbol}`))).toBeInTheDocument();
    // The EC number is set in DM Mono.
    expect(within(options[0]).getByText(`EC ${first.ec}`)).toHaveClass("font-mono");
  });

  it("marks the finder's recommendation as suggested and still does not choose it", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness organism="human" onChange={onChange} />);
    await type("lactate dehydrogenase");
    const answer = findLdhHuman.body as unknown as EnzymeFindResponse;
    const options = await screen.findAllByRole("option");
    const recommended = options.find((o) => o.getAttribute("data-recommended") === "true")!;
    expect(within(recommended).getByText("suggested")).toBeInTheDocument();
    expect(within(recommended).getByText(`EC ${answer.recommended_ec}`)).toBeInTheDocument();
    expect(screen.getAllByText("suggested")).toHaveLength(1);
    // Nothing is highlighted, Enter does nothing, and the screen holds no enzyme.
    const box = screen.getByRole("combobox");
    expect(box).not.toHaveAttribute("aria-activedescendant");
    await userEvent.keyboard("{Enter}");
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Held EC")).toHaveTextContent("");
  });

  it("chooses with ArrowDown and Enter, then shows the compact summary with a Change button", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness organism="human" onChange={onChange} />);
    await type("lactate dehydrogenase");
    const answer = findLdhHuman.body as unknown as EnzymeFindResponse;
    await screen.findAllByRole("option");
    await userEvent.keyboard("{ArrowDown}");
    const box = screen.getByRole("combobox");
    const options = screen.getAllByRole("option");
    expect(box).toHaveAttribute("aria-activedescendant", options[0].id);
    expect(options[0]).toHaveAttribute("aria-selected", "true");
    await userEvent.keyboard("{ArrowDown}{ArrowUp}{Enter}");
    expect(onChange).toHaveBeenCalledWith(answer.candidates[0].ec, expect.objectContaining({ ec: answer.candidates[0].ec, name: answer.candidates[0].name }));
    expect(screen.getByLabelText("Held EC")).toHaveTextContent(answer.candidates[0].ec);
    const chip = screen.getByRole("group", { name: /Enzyme/ });
    expect(within(chip).getByText(`EC ${answer.candidates[0].ec}`)).toHaveClass("font-mono");
    expect(within(chip).getByText(answer.candidates[0].name)).toBeInTheDocument();
    expect(within(chip).getByText(answer.candidates[0].reaction)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Change the enzyme/ })).toHaveFocus();
    expect(screen.queryByRole("combobox")).toBeNull();
  });

  it("chooses with a click, and Change gives the search back with focus in it", async () => {
    setup();
    mount(<Harness organism="human" />);
    await type("lactate dehydrogenase");
    const answer = findLdhHuman.body as unknown as EnzymeFindResponse;
    const options = await screen.findAllByRole("option");
    await userEvent.click(options[1]);
    expect(screen.getByLabelText("Held EC")).toHaveTextContent(answer.candidates[1].ec);
    await userEvent.click(screen.getByRole("button", { name: /^Change the enzyme/ }));
    expect(screen.getByLabelText("Held EC")).toHaveTextContent("");
    expect(screen.getByRole("combobox")).toHaveFocus();
  });

  it("has an option ready for Enter only when the finder resolved the name to one enzyme", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness onChange={onChange} />);
    await type("pyruvate kinase");
    const answer = findPyruvateKinase.body as unknown as EnzymeFindResponse;
    expect(answer.outcome).toBe("resolved");
    await screen.findAllByRole("option");
    const box = screen.getByRole("combobox");
    await waitFor(() => expect(box).toHaveAttribute("aria-activedescendant"));
    expect(screen.getByRole("status")).toHaveTextContent(/names one enzyme/);
    await userEvent.keyboard("{Enter}");
    expect(onChange).toHaveBeenCalledWith(answer.resolved_ec, expect.anything());
  });

  it("accepts an EC number", async () => {
    setup();
    mount(<Harness organism="human" />);
    await type("1.1.1.27");
    const answer = findEc.body as unknown as EnzymeFindResponse;
    expect(answer.resolved_ec).toBe("1.1.1.27");
    await screen.findAllByRole("option");
    await waitFor(() => expect(screen.getByRole("combobox")).toHaveAttribute("aria-activedescendant"));
    await userEvent.keyboard("{Enter}");
    expect(screen.getByLabelText("Held EC")).toHaveTextContent("1.1.1.27");
  });

  it("clears what was typed on Escape", async () => {
    setup();
    mount(<Harness />);
    await type("pyruvate kinase");
    await screen.findAllByRole("option");
    await userEvent.keyboard("{Escape}");
    expect(screen.getByRole("combobox")).toHaveValue("");
    expect(screen.getByRole("combobox")).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryAllByRole("option")).toHaveLength(0);
  });

  it("answers a typo with did-you-mean and does not resolve it", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness organism="human" onChange={onChange} />);
    await type("hexokinse");
    const answer = findTypo.body as unknown as EnzymeFindResponse;
    expect(answer.outcome).toBe("suggestions");
    await screen.findAllByRole("option");
    expect(screen.getByRole("status")).toHaveTextContent("No enzyme is named hexokinse. Did you mean:");
    expect(screen.getByRole("combobox")).not.toHaveAttribute("aria-activedescendant");
    await userEvent.keyboard("{Enter}");
    expect(onChange).not.toHaveBeenCalled();
    await userEvent.click(screen.getAllByRole("option")[0]);
    expect(onChange).toHaveBeenCalledWith(answer.candidates[0].ec, expect.anything());
  });

  it("says plainly when nothing matches, and why UniProt was not asked", async () => {
    setup();
    mount(<Harness />);
    await type("zzqx protein of no enzyme");
    const answer = findNone.body as unknown as EnzymeFindResponse;
    expect(answer.outcome).toBe("none");
    await screen.findByText(/Check the spelling/);
    expect(screen.queryAllByRole("option")).toHaveLength(0);
    expect(screen.getByText(answer.fallback_unavailable!)).toBeInTheDocument();
  });

  it("offers UniProt's real suggestions, labelled as UniProt's, when the server asked it", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness organism="human" onChange={onChange} />);
    await type("pyruvate kinase PKM");
    const answer = findPkm.body as unknown as EnzymeFindResponse;
    expect(answer.fallback?.suggestions.length).toBeGreaterThan(1);
    const options = await screen.findAllByRole("option");
    expect(options).toHaveLength(answer.fallback!.suggestions.length);
    for (const o of options) expect(within(o).getByText("from UniProt")).toBeInTheDocument();
    expect(screen.getByText(answer.fallback!.note)).toBeInTheDocument();
    await userEvent.click(options[0]);
    expect(onChange).toHaveBeenCalledWith(answer.fallback!.suggestions[0].ec, expect.anything());
  });

  it("shows a transferred number with its replacement, and chooses the replacement", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness onChange={onChange} />);
    const answer = findTransferred.body as unknown as EnzymeFindResponse;
    const old = answer.candidates.find((c) => c.status === "transferred")!;
    await type(old.ec);
    const options = await screen.findAllByRole("option");
    const row = options.find((o) => within(o).queryByText(`EC ${old.ec}`))!;
    expect(within(row).getByText(`transferred, now EC ${old.superseded_by[0]}`)).toBeInTheDocument();
    expect(within(row).getByText(`Choosing this uses EC ${old.superseded_by[0]}, which replaced it.`)).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/names one enzyme/);
    await userEvent.click(row);
    expect(onChange).toHaveBeenCalledWith(old.superseded_by[0], expect.anything());
  });

  it("shows a deleted number plainly and will not choose it", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness onChange={onChange} />);
    const answer = findDeleted.body as unknown as EnzymeFindResponse;
    const gone = answer.candidates[0];
    await type(gone.ec);
    const row = (await screen.findAllByRole("option"))[0];
    expect(within(row).getByText("deleted, no replacement")).toBeInTheDocument();
    expect(row).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(row);
    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole("status")).toHaveTextContent(/deleted from the enzyme nomenclature/);
  });

  it("offers a well-formed number the nomenclature does not hold as given, and says so", async () => {
    setup();
    const onChange = vi.fn();
    mount(<Harness onChange={onChange} />);
    await type("9.9.9.9");
    const answer = findUnlisted.body as unknown as EnzymeFindResponse;
    expect(answer.candidates).toHaveLength(0);
    const row = (await screen.findAllByRole("option"))[0];
    expect(within(row).getByText("use as given")).toBeInTheDocument();
    expect(within(row).getByText(/BRENDA may still know this number/)).toBeInTheDocument();
    await userEvent.click(row);
    expect(onChange).toHaveBeenCalledWith("9.9.9.9", expect.anything());
  });

  it("re-ranks when the organism field changes, asking the server again with the organism", async () => {
    const { seen } = setup();
    mount(<Harness />);
    await type("lactate dehydrogenase");
    await screen.findAllByRole("option");
    expect(seen.some((r) => r.url.includes("find") && !r.url.includes("organism="))).toBe(true);
    // Typing the organism moves focus out of the enzyme field; coming back asks again with it.
    await userEvent.type(screen.getByLabelText("Organism"), "human");
    await userEvent.click(screen.getByRole("combobox"));
    await waitFor(() => expect(seen.some((r) => r.url.includes("find") && r.url.includes("organism=human"))).toBe(true));
    const first = (findLdhHuman.body as unknown as EnzymeFindResponse).candidates[0];
    await waitFor(() => expect(screen.getAllByRole("option")[0]).toHaveTextContent(new RegExp(`human: ${first.organism_proteins[0].symbol}`)));
  });

  it("sends the session header and a short, safe question", async () => {
    const { seen } = setup();
    mount(<Harness />);
    await type("pyruvate kinase");
    await screen.findAllByRole("option");
    const find = seen.find((r) => r.url.startsWith("/api/enzymes/find"))!;
    expect(find.headers.get("X-Caterva-Session")).toBe("t0k");
    const params = new URL(find.url, "http://studio").searchParams;
    expect([...params.keys()].sort()).toEqual(["limit", "q"]);
    expect(find.method).toBe("GET");
  });

  it("says when the finder did not answer, and tries again on request", async () => {
    setSessionToken("t0k");
    let calls = 0;
    mockServer((req) => {
      if (req.url.startsWith("/api/enzymes/find")) {
        calls += 1;
        return calls === 1 ? json(500, { error: { code: "crash", message: "the index could not be read" } }) : serve(req);
      }
      return undefined;
    });
    mount(<Harness />);
    await type("pyruvate kinase");
    await screen.findByText(/The enzyme finder did not answer: the index could not be read/);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    await screen.findAllByRole("option");
  });

  it("shows the server's refusal under the field", () => {
    setup();
    mount(<EnzymeFinder value="" onChange={() => {}} error="subject: the engine refused this" />);
    expect(screen.getByRole("alert")).toHaveTextContent("subject: the engine refused this");
    expect(screen.getByRole("combobox")).toHaveAttribute("aria-invalid", "true");
  });
});

describe("a chosen enzyme", () => {
  it("is read back from the nomenclature when a screen opens with an EC number", async () => {
    setup();
    mount(<Harness initial="2.7.1.1" organism="human" />);
    const d = detailHexokinase.body as unknown as EnzymeDetail;
    const chip = screen.getByRole("group", { name: /Enzyme/ });
    expect(await within(chip).findByText(d.name)).toBeInTheDocument();
    expect(within(chip).getByText("EC 2.7.1.1")).toHaveClass("font-mono");
    expect(within(chip).getByText(d.reaction)).toBeInTheDocument();
    const symbols = d.isozymes.proteins.slice(0, 6).map((p) => p.symbol);
    expect(within(chip).getByText(`human: ${symbols.join(", ")}`)).toBeInTheDocument();
  });

  it("says when the nomenclature does not list the number, and that it is sent as given", async () => {
    setup();
    mount(<Harness initial="9.9.9.9" />);
    await screen.findByText(/not in the enzyme nomenclature release Caterva holds/);
    expect(screen.getByText("EC 9.9.9.9")).toBeInTheDocument();
  });
});

describe("the isoform chooser", () => {
  const d = detailHexokinase.body as unknown as EnzymeDetail;

  it("offers the organism's entries by name and sets the isoform to the symbol", async () => {
    setup();
    const onChange = vi.fn();
    mount(<IsoformChooser ec="2.7.1.1" organism="human" value="" onChange={onChange} />);
    const group = await screen.findByRole("group", { name: /Isoforms of EC 2\.7\.1\.1 in human/ });
    for (const p of d.isozymes.proteins) expect(within(group).getByRole("button", { name: p.entry_name })).toBeInTheDocument();
    expect(within(group).getByRole("button", { name: /^HXK1_HUMAN$/ })).toBeInTheDocument();
    await userEvent.click(within(group).getByRole("button", { name: d.isozymes.proteins[0].entry_name }));
    expect(onChange).toHaveBeenCalledWith(d.isozymes.proteins[0].symbol);
  });

  it("marks the chosen one and clears it when pressed again", async () => {
    setup();
    const onChange = vi.fn();
    mount(<IsoformChooser ec="2.7.1.1" organism="human" value={d.isozymes.proteins[1].symbol} onChange={onChange} />);
    const pressed = await screen.findByRole("button", { name: d.isozymes.proteins[1].entry_name });
    expect(pressed).toHaveAttribute("aria-pressed", "true");
    await userEvent.click(pressed);
    expect(onChange).toHaveBeenCalledWith("");
  });

  it("says nothing when the EC number is one protein in the organism", async () => {
    setup();
    const one = detailTpi.body as unknown as EnzymeDetail;
    expect(one.isozymes.count).toBe(1);
    const { container } = mount(<IsoformChooser ec="5.3.1.1" organism="human" value="" onChange={() => {}} />);
    await waitFor(() => expect(screen.queryByRole("group")).toBeNull());
    expect(container).toBeEmptyDOMElement();
  });

  it("says nothing without an organism", () => {
    setup();
    const { container } = mount(<IsoformChooser ec="2.7.1.1" organism="" value="" onChange={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("an organism with no protein", () => {
  it("is said plainly on the candidates the finder returned without one", async () => {
    setup();
    mount(<Harness organism="human" />);
    await type("lactate dehydrogenase");
    const answer = findLdhHuman.body as unknown as EnzymeFindResponse;
    const without = answer.candidates.filter((c) => !c.has_organism_protein);
    expect(without.length).toBeGreaterThan(0);
    const options = await screen.findAllByRole("option");
    for (const c of without) {
      const row = options.find((o) => within(o).queryByText(`EC ${c.ec}`))!;
      expect(within(row).getByText("no human protein recorded in the nomenclature; BRENDA may still hold measurements")).toBeInTheDocument();
    }
  });
});

describe("candidates are the finder's, not the page's", () => {
  it("renders every key it draws from the fixture's candidate", () => {
    const candidate = (findLdhHuman.body as unknown as EnzymeFindResponse).candidates[0] as EnzymeCandidate;
    for (const key of ["ec", "name", "why", "reaction", "class_path", "organism_proteins", "status", "superseded_by", "has_organism_protein", "recommended"] as const) {
      expect(candidate).toHaveProperty(key);
    }
  });
});

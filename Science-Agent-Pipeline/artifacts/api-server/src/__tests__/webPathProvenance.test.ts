/**
 * The web path: /api/resolve refuses, the page fills the gap, /api/simulate
 * runs. What the refusal carries, and what the run reports, decide whether a
 * resolved Km reaches the result as BRENDA's or as the student's.
 *
 * Measured 2026-11-02 against live BRENDA:
 *
 *   "hexokinase glucose human"
 *     -> 422, km 6 mM resolved (ref 641068), vmax refused for want of [E]0
 *   the page then ran "hexokinase glucose human km=6 s0=10 end=10 points=51 vmax=5"
 *     -> km origin "user", no citation
 *   "lactate dehydrogenase with pyruvate in humans with 50 nM enzyme"
 *     -> "BRENDA, KEGG and PubMed hold no kcat for this enzyme", while the
 *        runner had answered cross_species_withheld (BRENDA has LDH kcat
 *        rows from twenty organisms, none human)
 *   "glucokinase glucose rat"
 *     -> UniProt asked for an enzyme called "glucokinase glucose rat"
 *
 * The science-agent boundary is mocked so each test pins one decision of
 * queryResolver.ts; the live round trip is in the commit message's probe.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";
import { matchOrganism, stripOrganisms } from "../lib/organisms";
import { resolveQueryWithLLM } from "../lib/llmResolver";

// Undefined (no LLM configured) unless a test says otherwise, so every other
// case here runs the keyword path, as the deployed landing page does today.
vi.mock("../lib/llmResolver", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/llmResolver")>();
  return { ...original, resolveQueryWithLLM: vi.fn(async () => undefined) };
});

type Entities = {
  quantity?: string;
  enzymeName?: string;
  ecNumber?: string;
  organism?: string;
};

const seen: Entities[] = [];
let kcatAnswer: Record<string, unknown> = {};

const HEXOKINASE_KM = {
  found: true,
  km: 6,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "641068",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
  },
  literatureCandidates: [],
  logs: [],
};

const HEXOKINASE_KCAT = {
  found: true,
  kcat: 40.1,
  vmax: 0.002005,
  vmaxValidation: { ok: true, flagged: false },
  unit: "1/s",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "739603",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=2.7.1.1",
  },
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async (entities: Entities) => {
      seen.push({ ...entities });
      if (entities.quantity === "kcat") return kcatAnswer;
      return HEXOKINASE_KM;
    }),
  };
});

beforeEach(() => {
  seen.length = 0;
  kcatAnswer = HEXOKINASE_KCAT;
});

async function refusalOf(query: string): Promise<RequiredParametersMissingError> {
  try {
    await resolveQuery(query);
  } catch (err) {
    if (err instanceof RequiredParametersMissingError) return err;
    throw err;
  }
  throw new Error(`expected "${query}" to be refused`);
}

/** Resolve for the lookups it makes; whether it then runs is not the point. */
async function attempt(query: string): Promise<void> {
  try {
    await resolveQuery(query);
  } catch (err) {
    if (!(err instanceof RequiredParametersMissingError)) throw err;
  }
}

describe("the refusal carries provenance, so a form can keep it", () => {
  it("reports the resolved Km's citation and the missing Vmax's reason", async () => {
    const err = await refusalOf("hexokinase glucose human");
    expect(err.missing).toEqual(["vmax"]);
    expect(err.resolvedSoFar["km"]).toBe(6);
    const km = err.parameterProvenance["km"]!;
    expect(km.origin).toBe("resolved");
    expect(km.citation).toContain("(ref 641068)");
    expect(km.organism).toBe("Homo sapiens");
    expect(err.parameterProvenance["vmax"]!.unresolvedReason).toBe(
      "enzyme_conc_not_supplied",
    );
    expect(err.details["vmax"]).toContain("with 50 nM enzyme");
  });
});

describe("the LLM path's refusal carries the same provenance", () => {
  it("reports the resolved Km's citation when a model classified the query", async () => {
    // The two resolution paths throw from two places; a deployment with an
    // LLM key set must not hand the page a bare-number refusal again.
    vi.mocked(resolveQueryWithLLM).mockResolvedValueOnce({
      domain: "mm",
      parameters: {},
      reasoning: "identified hexokinase kinetics",
      modelCitations: [],
      entities: { enzymeName: "hexokinase", organism: "Homo sapiens" },
    } as never);
    const err = await refusalOf("hexokinase glucose human");
    expect(vi.mocked(resolveQueryWithLLM)).toHaveBeenCalled();
    expect(err.parameterProvenance["km"]!.origin).toBe("resolved");
    expect(err.parameterProvenance["km"]!.citation).toContain("(ref 641068)");
    expect(err.parameterProvenance["vmax"]!.unresolvedReason).toBe(
      "enzyme_conc_not_supplied",
    );
  });
});

describe("the run keeps the citation when the page sends only [E]0", () => {
  it("a resolved km stays resolved and cited through the run step", async () => {
    const run = await resolveQuery(
      "hexokinase with glucose in humans with 50 nM enzyme",
    );
    const km = run.parameterProvenance["km"]!;
    expect(km.origin).toBe("resolved");
    expect(km.citation).toContain("(ref 641068)");
    expect(run.parameterProvenance["vmax"]!.origin).toBe("resolved");
    expect(run.parameterProvenance["enzyme_conc"]!.origin).toBe("user");
    // "in humans" was read as naming the organism, so no assumption is
    // reported on the person's behalf.
    expect(run.provenance.flags.join(" ")).not.toMatch(/assumed: organism/);
  });

  it("echoing the resolved value as key=value is what relabelled it (why the page must not)", async () => {
    // Pins the server half of the old bug: `km=6` in the query IS the
    // person stating it, by design, so the fix has to be the page not
    // writing it there.
    const run = await resolveQuery(
      "hexokinase glucose human km=6 vmax=5 s0=10 end=10 points=51",
    );
    expect(run.parameterProvenance["km"]!.origin).toBe("user");
    expect(run.parameterProvenance["km"]!.citation).toBeUndefined();
  });
});

describe("a withheld kcat is not reported as no kcat", () => {
  it("names the organisms BRENDA does hold a kcat for", async () => {
    kcatAnswer = {
      found: false,
      source: "cross_species_withheld",
      crossSpeciesOrganismsAvailable: ["Oryctolagus cuniculus", "Gallus gallus"],
      literatureCandidates: [],
      logs: [],
    };
    const err = await refusalOf(
      "hexokinase with glucose in humans with 50 nM enzyme",
    );
    const detail = err.details["vmax"]!;
    expect(detail).toContain("Oryctolagus cuniculus, Gallus gallus");
    expect(detail).toContain("none measured in Homo sapiens");
    expect(detail).not.toMatch(/hold no kcat/);
    expect(err.parameterProvenance["km"]!.origin).toBe("resolved");
  });

  it("still says 'no kcat' when the literature genuinely has none", async () => {
    kcatAnswer = { found: false, source: "not_found", literatureCandidates: [], logs: [] };
    const err = await refusalOf(
      "hexokinase with glucose in humans with 50 nM enzyme",
    );
    expect(err.details["vmax"]).toMatch(/hold no kcat for this enzyme/);
  });
});

describe("the organism a person types", () => {
  it("reads plurals and 'in humans'", () => {
    expect(matchOrganism("hexokinase with glucose in humans")).toBe("Homo sapiens");
    expect(matchOrganism("human hexokinase")).toBe("Homo sapiens");
    expect(matchOrganism("liver of mice")).toBe("Mus musculus");
    expect(matchOrganism("in rats")).toBe("Rattus norvegicus");
    expect(matchOrganism("in yeasts")).toBe("Saccharomyces cerevisiae");
    expect(matchOrganism("in fruit flies")).toBe("Drosophila melanogaster");
  });

  it("reads the common names of BRENDA's classic enzyme sources", () => {
    expect(matchOrganism("rabbit muscle lactate dehydrogenase")).toBe(
      "Oryctolagus cuniculus",
    );
    expect(matchOrganism("bovine heart")).toBe("Bos taurus");
    expect(matchOrganism("porcine pancreas")).toBe("Sus scrofa");
    expect(matchOrganism("chicken liver")).toBe("Gallus gallus");
  });

  it("still does not match inside another word", () => {
    expect(matchOrganism("the reaction rate is high")).toBeUndefined();
    expect(matchOrganism("humanized antibody")).toBeUndefined();
    expect(matchOrganism("ratio of products")).toBeUndefined();
  });

  it("stripOrganisms blanks only the organism phrase", () => {
    expect(stripOrganisms("glucokinase glucose rat").trim().split(/\s+/)).toEqual([
      "glucokinase",
      "glucose",
    ]);
  });
});

describe("the enzyme-name guess is the enzyme, not the whole phrase", () => {
  const sentNames = () =>
    seen.filter((e) => e.quantity !== "kcat").map((e) => e.enzymeName);

  it("drops the substrate and organism after the -ase word", async () => {
    await attempt("glucokinase glucose rat");
    expect(sentNames()).toEqual(["glucokinase"]);
    expect(seen[0]!.organism).toBe("Rattus norvegicus");
  });

  it("keeps the words that are part of the name", async () => {
    await attempt("simulate pyruvate carboxylase with pyruvate in mice");
    expect(sentNames()).toEqual(["pyruvate carboxylase"]);
    expect(seen[0]!.organism).toBe("Mus musculus");
  });

  it("does not read a concentration phrase as part of the name", async () => {
    await attempt("glucose oxidase with 50 nM enzyme");
    expect(sentNames()).toEqual(["glucose oxidase"]);
  });
});

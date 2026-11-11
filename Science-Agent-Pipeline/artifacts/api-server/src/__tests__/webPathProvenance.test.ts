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
import { matchOrganism, matchOrganisms, stripOrganisms } from "../lib/organisms";
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
  substrate?: string;
  ecNumber?: string;
  organism?: string;
  isoform?: string;
};

const seen: Entities[] = [];
let kcatAnswer: Record<string, unknown> = {};
let kmAnswer: Record<string, unknown> = {};

// The runner's answer since ADR 0182: the Km and the kcat from one paper,
// ref 739603, the one paper holding a row of each among the rows chosen
// from (fallback_logic.resolve_kinetic_pair).
const HEXOKINASE_KM = {
  found: true,
  km: 6.3,
  unit: "mM",
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
      return kmAnswer;
    }),
  };
});

beforeEach(() => {
  seen.length = 0;
  kcatAnswer = HEXOKINASE_KCAT;
  kmAnswer = HEXOKINASE_KM;
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
    expect(err.resolvedSoFar["km"]).toBe(6.3);
    const km = err.parameterProvenance["km"]!;
    expect(km.origin).toBe("resolved");
    expect(km.citation).toContain("(ref 739603)");
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
    expect(err.parameterProvenance["km"]!.citation).toContain("(ref 739603)");
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
    expect(km.citation).toContain("(ref 739603)");
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

describe("a common name inside a longer animal's name is not that animal", () => {
  // Measured 2026-11-03 on the live API: "guinea pigs" grounded in Sus
  // scrofa (ref 640240), "naked mole rats" in Rattus norvegicus (ref
  // 640259). Unmatched, each falls to the labelled "assumed" default.
  it("does not read guinea pig, mole rat, sea cow or pig-tailed macaque", () => {
    expect(matchOrganism("hexokinase in guinea pigs")).toBeUndefined();
    expect(matchOrganism("hexokinase with glucose in a guinea pig")).toBeUndefined();
    expect(matchOrganism("hexokinase in naked mole rats")).toBeUndefined();
    expect(matchOrganism("hexokinase in the naked mole-rat")).toBeUndefined();
    expect(matchOrganism("hexokinase from the sea cow")).toBeUndefined();
    expect(matchOrganism("hexokinase in a pig-tailed macaque")).toBeUndefined();
    expect(matchOrganism("hexokinase in deer mice")).toBeUndefined();
  });

  it("still reads the animal itself", () => {
    expect(matchOrganism("hexokinase in pigs")).toBe("Sus scrofa");
    expect(matchOrganism("rat liver glucokinase")).toBe("Rattus norvegicus");
    expect(matchOrganism("hexokinase in cows")).toBe("Bos taurus");
    expect(matchOrganism("in mice")).toBe("Mus musculus");
  });
});

describe("a reagent's species is not the enzyme's", () => {
  // Measured 2026-11-03: a Pseudomonas hexokinase query "with bovine serum
  // albumin" came back with a Bos taurus Km (ref 662842), brenda_exact.
  it("sets aside serum albumin, BSA and ovalbumin", () => {
    expect(
      matchOrganism("pseudomonas aeruginosa hexokinase with glucose with bovine serum albumin"),
    ).toBe("Pseudomonas aeruginosa");
    expect(
      matchOrganism(
        "P. aeruginosa hexokinase with glucose in a buffer with 0.1 mg/ml BSA from cows",
      ),
    ).toBe("Pseudomonas aeruginosa");
    expect(matchOrganism("mycobacterium tuberculosis kinase, chicken ovalbumin")).toBe(
      "Mycobacterium tuberculosis",
    );
    expect(matchOrganism("E. coli hexokinase with human serum albumin")).toBe(
      "Escherichia coli",
    );
  });

  it("keeps an animal's own serum as the animal", () => {
    expect(matchOrganism("lactate dehydrogenase in rat serum")).toBe("Rattus norvegicus");
  });

  it("refuses, and looks nothing up, when two organisms remain", async () => {
    expect(matchOrganisms("rat hexokinase expressed in E. coli")).toEqual([
      "Escherichia coli",
      "Rattus norvegicus",
    ]);
    const err = await refusalOf("rat hexokinase with glucose expressed in E. coli");
    expect(seen).toEqual([]);
    const km = err.parameterProvenance["km"]!;
    expect(km.origin).toBe("default");
    expect(km.unresolvedReason).toBe("organism_ambiguous");
    expect(err.details["km"]).toContain("Escherichia coli, Rattus norvegicus");
    expect(err.resolvedSoFar).not.toHaveProperty("km");
  });
});

describe("the guess path sends the substrate the person named", () => {
  const kmLookups = () => seen.filter((e) => e.quantity !== "kcat");

  it("a bicarbonate query does not come back with the pyruvate Km", async () => {
    // Measured 2026-11-03: km 0.08 (ref 649744), which BRENDA lists for
    // PYRUVATE, under a query naming bicarbonate. With the substrate sent,
    // the runner's row filter applies and answers with what it does hold.
    kmAnswer = {
      found: false,
      source: "not_found",
      substratesAvailable: ["ATP", "HCO3-", "pyruvate"],
      literatureCandidates: [],
      logs: [],
    };
    const err = await refusalOf("pyruvate carboxylase with bicarbonate in humans");
    expect(kmLookups().map((e) => [e.enzymeName, e.substrate])).toEqual([
      ["pyruvate carboxylase", "bicarbonate"],
    ]);
    expect(err.resolvedSoFar).not.toHaveProperty("km");
    expect(err.parameterProvenance["km"]!.origin).toBe("default");
    expect(err.details["km"]).toContain("HCO3-");
  });

  it("reads the substrate past words that are not one", async () => {
    await attempt("pyruvate carboxylase activity with ATP in humans");
    expect(kmLookups()[0]!.substrate).toBe("atp");
    seen.length = 0;
    await attempt("glucokinase glucose rat");
    expect(kmLookups()[0]!.substrate).toBe("glucose");
  });

  it("asks the runner to choose a substrate when none is named, and states the choice", async () => {
    // Was "refuses, and looks nothing up, when no substrate is named"
    // (ADR 0178/0181). Measured 2026-11-03: "pyruvate carboxylase in humans"
    // went out with substrate "", the runner logged "BRENDA lookup will be
    // unfiltered by substrate", and the pyruvate row came back unnamed.
    // Since ADR 0182 the substrate goes out unnamed and the runner CHOOSES
    // the best-measured one, looks the Km up for exactly it, and sends the
    // choice back; the response states it with the alternatives.
    kmAnswer = {
      ...HEXOKINASE_KM,
      km: 0.08,
      citation: { ...HEXOKINASE_KM.citation, referenceId: "649744" },
      choices: [
        {
          role: "substrate",
          chosen: "pyruvate",
          why: "most Km and kcat rows for EC 6.4.1.1 in Homo sapiens",
          alternatives: [
            { name: "ATP", rows: { km: 4 } },
            { name: "HCO3-", rows: { km: 3, kcat: 1 } },
          ],
          considered: 3,
        },
      ],
    };
    const err = await refusalOf("pyruvate carboxylase in humans");
    expect(kmLookups().map((e) => [e.enzymeName, e.substrate])).toEqual([
      ["pyruvate carboxylase", undefined],
    ]);
    const km = err.parameterProvenance["km"]!;
    expect(km.origin).toBe("resolved");
    expect(km.note).toContain("Km of pyruvate, the substrate Caterva chose");
    const chosen = err.flags.find((f) => f.startsWith("substrate chosen: pyruvate"));
    expect(chosen).toContain("most Km and kcat rows for EC 6.4.1.1 in Homo sapiens");
    expect(chosen).toContain("ATP (Km 4 rows); HCO3- (Km 3 rows, kcat 1 row)");
    expect(chosen).toContain('"<enzyme> with <substrate>"');
  });

  it("the kcat bridge looks up the substrate the Km's lookup chose", async () => {
    kmAnswer = {
      ...HEXOKINASE_KM,
      choices: [
        { role: "substrate", chosen: "D-glucose", why: "most measured", alternatives: [], considered: 1 },
      ],
    };
    await attempt("hexokinase in humans with 50 nM enzyme");
    const kcat = seen.find((e) => e.quantity === "kcat");
    expect(kcat?.substrate).toBe("D-glucose");
  });

  it("says what is missing when BRENDA has nothing to choose from", async () => {
    kmAnswer = {
      found: false,
      source: "substrate_not_named",
      choiceRefusal:
        "No substrate was named, and BRENDA lists no Km row for any substrate of EC 6.4.1.1 " +
        "in Homo sapiens, so none could be chosen and nothing was looked up.",
      choices: [],
      literatureCandidates: [],
      logs: [],
    };
    const err = await refusalOf("pyruvate carboxylase in humans");
    const km = err.parameterProvenance["km"]!;
    expect(km.origin).toBe("default");
    expect(km.unresolvedReason).toBe("substrate_not_named");
    expect(err.details["km"]).toContain("BRENDA lists no Km row for any substrate of EC 6.4.1.1");
  });

  it("a table enzyme with no substrate named is not given the table's first one", async () => {
    // Was "a table enzyme keeps its documented substrate default": the
    // table's substrates[0] was sent with no flag, so "hexokinase in humans"
    // was silently a glucose query (and trypsin's was "protein"). It now
    // goes out unnamed, for the runner to choose and say so.
    await attempt("hexokinase in humans");
    expect(kmLookups().map((e) => e.substrate)).toEqual([undefined]);
    seen.length = 0;
    await attempt("hexokinase with mannose in humans");
    expect(kmLookups().map((e) => e.substrate)).toEqual(["mannose"]);
  });
});

describe("a gene symbol names its substrate after a connector", () => {
  const kmLookups = () => seen.filter((e) => e.quantity !== "kcat");

  it("reads CYP2B6 as the enzyme and bupropion as the substrate", async () => {
    // Found by the live baseline: "kinetics of CYP2B6 with bupropion" asked
    // UniProt for an enzyme called "cyp2b6 bupropion" and was refused for
    // naming no substrate.
    await attempt("kinetics of CYP2B6 with bupropion in humans");
    expect(kmLookups().map((e) => [e.enzymeName, e.substrate])).toEqual([
      ["cyp2b6", "bupropion"],
    ]);
  });

  it("reads 'CYP2B6 with bupropion' as a kinetics question, not an unrecognised one", async () => {
    await attempt("CYP2B6 with bupropion");
    expect(kmLookups().map((e) => [e.enzymeName, e.substrate])).toEqual([
      ["cyp2b6", "bupropion"],
    ]);
  });

  it("sends the gene symbol as the isoform, so another CYP's row is not cited as CYP2B6's", async () => {
    // CYP2B6 resolves to EC 1.14.14.1, which every P450 monooxygenase
    // shares; BRENDA's bupropion rows there are CYP2B6's, CYP2C19's and
    // CYP2D6's. Without the isoform the runner would take the best row of
    // any of them and the response would call it CYP2B6's.
    await attempt("kinetics of CYP2B6 with bupropion in humans");
    expect(kmLookups().map((e) => e.isoform)).toEqual(["CYP2B6"]);
  });

  it("states that it read the question as kinetics", async () => {
    let flags: string[] = [];
    try {
      flags = (await resolveQuery("CYP2B6 with bupropion")).provenance.flags;
    } catch (err) {
      if (!(err instanceof RequiredParametersMissingError)) throw err;
      flags = err.flags;
    }
    expect(flags.join(" ")).toContain("read as: enzyme kinetics of CYP2B6 with bupropion");
  });

  it("does not take later words as a substrate without a connector", async () => {
    await attempt("lysozyme kinetics from hen egg white");
    expect(kmLookups()[0]?.substrate).toBeUndefined();
  });
});

describe("a query naming two enzymes is not modelled as one", () => {
  it("refuses a coupled assay instead of simulating its first enzyme", async () => {
    // Measured 2026-11-03: pyruvate carboxylase alone (ref 649744), and
    // malate dehydrogenase mentioned nowhere in the response.
    const err = await refusalOf(
      "pyruvate carboxylase and malate dehydrogenase coupled assay with pyruvate in humans",
    );
    expect(seen).toEqual([]);
    expect(err.parameterProvenance["km"]!.unresolvedReason).toBe("ec_ambiguous");
    expect(err.details["km"]).toContain("pyruvate carboxylase, malate dehydrogenase");
  });

  it("does not count one enzyme named twice as two", async () => {
    await attempt("pyruvate dehydrogenase phosphatase with pyruvate in humans");
    expect(seen.map((e) => e.enzymeName)).toContain("pyruvate dehydrogenase phosphatase");
  });
});

describe("the refusal says what it assumed", () => {
  it("a misspelt organism's default is flagged on the 422 path", async () => {
    // Measured 2026-11-03: "in humna" came back 422 with a Homo sapiens Km
    // (ref 641068) and no "assumed: organism" anywhere in the body.
    const err = await refusalOf("hexokinase with glucose in humna");
    expect(err.parameterProvenance["km"]!.organism).toBe("Homo sapiens");
    expect(err.flags.join(" ")).toMatch(/assumed: organism = Homo sapiens/);
  });
});

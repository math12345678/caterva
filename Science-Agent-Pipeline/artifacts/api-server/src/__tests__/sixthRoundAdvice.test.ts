/**
 * Sixth review round, surfaces (ADR 0182).
 *
 * XS5R2-05: /api/resolve's 422 said the same thing about Vmax for every
 * query: "Caterva resolves kcat from literature ... State the enzyme
 * concentration ... and Vmax is derived and cited for you". For tyrosinase
 * in mouse and COX-2 with celecoxib no usable kcat exists, so the run that
 * advice leads to failed again. The Km's lookup already resolves the kcat
 * half of its pair; its outcome now decides the advice.
 *
 * XS5R2-04: for "hexokinase", compose and the Studio said the model is of
 * GCK, one of 5 human proteins; the API said only the row's accession. The
 * runner now sends compose's isozyme notice, and it is a flag.
 */
import { describe, expect, it, vi } from "vitest";

import { isozymeNoticeFlag, resolveQuery } from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";

const state: { km: Record<string, unknown> } = { km: {} };

const KM_BASE = {
  found: true,
  km: 0.6,
  unit: "mM",
  organism: "Mus musculus",
  source: "brenda_exact",
  crossSpecies: false,
  citation: { source: "BRENDA", referenceId: "745746", url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.14.18.1" },
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => state.km),
  };
});

const QUERY = "simulate Michaelis-Menten kinetics of tyrosinase with substrate L-Dopa in mouse s0=1 end=10 points=51";

async function refusal(): Promise<RequiredParametersMissingError> {
  try {
    await resolveQuery(QUERY);
  } catch (err) {
    if (err instanceof RequiredParametersMissingError) return err;
    throw err;
  }
  throw new Error("the query resolved; it should have stopped for vmax");
}

describe("XS5R2-05: the Vmax advice says what the kcat search found", () => {
  it("does not promise a Vmax from an enzyme concentration when no kcat exists", async () => {
    state.km = {
      ...KM_BASE,
      pairedKcat: {
        found: false,
        source: "cross_species_withheld",
        crossSpeciesOrganismsAvailable: ["Homo sapiens", "Streptomyces antibioticus"],
        crossSpeciesVariantOnly: [],
      },
    };
    const err = await refusal();
    const vmax = err.details["vmax"] ?? "";
    expect(vmax).toContain("the kcat search for this query came back empty");
    expect(vmax).toContain("none measured in Mus musculus");
    expect(vmax).toContain("stating an enzyme concentration alone will not give a Vmax");
    expect(vmax).not.toContain("Vmax is derived and cited for you");
  });

  it("says isozyme rows are isozymes, not variants", async () => {
    state.km = {
      ...KM_BASE,
      pairedKcat: {
        found: false,
        source: "cross_species_withheld",
        crossSpeciesOrganismsAvailable: ["Vibrio tyrosinaticus"],
        crossSpeciesVariantOnly: ["Vibrio tyrosinaticus"],
        crossSpeciesIsozymeOnly: ["Vibrio tyrosinaticus"],
      },
    };
    const vmax = (await refusal()).details["vmax"] ?? "";
    expect(vmax).toContain("each name an isozyme");
    expect(vmax).not.toContain("protein variant");
  });

  it("keeps the enzyme-concentration advice when a kcat was found, and names it", async () => {
    state.km = { ...KM_BASE, pairedKcat: { found: true, source: "brenda_exact", kcat: 38.1 } };
    const vmax = (await refusal()).details["vmax"] ?? "";
    expect(vmax).toContain("Vmax is derived and cited for you");
    expect(vmax).toContain("found 38.1 1/s");
  });

  it("reads as before for a runner that sends no paired kcat", async () => {
    state.km = { ...KM_BASE };
    const vmax = (await refusal()).details["vmax"] ?? "";
    expect(vmax).toContain("Vmax is derived and cited for you");
    expect(vmax).not.toContain("found");
  });
});

describe("XS5R2-04: which protein a multi-protein EC was modelled as", () => {
  const notice = {
    headline:
      "EC 2.7.1.1 is 5 proteins in human and no --isoform was given; every cited row names GCK, " +
      "so these are GCK's constants, not the other proteins'",
    detail:
      "EC 2.7.1.1 is 5 human proteins (HKDC1, HK1, HK2, HK3, GCK) and no --isoform was given; " +
      "every cited row names GCK, so the model is of GCK",
    remedy: "the model is of GCK, the protein every cited row names: pass --isoform GCK",
  };

  it("is one flag, the concern then what to do", () => {
    const flag = isozymeNoticeFlag(notice)!;
    expect(flag.startsWith("isozymes: EC 2.7.1.1 is 5 human proteins")).toBe(true);
    expect(flag).toContain("the model is of GCK. The model is of GCK");
    expect(isozymeNoticeFlag(null)).toBeUndefined();
  });

  it("reaches the refusal's flags and the Km's note", async () => {
    state.km = { ...KM_BASE, isozymeNotice: notice };
    const err = await refusal();
    expect(err.flags.some((f) => f.startsWith("isozymes: EC 2.7.1.1 is 5 human proteins"))).toBe(true);
    expect(err.parameterProvenance?.["km"]?.note ?? "").toContain("which protein: EC 2.7.1.1 is 5 proteins");
  });
});

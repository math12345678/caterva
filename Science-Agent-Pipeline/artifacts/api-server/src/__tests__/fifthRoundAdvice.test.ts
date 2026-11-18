import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";
import type { RequiredParametersMissingError } from "../lib/provenance";

/**
 * The fifth adversarial round of the real-values work (2026-11-12): advice
 * that leads to a run that succeeds, and the same alternatives as compose.
 *
 * V7-04: an organism whose every row measured a protein variant is not
 * offered behind allowCrossSpecies, which would withhold its rows again
 * (human COX-2's kcat; Mus musculus held one N580A row).
 *
 * V7-08: a compound with no row in the organism is answered with what that
 * organism holds, counted, in compose's words (`availableInTheOrganism`),
 * not the whole page's list.
 */

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return { ...original, resolveKineticValue: vi.fn() };
});

const LDH_QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate in " +
  "Mus musculus vmax=5 s0=10 end=10 points=51";

async function refusalFor(agentResult: unknown) {
  vi.mocked(resolveKineticValue).mockResolvedValueOnce(agentResult as never);
  try {
    await resolveQuery(LDH_QUERY);
  } catch (err) {
    return err as RequiredParametersMissingError;
  }
  throw new Error("expected resolveQuery to refuse, but it returned");
}

describe("advice that would be refused again is not given", () => {
  it("does not offer allowCrossSpecies for organisms holding only a variant's rows", async () => {
    const err = await refusalFor({
      found: false,
      source: "cross_species_withheld",
      crossSpeciesOrganismsAvailable: ["Rattus norvegicus"],
      crossSpeciesVariantOnly: ["Rattus norvegicus"],
      literatureCandidates: [],
      logs: [],
    });
    expect(err.message).toContain("Rattus norvegicus");
    expect(err.message).toContain("protein variant");
    expect(err.message).toContain("would not fill it either");
    expect(err.message).not.toContain("re-run with allowCrossSpecies");
  });

  it("offers the usable organisms and labels the variant-only ones", async () => {
    const err = await refusalFor({
      found: false,
      source: "cross_species_withheld",
      crossSpeciesOrganismsAvailable: ["Oryctolagus cuniculus", "Rattus norvegicus"],
      crossSpeciesVariantOnly: ["Rattus norvegicus"],
      literatureCandidates: [],
      logs: [],
    });
    expect(err.message).toContain("Oryctolagus cuniculus (rows of a protein variant only, withheld: Rattus norvegicus)");
    expect(err.message).toContain("allowCrossSpecies");
  });

  it("says what the organism holds, counted, as compose does", async () => {
    const err = await refusalFor({
      found: false,
      source: "not_found",
      substratesAvailable: ["(S)-lactate", "pyruvate"],
      availableInTheOrganism:
        "BRENDA has no Km row for lactate under EC 1.1.1.27 in Mus musculus; the substrates it " +
        "lists Km rows for there: pyruvate (4 rows). Re-run with --substrate set to one of them, " +
        "or supply it yourself",
      literatureCandidates: [],
      logs: [],
    });
    expect(err.message).toContain("pyruvate (4 rows)");
    expect(err.message).toContain("Name one of them in your query instead");
    expect(err.message).not.toContain("(S)-lactate");
    expect(err.message).not.toContain("--substrate");
  });
});

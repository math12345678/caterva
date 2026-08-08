import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";
import { resolveKineticValue } from "../lib/scienceAgent";

// The golden LDH record: km is populated, ki is NOT. A per-key Ki lookup
// must read the "ki" field only and never borrow km — queryResolver used to
// do `agentResult.km ?? agentResult.ki`, which leaked Km's value into the Ki
// slot whenever the Ki lookup lacked a ki field.
const GOLDEN_LDH_RESULT = {
  found: true,
  km: 10.73,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "740253",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => GOLDEN_LDH_RESULT),
  };
});

// km is user-overridden so only ki flows through kinetic resolution.
const CI_LDH_QUERY =
  "simulate competitive inhibition of lactate dehydrogenase on lactate " +
  "km=2 vmax=5 s0=10 i0=0 end=10 points=51";

const KI_RESULT = {
  found: true,
  ki: 1.2,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "760123",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
  assayConditions: { ph: 7.4, temperatureC: 25 },
  literatureCandidates: [],
  logs: [],
};

describe("Ki resolution — per-key lookup", () => {
  it("resolves ki from literature with its own citation", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce(KI_RESULT);
    const resolved = await resolveQuery(CI_LDH_QUERY);
    expect(resolved.parameters["ki"]).toBe(1.2);
    expect(resolved.parameters["km"]).toBe(2);
    const ki = resolved.parameterProvenance["ki"]!;
    expect(ki.origin).toBe("resolved");
    expect(ki.source).toBe("brenda_exact");
    expect(ki.organism).toBe("Homo sapiens");
    expect(ki.citation).toContain("(ref 760123)");
    expect(ki.citationStatus).toBe("verified");
    const flag = resolved.provenance.flags.find((f) => /resolved ki/i.test(f));
    expect(flag).toMatch(/1\.2/);
  });

  it("a wrong-constant swap is never cross-applied (km must not leak into ki)", async () => {
    // The Ki lookup returns BOTH fields with conflicting values; the per-key
    // rule must pick ki, not borrow km.
    vi.mocked(resolveKineticValue).mockResolvedValueOnce({
      ...KI_RESULT,
      km: 10.73,
      ki: 1.2,
    });
    const resolved = await resolveQuery(CI_LDH_QUERY);
    expect(resolved.parameters["ki"]).toBe(1.2);
    expect(resolved.parameters["ki"]).not.toBe(10.73);
    expect(resolved.parameters["km"]).toBe(2);
  });

  it("a cross-species Ki arrives flagged", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValueOnce({
      ...KI_RESULT,
      organism: "Sus scrofa",
      source: "brenda_cross_species",
      crossSpecies: true,
      citation: { ...KI_RESULT.citation, referenceId: "760001" },
    });
    const resolved = await resolveQuery(CI_LDH_QUERY);
    const ki = resolved.parameterProvenance["ki"]!;
    expect(ki.origin).toBe("resolved");
    expect(ki.organism).toBe("Sus scrofa");
    expect(ki.citationStatus).toBe("flagged");
  });

  it("an unresolved ki is blocked (default-origin hard rule)", async () => {
    // Default mock: GOLDEN_LDH_RESULT carries km but no ki field. The per-key
    // lookup must leave ki at origin "default", which the hard rule rejects.
    await expect(resolveQuery(CI_LDH_QUERY)).rejects.toBeInstanceOf(
      RequiredParametersMissingError,
    );
  });
});

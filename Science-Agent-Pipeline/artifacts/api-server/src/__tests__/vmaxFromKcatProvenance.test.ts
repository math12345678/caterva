import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";
import { resolveKineticValue } from "../lib/scienceAgent";

// ADR 0019: a resolved kcat plus a caller-supplied enzyme_conc bridges to a
// simulable Vmax. These tests mock the science-agent boundary (the Python
// bridge itself is exercised for real in Tests/test_fallback_logic.py's
// kcat tests and in bridge_vmax_from_kcat's own arithmetic, against the
// live-captured AChE fixture, kcat=6500 1/s, ref 649716) and check that
// queryResolver.ts combines the two sources into provenance correctly:
// a literature citation for kcat plus an explicit, uncited note for the
// caller-supplied enzyme_conc half — never silently presented as if the
// whole value were independently verified from literature.

const KM_RESULT = {
  found: true,
  km: 0.05,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "715396",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=3.1.1.7",
  },
  literatureCandidates: [],
  logs: [],
};

const KCAT_RESULT = {
  found: true,
  kcat: 6500,
  vmax: 6.5,
  vmaxValidation: { ok: true, flagged: false },
  unit: "1/s",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  citation: {
    source: "BRENDA",
    referenceId: "649716",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=3.1.1.7",
  },
  assayConditions: { ph: 8, temperatureC: 27 },
  literatureCandidates: [],
  logs: [],
};

const ACHE_QUERY =
  "simulate acetylcholinesterase with substrate acetyl thiocholine " +
  "enzyme_conc=0.001 s0=10 end=10 points=51";

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async (entities: { quantity?: string }) => {
      if (entities.quantity === "kcat") return KCAT_RESULT;
      return KM_RESULT;
    }),
  };
});

describe("Vmax-from-kcat bridge — ADR 0019", () => {
  it("bridges a resolved kcat and a user-supplied enzyme_conc into vmax", async () => {
    const resolved = await resolveQuery(ACHE_QUERY);
    expect(resolved.parameters["vmax"]).toBe(6.5);
    const vmax = resolved.parameterProvenance["vmax"]!;
    expect(vmax.origin).toBe("resolved");
    expect(vmax.citation).toContain("(ref 649716)");
    expect(vmax.citationStatus).toBe("verified");
    // The note must name BOTH halves of the bridge: the cited kcat AND the
    // uncited, caller-supplied enzyme_conc -- never presented as if the
    // whole Vmax were independently verified from literature alone.
    expect(vmax.note).toContain("6500");
    expect(vmax.note).toContain("0.001");
    expect(vmax.note).toMatch(/never resolved or.*defaulted/);
  });

  it("with no enzyme_conc override, the bridge never fires and vmax stays blocked", async () => {
    // No enzyme_conc means applyVmaxFromKcatResolution returns immediately
    // without calling resolveKineticValue at all -- vmax has no other way
    // to resolve in this domain, so the existing hard-block rule (no
    // simulation runs on an origin:"default" parameter) correctly rejects
    // the query, exactly as it would have before this bridge existed.
    const query =
      "simulate acetylcholinesterase with substrate acetyl thiocholine " +
      "s0=10 end=10 points=51";
    await expect(resolveQuery(query)).rejects.toBeInstanceOf(
      RequiredParametersMissingError,
    );
  });

  it("an explicit user-supplied vmax always wins over the bridge", async () => {
    const query =
      "simulate acetylcholinesterase with substrate acetyl thiocholine " +
      "enzyme_conc=0.001 vmax=99 s0=10 end=10 points=51";
    const resolved = await resolveQuery(query);
    expect(resolved.parameters["vmax"]).toBe(99);
    expect(resolved.parameterProvenance["vmax"]!.origin).toBe("user");
  });

  it("a rejected enzyme_conc (validation ok=false) does not fabricate a vmax", async () => {
    // vmaxValidation.ok=false must never produce a "resolved" vmax --
    // and with no other way for vmax to resolve in this domain, the
    // existing hard-block rule correctly rejects the query rather than
    // silently falling back to a default Vmax nobody chose.
    vi.mocked(resolveKineticValue).mockImplementation(async (entities: any) => {
      if (entities.quantity === "kcat") {
        return {
          ...KCAT_RESULT,
          vmax: undefined,
          vmaxValidation: { ok: false, flagged: false, reason: "enzyme_conc must be positive" },
        };
      }
      return KM_RESULT;
    });
    await expect(resolveQuery(ACHE_QUERY)).rejects.toBeInstanceOf(
      RequiredParametersMissingError,
    );
  });
});

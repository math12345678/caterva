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

  it("an [E]0 stated in words reaches the bridge, so a plain question runs", async () => {
    // This is the whole point of the bridge finally being reachable.
    //
    // Measured before this: EVERY plain-language enzyme-kinetics question
    // failed on "vmax could not be resolved from literature", because the
    // only way to supply [E]0 was the CLI syntax `enzyme_conc=0.001`. A
    // researcher describing their assay in a sentence could not get a
    // simulation out of this system at all -- the kcat half was sitting
    // in BRENDA the whole time, waiting on a number the user was perfectly
    // willing to state, just not in that notation.
    //
    // "1 uM enzyme" is 0.001 mM, and it must arrive as origin "user":
    // reading it out of prose is the user supplying it (grammar differs,
    // provenance does not), never Caterva inferring it. ADR 0013 stands.
    const resolved = await resolveQuery(
      "simulate acetylcholinesterase with 10 mM acetylthiocholine and " +
        "1 uM enzyme for 10 seconds",
    );
    expect(resolved.parameters["vmax"]).toBe(6.5);
    expect(resolved.parameterProvenance["vmax"]!.origin).toBe("resolved");
    expect(resolved.parameterProvenance["vmax"]!.note).toContain("0.001");

    expect(resolved.parameters["enzyme_conc"]).toBeCloseTo(0.001, 15);
    expect(resolved.parameterProvenance["enzyme_conc"]!.origin).toBe("user");

    // And the substrate is the SUBSTRATE, not the enzyme -- the two
    // concentrations in that sentence are 10,000x apart.
    expect(resolved.parameters["s0"]).toBe(10);
  });

  it("explains the [E]0 route instead of telling the user to go find a Vmax", async () => {
    // The generic refusal ("vmax could not be resolved from literature.
    // Add vmax=<value>") does not merely omit the bridge -- it recommends
    // the wrong action. A Vmax copied out of a paper was measured at that
    // paper's enzyme concentration; dropping it into a run at a different
    // [E]0 is wrong by the ratio of the two, and nothing downstream can
    // tell. So the refusal has to name the actual route.
    const query =
      "simulate acetylcholinesterase with 10 mM acetylthiocholine for 10 seconds";
    await expect(resolveQuery(query)).rejects.toThrow(
      /enzyme concentration/i,
    );
    await expect(resolveQuery(query)).rejects.toThrow(/kcat/);
  });

  it("an explicit user-supplied vmax always wins over the bridge", async () => {
    const query =
      "simulate acetylcholinesterase with substrate acetyl thiocholine " +
      "enzyme_conc=0.001 vmax=99 s0=10 end=10 points=51";
    const resolved = await resolveQuery(query);
    expect(resolved.parameters["vmax"]).toBe(99);
    expect(resolved.parameterProvenance["vmax"]!.origin).toBe("user");
  });

  // ---- when the bridge fails, say WHICH of the three things happened --
  //
  // All three used to push their reason into `flags`. But flags ride on a
  // SUCCESSFUL result, and a failed bridge means vmax stays origin
  // "default" and the hard block throws -- taking the flags with it. So
  // the system computed a specific, actionable reason and then discarded
  // it, leaving the user the generic "vmax could not be resolved from
  // literature". Measured on real queries: lactate dehydrogenase and
  // catalase both fail here, for different reasons, and neither said so.

  it("says the literature holds no kcat, rather than blaming Vmax", async () => {
    vi.mocked(resolveKineticValue).mockImplementation(async (entities: any) =>
      entities.quantity === "kcat"
        ? { found: false, literatureCandidates: [], logs: [] }
        : KM_RESULT,
    );
    const err = await resolveQuery(ACHE_QUERY).catch((e: Error) => e);
    expect(err).toBeInstanceOf(RequiredParametersMissingError);
    // Names the actual gap...
    expect((err as Error).message).toMatch(/no kcat for this enzyme/i);
    // ...and what to do about it. Promoting this note replaces the
    // generic "Add vmax=<value>" line, so the note has to carry its own
    // instruction or the user is left worse off than before.
    expect((err as Error).message).toMatch(/kcat=<value>/);
    expect((err as Error).message).toMatch(/--cite/);
  });

  it("distinguishes a rejected enzyme_conc from a missing one", async () => {
    // The user HAS stated an enzyme concentration. Telling them to state
    // one reads as the system not listening; the actionable fact is the
    // validator's reason.
    vi.mocked(resolveKineticValue).mockImplementation(async (entities: any) =>
      entities.quantity === "kcat"
        ? {
            ...KCAT_RESULT,
            vmax: undefined,
            vmaxValidation: {
              ok: false,
              flagged: false,
              reason: "enzyme_conc is implausibly high for an enzyme",
            },
          }
        : KM_RESULT,
    );
    const err = await resolveQuery(ACHE_QUERY).catch((e: Error) => e);
    expect((err as Error).message).toMatch(/implausibly high/);
    expect((err as Error).message).toMatch(/kcat is not the problem/i);
    // It must NOT ask for the thing that was already given.
    expect((err as Error).message).not.toMatch(/State the enzyme concentration/i);
  });

  it("says an uncheckable citation was declined, not that nothing was found", async () => {
    // A kcat WAS found. Refusing it for having no locator is a policy this
    // code applied, and the generic "could not be resolved from
    // literature" reports that as the literature being silent.
    vi.mocked(resolveKineticValue).mockImplementation(async (entities: any) =>
      entities.quantity === "kcat"
        ? { ...KCAT_RESULT, citation: { source: "BRENDA" } }
        : KM_RESULT,
    );
    const err = await resolveQuery(ACHE_QUERY).catch((e: Error) => e);
    expect((err as Error).message).toMatch(/no reference id or URL/i);
    expect((err as Error).message).toMatch(/6500/); // the value that was found
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

/**
 * Regressions for four defects in what the API reports about its own rigour.
 *
 * Each was invisible to a green suite because the existing tests asserted
 * that fields EXIST rather than what they say.
 *
 * 1. `/simulate/:jobId/audit` returned `jobId: ""` for every job. The route
 *    test asserted five other properties and never looked at this one.
 *
 * 2. `strendaCompliant` was stamped on EVERY numeric parameter of an mm-ish
 *    domain, including `end` and `points` — a STRENDA verdict on an
 *    integration window. That is ADR 0021's error (the standard governs
 *    enzyme kinetic constants only) resurfacing at a route that bypassed
 *    the guard ADR 0021 installed in `provenance.ts`.
 *
 * 3. `getDomainCitation` returned the placeholder `"Domain: monte_carlo_pi"`
 *    for domains absent from DOMAIN_LITERATURE_MAP, and callers pushed it
 *    straight into `provenance.modelCitations`. A label shipped to the
 *    client inside the list of citations backing a scientific result.
 *
 * 4. The dashboard's `publicationBlocked` tested `origin === "llm"` alone,
 *    ignoring `default` — which the hard rule blocks identically. A job
 *    carrying an unverified default counted as publication-ready.
 */
import { describe, expect, it } from "vitest";

import { getDomainCitation, DOMAIN_LITERATURE_MAP } from "../lib/domain-literature";
import { STRENDA_GOVERNED_FIELDS, unverifiedOriginKeys } from "../lib/provenance";

describe("domain citations are citations, not labels", () => {
  it("returns undefined rather than a placeholder for an unmapped domain", () => {
    // "sbml" is the raw-SBML escape hatch: the caller supplies the model,
    // so Caterva has nothing of its own to cite.
    expect(getDomainCitation("sbml")).toBeUndefined();
    expect(getDomainCitation("not_a_real_domain")).toBeUndefined();
  });

  it("never returns a string beginning 'Domain:'", () => {
    // The exact placeholder that reached modelCitations.
    const domains = [
      "sbml",
      "monte_carlo_pi",
      "gillespie_ssa_replicates",
      "unknown_domain",
    ];

    // Collected, then asserted in one shot. Per-domain
    // `if (citation !== undefined)` would skip every check the day
    // getDomainCitation started returning undefined for everything -- the
    // regression the test exists to catch would make it pass.
    const placeholders = domains
      .map((domain) => [domain, getDomainCitation(domain)] as const)
      .filter(([, citation]) => citation?.startsWith("Domain:"))
      .map(([domain]) => domain);

    expect(
      placeholders,
      "these domains returned the 'Domain: <name>' placeholder, which is a " +
        "label rather than a citation and must never reach modelCitations",
    ).toEqual([]);
  });

  it("the domains that were missing now have real literature", () => {
    // They were dispatchable and simulable, but had no entry, which is why
    // the placeholder was reachable at all. (monte_carlo_pi was the other
    // one; it was archived on 2026-09-27.)
    for (const domain of ["gillespie_ssa_replicates"]) {
      const entry = DOMAIN_LITERATURE_MAP[domain];
      expect(entry, `${domain} has no literature entry`).toBeDefined();
      expect(entry!.references.length).toBeGreaterThan(0);
      const citation = getDomainCitation(domain);
      expect(citation).toBeDefined();
      // A real citation names an author and a year.
      expect(citation).toMatch(/\d{4}/);
    }
  });

  it("a domain's justification never claims a source for its numbers", () => {
    // Eight defaultJustification strings said "per <Author>" for values
    // those papers do not contain; four also stated numbers that did not
    // match DOMAIN_DEFAULTS. The pattern is banned outright.
    for (const [domain, entry] of Object.entries(DOMAIN_LITERATURE_MAP)) {
      expect(
        entry.defaultJustification,
        `${domain} attributes its default VALUES to a paper`,
      ).not.toMatch(/\)\s+per\s+[A-Z]/);
    }
  });
});

describe("STRENDA applies only to enzyme kinetic constants", () => {
  it("the governed set does not include presentational parameters", () => {
    for (const notKinetic of ["end", "points", "s0", "seed", "n_replicates"]) {
      expect(
        STRENDA_GOVERNED_FIELDS.has(notKinetic),
        `${notKinetic} is not an enzyme kinetic constant`,
      ).toBe(false);
    }
  });

  it("the governed set contains exactly the kinetic constants", () => {
    for (const kinetic of ["km", "ki", "kcat", "vmax"]) {
      expect(STRENDA_GOVERNED_FIELDS.has(kinetic)).toBe(true);
    }
  });
});

describe("publication readiness uses the hard rule's own predicate", () => {
  it("a default-origin parameter blocks publication", () => {
    // The hard rule (unverifiedOriginKeys) treats `default` and `llm`
    // identically. The dashboard checked only `llm`.
    const blocked = unverifiedOriginKeys({
      km: { origin: "resolved", source: "brenda", citation: "BRENDA (ref 1)" },
      vmax: { origin: "default" },
    });
    expect(blocked).toContain("vmax");
  });

  it("an llm-origin parameter blocks publication", () => {
    const blocked = unverifiedOriginKeys({
      km: { origin: "llm", note: "model-supplied" },
    });
    expect(blocked).toContain("km");
  });

  it("user and resolved origins do not block", () => {
    const blocked = unverifiedOriginKeys({
      km: { origin: "resolved", source: "brenda", citation: "BRENDA (ref 1)" },
      s0: { origin: "user" },
    });
    expect(blocked).toEqual([]);
  });
});

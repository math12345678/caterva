import { describe, expect, it } from "vitest";
import { auditForPublication } from "../lib/literature-verifier";

describe("publication readiness is decided by canPublish, per parameter", () => {
  it("does NOT call keyword-matched values plus a default publication-ready", () => {
    // The exact case the audit found: two flagged (keyword-matched, no DOI)
    // and one unverifiable (a system default). The old boolean returned
    // true and summarised it as "Publication ready: 0 verified, 2 with
    // literature backing".
    const audit = auditForPublication({
      km: { level: "flagged", message: "keyword match - use as estimate only" } as never,
      vmax: { level: "flagged", message: "keyword match - use as estimate only" } as never,
      s0: { level: "unverifiable", message: "system default" } as never,
    });

    expect(audit.readyToPublish).toBe(false);
    expect(audit.summary).toMatch(/not ready/i);
  });

  it("accepts a flagged value that carries a DOI", () => {
    // canPublish's own rule: flagged is fine IF it can be cited.
    const audit = auditForPublication({
      km: {
        level: "flagged",
        message: "literature value",
        reference: { doi: "10.1073/pnas.88.16.7328" },
      } as never,
    });
    expect(audit.readyToPublish).toBe(true);
  });

  it("blocks an unverifiable MEASURED quantity even with no pending ones", () => {
    // km is a property of the enzyme: somebody measured it, so an
    // unverifiable km cannot appear in a paper uncited.
    const audit = auditForPublication({
      km: { level: "unverifiable", message: "no source" } as never,
      vmax: { level: "verified", message: "ok" } as never,
    });
    expect(audit.readyToPublish).toBe(false);
  });

  it("does NOT block on an experimental condition, which cannot be cited", () => {
    // The counterpart, and the distinction that matters: a paper STATES
    // its substrate concentration, it does not cite one. Requiring a
    // citation for s0 is the same category error that made Layer 1 reject
    // every run with "Parameter 's0' has no literature backing".
    const audit = auditForPublication({
      km: { level: "verified", message: "ok" } as never,
      s0: { level: "unverifiable", message: "user supplied" } as never,
    });
    expect(audit.readyToPublish).toBe(true);
  });

  it("is not publication-ready with no parameters at all", () => {
    // An empty set is not a set that passed.
    expect(auditForPublication({}).readyToPublish).toBe(false);
  });
});

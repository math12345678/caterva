/**
 * The literature endpoint must not claim more than the data supports.
 *
 * GET /api/pipeline/literature answered, verbatim:
 *
 *   "All parameters in Caterva are backed by peer-reviewed scientific
 *    literature. Every domain has primary references with DOI."
 *
 * Both halves were false, and the second is checkable in one pass over
 * the endpoint's own data: four domains carry NO reference with a DOI,
 * because their primary sources are books or predate DOI assignment
 * (Copeland 2013, Anderson & May 1991, Lotka 1925).
 *
 * The first half was false BY DESIGN, which is the worse one. Parameters
 * carry a provenance origin: "resolved" came from literature, "user" came
 * from the person asking, and "llm"/"default" are BLOCKED rather than
 * reported. A product whose entire pitch is that it refuses to invent
 * numbers should not advertise that every number is literature-backed --
 * the refusals are the feature, and this sentence sold them as absent.
 *
 * These tests check the CLAIM against the DATA rather than pinning a
 * string, so the endpoint cannot drift back by either route: rewording
 * the promise, or losing the references that make the weaker promise
 * true.
 */
import { describe, expect, it } from "vitest";
import request from "supertest";

import app from "../app";
import { DOMAIN_LITERATURE_MAP } from "../lib/domain-literature";

describe("GET /api/pipeline/literature does not overclaim", () => {
  it("does not say every parameter is literature-backed", async () => {
    const res = await request(app).get("/api/pipeline/literature");
    expect(res.status).toBe(200);
    expect(res.body.message).not.toMatch(/all parameters/i);
    // The specific promise the provenance system exists to NOT make.
    expect(res.body.message).not.toMatch(
      /every domain has primary references with DOI/i,
    );
  });

  it("says instead that a parameter's origin decides, and refusal is possible", async () => {
    // Asserted positively: a message that merely stopped overclaiming
    // would pass the check above while telling the reader nothing.
    const res = await request(app).get("/api/pipeline/literature");
    expect(res.body.message).toMatch(/refused/i);
    expect(res.body.message).toMatch(/provenance|origin/i);
  });

  it("the weaker claim it now makes is true: every domain has a reference", async () => {
    const res = await request(app).get("/api/pipeline/literature");
    const domains = res.body.domains as { domain: string }[];
    expect(domains.length).toBeGreaterThan(5);

    for (const { domain } of domains) {
      const entry = DOMAIN_LITERATURE_MAP[domain];
      expect(entry, `${domain} is served with no literature entry`).toBeDefined();
      expect(
        entry!.references.length,
        `${domain} is served with zero references`,
      ).toBeGreaterThan(0);
    }
  });

  it("and the stronger claim it dropped is still false", async () => {
    // The premise of the correction, pinned. If every reference ever DID
    // acquire a DOI, the old sentence would become true and this test
    // should be re-read deliberately rather than quietly passing.
    const withoutDoi = Object.entries(DOMAIN_LITERATURE_MAP)
      .filter(([, entry]) => entry.references.every((r) => !r.doi))
      .map(([domain]) => domain);

    expect(
      withoutDoi.length,
      "every domain now has a DOI-bearing reference, so the claim this " +
        "endpoint dropped would now be true -- re-read the message",
    ).toBeGreaterThan(0);
  });
});

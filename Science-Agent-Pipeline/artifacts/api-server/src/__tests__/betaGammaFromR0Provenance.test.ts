import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { RequiredParametersMissingError } from "../lib/provenance";

// ADR 0017 / ADR 0020: a recognized disease name bridges a literature
// (R0, infectious period) pair to the SIR engine's own (beta, gamma).
// Unlike the Ki/kcat tests, this is NOT mocked at the science-agent
// boundary -- it spawns the real Python bridge and reads the real
// Tests/epidemiology_resolver.py registry, so a passing test here is a
// genuine end-to-end proof, not a fixture replay.

describe("beta/gamma-from-R0 bridge — ADR 0017 / ADR 0020 (real, unmocked)", () => {
  it("bridges COVID-19's real (R0, infectious period) into beta/gamma", async () => {
    const query =
      "simulate covid-19 outbreak s0=990 i0=10 r0_recovered=0 end=100 points=101";
    const resolved = await resolveQuery(query);
    expect(resolved.domain).toBe("sir");
    // Hussein et al. (2021): R0=3.14, infectious_period=5.45 days ->
    // gamma = 1/5.45, beta = R0 * gamma.
    expect(resolved.parameters["gamma"]).toBeCloseTo(1 / 5.45, 6);
    expect(resolved.parameters["beta"]).toBeCloseTo(3.14 * (1 / 5.45), 6);

    const beta = resolved.parameterProvenance["beta"]!;
    const gamma = resolved.parameterProvenance["gamma"]!;
    expect(beta.origin).toBe("resolved");
    expect(gamma.origin).toBe("resolved");
    expect(beta.citationStatus).toBe("verified");
    expect(beta.citation).toContain("33214421"); // Hussein et al. PMID
    expect(beta.note).toContain("3.14");
    expect(beta.note).toContain("5.45");
  }, 20000);

  it("an unrecognized disease leaves beta/gamma unresolved (hard-blocked)", async () => {
    // "measles outbreak" matches the sir keyword path but not any entry in
    // DISEASES/the registry -- must fail honestly, never fabricate an R0.
    const query = "simulate measles outbreak s0=990 i0=10 r0_recovered=0 end=100 points=101";
    await expect(resolveQuery(query)).rejects.toBeInstanceOf(
      RequiredParametersMissingError,
    );
  }, 20000);

  it("an explicit user-supplied beta/gamma always wins over the bridge", async () => {
    const query =
      "simulate covid-19 outbreak beta=0.99 gamma=0.5 s0=990 i0=10 r0_recovered=0 end=100 points=101";
    const resolved = await resolveQuery(query);
    expect(resolved.parameters["beta"]).toBe(0.99);
    expect(resolved.parameters["gamma"]).toBe(0.5);
    expect(resolved.parameterProvenance["beta"]!.origin).toBe("user");
    expect(resolved.parameterProvenance["gamma"]!.origin).toBe("user");
  }, 20000);

  it("supplying only one of beta/gamma skips the bridge entirely (no mixed sourcing)", async () => {
    // beta is user-supplied, gamma is not -- the bridge must not fill in
    // gamma from literature while beta comes from the user; the whole pair
    // stays from one source or the other, so this should hard-block on the
    // missing gamma rather than silently combining incompatible sources.
    const query =
      "simulate covid-19 outbreak beta=0.99 s0=990 i0=10 r0_recovered=0 end=100 points=101";
    await expect(resolveQuery(query)).rejects.toBeInstanceOf(
      RequiredParametersMissingError,
    );
  }, 20000);
});

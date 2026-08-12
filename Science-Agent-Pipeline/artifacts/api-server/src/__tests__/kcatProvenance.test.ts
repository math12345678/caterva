/**
 * kcat and enzyme_conc must carry provenance like every other parameter.
 *
 * ADR 0008 requires exactly one provenance entry per key in `parameters`,
 * and `resolveQuery` throws on any violation. So a parameter that reaches
 * `parameters` without a provenance entry is not a cosmetic gap -- it is a
 * 500, which is precisely how the STRENDA rule broke the resolver earlier
 * in Stage 8 (enforcement landed ahead of its producer).
 *
 * Confirmed against the compiled module before these tests were written:
 * feeding `run_mm`'s echoed output (which includes kcat and enzyme_conc)
 * to `validateParameterProvenance` with resolver-built provenance produced
 *
 *     kcat has a parameter value but no provenance
 *     enzyme_conc has a parameter value but no provenance
 *
 * The question these tests answer is whether that state is *reachable*.
 */

import { describe, expect, it } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { validateParameterProvenance } from "../lib/provenance";

describe("kcat/enzyme_conc provenance (ADR 0008 x ADR 0013)", () => {
  it("a query supplying kcat and enzyme_conc gets provenance for both", async () => {
    const resolved = await resolveQuery(
      "simulate enzyme kinetics kcat=118 enzyme_conc=0.00001 km=2 vmax=5 s0=10 end=10 points=51",
    );

    expect(resolved.domain).toBe("mm");
    // Both must appear in parameters -- otherwise the query silently did
    // nothing and the rest of this test is vacuous.
    expect(resolved.parameters).toHaveProperty("kcat");
    expect(resolved.parameters).toHaveProperty("enzyme_conc");

    // ...and both must carry provenance. They came from the query, so
    // `user` is the honest origin: a value the person typed, not one this
    // project chose (`default`) or a model invented (`llm`).
    expect(resolved.parameterProvenance["kcat"]?.origin).toBe("user");
    expect(resolved.parameterProvenance["enzyme_conc"]?.origin).toBe("user");
  });

  it("the resolved provenance satisfies the ADR 0008 contract", async () => {
    const resolved = await resolveQuery(
      "simulate enzyme kinetics kcat=118 enzyme_conc=0.00001 km=2 vmax=5 s0=10 end=10 points=51",
    );
    // resolveQuery throws on violations, so reaching here already proves a
    // lot -- but assert explicitly rather than relying on absence of throw.
    expect(
      validateParameterProvenance(
        resolved.parameters,
        resolved.parameterProvenance,
      ),
    ).toEqual([]);
  });

  it("enzyme_conc is never resolved from literature", async () => {
    /**
     * ADR 0013: [E]0 is a property of an EXPERIMENT, not of an enzyme.
     * BRENDA reports the conditions a turnover number was measured under,
     * not how much enzyme a student is about to put in a tube.
     *
     * So it must never arrive as `origin: "resolved"`. If it ever does,
     * something is inventing an assay.
     */
    const resolved = await resolveQuery(
      "simulate lactate dehydrogenase km=2 enzyme_conc=0.00001 vmax=5 s0=10 end=10 points=51",
    );
    const provenance = resolved.parameterProvenance["enzyme_conc"];

    // Stated unconditionally. `enzyme_conc` is absent from RESOLVABLE_FIELDS,
    // so the entry is `undefined` BY DESIGN -- which is exactly why an
    // `if (provenance)` guard here would never run its body, and the test
    // would pass without checking anything.
    expect(
      provenance === undefined || provenance.origin !== "resolved",
      "enzyme_conc must never arrive as origin 'resolved': [E]0 is a property " +
        "of an experiment, not of an enzyme (ADR 0013)",
    ).toBe(true);
    expect(provenance?.citation).toBeUndefined();
  });

  it("kcat and enzyme_conc are not resolvable fields", async () => {
    /**
     * ADR 0012/0013 stop deliberately short of RESOLVABLE_FIELDS. kcat has
     * a lookup path in the literature layer, but resolving one still does
     * not produce a simulable parameter on its own -- it needs an [E]0 the
     * caller supplies. The narrowness note must therefore stay true.
     */
const resolved = await resolveQuery(
      "simulate lactate dehydrogenase km=2 vmax=5 s0=10 end=10 points=51",
    );
    const origins = ["kcat", "enzyme_conc"].map(
      (key) => resolved.parameterProvenance[key]?.origin,
    );

    // Compared as a whole, so the assertion runs whether the entries exist or
    // not. `undefined` (never populated) and any non-"resolved" origin both
    // satisfy the narrowness note; only "resolved" violates it.
    expect(
      origins.filter((origin) => origin === "resolved"),
      "kcat/enzyme_conc are outside RESOLVABLE_FIELDS: resolving a turnover " +
        "number does not yield a simulable parameter without an [E]0 the " +
        "caller supplies (ADR 0012/0013)",
    ).toEqual([]);
  });

  it("a plain mm query carries neither key", async () => {
    /**
     * The pairing that keeps the tests above honest. If kcat and
     * enzyme_conc leaked into every mm request, the first test would pass
     * for the wrong reason -- and every default simulation would claim a
     * turnover number nobody supplied.
     */
    const resolved = await resolveQuery(
      "simulate enzyme kinetics km=2 vmax=5 s0=10 end=10 points=51",
    );
    expect(resolved.parameters).not.toHaveProperty("kcat");
    expect(resolved.parameters).not.toHaveProperty("enzyme_conc");
    expect(
      validateParameterProvenance(
        resolved.parameters,
        resolved.parameterProvenance,
      ),
    ).toEqual([]);
  });
});

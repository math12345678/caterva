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
      "simulate enzyme kinetics kcat=118 enzyme_conc=0.00001",
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
      "simulate enzyme kinetics kcat=118 enzyme_conc=0.00001",
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
      "simulate lactate dehydrogenase enzyme_conc=0.00001",
    );
    const provenance = resolved.parameterProvenance["enzyme_conc"];
    if (provenance) {
      expect(provenance.origin).not.toBe("resolved");
      expect(provenance.citation).toBeUndefined();
    }
  });

  it("kcat and enzyme_conc are not resolvable fields", async () => {
    /**
     * ADR 0012/0013 stop deliberately short of RESOLVABLE_FIELDS. kcat has
     * a lookup path in the literature layer, but resolving one still does
     * not produce a simulable parameter on its own -- it needs an [E]0 the
     * caller supplies. The narrowness note must therefore stay true.
     */
    const resolved = await resolveQuery("simulate lactate dehydrogenase");
    for (const key of ["kcat", "enzyme_conc"]) {
      const provenance = resolved.parameterProvenance[key];
      if (provenance) {
        expect(provenance.origin).not.toBe("resolved");
      }
    }
  });

  it("a plain mm query carries neither key", async () => {
    /**
     * The pairing that keeps the tests above honest. If kcat and
     * enzyme_conc leaked into every mm request, the first test would pass
     * for the wrong reason -- and every default simulation would claim a
     * turnover number nobody supplied.
     */
    const resolved = await resolveQuery("simulate enzyme kinetics");
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

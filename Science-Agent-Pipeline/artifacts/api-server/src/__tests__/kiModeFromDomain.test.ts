/**
 * The Ki lookup carries the model's inhibition mode, and a refusal for lack
 * of a row of that mode says which modes exist.
 *
 * BRENDA ref 739793 gives human LDH two Ki values for one quinoline
 * sulfonamide, from one paper: 0.00059 mM "competitive versus NADH" and
 * 0.00252 mM "noncompetitive versus pyruvate". The runner used to take the
 * lower whatever the model was. It now ranks the rows by the model's mode
 * with the ranking `caterva compose` uses (fallback_logic, inhibition_mode=),
 * and this side only has to send the mode and the model's substrate, and
 * explain the refusal that can come back. The ranking itself is tested on
 * the committed BRENDA pages in Tests/test_ki_mode_resolution.py.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  buildUnresolvedKineticProvenanceForTest as build,
  extractInhibitor,
  resolveQuery,
  rowScopeFlags,
} from "../lib/queryResolver";
import { KI_MODE_OF_DOMAIN, RESOLVABLE_FIELDS } from "../lib/provenance";
import { resolveKineticValue, type ScienceAgentResult } from "../lib/scienceAgent";

const QUINOLINE =
  "3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid";

/**
 * What the runner answers when every Ki row states another mode: rabbit
 * erythrocyte hexokinase and MgADP- (BRENDA ref 640206), whose only Ki rows
 * are 3 mM "mixed inhibitor versus MgATP2-" and 7.8 mM "mixed inhibitor
 * versus glucose", refused for a competitive model. The strings are the
 * resolver's own for that case (Tests/test_ki_mode_resolution.py,
 * TestMixed.test_a_competitive_model_is_refused, on the recorded page).
 */
const MIXED_ONLY: ScienceAgentResult = {
  found: false,
  source: "mode_withheld",
  modesAvailable: ["mixed inhibition versus MgATP2-", "mixed inhibition versus glucose"],
  literatureCandidates: [],
  logs: [],
};

const NOT_FOUND: ScienceAgentResult = {
  found: false,
  source: "not_found",
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return { ...original, resolveKineticValue: vi.fn(async () => NOT_FOUND) };
});

type Sent = {
  quantity: string;
  substrate?: string;
  inhibitionMode?: string;
  modelSubstrate?: string;
};

describe("the domain's mode goes with the Ki lookup, and only with it", () => {
  const mocked = vi.mocked(resolveKineticValue);
  beforeEach(() => mocked.mockClear());
  const settle = (p: Promise<unknown>) => p.then(() => "", (e: Error) => e.message);

  it("reads the quinoline sulfonamide's name whole", () => {
    expect(
      extractInhibitor(`competitive inhibition of human lactate dehydrogenase by ${QUINOLINE} with pyruvate`),
    ).toBe(QUINOLINE);
  });

  it("sends competitive, and the model's substrate beside the inhibitor", async () => {
    await settle(
      resolveQuery(`competitive inhibition of human lactate dehydrogenase by ${QUINOLINE} with pyruvate`),
    );
    const calls = mocked.mock.calls.map(([arg]) => arg as Sent);
    const ki = calls.find((c) => c.quantity === "ki");
    const km = calls.find((c) => c.quantity === "km");
    expect(ki).toMatchObject({
      substrate: QUINOLINE,
      inhibitionMode: "competitive",
      modelSubstrate: "pyruvate",
    });
    // A mode says nothing about a Km, and a Km payload stays the one the
    // recorded HTTP fixtures were made for.
    expect(km?.substrate).toBe("pyruvate");
    expect(km).not.toHaveProperty("inhibitionMode");
    expect(km).not.toHaveProperty("modelSubstrate");
  });

  it("sends no mode for a domain that is not an inhibition model", async () => {
    await settle(resolveQuery("michaelis menten kinetics for hexokinase with glucose"));
    const calls = mocked.mock.calls.map(([arg]) => arg as Sent);
    expect(calls.length).toBeGreaterThan(0);
    expect(calls.every((c) => c.inhibitionMode === undefined)).toBe(true);
  });

  it("every domain that resolves a Ki names the mode its model is", () => {
    const withKi = Object.entries(RESOLVABLE_FIELDS)
      .filter(([, keys]) => keys.includes("ki"))
      .map(([domain]) => domain);
    expect(withKi).toEqual(["mm_competitive_inhibition"]);
    for (const domain of withKi) {
      expect(KI_MODE_OF_DOMAIN[domain]).toBeDefined();
    }
    expect(KI_MODE_OF_DOMAIN["mm_competitive_inhibition"]).toBe("competitive");
  });
});

describe("a refusal by mode names the modes that exist", () => {
  const mocked = vi.mocked(resolveKineticValue);
  const settle = (p: Promise<unknown>) => p.then(() => "", (e: Error) => e.message);

  it("reaches the reader through the missing-parameter error", async () => {
    // The API's organism table has no rabbit, so the query cannot name the
    // system the refusal above is from; what is tested is that the runner's
    // refusal becomes the reader's sentence. km is supplied so the Ki is the
    // only lookup.
    mocked.mockImplementation(async (entities) =>
      (entities as Sent).quantity === "ki" ? MIXED_ONLY : NOT_FOUND,
    );
    const refusal = await settle(
      resolveQuery(
        "competitive inhibition of hexokinase by MgADP- with glucose km=0.1 vmax=1 s0=1 i0=1",
      ),
    );
    expect(refusal).toContain(
      "every KI BRENDA holds for this system states another inhibition mode " +
        "(mixed inhibition versus MgATP2-; mixed inhibition versus glucose)",
    );
    expect(refusal).toContain("This model is competitive inhibition");
    // The generic sentence would say the literature has no value, which is
    // false: it has two, of another mechanism.
    expect(refusal).not.toContain("Could not resolve a real KI");
  });

  it("says why none was used and what the reader can do", () => {
    const p = build(
      "ki", "mode_withheld", MIXED_ONLY.modesAvailable,
      undefined, undefined, undefined, "competitive",
    );
    expect(p.unresolvedReason).toBe("mode_withheld");
    expect(p.origin).toBe("default");
    expect(p.note).toBe(
      "This model is competitive inhibition, and every KI BRENDA holds for this system " +
        "states another inhibition mode (mixed inhibition versus MgATP2-; mixed inhibition " +
        "versus glucose). A KI belongs to the mechanism it was measured under, so none of " +
        "these is this model's KI, and none was used. Supply ki= with a competitive " +
        "constant to run the model.",
    );
  });
});

describe("rowScopeFlags names a Kitz-Wilson row for what it is", () => {
  // BRENDA ref 702238's MAO-B phenylhydrazine row: "determined from
  // Kitz-Wilson plots", the K_I of an irreversible inactivation.
  it("instead of calling it only unstated", () => {
    const flags = rowScopeFlags("ki", {
      isoform: "MAO-B", inhibitionMode: "unstated", versus: null, kitzWilson: true,
    });
    expect(flags).toContain(
      "KI: the source row was determined from Kitz-Wilson plots, which give the K_I of an " +
        "irreversible inactivation, not a reversible Ki; it states no inhibition mode.",
    );
    expect(flags.join(" ")).not.toContain("which binding event it measured is unknown");
  });

  it("and says nothing of it for a row that is not one", () => {
    const flags = rowScopeFlags("ki", {
      isoform: null, inhibitionMode: "unstated", versus: null, kitzWilson: false,
    });
    expect(flags.join(" ")).not.toContain("Kitz-Wilson");
  });
});

/**
 * The kcat a Vmax is bridged from is said for what its row measured, as the
 * Km is (review of the web fixes, 2026-11-12, live).
 *
 * "HK2 with glucose with 50 nM enzyme" carried Km 0.37 mM from the
 * hexokinase II row (BRENDA ref 702867) and bridged Vmax from kcat 60.4 1/s,
 * BRENDA ref 703624: a glucokinase paper's "wild type enzyme" row, which
 * names no isoform. The Km's row scope was said; the kcat's was not, so the
 * response read as an HK2 Km and an HK2 kcat. The CLI said it
 * (rowScopeLines); the API now says it the same way.
 *
 * Offline: the stand-in reader answers with compose's recorded reading of
 * "HK2 with glucose", and the runner is mocked with the two rows.
 */
import path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

const citation = (ref: string) => ({ source: "BRENDA", referenceId: ref, url: "https://www.brenda-enzymes.org/" });

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async (req: { quantity: string }) =>
      req.quantity === "kcat"
        ? {
            found: true, kcat: 60.4, vmax: 0.00302, vmaxValidation: { ok: true },
            unit: "1/s", organism: "Homo sapiens", source: "brenda_exact",
            citation: citation("703624"),
            rowScope: { isoform: null, inhibitionMode: "unstated", versus: null, kitzWilson: false },
            literatureCandidates: [], logs: [],
          }
        : {
            found: true, km: 0.37, unit: "mM", organism: "Homo sapiens", source: "brenda_exact",
            citation: citation("702867"),
            rowScope: { isoform: "HK-II", inhibitionMode: "unstated", versus: null, kitzWilson: false, sameIsoformAsRequested: true },
            literatureCandidates: [], logs: [],
          },
    ),
  };
});

const here = path.dirname(fileURLToPath(import.meta.url));
const STANDIN = path.join(here, "fixtures", "sentence_reader_standin.py");

describe("the bridged kcat's row", () => {
  beforeEach(() => {
    vi.stubEnv("CATERVA_SENTENCE_READER", STANDIN);
    vi.mocked(resolveKineticValue).mockClear();
  });
  afterEach(() => vi.unstubAllEnvs());

  it("says it names no isoform, under a Km that does", async () => {
    const r = await resolveQuery("HK2 with glucose with 50 nM enzyme");
    expect(r.parameters["vmax"]).toBeCloseTo(0.00302);
    const flags = r.provenance.flags;
    expect(flags).toContain(
      "KCAT: the source row names no isoform, so whether it measured HK2, the one the query names, is unknown.",
    );
    // The Km's row IS HK2's, by the runner's own comparison: nothing said.
    expect(flags.some((f) => f.startsWith("KM") && f.includes("isoform"))).toBe(false);
  });
});

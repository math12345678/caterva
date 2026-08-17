/**
 * What each data source REQUIRES of someone publishing a run.
 *
 * WHY THIS FILE EXISTS SEPARATELY
 * -------------------------------
 * ADR 0081 added `dataSourceObligations` to the publication-readiness audit
 * and claimed:
 *
 *   "A source with no recorded citation_request produces no obligation."
 *
 * **That was false.** `citationObligations` filtered on `source !== null`,
 * not on `citation_request`, so NCBI Taxonomy — public domain, no recorded
 * request — produced an entry with `citationRequest: null`.
 *
 * Worse, the test written to cover it was:
 *
 *   it("omits a source with no recorded citation request ...", () => {
 *     const ncbi = loadDataSources().find(s => s.tokens.includes("ncbi"));
 *     expect(ncbi?.citation_request).toBeNull();
 *   });
 *
 * which asserts a field of the JSON table and never calls the function
 * whose behaviour the name describes. It could not fail for the reason it
 * claimed, and it passed while the ADR above it was wrong.
 *
 * Found by re-reading my own work an hour after writing it, not by any
 * check. That is the seventh instance this session of a verification
 * artifact testing something adjacent to the thing it names.
 *
 * THE RESOLUTION
 * --------------
 * The code was right and the ADR was wrong. A source that contributed
 * should be LISTED — a reader about to publish should know NCBI Taxonomy
 * was used, even though it requires no citation. What was missing is a
 * statement of what each source REQUIRES, rather than a `null` the reader
 * has to interpret.
 *
 * So `requirement` is three-valued: `cite` / `none` / `unknown`. "Nothing
 * is required" and "we do not know what is required" are different facts,
 * and this project's recurring defect is exactly their collapse.
 */

import { describe, expect, it } from "vitest";

import { citationObligations, loadDataSources } from "../lib/dataSources";
import type { ParameterProvenance } from "../lib/provenance";

const brenda = {
  origin: "resolved",
  citation: "BRENDA ref 740253",
  source: "brenda_exact",
} as unknown as ParameterProvenance;

const ncbi = {
  origin: "resolved",
  citation: "NCBI Taxonomy 9606",
  source: "ncbi_taxonomy",
} as unknown as ParameterProvenance;

describe("what each contributing source requires", () => {
  it("says `cite` and how, for a source that asks to be cited", () => {
    const [obligation] = citationObligations({ km: brenda });
    expect(obligation?.requirement).toBe("cite");
    expect(obligation?.citationRequest).toContain(
      "brenda-enzymes.org/references.php",
    );
  });

  it("lists a no-citation source and says `none` rather than omitting it", () => {
    // The behaviour ADR 0081 described wrongly. NCBI Taxonomy contributed,
    // so it is listed; it requires no citation, so it says so.
    const obligations = citationObligations({ organism: ncbi });
    expect(obligations).toHaveLength(1);
    expect(obligations[0]?.source).toBe("ncbi");
    expect(obligations[0]?.requirement).toBe("none");
    expect(obligations[0]?.citationRequest).toBeNull();
  });

  it("distinguishes `none` from `unknown`", () => {
    // The distinction is the point. Both have citationRequest === null, so
    // a reader inferring from that field alone cannot tell "public domain,
    // nothing owed" from "we have no idea what this source requires".
    const withTerms = loadDataSources().filter((s) => s.licence !== null);
    const withoutTerms = withTerms.map((s) => ({ ...s, licence: null }));

    const known = citationObligations({ organism: ncbi }, withTerms);
    const unknown = citationObligations({ organism: ncbi }, withoutTerms);

    expect(known[0]?.requirement).toBe("none");
    expect(unknown[0]?.requirement).toBe("unknown");
    expect(known[0]?.citationRequest).toBe(unknown[0]?.citationRequest);
  });

  it("requires nothing of a run that used no described source", () => {
    const user = { origin: "user" } as unknown as ParameterProvenance;
    expect(citationObligations({ km: user })).toEqual([]);
  });

  it("never reports `cite` without saying how", () => {
    // A requirement a reader cannot act on is the Katz objection again:
    // a citation nobody can act on is not a citation.
    //
    // `citeSeen` is what makes this test able to fail. Every assertion here
    // sits inside `if (requirement === "cite")`, so without it the test
    // passes when NO source yields a `cite` obligation — including if
    // `loadDataSources()` returned an empty list, or if a refactor stopped
    // producing `cite` at all. It would then be green precisely when the
    // behaviour it names had disappeared.
    //
    // That is the defect this file's own header describes: a verification
    // artifact asserting something adjacent to the thing it names. It was
    // caught by `scripts/check_no_vacuous_tests.py`, which reports a test
    // whose every assertion is inside a conditional.
    let citeSeen = 0;
    for (const source of loadDataSources()) {
      const probe = {
        origin: "resolved",
        citation: `${source.tokens[0]} ref 1`,
        source: source.tokens[0],
      } as unknown as ParameterProvenance;
      for (const obligation of citationObligations({ x: probe })) {
        if (obligation.requirement === "cite") {
          citeSeen += 1;
          expect(obligation.citationRequest).toBeTruthy();
        }
      }
    }
    // At least one source in the shipped table requires citation — BRENDA
    // is CC BY 4.0 and its attribution requirement is the reason this whole
    // mechanism exists. If that stops being true, this test should be
    // rewritten deliberately rather than pass by having checked nothing.
    expect(citeSeen).toBeGreaterThan(0);
  });
});

/**
 * The papers Caterva found are offered to the student who needs them.
 *
 * WHY THIS EXISTS
 * ---------------
 * When BRENDA carries no value, `fallback_logic.py` does not stop. It
 * searches PubMed and CORE, and on a hit returns
 * `source: "literature_candidates"` with the list attached — the fallback
 * whose entire job is the case where the primary path failed.
 *
 * `literatureCandidates` was declared on `ScienceAgentResult`, populated by
 * `_candidates_to_dict`, emitted on two runner branches, and read by
 * NOTHING. The only non-test references in the whole tree were the
 * declaration and an empty-array initialiser. A student was told "could not
 * resolve" while the system held papers that probably contain the number.
 *
 * ADR 0039's defect on the one path that exists to help when everything
 * else failed. Found by the reachability guard's scope check (ADR 0105)
 * refusing to clear `literature_candidates.title` on a leaf name that
 * `citation.title` had just made appear.
 *
 * WHY THE ERROR AND NOT A FLAG
 * ----------------------------
 * The first version of this file read `provenance.flags`, and every case
 * came back empty. A probe showed why: when a kinetic constant cannot be
 * resolved and was not supplied, `resolveQuery` THROWS. There is no
 * response, so there are no flags — the papers were unreachable by
 * construction on the exact path where they matter.
 *
 * The error is where a student meets this, and it is the message telling
 * them to go and find the value themselves. So that is where the papers
 * belong.
 */
import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";

const CANDIDATES = [
  {
    title: "Purification and kinetics of lactate dehydrogenase from human muscle",
    url: "https://pubmed.ncbi.nlm.nih.gov/1234567/",
    source: "pubmed" as const,
    pmid: "1234567",
    doi: null,
  },
  {
    title: "Substrate affinity of LDH isoenzymes under physiological conditions",
    url: "https://core.ac.uk/download/98765.pdf",
    source: "core" as const,
    pmid: null,
    doi: "10.1000/example",
  },
];

const NOT_FOUND_WITH_CANDIDATES = {
  found: false,
  source: "literature_candidates",
  organism: "Homo sapiens",
  crossSpecies: false,
  literatureCandidates: CANDIDATES,
  logs: [],
};

const NOT_FOUND_EMPTY_HANDED = {
  found: false,
  source: "not_found",
  organism: "Homo sapiens",
  crossSpecies: false,
  literatureCandidates: [],
  logs: [],
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => NOT_FOUND_WITH_CANDIDATES),
  };
});

// km deliberately NOT supplied: this is the unresolved path, and supplying
// it would resolve the very situation under test.
const QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate in " +
  "Homo sapiens vmax=5 s0=10 end=10 points=51";

/** What the student is actually shown: the refusal message. */
async function refusalFor(result: unknown): Promise<string> {
  vi.mocked(resolveKineticValue).mockResolvedValue(result as never);
  try {
    await resolveQuery(QUERY);
  } catch (error) {
    return (error as Error).message;
  }
  throw new Error("expected the query to be refused, and it was not");
}

describe("candidate papers are offered rather than discarded", () => {
  it("names the papers, not just a count", async () => {
    const flags = await refusalFor(NOT_FOUND_WITH_CANDIDATES);
    expect(flags).toContain(
      "Purification and kinetics of lactate dehydrogenase from human muscle",
    );
    expect(flags).toContain(
      "Substrate affinity of LDH isoenzymes under physiological conditions",
    );
  });

  /**
   * A title with no locator is a claim; a title with one is checkable. The
   * two sources need different locators — PubMed's esummary never supplies
   * a DOI and CORE has no PMID — so covering only one silently drops half
   * the offers' provenance.
   */
  it("carries a locator for each, from whichever source it came", async () => {
    const flags = await refusalFor(NOT_FOUND_WITH_CANDIDATES);
    expect(flags).toContain("PMID 1234567");
    expect(flags).toContain("doi 10.1000/example");
  });

  /**
   * The offer must not read as a resolution. Caterva does not extract
   * numbers from full text, and a flag listing papers beside a defaulted
   * value could easily be read as "we used these".
   */
  it("says plainly that no value was taken from them", async () => {
    const flags = await refusalFor(NOT_FOUND_WITH_CANDIDATES);
    expect(flags).toMatch(/does not extract numbers from full text/i);
  });

  it("says nothing when there are no candidates", async () => {
    const flags = await refusalFor(NOT_FOUND_EMPTY_HANDED);
    expect(flags).not.toMatch(/candidate paper/i);
  });

  /**
   * The instruction the student must act on survives the offer.
   *
   * `missingKeyDetails` PROMOTES a note into the error and drops the
   * generic sentence for keys that have one — which would take the
   * "Add km=<value>" instruction with it. That regression has happened
   * here before, and it is why the offer is appended rather than
   * substituted.
   */
  it("still tells them how to supply the value themselves", async () => {
    const message = await refusalFor(NOT_FOUND_WITH_CANDIDATES);
    expect(message).toMatch(/km=/);
  });

  /**
   * A guard against the shape this replaced: a value that DID resolve must
   * not carry an offer of papers to go and read instead. It resolves, so
   * there is no refusal to inspect — the assertion is that the query
   * SUCCEEDS, which is itself the statement that no offer was made.
   */
  it("says nothing when the value resolved", async () => {
    vi.mocked(resolveKineticValue).mockResolvedValue({
      found: true,
      km: 2.5,
      unit: "mM",
      organism: "Homo sapiens",
      source: "brenda_exact",
      crossSpecies: false,
      citation: {
        source: "BRENDA",
        referenceId: "740253",
        url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
      },
      assayConditions: { ph: 7.4, temperatureC: 37 },
      literatureCandidates: CANDIDATES,
      logs: [],
    } as never);
    const resolved = await resolveQuery(QUERY);
    const notes = Object.values(resolved.parameterProvenance)
      .map((p) => p?.note ?? "")
      .join("\n");
    expect(notes).not.toMatch(/candidate paper/i);
  });
});

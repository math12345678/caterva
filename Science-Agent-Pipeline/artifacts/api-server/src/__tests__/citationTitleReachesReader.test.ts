/**
 * The paper's title reaches the person reading the citation.
 *
 * WHY THIS EXISTS
 * ---------------
 * `Citation.title` was resolved by the Python side, emitted by the runner,
 * and declared on the TypeScript interface. `formatResolvedCitation`'s
 * parameter type did not mention it, so a student read
 *
 *     BRENDA (ref 740253) — https://www.brenda-enzymes.org/...
 *
 * and could not tell what paper backed the number without opening the link.
 * In a tool whose entire claim is that its values are literature-backed, the
 * one human-readable part of the evidence was the part not shown. Found by
 * the reachability guard (ADR 0102) once it learned to descend into nested
 * models.
 *
 * WHY THE RESOLVER IS DRIVEN RATHER THAN THE FORMATTER
 * ----------------------------------------------------
 * The first draft of this file asserted on string CONSTANTS spelling out
 * what the formatter was believed to produce. Every case passed, and would
 * have passed with the formatter unchanged — a test that cannot fail,
 * checking my own expectation instead of the code. `formatResolvedCitation`
 * is not exported, and exporting it to make it testable would have moved
 * the same weakness one layer down: what matters is not what the function
 * returns, it is what lands in `parameterProvenance`, which is what a
 * reader sees.
 *
 * So the mocked runner supplies a title and the real `resolveQuery` runs.
 * The title is a phrase nothing at this call site could invent, which is
 * the same device `reliabilityFromRunner.test.ts` uses: if it appears in
 * the output, it can only have travelled.
 */
import { describe, expect, it, vi } from "vitest";

import { resolveQuery } from "../lib/queryResolver";
import { resolveKineticValue } from "../lib/scienceAgent";
import { isLocatableCitation } from "../lib/provenance";
import {
  locatorsFromCitationString,
  citationConsistentWithLocators,
} from "../lib/citeVerify";

/** Unreachable by reconstruction: nothing here can invent this sentence. */
const TITLE = "Kinetic properties of human lactate dehydrogenase isoenzymes";

const BASE = {
  found: true,
  km: 2.5,
  unit: "mM",
  organism: "Homo sapiens",
  source: "brenda_exact",
  crossSpecies: false,
  assayConditions: { ph: 7.4, temperatureC: 37 },
  literatureCandidates: [],
  logs: [],
};

const WITH_TITLE = {
  ...BASE,
  citation: {
    source: "BRENDA",
    referenceId: "740253",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    title: TITLE,
  },
};

const WITHOUT_TITLE = {
  ...BASE,
  citation: {
    source: "BRENDA",
    referenceId: "740253",
    url: "https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
  },
};

/** A title and no locator. Must still be refused. */
const TITLE_BUT_NO_LOCATOR = {
  ...BASE,
  citation: { source: "BRENDA", title: TITLE },
};

vi.mock("../lib/scienceAgent", async (importOriginal) => {
  const original = await importOriginal<typeof import("../lib/scienceAgent")>();
  return {
    ...original,
    resolveKineticValue: vi.fn(async () => WITH_TITLE),
  };
});

const QUERY =
  "simulate michaelis menten of lactate dehydrogenase on lactate in " +
  "Homo sapiens vmax=5 s0=10 end=10 points=51";

async function citationFor(result: unknown): Promise<string | undefined> {
  vi.mocked(resolveKineticValue).mockResolvedValueOnce(result as never);
  const resolved = await resolveQuery(QUERY);
  return resolved.parameterProvenance["km"]?.citation;
}

describe("the citation title reaches the reader", () => {
  it("the title appears in what a reader is shown", async () => {
    const citation = await citationFor(WITH_TITLE);
    expect(citation).toBeDefined();
    expect(citation).toContain(TITLE);
  });

  it("without a title the string is unchanged", async () => {
    const citation = await citationFor(WITHOUT_TITLE);
    expect(citation).toBe(
      "BRENDA (ref 740253) — https://www.brenda-enzymes.org/enzyme.php?ecno=1.1.1.27",
    );
  });

  /**
   * A title is not a locator, and the consequence is stronger than "the
   * title is omitted".
   *
   * The first version of this case asserted only that the title did not
   * appear. Running it showed what actually happens: `formatResolvedCitation`
   * returns undefined, the value degrades to unresolved, and the whole
   * simulation is REFUSED with `RequiredParametersMissingError`. That is the
   * correct answer — a citation carrying a beautifully descriptive title and
   * nothing to find it by is still unfindable — and asserting the weaker
   * thing would have passed even if the gate had moved below the title.
   *
   * So the assertion is the refusal itself. The `hasRef || hasUrl` gate sits
   * upstream of the title, and adding a title can never promote an
   * unlocatable citation.
   */
  it("a title cannot promote an unlocatable citation: the value is refused", async () => {
    await expect(citationFor(TITLE_BUT_NO_LOCATOR)).rejects.toThrow(
      /km could not be resolved from literature/,
    );
  });
});

describe("the three parsers of that string still work with a title in it", () => {
  /**
   * THE LOAD-BEARING CASE.
   *
   * `provenance.ts` and `citeVerify.ts` both read the ref id with
   * `/\(ref ([^)]*)\)/`. The title is placed AFTER that group and before
   * the URL precisely so the same span still matches. Asserted rather than
   * reasoned about: this repository has a standing record of a regex that
   * looked obviously fine and was not — `"PubMed ref 12345678"` has a
   * five-character gap where the pattern allowed four, and the first
   * end-to-end run wrote ZERO MIRIAM annotations.
   */
  it("the ref id is still locatable with a title in the way", async () => {
    const titled = await citationFor(WITH_TITLE);
    const plain = await citationFor(WITHOUT_TITLE);
    expect(isLocatableCitation(titled!)).toBe(true);
    expect(isLocatableCitation(titled!)).toBe(isLocatableCitation(plain!));
  });

  it("the same locators are extracted with and without the title", async () => {
    const titled = await citationFor(WITH_TITLE);
    const plain = await citationFor(WITHOUT_TITLE);
    expect(locatorsFromCitationString(titled!)).toEqual(
      locatorsFromCitationString(plain!),
    );
    // A locator list that is empty either way would satisfy the line above
    // while proving nothing.
    expect(locatorsFromCitationString(titled!).length).toBeGreaterThan(0);
  });

  it("locator consistency is unaffected by the title", async () => {
    const titled = await citationFor(WITH_TITLE);
    const plain = await citationFor(WITHOUT_TITLE);
    const locators = locatorsFromCitationString(plain!);
    expect(citationConsistentWithLocators(titled!, locators)).toBe(true);
  });

  /**
   * `splitCitation` in `commandSimulateResolved.ts` takes the source as the
   * first whitespace-delimited token, for the SBML annotator's MIRIAM ids.
   */
  it("the source is still the first whitespace-delimited token", async () => {
    const titled = await citationFor(WITH_TITLE);
    expect(titled!.split(" ")[0]).toBe("BRENDA");
  });
});

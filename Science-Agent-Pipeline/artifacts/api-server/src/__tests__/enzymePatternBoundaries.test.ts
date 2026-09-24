/**
 * An enzyme abbreviation is a word, and must not match inside a longer one.
 *
 * Every pattern in ENZYMES carried its common abbreviation as a bare
 * alternative with no word boundary, so `/acetyl.?coa carboxylase|acc/i`
 * matched the "acc" in "unvaccinated" and a measles query classified as
 * enzyme kinetics. `sod` matched "sodium"; `ache` matched "headache";
 * `/trypsin/i`, declared first, matched inside "chymotrypsin" and returned
 * the wrong EC number for every chymotrypsin query. See ADR 0205.
 *
 * This asserts the property rather than the ten specific words that
 * happened to be found, because the next abbreviation added without a
 * boundary will be a different word.
 */
import { describe, expect, it } from "vitest";

import { ENZYMES, matchEnzyme } from "../lib/enzymes";

// Ordinary English and ordinary scientific prose. None of it names an
// enzyme; every word here contains a would-be abbreviation as a substring.
const INNOCENT = [
  "unvaccinated",
  "vaccine",
  "accurate",
  "according",
  "accumulate",
  "sodium",
  "headache",
  "teacher",
  "adhesion",
  "coxsackie",
];

describe("enzyme patterns match words, not substrings", () => {
  it.each(INNOCENT)("does not find an enzyme in %j", (word) => {
    const found = matchEnzyme(`model the ${word} of a population`);
    expect(found?.enzymeName ?? null).toBeNull();
  });

  it("finds chymotrypsin, not the trypsin declared before it", () => {
    // Substring matching plus table order, which is the same defect wearing
    // a different hat: the answer was a real enzyme, just the wrong one.
    expect(matchEnzyme("chymotrypsin activity")?.enzymeName).toBe(
      "chymotrypsin",
    );
    expect(matchEnzyme("trypsin digestion")?.enzymeName).toBe("trypsin");
  });

  it.each([
    ["LDH activity in muscle", "lactate dehydrogenase"],
    ["SOD assay results", "superoxide dismutase"],
    ["G6PD deficiency screening", "glucose-6-phosphate dehydrogenase"],
    ["hexokinase HK1 kinetics", "hexokinase"],
  ])("still matches the bare abbreviation in %j", (query, expected) => {
    // The direction that bounds the fix. Boundaries must not cost the
    // abbreviations the alternatives exist to catch.
    expect(matchEnzyme(query)?.enzymeName).toBe(expected);
  });

  it("declares no alphanumeric alternative without a word boundary", () => {
    // The property itself, asserted on the table rather than on examples,
    // so a pattern added tomorrow is covered without anyone thinking of the
    // word that would break it.
    const unbounded: string[] = [];
    for (const entry of ENZYMES) {
      for (const alt of entry.pattern.source.split("|")) {
        if (/^[a-z0-9 ]+(\\d\?|[a-z]\?)?$/i.test(alt)) {
          unbounded.push(`${entry.enzymeName}: /${alt}/`);
        }
      }
    }
    expect(unbounded).toEqual([]);
  });
});

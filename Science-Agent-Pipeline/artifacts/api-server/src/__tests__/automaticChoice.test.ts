/**
 * How a choice the runner made becomes a sentence the reader sees (ADR 0182).
 *
 * The choosing is Python's (caterva.compose.defaults); automaticChoice.ts
 * only words it. What is pinned: the flag starts "<role> chosen:" so a
 * client can find it, it carries the chooser's reason and the alternatives
 * with their row counts, it says how to choose otherwise, and a malformed
 * choice is dropped rather than half-stated.
 */
import { describe, expect, it } from "vitest";

import {
  choiceFlag,
  describeAlternatives,
  isChoiceFlag,
  readChoices,
  type AutomaticChoice,
} from "../lib/automaticChoice";

const GLUCOSE: AutomaticChoice = {
  role: "substrate",
  chosen: "D-glucose",
  why: "most Km and kcat rows for EC 2.7.1.1 in Homo sapiens.",
  alternatives: [
    { name: "ATP", rows: { km: 106 } },
    { name: "D-mannose", rows: { km: 9, kcat: 1 } },
  ],
  considered: 12,
};

describe("choiceFlag", () => {
  it("names the choice, the reason, the alternatives and the way out", () => {
    expect(choiceFlag(GLUCOSE)).toBe(
      "substrate chosen: D-glucose -- most Km and kcat rows for EC 2.7.1.1 in Homo sapiens. " +
        "Alternatives: ATP (Km 106 rows); D-mannose (Km 9 rows, kcat 1 row). " +
        'Name the substrate in the query ("<enzyme> with <substrate>") to use another.',
    );
    expect(isChoiceFlag(choiceFlag(GLUCOSE))).toBe(true);
  });

  it("says so when nothing else had rows", () => {
    expect(choiceFlag({ ...GLUCOSE, alternatives: [] })).toContain(
      "No other candidate had usable rows.",
    );
  });

  it("tells an inhibitor's reader how to name one", () => {
    expect(
      choiceFlag({ role: "inhibitor", chosen: "oxamate", why: "most Ki rows", alternatives: [], considered: 1 }),
    ).toContain('("inhibited by <compound>")');
  });
});

describe("describeAlternatives", () => {
  it("lists five and counts the rest", () => {
    const many = Array.from({ length: 8 }, (_, i) => ({ name: `S${i}`, rows: { km: 8 - i } }));
    expect(describeAlternatives(many)).toBe(
      "S0 (Km 8 rows); S1 (Km 7 rows); S2 (Km 6 rows); S3 (Km 5 rows); S4 (Km 4 rows), and 3 more",
    );
  });
});

describe("readChoices", () => {
  it("keeps well-formed choices and drops the rest", () => {
    expect(readChoices([GLUCOSE, { role: "substrate", chosen: "" }, null, "x"])).toEqual([GLUCOSE]);
  });

  it("reads an absent field as no choices, as a runner that predates them sends", () => {
    expect(readChoices(undefined)).toEqual([]);
  });
});

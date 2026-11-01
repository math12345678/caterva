/**
 * copy.ts rewrites the engine's terminal phrasings for the window. Every
 * input here is a string the engine produced (recorded in the fixtures or
 * read from its source); the expectation is the page's sentence.
 */
import { describe, expect, it } from "vitest";

import {
  describeSource,
  humaniseIdentifier,
  humaniseStage,
  networkFailureOf,
  networkSentence,
  plain,
  plural,
  readPlaceholder,
  placeholderRowReason,
  plainMarkdown,
  readCompoundList,
  withoutUrls,
} from "@/lib/copy";

const UNIPROT_TIMEOUT =
  "ReadTimeout: HTTPSConnectionPool(host='rest.uniprot.org', port=443): Read timed out. (read timeout=30)";
const UNIPROT_503 =
  "HTTPError: 503 Server Error: Service Unavailable for url: https://rest.uniprot.org/uniprotkb/search?query=ec%3A1.1.1.27&format=json&size=500";

describe("plural", () => {
  it("agrees with the count and groups thousands", () => {
    expect(plural(1, "run")).toBe("1 run");
    expect(plural(8, "run")).toBe("8 runs");
    expect(plural(0, "row")).toBe("0 rows");
    expect(plural(1234, "constant")).toBe("1,234 constants");
    expect(plural(2, "analysis", "analyses")).toBe("2 analyses");
  });
});

describe("the engine's flags, said in the page's words", () => {
  it("drops the flag from the organism reading", () => {
    expect(plain("Read --organism 'human' as Homo sapiens.")).toBe("Read 'human' as Homo sapiens.");
  });

  it("names the field for a re-run, with no dash used as punctuation", () => {
    const engine =
      "re-run with --organism set to one the provenance table lists as holding a measurement, or supply the constants yourself -- start with the top of its influence ranking";
    expect(plain(engine)).toBe(
      "set Organism to one the provenance table lists as holding a measurement, or supply the constants yourself. Start with the top of its influence ranking",
    );
  });

  it("rewrites the cross-species placeholder reason without losing the organisms", () => {
    const engine =
      "no value in the organism requested; measurements exist in other organisms, and one is never substituted for yours (ADR 0024) -- re-run with --organism set to one of them to build the model there -- available in: Anas platyrhynchos, Escherichia coli (searched under the requirement that organism must be Homo sapiens, raised by your own request)";
    const out = plain(engine);
    expect(out).toContain("(ADR 0024). Set Organism to one of them to build the model there. Available in: Anas platyrhynchos, Escherichia coli");
    expect(out).not.toMatch(/--/);
  });

  it("translates the validate and robustness hints into the tick boxes", () => {
    expect(plain("not run -- pass --validate (or `validation=`) for the cross-module consistency check")).toBe(
      "not run. Tick Cross-checks for the cross-module consistency check",
    );
    expect(plain("not run -- pass --robustness (or `robustness=`) to resample the placeholders")).toBe(
      "not run. Tick Robustness to the placeholders to resample the placeholders",
    );
  });

  it("names the Isoform field", () => {
    const engine =
      "pass --isoform with the isoform's name as the papers write it (for example --isoform LDH-A) to take each constant from a row that measured it";
    expect(plain(engine)).toBe("set Isoform to the name the papers write (for example LDH-A) to take each constant from a row that measured it");
    expect(plain("pass the one simulated (--isoform) to compare like with like")).toBe(
      "set Isoform to the one simulated to compare like with like",
    );
  });

  it("rewrites the seed, ph, temperature and ionic strength notes", () => {
    expect(plain("no band was produced across the 3 values: no seed was supplied. Re-run with --seed N.")).toBe(
      "no band was produced across the 3 values: no seed was supplied. Set Seed and run it again.",
    );
    expect(plain("chosen: 310 K, set with --temperature")).toBe("chosen: 310 K, set in Temperature");
    expect(plain("chosen: set with --ph")).toBe("chosen: set in pH");
    expect(plain("physiological default; override with --ionic-strength")).toBe("physiological default; set the ionic strength to change it");
  });

  it("does not name the script behind a command", () => {
    expect(plain("the default of cite.py --vmax; chosen for this run")).toBe("the stated default for Vmax; chosen for this run");
    expect(plain("Every number in the lab report is either cited or declared as yours (cite.py's own check).")).toBe(
      "Every number in the lab report is either cited or declared as yours (the command's own check).",
    );
  });

  it("drops the terminal command a description points at", () => {
    expect(plain("every number, its origin and its citation (caterva compose --export csv)")).toBe("every number, its origin and its citation");
    expect(plain("a chosen cutoff, not a physical boundary (caterva prepare)")).toBe("a chosen cutoff, not a physical boundary");
  });

  it("tells the person how to choose a protein without flags", () => {
    expect(
      plain("Refused: EC 1.1.1.27 in Homo sapiens is 3 different proteins with structures. Choose with --gene or --uniprot: LDHA (P00338, 46 entries)."),
    ).toBe("Refused: EC 1.1.1.27 in Homo sapiens is 3 different proteins with structures. Choose one by its gene or its UniProt entry: LDHA (P00338, 46 entries).");
  });

  it("removes the parser's prefix and names the field", () => {
    expect(plain("caterva compose: error: --robustness needs at least one sample; got 0.")).toBe("Robustness needs at least one sample; got 0.");
  });
});

describe("dashes", () => {
  it("replaces the long dash in the constants refusal the engine used to print", () => {
    const engine =
      "A report needs an enzyme and an organism. Give the enzyme as an EC number ('ec') or as a name ('enzyme') \u2014 a name is looked up in UniProt, and refused if it matches more than one enzyme.";
    const out = plain(engine);
    expect(out).not.toContain("\u2014");
    expect(out).toContain("('enzyme'); a name is looked up in UniProt");
  });

  it("replaces the long dash in a data source's creator", () => {
    expect(plain("the BRENDA team at the Leibniz Institute DSMZ \u2014 German Collection of Microorganisms and Cell Cultures GmbH, Braunschweig, Germany")).toBe(
      "the BRENDA team at the Leibniz Institute DSMZ, German Collection of Microorganisms and Cell Cultures GmbH, Braunschweig, Germany",
    );
    expect(plain("cite BRENDA's current publication -- https://www.brenda-enzymes.org/references.php")).toBe(
      "cite BRENDA's current publication: https://www.brenda-enzymes.org/references.php",
    );
  });

  it("leaves a name that contains two hyphens alone", () => {
    expect(plain("polyphosphate--glucose phosphotransferase")).toBe("polyphosphate--glucose phosphotransferase");
  });

  it("leaves text without any of these unchanged", () => {
    const t = "Searching BRENDA for EC 2.7.1.1 in Homo sapiens";
    expect(plain(t)).toBe(t);
  });
});

describe("plurals in engine text", () => {
  it("writes the count's own plural", () => {
    expect(plain("2 row(s); 3 constant(s) measured")).toBe("2 rows; 3 constants measured");
    expect(plain("1 row(s)")).toBe("1 row");
    expect(plain("MEASURED (3 row(s) fit this state)")).toBe("MEASURED (3 rows fit this state)");
    expect(plain("8 run(s)")).toBe("8 runs");
  });
});

describe("an upstream outage", () => {
  it("is recognised from the exception text, with the host", () => {
    expect(networkFailureOf(UNIPROT_TIMEOUT)).toEqual({ host: "rest.uniprot.org", status: null, timed_out: true });
    expect(networkFailureOf(UNIPROT_503)).toEqual({ host: "rest.uniprot.org", status: 503, timed_out: false });
  });

  it("is not claimed by a refusal that only mentions the network", () => {
    expect(networkFailureOf("Refused: offline mode is on, and this request needs the network.")).toBeNull();
    expect(networkFailureOf("Refused: 'lactate dehydrogenase' names 2 enzymes.")).toBeNull();
  });

  it("is said as a sentence a person can act on", () => {
    expect(networkSentence(networkFailureOf(UNIPROT_TIMEOUT), "search again")).toBe(
      "UniProt did not answer. Check the network, then search again.",
    );
    expect(networkSentence(networkFailureOf(UNIPROT_503))).toBe("UniProt did not answer. Check the network, then try again.");
    expect(networkSentence(null)).toBe("A database did not answer. Check the network, then try again.");
  });

  it("names the host, not the URL", () => {
    expect(withoutUrls(UNIPROT_503)).toBe("HTTPError: 503 Server Error: Service Unavailable for url: UniProt");
    expect(withoutUrls("see https://data.rcsb.org/rest/v1/core/entry/1AKI now")).toBe("see the RCSB data now");
  });
});

describe("identifiers in words", () => {
  it("says what a model identifier is", () => {
    expect(humaniseIdentifier("reaction_kcat")).toBe("kcat of the reaction");
    expect(humaniseIdentifier("reaction_Km")).toBe("Km of the reaction");
    expect(humaniseIdentifier("competitive_inhibition.kcat")).toBe("kcat of competitive inhibition");
    expect(humaniseIdentifier("hill_repression.ks")).toBe("ks of hill repression");
    expect(humaniseIdentifier("A_total")).toBe("A_total");
  });

  it("humanises the identifiers in a progress sentence", () => {
    expect(humaniseStage("Looking up reaction_kcat in BRENDA's kcat table for EC 1.1.1.27")).toBe(
      "Looking up kcat of the reaction in BRENDA's kcat table for EC 1.1.1.27",
    );
  });
});

describe("the placeholder boilerplate", () => {
  const withTable =
    "ILLUSTRATIVE PLACEHOLDER: Caterva's motif library value for competitive_inhibition.kcat. No publication supplies this number and nobody measured it. It is here so the structure can be checked, dimensioned and simulated; the measurement that would replace it is in the kcat table.";
  const noTable =
    "ILLUSTRATIVE PLACEHOLDER: Caterva's motif library value for hill_repression.ks. No publication supplies this number and nobody measured it. It is here so the structure can be checked, dimensioned and simulated; no database table serves it, so it is resolvable only from a paper.";

  it("keeps only what differs per row", () => {
    expect(readPlaceholder(withTable)).toEqual({ what: "kcat of competitive inhibition", identifier: "competitive_inhibition.kcat", table: "kcat", noTable: false });
    expect(placeholderRowReason(readPlaceholder(withTable)!)).toBe(
      "Library value for the kcat of competitive inhibition. A measurement would be in BRENDA's kcat table.",
    );
  });

  it("says the real reason when no table serves the constant", () => {
    const reading = readPlaceholder(noTable)!;
    expect(reading.noTable).toBe(true);
    const row = placeholderRowReason(reading);
    expect(row).toBe("Library value for the ks of hill repression. No database table serves it; only a paper can supply it.");
    expect(row).not.toMatch(/PLACEHOLDER/);
    for (const line of row.split(/(?<=\.) /)) expect(line.length).toBeLessThanOrEqual(70);
  });

  it("returns null for a reason the engine wrote for this constant alone", () => {
    expect(readPlaceholder("no value in the organism requested; measurements exist in other organisms")).toBeNull();
  });
});

describe("markdown prose", () => {
  it("rewrites sentences and leaves code exactly as written", () => {
    const source = [
      "Not run -- pass --validate (or `validation=`) for the check.",
      "",
      "```",
      "caterva compose \"x\" --organism human --robustness",
      "```",
      "",
      "Re-run with `--seed 7` -- the table says so.",
    ].join("\n");
    expect(plainMarkdown(source)).toBe(
      [
        "Not run. Pass Cross-checks (or `validation=`) for the check.",
        "",
        "```",
        "caterva compose \"x\" --organism human --robustness",
        "```",
        "",
        "Re-run with `--seed 7`. The table says so.",
      ].join("\n"),
    );
  });
});

describe("compounds with a Ki", () => {
  it("reads bind's refusal into its sentence and its compounds", () => {
    const reason =
      "No Ki for 'oxamate' with EC 1.1.1.27 in Homo sapiens.\nCompounds that do have one: 3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid; gossypol";
    expect(readCompoundList(reason)).toEqual({
      lead: "No Ki for 'oxamate' with EC 1.1.1.27 in Homo sapiens.",
      compounds: ["3-[7-(2,4-dimethoxypyrimidin-5-yl)-3-sulfamoylquinolin-4-yl]aminobenzoic acid", "gossypol"],
    });
  });

  it("leaves any other refusal alone", () => {
    expect(readCompoundList("Refused: nothing")).toBeNull();
  });
});

describe("resolver source tokens", () => {
  it("says what the engine says each outcome means, and never guesses an unknown one", () => {
    expect(describeSource("brenda_exact")).toBe("found in BRENDA, in the organism asked for");
    expect(describeSource("cross_species_withheld")).toBe("exists in another organism, which you did not allow");
    expect(describeSource("some_new_token")).toBe("some new token");
  });
});

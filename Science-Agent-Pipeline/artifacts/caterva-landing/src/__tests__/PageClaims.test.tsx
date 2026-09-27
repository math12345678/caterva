/**
 * The page must not make a stronger claim than the pipeline makes.
 *
 * The Michaelis-Menten example card said "Km literature-verified (10.73
 * mM, real BRENDA value)". Re-resolved live through `resolveQuery`, the
 * value and the source are genuinely real -- BRENDA ref 740253, EC
 * 1.1.1.27, Homo sapiens -- but the resolver returns:
 *
 *     citationStatus: "flagged"
 *     strendaStatus:  "incomplete"
 *     note: "Assay temperature not reported by the source; STRENDA
 *            requires it for kinetic data, so this value is flagged
 *            rather than verified."
 *
 * So Caterva's own resolver declines to call that number verified, and
 * the marketing page called it verified anyway. That is the exact defect
 * this product exists to refuse, committed on the page that advertises
 * refusing it -- and it is worse than an ordinary overstatement, because
 * "verified" is a defined term here with a specific meaning the codebase
 * enforces everywhere else.
 *
 * Checked against the source text rather than a live resolve: a network
 * call to BRENDA in the landing app's unit tests would be slow, flaky and
 * offline-hostile. The trade-off is that this pins the WORDING, not the
 * underlying status -- if BRENDA later publishes a temperature for this
 * measurement, the value becomes genuinely verified and this test has to
 * be updated deliberately, which is the right amount of friction for a
 * claim of that kind.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import path from "node:path";

const gallery = readFileSync(
  path.join(__dirname, "..", "cli", "ExampleGallery.tsx"),
  "utf-8",
);

/** The `description:` strings, with their surrounding card text. */
function descriptions(): string[] {
  return [...gallery.matchAll(/description:\s*((?:"[^"]*"\s*\+?\s*)+),/g)].map(
    (m) => m[1]!.replace(/"\s*\+\s*"/g, "").replace(/"/g, ""),
  );
}

describe("example cards do not overstate what the pipeline returns", () => {
  it("does not call the flagged Km 'verified'", () => {
    const overclaims = descriptions().filter((d) =>
      /literature-verified|literature verified/i.test(d),
    );
    expect(
      overclaims,
      `card descriptions claiming "verified": ${overclaims.join(" | ")}`,
    ).toEqual([]);
  });

  it("says the Km is flagged, and why", () => {
    // Asserted positively as well. A description that simply stopped
    // mentioning the status would pass the check above while telling the
    // reader less than the truth.
    const mm = descriptions().find((d) => d.includes("10.73"));
    expect(mm, "the Michaelis-Menten card no longer states its Km").toBeDefined();
    expect(mm).toMatch(/flagged/i);
    expect(mm).toMatch(/temperature/i);
  });

  it("still says the value and its source are real", () => {
    // The correction must not swing the other way. The number IS a real
    // BRENDA measurement with a followable reference; underselling that
    // would be its own inaccuracy.
    const mm = descriptions().find((d) => d.includes("10.73"))!;
    expect(mm).toMatch(/BRENDA/);
    expect(mm).toMatch(/1\.1\.1\.27/);
  });

  it("reads a non-trivial number of descriptions", () => {
    // A parser that silently matched nothing would make every check above
    // vacuous.
    expect(descriptions().length).toBeGreaterThanOrEqual(3);
  });
});

/**
 * A comparison page must not invent the thing it compares against.
 *
 * WorkflowCompare.tsx claimed the manual alternative takes "2-4 hours"
 * and "hours of work", with no source, in a file that had zero comment
 * lines in a repo where every other file documents where its numbers come
 * from. Nobody here has timed a researcher doing that work.
 *
 * A fabricated comparison is the same defect as a fabricated Km, and it
 * sat on the page advertising that Caterva never fabricates one. Choosing
 * a smaller, more modest invented number would have been the identical
 * defect wearing a humbler face.
 *
 * The Caterva side keeps a figure because that one was measured
 * end-to-end (2.0-28.3 s across three queries on 2026-09-05), and the
 * file records the runs.
 */
describe("the workflow comparison does not invent durations", () => {
  const source = readFileSync(
    path.join(__dirname, "..", "cli", "WorkflowCompare.tsx"),
    "utf-8",
  );

  /** Lines that render, i.e. not comments. */
  const rendered = source
    .split("\n")
    .filter((line) => !/^\s*(\/\/|\*|\/\*)/.test(line))
    .join("\n");

  it("makes no unsourced claim about how long the manual workflow takes", () => {
    // The comment block explaining the removal is allowed to say "2-4
    // hours"; the rendered copy is not.
    expect(rendered).not.toMatch(/2\s*[-\u2013]\s*4\s*hours/i);
    expect(rendered).not.toMatch(/hours of work/i);
  });

  it("still describes the manual work, rather than deleting the comparison", () => {
    // The fix must not be "remove the section". A reader should still see
    // what the alternative involves.
    expect(rendered).toMatch(/Literature search/i);
    expect(rendered).toMatch(/Cross-reference papers/i);
  });

  it("keeps the Caterva figure, which is measured, and labels it so", () => {
    expect(rendered).toMatch(/under 30 s/i);
    expect(rendered).toMatch(/measured/i);
  });

  it("records the measurements behind that figure in the file", () => {
    // A number is only as good as its recorded basis. If someone changes
    // the claim they have to change the evidence next to it.
    //
    // Asserted against the COMMENT block specifically, per measurement
    // line. A first version checked the whole file for "28.3 s" and
    // passed even after that figure was scrubbed from the comment --
    // because the rendered copy also contains "2.0-28.3 s". The evidence
    // and the claim have to be checked separately or the evidence check
    // is really just a second claim check.
    const comments = source
      .split("\n")
      .filter((line) => /^\s*\/\//.test(line))
      .join("\n");
    expect(comments).toMatch(/hexokinase[^\n]*28\.3 s/);
    expect(comments).toMatch(/covid[^\n]*2\.6 s/i);
    expect(comments).toMatch(/influenza[^\n]*2\.0 s/i);
    expect(comments).toMatch(/2026-09-05/);
  });
});

/**
 * A named enzyme, a named disease, and a sample export are all CLAIMS.
 *
 * Three surfaces shipped numbers that contradicted the product's own
 * resolver, under real names, on the pages that advertise never inventing
 * a number:
 *
 *   KineticsPlayground  LDH Km 0.5 (resolver: 10.73, BRENDA 740253) and
 *                       hexokinase Km 0.1 (resolver: 6, BRENDA 641068).
 *                       Off by 21x and 60x.
 *   EpiPlayground       "COVID (mild)" gamma 0.07 = a 14.3-day infectious
 *                       period against the registry's 5.45 days; and a
 *                       "Measles (high)" preset, when the resolver
 *                       REFUSES measles because Guerra et al. 2017 found
 *                       no single R0 defensible.
 *   ExportFormats       a sample export attributing Km 2.0 and Vmax 5.0
 *                       to BRENDA -- the unverified teaching defaults the
 *                       hard rule blocks -- plus "PMID:12345678".
 *
 * All values are now the ones the product actually resolves, measured
 * 2026-09-05, or are explicitly labelled as carrying no literature claim.
 */
describe("presets and samples do not contradict the resolver", () => {
  const read = (f: string) =>
    readFileSync(path.join(__dirname, "..", "cli", f), "utf-8");

  it("enzyme presets carry the Km the resolver returns", () => {
    const src = read("KineticsPlayground.tsx");
    expect(src).toMatch(/label: "LDH", km: 10\.73/);
    expect(src).toMatch(/label: "Hexokinase", km: 6/);
    // The wrong ones must not come back.
    expect(src).not.toMatch(/label: "LDH", km: 0\.5/);
    expect(src).not.toMatch(/label: "Hexokinase", km: 0\.1\b/);
    // Each named enzyme cites where its Km came from.
    for (const ref of ["740253", "641068", "649716"]) {
      expect(src, `missing BRENDA ref ${ref}`).toContain(ref);
    }
  });

  it("drops enzyme names with no resolved value rather than inventing one", () => {
    // Trypsin shipped Km 15 with no source and no resolver value.
    expect(read("KineticsPlayground.tsx")).not.toMatch(/label: "Trypsin"/);
  });

  it("ships no measles preset, because the resolver refuses measles", () => {
    // Shipping one asserts exactly what the resolver declines to assert.
    const src = read("EpiPlayground.tsx");
    const rendered = src
      .split("\n")
      .filter((l) => !/^\s*(\/\/|\*)/.test(l))
      .join("\n");
    expect(rendered).not.toMatch(/measles/i);
  });

  it("disease presets match the literature registry", () => {
    const src = read("EpiPlayground.tsx");
    // Hussein et al. 2021: R0 3.14 / 5.45 d -> gamma 0.1835, beta 0.5761.
    expect(src).toMatch(/label: "COVID-19",\s*\n\s*beta: 0\.5761,\s*\n\s*gamma: 0\.1835/);
    expect(src).toContain("33214421");
    // The old value implied a 14.3-day infectious period.
    expect(src).not.toMatch(/gamma: 0\.07\b/);
  });

  it("unnamed shapes carry no literature claim", () => {
    // Presets that are not diseases must say so, not borrow a name.
    const src = read("EpiPlayground.tsx");
    expect(src).toMatch(/Faster spread/);
    expect(src).toMatch(/no literature claim/);
  });

  it("the sample export shows real provenance, not teaching defaults", () => {
    const src = read("ExportFormats.tsx");
    const rendered = src
      .split("\n")
      .filter((l) => !/^\s*(\/\/|\*)/.test(l))
      .join("\n");
    // The placeholder PMID and the blocked defaults must be gone.
    expect(rendered).not.toContain("PMID:12345678");
    expect(rendered).not.toMatch(/"Km": \{ "value": 2\.0[^}]*"source": "BRENDA"/);
    expect(rendered).not.toMatch(/"Vmax": \{ "value": 5\.0[^}]*"source": "BRENDA"/);
    // Real resolved values, with Vmax shown as DERIVED rather than
    // looked up -- it is not a property of the enzyme alone.
    expect(rendered).toContain("641068");
    expect(rendered).toMatch(/"vmax"[\s\S]{0,200}derived: kcat/);
  });
});

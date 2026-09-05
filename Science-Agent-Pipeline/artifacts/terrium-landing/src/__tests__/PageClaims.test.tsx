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
 * So Terrium's own resolver declines to call that number verified, and
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
 * sat on the page advertising that Terrium never fabricates one. Choosing
 * a smaller, more modest invented number would have been the identical
 * defect wearing a humbler face.
 *
 * The Terrium side keeps a figure because that one was measured
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

  it("keeps the Terrium figure, which is measured, and labels it so", () => {
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

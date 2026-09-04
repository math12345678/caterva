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

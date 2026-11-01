/**
 * The page may not advertise a data source the product does not query.
 *
 * KEGG is OFF unless an operator sets CATERVA_ENABLE_KEGG, and the reason
 * is written into Tests/enzyme_lookup.py: KEGG's terms say it "is not a
 * public database", that non-academic use "requires a commercial license",
 * and that academic users "who utilize KEGG for providing services are
 * requested to obtain an academic service provider license". Caterva
 * provides a service. The module's own comment concludes: "a licence from
 * Pathway Solutions is indicated, and nobody has obtained one."
 *
 * The landing page nevertheless told every visitor, in eleven places, that
 * Caterva queries KEGG for parameters:
 *
 *   FAQ            "resolves real kinetic parameters from BRENDA, KEGG,
 *                   and PubMed"
 *   FAQ            "sourced exclusively from ... KEGG for pathway data"
 *   FeatureCards   "Every parameter traces to BRENDA, KEGG, or PubMed"
 *   CliApp         "We query BRENDA, KEGG, & PubMed"
 *   CookieConsent  "Data sources (BRENDA, KEGG, PubMed) are queried
 *                   server-side"   <- a privacy statement, and false
 *   LiveStatusPanel  listed kegg.jp as a service with a green dot
 *   WorkflowCompare  "BRENDA lookup -> KEGG pathway -> PubMed verification"
 *
 * Wrong on two counts, not one. KEGG is disabled, AND the function behind
 * it (resolve_substrate_from_kegg) returns a substrate NAME -- it has
 * never supplied a kinetic value, so "every parameter traces to KEGG"
 * could not be true even with the licence.
 *
 * Crediting KEGG as prior art is fine (TeamSection lists it under
 * "standing on the shoulders of giants"), and so is describing the
 * historical parsing layer in the changelog. Claiming it as a live source
 * is not.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const CLI = path.join(__dirname, "..", "cli");

/** Files whose KEGG mentions are credits or history, not usage claims. */
const NOT_USAGE_CLAIMS = new Set([
  "TeamSection.tsx", // "standing on the shoulders of giants" credits
  "ChangelogModal.tsx", // what was built, historically
]);

/** Phrasings that assert KEGG is queried or supplies values. */
const USAGE_PATTERNS: Array<[string, RegExp]> = [
  ["queries KEGG", /\bquery\b[^."]{0,40}KEGG|KEGG[^."]{0,40}\bqueried\b/i],
  ["parameters from KEGG", /parameters?[^."]{0,60}KEGG/i],
  ["traces to KEGG", /trace[sd]?\s+to[^."]{0,40}KEGG/i],
  ["KEGG in the pipeline arrow", /KEGG\s*(?:pathway\s*)?(?:\\u2192|→)/i],
];

/** A mention is fine if the same sentence says it is disabled. */
const QUALIFIED = /disabled|off by default|pending a licence|pending a license|not enabled|CATERVA_ENABLE_KEGG/i;

function sentencesMentioningKegg(source: string): string[] {
  return source
    .split(/(?<=[.!?])\s+|\n/)
    .filter((s) => /KEGG/i.test(s));
}

describe("no live-source claim for a source that is disabled", () => {
  it("no component claims Caterva queries KEGG or sources parameters from it", () => {
    const offenders: string[] = [];
    for (const file of readdirSync(CLI)) {
      if (!file.endsWith(".tsx") && !file.endsWith(".ts")) continue;
      if (NOT_USAGE_CLAIMS.has(file)) continue;
      const source = readFileSync(path.join(CLI, file), "utf-8");
      for (const sentence of sentencesMentioningKegg(source)) {
        // Comments explaining the situation are the point, not a breach.
        if (/^\s*(\/\/|\*)/.test(sentence)) continue;
        if (QUALIFIED.test(sentence)) continue;
        for (const [label, pattern] of USAGE_PATTERNS) {
          if (pattern.test(sentence)) {
            offenders.push(`${file}: ${label} -> ${sentence.trim().slice(0, 110)}`);
          }
        }
      }
    }
    expect(offenders, offenders.join("\n")).toEqual([]);
  });

  it("the cookie notice does not name KEGG among sources queried server-side", () => {
    // Singled out because it is a privacy statement. Being wrong there is
    // a different category of wrong from marketing copy.
    const consent = readFileSync(path.join(CLI, "CookieConsent.tsx"), "utf-8");
    const claim = consent.match(/sources \(([^)]*)\) are queried server-side/);
    expect(claim, "the server-side sources sentence moved or changed shape").toBeTruthy();
    expect(claim![1]).not.toMatch(/KEGG/i);
    // ...and still names the ones that ARE queried, so the fix was not
    // "delete the sentence".
    expect(claim![1]).toMatch(/BRENDA/i);
    expect(claim![1]).toMatch(/PubMed/i);
  });

  it("the status panel does not list a disabled source as a service", () => {
    const panel = readFileSync(path.join(CLI, "LiveStatusPanel.tsx"), "utf-8");
    expect(panel).not.toMatch(/kegg\.jp/i);
    // The real services are still listed -- a guard that passed because
    // the list went empty would prove nothing.
    expect(panel).toMatch(/brenda-enzymes\.org/i);
    expect(panel).toMatch(/eutils\.ncbi\.nlm\.nih\.gov/i);
  });

  it("checks a meaningful number of files", () => {
    const scanned = readdirSync(CLI).filter(
      (f) => (f.endsWith(".tsx") || f.endsWith(".ts")) && !NOT_USAGE_CLAIMS.has(f),
    );
    expect(scanned.length).toBeGreaterThan(20);
  });
});

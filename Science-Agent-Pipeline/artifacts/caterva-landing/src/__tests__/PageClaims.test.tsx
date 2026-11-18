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
// Imported statically: loading GetCaterva pulls in TerminalWindow, Reveal
// and framer-motion, which on a cold, loaded machine ran past vitest's 5s
// test timeout when it was a dynamic import inside the test body.
import { DOMAINS, RELEASE_TAG } from "@/lib/domains";
import { MAIN_ONLY, RELEASE } from "@/cli/GetCaterva";

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
    // vacuous. Every card must be read, however many there are.
    const cards = [...gallery.matchAll(/^\s{4}id: "/gm)].length;
    expect(cards).toBeGreaterThanOrEqual(2);
    expect(descriptions().length).toBe(cards);
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
 * The Caterva side kept "under 30 s (measured)" from three runs on
 * 2026-09-05 (2.0-28.3 s). Two were SIR/influenza queries, domains archived
 * on 2026-09-27, and one enzyme run is not a bound, so on 2026-10-31 the
 * figure was withdrawn. The runs stay recorded in the file's comments, so
 * whoever restores a figure starts from what was measured.
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

  it("claims no Caterva duration either, since none is measured on live domains", () => {
    expect(rendered).not.toMatch(/under 30 s/i);
    expect(rendered).not.toMatch(/\d+(\.\d+)?\s*(s|sec|seconds)\b/i);
    expect(rendered).toMatch(/not yet measured/i);
  });

  it("keeps the withdrawn measurements on record in the file", () => {
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

  it("enzyme presets carry only a Km the live resolver still returns", () => {
    // Re-measured 2026-11-02 against live BRENDA: hexokinase/glucose is
    // still 6 mM (ref 641068); LDH/pyruvate now resolves 0.03 mM (not the
    // preset's 10.73) and AChE/acetylcholine 0.0714 mM (not 0.09). The two
    // stale presets were removed rather than re-pasted, so no hard-coded
    // value can drift from the resolver again unnoticed.
    const src = read("KineticsPlayground.tsx");
    const presets = src.slice(
      src.indexOf("const PRESETS"),
      src.indexOf("export default function"),
    );
    expect(presets).toMatch(/label: "Hexokinase",\s*km: 6,/);
    expect(presets).toContain("641068");
    expect(presets).not.toMatch(/label: "LDH"/);
    expect(presets).not.toMatch(/label: "AChE"/);
    expect(presets).not.toMatch(/label: "Hexokinase",\s*km: 0\.1\b/);
  });

  it("labels a preset's Vmax and s0 as illustrative, on the page", () => {
    // Vmax needs [E]0 (ADR 0013) and s0 is the experiment's choice; a
    // number next to an enzyme's name with no label reads as that enzyme's.
    const src = read("KineticsPlayground.tsx");
    expect(src).toMatch(/are illustrative experimental choices, not\s+literature values/);
    expect(src).toContain('data-testid="preset-provenance"');
  });

  it("drops enzyme names with no resolved value rather than inventing one", () => {
    // Trypsin shipped Km 15 with no source and no resolver value.
    expect(read("KineticsPlayground.tsx")).not.toMatch(/label: "Trypsin"/);
  });

  it("the sample export shows real provenance, not teaching defaults", () => {
    const src = read("ExportFormats.tsx");
    const rendered = src
      .split("\n")
      .filter((l) => !/^\s*(\/\/|\*)/.test(l))
      .join("\n");
    // The placeholder PMID and the blocked defaults must not come back.
    expect(rendered).not.toContain("PMID:12345678");
    expect(rendered).not.toMatch(/value="2\.0"|value="5\.0"/);
    // Nor a command Caterva does not have.
    expect(rendered).not.toMatch(/caterva export\b/);
    // The samples come from the generated file, not from literals here.
    expect(src).toContain('from "@/lib/exportSamples"');
    expect(src).not.toMatch(/const (SBML|CSV|JSON)_PREVIEW/);
  });

  it("the generated samples are the four real formats of one real run", () => {
    const gen = readFileSync(
      path.join(__dirname, "..", "lib", "exportSamples.ts"),
      "utf-8",
    );
    expect(gen).toMatch(/^\/\/ GENERATED by scripts\/refresh_export_samples\.py/);
    for (const f of ["sbml", "antimony", "csv", "methods"]) {
      expect(gen).toContain(`"format": "${f}"`);
    }
    // What BRENDA returned: Km 0.03 (ref 286469), gossypol's Ki 0.0014
    // (ref 711801), and that row's own qualifiers carried into the file.
    expect(gen).toContain("BRENDA ref 286469");
    expect(gen).toContain("BRENDA ref 711801");
    expect(gen).toContain("SOURCE ROW: the row measured isoform LDH-B");
    expect(gen).toContain("VALUES DISAGREE");
    expect(gen).toContain("ILLUSTRATIVE PLACEHOLDER");
  });
});

/**
 * BRENDA ref 739793 is a quinoline sulfonamide against His-tagged human
 * LDH-A, not oxamate (Tests/fixtures/brenda_ldh_fixture.html). Its pyruvate
 * row is 0.00252 mM, noncompetitive; its 0.00059 mM is competitive against
 * NADH. The page once paired 0.00059 with Km(pyruvate) as "Ki (oxamate)".
 */
describe("the inhibition demo cites what ref 739793 measured", () => {
  const files = ["DashboardPreview.tsx", "ExampleGallery.tsx", "CommandPalette.tsx", "AgentSimulator.tsx"]
    .map((f) => readFileSync(path.join(__dirname, "..", "cli", f), "utf-8"));

  it("never names oxamate or the NADH-row value", () => {
    for (const src of files) {
      expect(src.toLowerCase()).not.toContain("oxamate");
      expect(src).not.toMatch(/KI = 0\.00059|Ki 0\.00059/);
    }
  });

  it("uses the pyruvate row and draws noncompetitive inhibition", () => {
    const [dash, galleryNow] = files;
    expect(dash).toContain("const KI = 0.00252;");
    expect(dash).toContain("VMAX / (1 + inhibitor / KI)");
    expect(galleryNow).toContain("INHIBITOR_KI = 0.00252");
  });
});

/**
 * The release the page offers is the package's version, not a typed one.
 *
 * On 2026-11-01 the page offered v0.4.0 as the download, labelled released
 * work "In v0.4.0", showed "v0.7.0" on its 404 page and called the
 * structure and MD tools main-only, four days after v0.6.0 (which carries
 * them) was published on 2026-10-28. RELEASE_TAG now comes from
 * repoFacts.json, which scripts/check_landing_test_counts.py derives from
 * caterva/__init__.py. These tests hold the rest of the page to that one
 * value.
 */
describe("the release the page names is RELEASE_TAG", () => {
  const src = (...p: string[]) =>
    readFileSync(path.join(__dirname, "..", ...p), "utf-8");

  it("takes RELEASE_TAG from the generated repoFacts.json", () => {
    const facts = JSON.parse(src("lib", "generated", "repoFacts.json"));
    expect(RELEASE_TAG).toBe(facts.releaseTag);
    expect(RELEASE_TAG).toMatch(/^v\d+\.\d+\.\d+$/);
  });

  it("re-reads the download's date and commands when the release moves on", () => {
    // The date, platforms and command list cannot be derived from the
    // tree, so GetCaterva records the tag they were read against. A new
    // version fails here until somebody reads the new tag's app.py.
    expect(RELEASE.readFor).toBe(RELEASE_TAG);
    expect(RELEASE.tag).toBe(RELEASE_TAG);
    expect(RELEASE.url.endsWith(`/releases/tag/${RELEASE_TAG}`)).toBe(true);
    // A command cannot be both in the release and main-only.
    expect(MAIN_ONLY.filter((c) => RELEASE.commands.includes(c))).toEqual([]);
  });

  it("types no version as current outside lib/domains.ts", () => {
    // History (ChangelogModal, and "the v0.4.0 release still runs them",
    // which is true of that tag) may name old versions; nothing else may
    // type a version string where RELEASE_TAG belongs.
    const files: [string[], RegExp][] = [
      [["cli", "GetCaterva.tsx"], /tag:\s*"v\d/],
      [["cli", "RoadmapSection.tsx"], /label:\s*"In v\d/],
      [["pages", "not-found.tsx"], /CATERVA v\d|Download v\d/],
      [["lib", "domains.ts"], /RELEASE_TAG\s*(?::\s*string\s*)?=\s*"v/],
      // The FAQ and the updates box named the main branch, not a release,
      // as the home of the MD tools until 2026-11-01; they now say
      // RELEASE_TAG, and a typed tag in its place fails here.
      [["cli", "FAQSection.tsx"], /In v\d|on the main branch, `prepare`/],
      [["cli", "CliApp.tsx"], /v\d+\.\d+\.\d+ carries|next release will carry/],
    ];
    for (const [p, typed] of files) {
      expect(src(...p), p.join("/")).not.toMatch(typed);
    }
  });

  it("marks released exactly the capabilities the release registers", () => {
    // Read against `git show v0.6.0:caterva/app.py`, which registers
    // compose, sim, prepare, md, analyze, bind, complex and fep among its
    // fourteen commands. When RELEASE_TAG moves on, the test above fails
    // first and this list is re-read with it.
    // Every command a description names counts, so "caterva bind,
    // complex, fep" needs all three in the release, not only `bind`.
    const commandsOf = (desc: string) =>
      [...desc.matchAll(/caterva (\w+(?:, \w+)*)/g)].flatMap((m) =>
        m[1]!.split(", "),
      );
    for (const d of DOMAINS) {
      const named = commandsOf(d.desc);
      // A description that names no command would pass vacuously.
      expect(named.length, `${d.id} names no caterva command`).toBeGreaterThan(0);
      const inRelease = named.every((c) => RELEASE.commands.includes(c));
      expect(d.status, `${d.id} (${named.join(", ")})`).toBe(
        inRelease ? "released" : "main",
      );
    }
  });
});

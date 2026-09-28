/**
 * Every destination the page advertises has to exist.
 *
 * The testimonials SECTION was removed on 2026-08-15 because it carried
 * five invented quotes attributed to named academics at five real
 * universities, under a "Trusted by educators" heading, for a pre-launch
 * product with no users (ADR 0071). The comment where it used to live
 * says all of that.
 *
 * The removal was half-done. `testimonials` stayed in the top nav, in the
 * mobile section counter, and in the terminal's `help` output as "see
 * what researchers are saying" -- and typing it printed "scrolling to
 * researcher testimonials..." and scrolled nowhere. So the page went on
 * promising social proof that had been deleted for being fabricated. A
 * visitor clicking it learned nothing except that the site is broken.
 *
 * `scripts/check_no_fabricated_endorsements.py` guards the institution
 * names. Nothing guarded the links, because the nav is a list of strings
 * and the sections are JSX elsewhere -- two hand-written lists of the
 * same fact, drifting.
 *
 * These read the SOURCE rather than rendering the app. Rendering CliApp
 * needs the API, framer-motion's rAF and IntersectionObserver, and a test
 * that mocks all three to check a list of anchors is one that gets
 * deleted the first time it breaks.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import path from "node:path";

const CLI = path.join(__dirname, "..", "cli");
const read = (file: string) => readFileSync(path.join(CLI, file), "utf-8");

/** Pull the string literals out of a named array literal. */
function arrayLiterals(source: string, name: string): string[] {
  const start = source.indexOf(name);
  if (start === -1) return [];
  // Stop at the first `]` that closes the literal, not at a later one.
  const open = source.indexOf("[", start);
  const close = source.indexOf("]", open);
  if (open === -1 || close === -1) return [];
  return [...source.slice(open, close).matchAll(/"([a-z-]+)"/g)].map(
    (m) => m[1]!,
  );
}

function navItems(): string[] {
  const items = arrayLiterals(read("CliApp.tsx"), "const NAV_ITEMS");
  expect(items.length, "NAV_ITEMS not found or empty").toBeGreaterThan(10);
  return items;
}

/**
 * Every `id="..."` rendered anywhere in the cli tree.
 *
 * Scans the DIRECTORY rather than a hand-written file list. The first
 * version of this test listed the files it thought mattered and reported
 * `compare` as a dead link -- because `id="compare"` lives in
 * WorkflowCompare.tsx, which was not on the list. A guard whose own
 * inventory can go stale is the defect it is supposed to catch.
 */
function renderedIds(): Set<string> {
  const ids = new Set<string>();
  for (const file of readdirSync(CLI)) {
    if (!file.endsWith(".tsx") && !file.endsWith(".ts")) continue;
    for (const m of read(file).matchAll(/\bid=["'{`]+([a-z-]+)["'`}]/g)) {
      ids.add(m[1]!);
    }
  }
  // The merged MuleRun chapters (the Evidence Cathedral and the rest) are
  // static markup rendered by src/mule/MuleChapters.tsx.
  const mule = readFileSync(path.join(__dirname, "..", "mule", "chapters.html"), "utf-8");
  for (const m of mule.matchAll(/\bid="([a-z-]+)"/g)) ids.add(m[1]!);
  return ids;
}

describe("the page does not advertise destinations it does not have", () => {
  it("every nav item resolves to a section that exists", () => {
    const ids = renderedIds();
    const missing = navItems().filter((item) => !ids.has(item));
    expect(
      missing,
      `nav links with no matching section id: ${missing.join(", ")}`,
    ).toEqual([]);
  });

  it("checks a non-trivial number of nav items against real ids", () => {
    // A guard over an empty list, or against an empty id set, passes
    // forever. This is what makes the check above a check.
    expect(navItems().length).toBeGreaterThan(10);
    expect(renderedIds().size).toBeGreaterThan(10);
  });

  it("offers no terminal command that navigates nowhere", () => {
    // The terminal's command list is a THIRD copy of the section names.
    // `testimonials` survived there after the nav was the obvious place
    // to look, which is exactly why this is checked separately.
    const shell = read("InteractiveShell.tsx");
    const ids = renderedIds();
    const nav = new Set(navItems());
    const commands = arrayLiterals(shell, "const COMMANDS").filter((c) =>
      nav.has(c),
    );
    const broken = commands.filter((c) => !ids.has(c));
    expect(
      broken,
      `terminal commands that navigate nowhere: ${broken.join(", ")}`,
    ).toEqual([]);
  });

  it("keeps testimonials out of the nav and the terminal, by name", () => {
    // Named explicitly so restoring it is a deliberate act against a test
    // that says why, not an accident. This checks the LISTS, not the
    // file: the comment marking where the section was removed explains
    // the fabrication and must stay readable.
    const commands = arrayLiterals(read("InteractiveShell.tsx"), "const COMMANDS");
    const counter = arrayLiterals(read("FloatingSectionCounter.tsx"), "const NAV_ITEMS");
    // Each list must actually have been found. The first version of this
    // test looked for `const SECTIONS` in FloatingSectionCounter, which
    // does not exist -- so it compared against an empty array and could
    // not fail.
    expect(commands.length).toBeGreaterThan(10);
    expect(counter.length).toBeGreaterThan(10);

    expect(navItems()).not.toContain("testimonials");
    expect(commands).not.toContain("testimonials");
    expect(counter).not.toContain("testimonials");
  });

  it("keeps the two copies of the nav list identical", () => {
    // CliApp and FloatingSectionCounter each hold their own NAV_ITEMS.
    // Two hand-written copies of one fact is what let `testimonials`
    // survive in one place after being removed from the other, and it is
    // the same defect that has bitten this repo in the enzyme lists, the
    // unit tables, and the resolver domain lists.
    //
    // Pinning them equal does not remove the duplication, but it does
    // make drift loud instead of silent -- the same remedy used for
    // KM_PLAUSIBLE_MAX_MM and for statedQuantities vs src/units.ts.
    expect(
      arrayLiterals(read("FloatingSectionCounter.tsx"), "const NAV_ITEMS"),
    ).toEqual(navItems());
  });
});

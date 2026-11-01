/**
 * The MuleRun chapters, merged into the site on 2026-09-28, must say what
 * Caterva does today.
 *
 * They arrived advertising PCR, Monte Carlo, SIR/SEIR and population
 * genetics (archived on 2026-09-27), and an illustrative Km of 0.42 mM,
 * while the same page's microscope and gallery show the real value. Their
 * "real output" panel was a transcript whose result the resolver no longer
 * returns. These read the source, like NavIntegrity.test.tsx does.
 */
import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, statSync } from "node:fs";
import path from "node:path";

const MULE = path.join(__dirname, "..", "mule");

function files(dir: string): string[] {
  return readdirSync(dir).flatMap((f) => {
    const p = path.join(dir, f);
    return statSync(p).isDirectory() ? files(p) : [p];
  });
}

const sources = files(MULE).filter((p) => /\.(html|js)$/.test(p));
const text = (p: string) =>
  readFileSync(p, "utf-8")
    // comments may record history; only rendered text and data count
    .replace(/<!--[\s\S]*?-->/g, "")
    .replace(/\/\*[\s\S]*?\*\//g, "")
    .replace(/^\s*\/\/.*$/gm, "");

describe("the merged chapters describe the product as it is", () => {
  it("name no archived domain", () => {
    const stale = /\b(SIR|SEIR|Monte Carlo|Wright[–-]Fisher|population genetics|PCR amplification|Lotka|repressilator|Lennard-Jones)\b/;
    const hits = sources.filter((p) => stale.test(text(p))).map((p) => path.relative(MULE, p));
    expect(hits, `archived domains still named in: ${hits.join(", ")}`).toEqual([]);
  });

  it("carry the real LDH Km, not the illustrative 0.42", () => {
    const hits = sources
      .filter((p) => !p.endsWith("geometry.js"))
      .filter((p) => /\b0\.42\b/.test(text(p)))
      .map((p) => path.relative(MULE, p));
    expect(hits).toEqual([]);
    const micro = readFileSync(path.join(MULE, "js/config/microscope.js"), "utf-8");
    expect(micro).toContain("value: '0.03'");
    expect(micro).toContain("286469");
  });

  it("quote a transcript the tool can still produce", () => {
    const html = readFileSync(path.join(MULE, "chapters.html"), "utf-8");
    expect(html).toContain("| km | 0.03 mM | literature | BRENDA ref 286469 |");
    expect(html).not.toContain("scientific resolve");
  });
});

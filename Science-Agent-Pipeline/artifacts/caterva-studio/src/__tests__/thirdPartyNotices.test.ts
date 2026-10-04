import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterAll, describe, expect, it } from "vitest";
import {
  acceptedUnder,
  bundledFiles,
  collectPackages,
  declaredLicense,
  NoticesError,
  packageDirectoryOf,
  renderNotices,
} from "../../tools/thirdPartyNotices";

const root = mkdtempSync(path.join(tmpdir(), "notices-"));
afterAll(() => rmSync(root, { recursive: true, force: true }));

/** A fake installed package, laid out the way pnpm lays it out. */
function install(name: string, manifest: Record<string, unknown>, files: Record<string, string>): string {
  const directory = path.join(root, "node_modules", ".pnpm", `${name.replace("/", "+")}@1.0.0`, "node_modules", name);
  mkdirSync(directory, { recursive: true });
  writeFileSync(path.join(directory, "package.json"), JSON.stringify({ name, version: "1.0.0", ...manifest }));
  for (const [file, text] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(directory, file)), { recursive: true });
    writeFileSync(path.join(directory, file), text);
  }
  return path.join(directory, "index.js");
}

describe("which package a bundled file belongs to", () => {
  it("finds the package under pnpm's layout, scoped or not", () => {
    expect(packageDirectoryOf("/r/node_modules/.pnpm/a@1/node_modules/a/dist/x.js?v=1")).toBe("/r/node_modules/.pnpm/a@1/node_modules/a");
    expect(packageDirectoryOf("/r/node_modules/.pnpm/s@1/node_modules/@s/pkg/lib/x.js")).toBe("/r/node_modules/.pnpm/s@1/node_modules/@s/pkg");
  });
  it("ignores the page's own source", () => {
    expect(packageDirectoryOf("/r/artifacts/caterva-studio/src/main.tsx")).toBeNull();
  });
});

describe("which licences are accepted", () => {
  it.each(["MIT", "ISC", "Apache-2.0", "BSD-3-Clause", "0BSD", "OFL-1.1"])("accepts %s", (id) => {
    expect(acceptedUnder(id)).toEqual([id]);
  });
  it("accepts an OR when one side is allowed, and an AND only when both are", () => {
    expect(acceptedUnder("(GPL-3.0-only OR MIT)")).toEqual(["MIT"]);
    expect(acceptedUnder("MIT AND ISC")).toEqual(["MIT", "ISC"]);
    expect(acceptedUnder("MIT AND GPL-3.0-only")).toBeNull();
  });
  it.each(["GPL-3.0-only", "LGPL-2.1-or-later", "AGPL-3.0", "SEE LICENSE IN LICENSE.md", "UNLICENSED", "CC-BY-NC-4.0"])("refuses %s", (id) => {
    expect(acceptedUnder(id)).toBeNull();
  });
  it("reads the licence field in its three shapes", () => {
    expect(declaredLicense({ license: "MIT" })).toBe("MIT");
    expect(declaredLicense({ license: { type: "ISC" } })).toBe("ISC");
    expect(declaredLicense({ licenses: [{ type: "MIT" }, { type: "Apache-2.0" }] })).toBe("MIT OR Apache-2.0");
    expect(declaredLicense({})).toBeNull();
  });
});

describe("collecting the bundle's packages", () => {
  it("reads each package's licence texts and sorts them", () => {
    const b = install("bbb", { license: "MIT" }, { LICENSE: "Copyright (c) B\nMIT text" });
    const a = install("@scope/aaa", { license: "Apache-2.0" }, { LICENSE: "Apache text", NOTICE: "Notice text" });
    const found = collectPackages([b, a, path.join(root, "src", "own.ts")]);
    expect(found.map((p) => p.name)).toEqual(["@scope/aaa", "bbb"]);
    expect(found[0].texts.map((t) => t.file)).toEqual(["LICENSE", "NOTICE"]);
    const text = renderNotices(found);
    expect(text).toContain("2 packages:");
    expect(text).toContain("Apache text");
    expect(text).toContain("Copyright (c) B");
    expect(renderNotices(found)).toBe(text);
  });

  it("fails the build for a bundled package with no licence text", () => {
    const file = install("nolicence", { license: "MIT" }, { "README.md": "hello" });
    expect(() => collectPackages([file])).toThrow(NoticesError);
    expect(() => collectPackages([file])).toThrow(/nolicence@1.0.0 \(MIT\) ships no licence text/);
  });

  it("fails the build for an incompatible licence even when its text is there", () => {
    const file = install("copyleft", { license: "GPL-3.0-only" }, { LICENSE: "GPL text" });
    expect(() => collectPackages([file])).toThrow(/copyleft@1.0.0 is licensed "GPL-3.0-only"/);
  });

  it("fails for a package declaring no licence", () => {
    const file = install("silent", {}, { LICENSE: "text" });
    expect(() => collectPackages([file])).toThrow(/silent@1.0.0 declares no licence/);
  });

  it("names every problem at once", () => {
    const one = install("p-one", { license: "MIT" }, {});
    const two = install("p-two", { license: "AGPL-3.0" }, { LICENSE: "x" });
    expect(() => collectPackages([one, two])).toThrow(/p-one[\s\S]*p-two/);
  });

  it("writes a notice only for the packages the build has listed as shipping none", () => {
    const file = install("wouter", { license: "Unlicense" }, {});
    const [wouter] = collectPackages([file]);
    expect(wouter.texts[0].file).toBe("(written by the build)");
    expect(wouter.texts[0].text).toContain("free and unencumbered software");
    const stranger = install("not-listed", { license: "Unlicense" }, {});
    expect(() => collectPackages([stranger])).toThrow(/ships no licence text/);
  });

  it("takes a vendored licence file from lib-vendor, and an MIT notice from the author", () => {
    const file = install("victory-vendor", { license: "MIT AND ISC", author: "Formidable" }, { "lib-vendor/d3-array/LICENSE": "ISC text of d3-array" });
    const [pkg] = collectPackages([file]);
    expect(pkg.texts.map((t) => t.file)).toEqual(["lib-vendor/d3-array/LICENSE", "(written by the build)"]);
    expect(pkg.texts[1].text).toContain("Copyright (c) Formidable");
  });
});

describe("the bundle's module graph", () => {
  it("takes chunk modules and asset sources, and nothing else", () => {
    const files = bundledFiles({
      "a.js": { type: "chunk", modules: { "/x/node_modules/p/i.js": {}, "/x/src/m.ts": {} } },
      "f.woff2": { type: "asset", originalFileNames: ["/x/node_modules/@fontsource/f/files/f.woff2"] },
      "index.html": { type: "asset" },
    });
    expect(files.sort()).toEqual(["/x/node_modules/@fontsource/f/files/f.woff2", "/x/node_modules/p/i.js", "/x/src/m.ts"]);
  });
});

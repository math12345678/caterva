/// <reference types="node" />
/**
 * The licence text of every package that ends up in the built page.
 *
 * The page bundles React, d3, three, recharts, Radix, markdown-it, lucide,
 * framer-motion and the three typefaces. Each of those licences (MIT, BSD,
 * ISC, Apache-2.0, OFL-1.1, 0BSD) asks that its notice travel with copies of
 * the work, and the built assets carry none. This module is the build step
 * that closes that gap: a Vite plugin reads the bundle's own module graph
 * (every module id of every chunk, and the source file of every emitted
 * asset), maps each to its package, reads the licence files the package
 * ships, and writes one `licenses/THIRD-PARTY-NOTICES.txt` beside the page.
 *
 * The build FAILS when a bundled package ships no licence text, declares no
 * licence, or declares one outside the allow-list below. Those are the
 * licences compatible with distributing the page under Apache-2.0 with the
 * notice retained; anything else needs a person's decision, not a default.
 */
import { existsSync, readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import type { Plugin } from "vite";

/** SPDX identifiers the page may bundle. */
export const ALLOWED_LICENSES: ReadonlySet<string> = new Set([
  "MIT",
  "BSD-2-Clause",
  "BSD-3-Clause",
  "ISC",
  "Apache-2.0",
  "0BSD",
  "OFL-1.1",
  // A public-domain dedication (wouter, the router). It places no condition
  // on redistribution, so it is compatible with Apache-2.0; its text is
  // still carried like the others.
  "Unlicense",
]);

/**
 * Packages that declare MIT or the Unlicense in their package.json and ship
 * no licence file at all. Their notice is written from the standard text of
 * that licence (and, for MIT, the author the package names) and says so in
 * the file. Nothing else is ever reconstructed: a bundled package outside
 * this list with no licence text fails the build.
 */
export const WITHOUT_A_FILE: Readonly<Record<string, "MIT" | "Unlicense">> = {
  "react-remove-scroll-bar": "MIT",
  "victory-vendor": "MIT",
  wouter: "Unlicense",
};

const UNLICENSE_TEXT = `This is free and unencumbered software released into the public domain.

Anyone is free to copy, modify, publish, use, compile, sell, or distribute
this software, either in source code form or as a compiled binary, for any
purpose, commercial or non-commercial, and by any means.

In jurisdictions that recognize copyright laws, the author or authors of this
software dedicate any and all copyright interest in the software to the public
domain. We make this dedication for the benefit of the public at large and to
the detriment of our heirs and successors. We intend this dedication to be an
overt act of relinquishment in perpetuity of all present and future rights to
this software under copyright law.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN
ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION
WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

For more information, please refer to <https://unlicense.org>`;

const MIT_TEXT = `Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in
all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.`;

export const NOTICES_FILE = "licenses/THIRD-PARTY-NOTICES.txt";

export interface BundledPackage {
  name: string;
  version: string;
  /** The SPDX expression the package declares. */
  declared: string;
  /** The allowed identifier(s) the expression was accepted under. */
  accepted: string[];
  homepage: string;
  directory: string;
  texts: { file: string; text: string }[];
}

export class NoticesError extends Error {}

/** The package directory a module or asset path lives in, or null when it is not under node_modules. */
export function packageDirectoryOf(file: string): string | null {
  const clean = file.split("?")[0].replace(/\\/g, "/");
  const marker = "/node_modules/";
  const at = clean.lastIndexOf(marker);
  if (at < 0) return null;
  const rest = clean.slice(at + marker.length).split("/");
  const length = rest[0].startsWith("@") ? 2 : 1;
  if (rest.length < length) return null;
  return clean.slice(0, at + marker.length) + rest.slice(0, length).join("/");
}

/** The package.json `license` field as one SPDX expression. */
export function declaredLicense(pkg: Record<string, unknown>): string | null {
  const field = pkg.license;
  if (typeof field === "string" && field.trim()) return field.trim();
  if (field && typeof field === "object" && typeof (field as { type?: unknown }).type === "string") {
    return (field as { type: string }).type;
  }
  const legacy = pkg.licenses;
  if (Array.isArray(legacy) && legacy.length > 0) {
    const types = legacy.map((entry) => (entry && typeof entry === "object" ? (entry as { type?: unknown }).type : entry));
    if (types.every((t) => typeof t === "string")) return (types as string[]).join(" OR ");
  }
  return null;
}

/**
 * The allowed identifiers an SPDX expression is accepted under, or null when
 * it is not. `A OR B` is accepted when either side is (the recipient may take
 * that one); `A AND B` only when both are.
 */
export function acceptedUnder(expression: string): string[] | null {
  const tokens = expression.replace(/[()]/g, " ").trim().split(/\s+/);
  const parseOr = (words: string[]): string[] | null => {
    const alternatives: string[][] = [[]];
    for (const word of words) {
      if (word.toUpperCase() === "OR") alternatives.push([]);
      else alternatives[alternatives.length - 1].push(word);
    }
    for (const alternative of alternatives) {
      const parts: string[][] = [[]];
      for (const word of alternative) {
        if (word.toUpperCase() === "AND") parts.push([]);
        else parts[parts.length - 1].push(word);
      }
      const ids = parts.map((p) => p.join(" "));
      if (ids.length > 0 && ids.every((id) => ALLOWED_LICENSES.has(id))) return ids;
    }
    return null;
  };
  return tokens.length === 0 || tokens[0] === "" ? null : parseOr(tokens);
}

const LICENCE_FILE = /^(licen[cs]e|licen[cs]e[-_.].*|copying|copying[-_.].*|notice|notice[-_.].*)$/i;

function licenceFilesIn(directory: string, prefix: string): { file: string; text: string }[] {
  return readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile() && LICENCE_FILE.test(entry.name) && !/\.(js|mjs|cjs|ts|json)$/i.test(entry.name))
    .map((entry) => entry.name)
    .sort()
    .map((file) => ({ file: prefix + file, text: readFileSync(path.join(directory, file), "utf8").replace(/\r\n/g, "\n").trim() }))
    .filter((entry) => entry.text.length > 0);
}

/** The licence files a package ships at its root. */
export function licenceTexts(directory: string): { file: string; text: string }[] {
  return existsSync(directory) ? licenceFilesIn(directory, "") : [];
}

/** Licence files of code a package vendors inside itself, one directory down from `lib-vendor`. */
export function vendoredLicenceTexts(directory: string): { file: string; text: string }[] {
  const vendor = path.join(directory, "lib-vendor");
  if (!existsSync(vendor)) return [];
  return readdirSync(vendor, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort()
    .flatMap((name) => licenceFilesIn(path.join(vendor, name), `lib-vendor/${name}/`));
}

function reconstructed(
  kind: "MIT" | "Unlicense",
  name: string,
  version: string,
  pkg: Record<string, unknown>,
  source: string,
): { file: string; text: string } {
  if (kind === "Unlicense") {
    return {
      file: "(written by the build)",
      text:
        `${name} ${version} ships no licence file. Its package.json declares the Unlicense; the standard\n` +
        `text follows. The authoritative text is in the package's repository${source ? ` (${source})` : ""}.\n\n` +
        UNLICENSE_TEXT,
    };
  }
  const author = pkg.author;
  const holder =
    typeof author === "string"
      ? author.replace(/\s*<[^>]*>/, "").replace(/\s*\([^)]*\)/, "").trim()
      : author && typeof (author as { name?: unknown }).name === "string"
        ? (author as { name: string }).name
        : "";
  if (!holder) throw new NoticesError(`${name}@${version} ships no licence file and names no author to write one from`);
  return {
    file: "(written by the build)",
    text:
      `${name} ${version} ships no licence file. Its package.json declares the MIT licence and names its\n` +
      `author; the standard MIT text follows with that author as copyright holder. The authoritative\n` +
      `text is in the package's repository${source ? ` (${source})` : ""}.\n\n` +
      `Copyright (c) ${holder}\n\n${MIT_TEXT}`,
  };
}

/** Resolve every bundled file to its package, check it, and read its licence texts. */
export function collectPackages(files: Iterable<string>): BundledPackage[] {
  const directories = new Set<string>();
  for (const file of files) {
    const directory = packageDirectoryOf(file);
    if (directory) directories.add(directory);
  }
  const packages: BundledPackage[] = [];
  const problems: string[] = [];
  for (const directory of [...directories].sort()) {
    const manifest = path.join(directory, "package.json");
    if (!existsSync(manifest)) {
      problems.push(`${directory}: no package.json`);
      continue;
    }
    const pkg = JSON.parse(readFileSync(manifest, "utf8")) as Record<string, unknown>;
    const name = String(pkg.name ?? path.basename(directory));
    const version = String(pkg.version ?? "unknown");
    const declared = declaredLicense(pkg);
    if (declared === null) {
      problems.push(`${name}@${version} declares no licence`);
      continue;
    }
    const accepted = acceptedUnder(declared);
    if (accepted === null) {
      problems.push(`${name}@${version} is licensed "${declared}", which is not one of ${[...ALLOWED_LICENSES].join(", ")}`);
      continue;
    }
    const repository = pkg.repository;
    const homepage =
      typeof pkg.homepage === "string"
        ? pkg.homepage
        : typeof repository === "string"
          ? repository
          : repository && typeof (repository as { url?: unknown }).url === "string"
            ? (repository as { url: string }).url
            : "";
    let texts = licenceTexts(directory);
    const kind = WITHOUT_A_FILE[name];
    if (texts.length === 0 && kind !== undefined && accepted.includes(kind)) {
      try {
        texts = [...vendoredLicenceTexts(directory), reconstructed(kind, name, version, pkg, homepage)];
      } catch (error) {
        problems.push((error as Error).message);
        continue;
      }
    }
    if (texts.length === 0) {
      problems.push(`${name}@${version} (${declared}) ships no licence text in ${directory}`);
      continue;
    }
    packages.push({ name, version, declared, accepted, homepage, directory, texts });
  }
  if (problems.length > 0) {
    throw new NoticesError(
      `The page bundles packages whose licence cannot be conveyed:\n  - ${problems.join("\n  - ")}\n` +
        "Add the licence text to the package's entry, replace the package, or decide the licence is acceptable and extend ALLOWED_LICENSES in tools/thirdPartyNotices.ts.",
    );
  }
  packages.sort((a, b) => (a.name === b.name ? a.version.localeCompare(b.version) : a.name.localeCompare(b.name)));
  return packages;
}

/** The text of THIRD-PARTY-NOTICES.txt. Deterministic: no dates, sorted. */
export function renderNotices(packages: readonly BundledPackage[]): string {
  const rule = "=".repeat(78);
  const lines = [
    "Third-party software in Caterva Studio's page",
    "",
    "Caterva Studio's page is built from Caterva's own code (Apache-2.0, see the",
    "LICENSE file of the release) and the packages listed here, which the build",
    "bundled into the page's scripts and styles or copied beside them (the three",
    "typefaces). This file was generated from the build's own module graph: a",
    "package appears if and only if something from it is in the page. The build",
    "refuses to finish if a bundled package has no licence text or a licence",
    `outside ${[...ALLOWED_LICENSES].join(", ")}.`,
    "",
    `${packages.length} packages:`,
    "",
    ...packages.map((p) => `  ${p.name} ${p.version}  ${p.declared}`),
    "",
  ];
  for (const p of packages) {
    lines.push(rule, `${p.name} ${p.version}`, `License: ${p.declared}`);
    if (p.homepage) lines.push(`Source: ${p.homepage}`);
    lines.push(rule, "");
    for (const { file, text } of p.texts) {
      lines.push(`--- ${file} ---`, "", text, "");
    }
  }
  return lines.join("\n");
}

interface BundleLike {
  [fileName: string]: {
    type: "chunk" | "asset";
    modules?: Record<string, unknown>;
    originalFileNames?: string[];
    originalFileName?: string | null;
  };
}

/** Every source file the bundle was made from: modules of chunks, sources of assets. */
export function bundledFiles(bundle: BundleLike): string[] {
  const files = new Set<string>();
  for (const output of Object.values(bundle)) {
    if (output.type === "chunk") {
      for (const id of Object.keys(output.modules ?? {})) files.add(id);
    } else {
      for (const name of output.originalFileNames ?? []) files.add(name);
      if (output.originalFileName) files.add(output.originalFileName);
    }
  }
  return [...files];
}

/**
 * The Vite plugin. `root` is where relative asset sources resolve from (the
 * page's directory); absolute module ids are used as they are.
 */
export function thirdPartyNotices(root: string): Plugin {
  return {
    name: "caterva-third-party-notices",
    apply: "build",
    generateBundle(_options, bundle) {
      // Rollup's virtual modules (the CommonJS interop proxies) are named
      // "\0" + the real path; the real path is what names the package.
      const files = bundledFiles(bundle as unknown as BundleLike)
        .map((f) => f.replace(/^\0/, ""))
        .map((f) => (path.isAbsolute(f) ? f : path.resolve(root, f)));
      const packages = collectPackages(files);
      this.emitFile({ type: "asset", fileName: NOTICES_FILE, source: renderNotices(packages) });
    },
  };
}

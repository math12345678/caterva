import { mkdtempSync, mkdirSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

import { findRepositoryRoot } from "../lib/repoRoot";

const tempDirs: string[] = [];

function makeFakeRepo(): string {
  const root = mkdtempSync(path.join(tmpdir(), "caterva-root-"));
  tempDirs.push(root);
  mkdirSync(path.join(root, "caterva"));
  mkdirSync(path.join(root, "Science-Agent-Pipeline"));
  writeFileSync(
    path.join(root, "Science-Agent-Pipeline", "pnpm-workspace.yaml"),
    "packages:\n  - 'artifacts/*'\n",
  );
  return root;
}

afterEach(() => {
  tempDirs.splice(0).forEach((dir) => {
    try {
      // Best-effort cleanup; leftover tmp dirs are harmless.
      rmSync(dir, { recursive: true, force: true });
    } catch {
      // ignore
    }
  });
});

describe("findRepositoryRoot", () => {
  it("finds the root from a deep nested api-server path", () => {
    const root = makeFakeRepo();
    const deepPath = path.join(
      root,
      "Science-Agent-Pipeline",
      "artifacts",
      "api-server",
      "src",
      "lib",
    );
    expect(findRepositoryRoot(deepPath)).toBe(path.resolve(root));
  });

  it("finds the root from the root itself", () => {
    const root = makeFakeRepo();
    expect(findRepositoryRoot(root)).toBe(path.resolve(root));
  });

  it("is indifferent to source vs dist depth", () => {
    const root = makeFakeRepo();
    const src = findRepositoryRoot(
      path.join(
        root,
        "Science-Agent-Pipeline",
        "artifacts",
        "api-server",
        "src",
        "lib",
      ),
    );
    const dist = findRepositoryRoot(
      path.join(
        root,
        "Science-Agent-Pipeline",
        "artifacts",
        "api-server",
        "dist",
        "lib",
      ),
    );
    expect(src).toBe(dist);
  });

  it("throws when no repo markers exist up the tree", () => {
    const root = mkdtempSync(path.join(tmpdir(), "caterva-empty-"));
    tempDirs.push(root);
    expect(() => findRepositoryRoot(root)).toThrow(
      /Could not find Caterva repository root/,
    );
  });

  it("does not accept a directory with only one of the two markers", () => {
    const root = mkdtempSync(path.join(tmpdir(), "caterva-half-"));
    tempDirs.push(root);
    mkdirSync(path.join(root, "caterva"));
    expect(() => findRepositoryRoot(root)).toThrow(
      /Could not find Caterva repository root/,
    );
  });
});

import { createHash } from "node:crypto";
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { findRepositoryRoot } from "./repoRoot";

/**
 * Which build of the engine computed a result.
 *
 * The /api/simulate cache was keyed by the query text alone. A result
 * computed by an older build was replayed by every later one, so the
 * stream showed numbers the current build no longer picks (sixth review
 * round, XS5R2-01: donepezil's Km 0.04 mM from ref 666973, where every
 * other surface on the same HEAD carried 0.054 mM from ref 652194). The
 * replay note blamed "literature curated since that date". The cause was
 * a changed engine.
 *
 * The build is a hash of the code that decides a result: the Python
 * engine under `caterva/`, the literature resolver the runner imports
 * from `Tests/` (fallback_logic.py and what it uses; the `test_*.py`
 * files there are left out), and this server's own resolver sources. A
 * content hash, not a git sha, so an uncommitted edit is a new build too.
 * Tests are left out: they do not change what a query resolves to.
 *
 * `CATERVA_ENGINE_BUILD` overrides it, for deployments that ship without
 * the sources.
 */
let cached: string | undefined;

const SKIP_DIRS = new Set([
  "__tests__",
  "tests",
  "__pycache__",
  "node_modules",
  ".pytest_cache",
  "dist",
]);

function collect(dir: string, exts: readonly string[], out: string[]): void {
  let names: string[];
  try {
    names = readdirSync(dir);
  } catch {
    return;
  }
  for (const name of names.sort()) {
    if (SKIP_DIRS.has(name) || name.startsWith(".")) continue;
    const full = path.join(dir, name);
    let isDir = false;
    try {
      isDir = statSync(full).isDirectory();
    } catch {
      continue;
    }
    if (isDir) collect(full, exts, out);
    else if (exts.some((e) => name.endsWith(e)) && !name.startsWith("test_"))
      out.push(full);
  }
}

/** Hash the given source trees. Exported for testing. */
export function hashSources(root: string, trees: readonly string[]): string {
  const hash = createHash("sha256");
  let count = 0;
  for (const tree of trees) {
    const files: string[] = [];
    collect(path.join(root, tree), [".py", ".ts", ".json"], files);
    for (const file of files) {
      hash.update(path.relative(root, file));
      hash.update("\0");
      try {
        hash.update(readFileSync(file));
      } catch {
        continue;
      }
      hash.update("\0");
      count += 1;
    }
  }
  // No sources found means the build cannot be told apart from any other.
  // "unknown" never matches a stored build, so nothing is replayed.
  if (count === 0) return "unknown";
  return hash.digest("hex").slice(0, 16);
}

/** The source trees whose contents decide what a query resolves to. */
export const ENGINE_TREES: readonly string[] = [
  "caterva",
  // Where the resolver lives: science_agent_runner.py imports
  // fallback_logic from here. A change to it changes the numbers.
  "Tests",
  path.join("Science-Agent-Pipeline", "artifacts", "api-server", "src"),
];

export function engineBuild(): string {
  const override = process.env["CATERVA_ENGINE_BUILD"]?.trim();
  if (override) return override;
  if (cached) return cached;
  try {
    const here = path.dirname(fileURLToPath(import.meta.url));
    const root = findRepositoryRoot(here);
    cached = hashSources(root, ENGINE_TREES);
  } catch {
    cached = "unknown";
  }
  return cached;
}

/**
 * Whether a stored result may be replayed by this build. A result with no
 * recorded build was written before builds were recorded, so it may come
 * from any older engine: it is not replayed.
 */
export function replayableBuild(stored: unknown): boolean {
  const current = engineBuild();
  return (
    typeof stored === "string" &&
    stored.length > 0 &&
    stored !== "unknown" &&
    current !== "unknown" &&
    stored === current
  );
}

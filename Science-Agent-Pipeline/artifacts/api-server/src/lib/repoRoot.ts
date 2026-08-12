import { existsSync } from "node:fs";
import path from "node:path";

/**
 * Find the Terrium repository root without relying on source/dist depth.
 *
 * The two markers intentionally cross the language boundary: Terium must
 * be importable from `Terium/`, and the application workspace must be the
 * nested `Science-Agent-Pipeline/` checkout. A moved api-server directory
 * therefore keeps working as long as the repository contract remains intact.
 */
export function findRepositoryRoot(startDir: string): string {
  let candidate = path.resolve(startDir);
  while (true) {
    const hasEngine = existsSync(path.join(candidate, "Terium"));
    const hasWorkspace = existsSync(
      path.join(candidate, "Science-Agent-Pipeline", "pnpm-workspace.yaml"),
    );
    if (hasEngine && hasWorkspace) return candidate;

    const parent = path.dirname(candidate);
    if (parent === candidate) {
      throw new Error(
        `Could not find Terrium repository root from ${startDir}; ` +
          "expected Terium/ and Science-Agent-Pipeline/pnpm-workspace.yaml",
      );
    }
    candidate = parent;
  }
}

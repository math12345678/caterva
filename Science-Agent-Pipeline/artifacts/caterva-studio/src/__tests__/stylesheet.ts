/// <reference types="node" />
/**
 * The page's own stylesheets as text, read from disk, for the tests that
 * hold the CSS to a rule (series contrast, reduced motion, the palette's
 * scrim). jsdom does not apply them, so the rule is checked where it is
 * written.
 */
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

function read(relative: string): string {
  return readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");
}

export const css = read("../index.css");

export const allCss: Record<string, string> = {
  "index.css": css,
  "kinetics.css": read("../screens/kinetics/kinetics.css"),
  "workspace.css": read("../screens/workspace/workspace.css"),
  "structure.css": read("../screens/structure/structure.css"),
  "enzyme.css": read("../components/enzyme/enzyme.css"),
};

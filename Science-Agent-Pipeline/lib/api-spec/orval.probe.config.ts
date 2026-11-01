/**
 * Codegen verification config — used by `scripts/check_codegen_loads.py`.
 *
 * WHY A SECOND CONFIG EXISTS
 * --------------------------
 * `orval.config.ts` writes into `lib/api-zod/src/generated` with
 * `clean: true`. A guard cannot use it directly: verifying the contract by
 * overwriting the contract means a failing check leaves the tree broken, and
 * a guard that damages what it inspects gets disabled the first time it is
 * inconvenient.
 *
 * So this generates the same output into a scratch directory the guard
 * supplies via `ORVAL_VERIFY_OUT`. Nothing under `lib/` is touched.
 *
 * IT SPREADS THE SHIPPED CONFIG. IT DOES NOT RESTATE IT.
 * ------------------------------------------------------
 * Everything below comes from `orval.config.ts` at run time. **Only
 * `workspace` is replaced.**
 *
 * The first version of this file restated the settings instead — it
 * hardcoded `client`, `mode`, `formatter` and pulled in only the `zod`
 * override. It hardcoded `mode: "single"`. The shipped config says
 * `mode: "split"`.
 *
 * That single divergence made the guard pass for the wrong reason, and it
 * hid a real defect: orval honours the `coerce` override in `single` mode
 * and ignores it in `split`, so the two modes emit different validators —
 * `zod.coerce.date()` against `zod.string().datetime({ offset: true })`.
 * The committed files match `single`. The shipped config says `split`. They
 * have therefore not agreed for as long as both have existed, and a guard
 * written specifically to catch that reported OK.
 *
 * A verification config that maintains its own copy of the settings
 * verifies the copy. That is the same failure the guard exists to detect,
 * one level up, and it is why this file now spreads rather than restates.
 */
import { defineConfig } from "orval";
import path from "path";

import mainConfig from "./orval.config";

const outDir = process.env["ORVAL_VERIFY_OUT"];
if (!outDir) {
  throw new Error(
    "ORVAL_VERIFY_OUT is not set. This config is only for " +
      "scripts/check_codegen_loads.py; running it by hand without an output " +
      "directory would be a no-op that looked like a pass.",
  );
}

/**
 * `as any` because orval's exported config type is a union of shapes.
 * Narrowing it here would create a second thing to maintain, which is
 * precisely what this file exists to avoid.
 */
const shipped = (mainConfig as any).zod;
if (!shipped?.output) {
  throw new Error(
    "orval.config.ts has no `zod` target with an `output`. This config " +
      "mirrors that target; if it moved or was renamed, this guard is " +
      "checking nothing and must be updated rather than left passing.",
  );
}

export default defineConfig({
  zod: {
    ...shipped,
    output: {
      ...shipped.output,
      // The ONLY intentional difference from the shipped configuration.
      workspace: path.join(outDir, "api-zod", "src"),
    },
  },
});

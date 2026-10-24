/**
 * Re-checking a run's claims bundle: `POST /api/runs/{id}/verify`
 * (docs/studio/CONTRACT.md 7, amended 2026-10-17).
 *
 * The server runs the one function `caterva verify` calls over the bundle
 * a compose run wrote beside its artifacts (CONTRACT.md 11) and answers the
 * command's `--json` report line for line, plus when it ran. The page never
 * reads the bundle itself: what it shows is the checker's own lines. A POST
 * because it does work (every pinned page is gunzipped and re-digested).
 *
 * The answer is checked against its schema before anyone reads it, for the
 * reason src/lib/schemas.ts gives: a check whose `ok` arrived as something
 * other than a boolean must not be drawn as passed. The page draws each
 * check by its `status` (held, failed, did not run), the three states the
 * command prints as ok, FAIL and n/a; `ok` is "did not fail", so a check
 * that did not run is ok without having held, and the two must agree.
 */
import { z } from "zod";

import { apiPost } from "./client";
import type { VerifyCheck, VerifyReport } from "./types";

export const VerifyCheckSchema = z
  .object({
    name: z.string(),
    claim: z.string().nullable(),
    ok: z.boolean(),
    status: z.enum(["ok", "failed", "not run"]),
    detail: z.string(),
  })
  .passthrough()
  .refine((c) => c.ok === (c.status !== "failed"), {
    message: "`ok` and `status` disagree: a check is ok exactly when it did not fail",
    path: ["status"],
  });

export const VerifyReportSchema = z
  .object({ ok: z.boolean(), checks: z.array(VerifyCheckSchema), ran_at: z.string() })
  .passthrough();

type Pin<T> = z.ZodType<T, z.ZodTypeDef, unknown>;
export const PINNED = {
  verifyCheck: VerifyCheckSchema satisfies Pin<VerifyCheck>,
  verifyReport: VerifyReportSchema satisfies Pin<VerifyReport>,
};

/** The checker's name for the line that lists what it cannot check; those lines are ok and prove nothing. */
export const NOT_CHECKED = "not checked";

export function verifyRun(id: string): Promise<VerifyReport> {
  return apiPost<VerifyReport>(`/api/runs/${encodeURIComponent(id)}/verify`, {}, VerifyReportSchema);
}

/** A report's checks sorted as the command prints them: what ran, then what was not checked. */
export function ranChecks(report: VerifyReport): VerifyCheck[] {
  return report.checks.filter((c) => c.name !== NOT_CHECKED);
}

export function notChecked(report: VerifyReport): VerifyCheck[] {
  return report.checks.filter((c) => c.name === NOT_CHECKED);
}

export function failedChecks(report: VerifyReport): VerifyCheck[] {
  return ranChecks(report).filter((c) => c.status === "failed");
}

/** The checks that held: not the ones that did not run, which are ok without having held. */
export function heldChecks(report: VerifyReport): VerifyCheck[] {
  return ranChecks(report).filter((c) => c.status === "ok");
}

/** The checks that could not run (a dominance check on a claim that carried no ordinals), each with its reason. */
export function notRunChecks(report: VerifyReport): VerifyCheck[] {
  return ranChecks(report).filter((c) => c.status === "not run");
}

/** The command's mark for each state: `caterva verify` prints ok, FAIL or n/a. */
export const PRINTED: Record<VerifyCheck["status"], string> = { ok: "ok", failed: "FAIL", "not run": "n/a" };

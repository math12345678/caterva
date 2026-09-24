/**
 * What the front door does with twenty real questions, measured at the ROUTE.
 *
 * `frontDoorCoverage.test.ts` measures the resolver alone: whether the
 * catalogue matches a typed sentence. This file measures what a person on
 * the other end of `POST /simulate` actually receives, which is a different
 * and much bigger surface, because the responder now has a third path:
 *
 *   1. The catalogue matches -> the engine runs the named model.
 *   2. The catalogue refuses as unrecognized -> `runPipeline` falls through
 *      to the composer, which builds the mechanism (structure_only) or
 *      refuses it with a precise reason.
 *   3. The catalogue matches but a required parameter was never stated ->
 *      refused with the missing input named.
 *
 * The composer's contribution is the point of this file. Before the
 * fallthrough, "three step phosphorylation cascade" and "a toggle switch
 * between two repressors" were answered with "try vocabulary closer to the
 * fifteen supported domains" -- and the sentence was closer to the right
 * machine than the message was to the truth. Now they come back as
 * mechanisms, un-simulated, their required constants listed instead of
 * fabricated. "glycolysis in yeast" is refused for the true reason (a named
 * pathway needs a pathway database), not for a made-up vocabulary problem.
 *
 * These run the real subprocess and the real composer; nothing is mocked.
 * No LLM key, the same honest default as the resolver-level harness.
 */
import { writeFileSync } from "node:fs";

import { describe, expect, it } from "vitest";
import request from "supertest";
import { mkdtempSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";

import { QUERIES } from "./frontDoorCoverage.test";

process.env["CACHE_FILE"] = join(
  mkdtempSync(join(tmpdir(), "front-door-route-")),
  "cache.json",
);

const app = (await import("../app")).default;

async function runToTerminal(
  body: object,
  timeoutMs = 90_000,
): Promise<{
  status: string;
  domain?: string;
  error?: { error?: string; message?: string };
  result?: {
    domain?: string;
    composition?: {
      rule?: string;
      structureOnly?: boolean;
      toResolve?: unknown[];
    };
  };
}> {
  const posted = await request(app).post("/api/simulate").send(body);
  if (posted.status !== 202) {
    return { status: "rejected", error: { error: String(posted.status) } };
  }
  const jobId = posted.body.jobId as string;

  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const fetched = await request(app).get(`/api/simulate/${jobId}`);
    const status = fetched.body.status;
    if (status === "completed" || status === "failed") return fetched.body;
    await new Promise((r) => setTimeout(r, 150));
  }
  throw new Error(`job ${jobId} did not finish within ${timeoutMs}ms`);
}

describe("the fallthrough's three previously-unrecognized queries", () => {
  it("answers the cascade with a composed structure, not a refusal", async () => {
    const job = await runToTerminal({
      query: "three step phosphorylation cascade",
    });

    expect(job.status, JSON.stringify(job)).toBe("completed");
    const composition = job.result?.composition;
    expect(composition?.rule).toBe("phosphorylation_cascade");
    expect(composition?.structureOnly).toBe(true);
    expect(composition?.toResolve).toHaveLength(12);
  }, 120_000);

  it("answers the toggle switch with a composed structure", async () => {
    const job = await runToTerminal({
      query: "a toggle switch between two repressors",
    });

    expect(job.status, JSON.stringify(job)).toBe("completed");
    const composition = job.result?.composition;
    // The rule name is the grammar's; the point is that a gene circuit that
    // has no catalogue entry now comes back as a mechanism.
    expect(composition?.rule).toBeTruthy();
    expect(composition?.toResolve?.length).toBeGreaterThan(0);
  }, 120_000);

  it("refuses glycolysis for the true reason, not for vocabulary", async () => {
    const job = await runToTerminal({ query: "glycolysis in yeast" });

    expect(job.status).toBe("failed");
    expect(job.error?.error).toBe("UNRECOGNIZED_QUERY");
    // The refuser's heading -- the engineered message that distinguishes a
    // pathway database problem from a sentence-shape problem -- is pinned
    // here, not the engine's own reason text, because that is this
    // module's contribution and the thing a regression could silently drop.
    expect(job.error?.message).toContain("composer does not hold");
    expect(job.error?.message).not.toContain("fifteen supported domains");
  }, 120_000);

  it(
    "measures and records the route-level coverage of all twenty queries",
    async () => {
      const rows: string[] = [];
      let answered = 0;
      let answeredComposed = 0;
      let correct = 0;

      for (const testCase of QUERIES) {
        const job = await runToTerminal({ query: testCase.query });
        const domain = job.result?.domain;
        const got = job.status === "completed"
          ? domain ?? "completed"
          : job.error?.error ?? "rejected";

        if (job.status === "completed") {
          answered += 1;
          if (domain === "compose") answeredComposed += 1;
          if (testCase.expect !== null && domain === testCase.expect) {
            correct += 1;
          }
        }

        const verdict =
          job.status === "completed" && testCase.expect === domain
            ? "OK"
            : job.status === "completed" && domain === "compose" && testCase.expect === null
              ? "STRUCTURE"
              : job.status === "completed"
                ? "WRONG-MODEL"
                : "REFUSED";
        rows.push(
          `${verdict.padEnd(12)} ${testCase.query.slice(0, 46).padEnd(48)} -> ${got}`,
        );
      }

      const report = [
        "",
        "FRONT DOOR COVERAGE, AT THE ROUTE (no LLM key -- the keyword path)",
        "=".repeat(78),
        ...rows,
        "=".repeat(78),
        `completed ${answered}/${QUERIES.length}` +
          ` (incl. ${answeredComposed} composed structure(s)), ` +
          `correct model ${correct}/${QUERIES.length}`,
        "",
      ].join("\n");
      console.log(report);
      writeFileSync("front-door-route-coverage.txt", report);

      // Same philosophy as the resolver-level harness: the number is a
      // measurement recorded in the file, not a bar the harness is tuned
      // against. The three behaviours above are the contract; the count is
      // its report.
      expect(QUERIES).toHaveLength(20);
    },
    600_000,
  );
});
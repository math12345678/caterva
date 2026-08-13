/**
 * What the runner says when the engine does not come back.
 *
 * Every message here reaches the user verbatim: `runPipeline` catches the
 * rejection and stores `err.message` as the job's PIPELINE_ERROR text, which
 * is what `GET /api/simulate/:jobId` returns. So these strings are product
 * copy, not log noise, and they used to be actively misleading -- a run that
 * was killed for memory reported "exited with code null", and a run that
 * produced nothing reported "exited with code 0", naming a SUCCESS status as
 * the reason for a failure.
 *
 * Nothing is mocked. A wrapper script stands in for the interpreter: it
 * forwards the capability probe (`python -c ...`) to the real supported
 * interpreter so `resolvePythonExecutable` accepts it, then misbehaves in a
 * chosen way when asked to run the runner script. The code path exercised is
 * the real `runTerium`, including the real `spawn`.
 */
import { describe, it, expect, beforeAll, afterEach } from "vitest";
import { chmodSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";

import { resolvePythonExecutable } from "../lib/python";
import { REPO_ROOT, runTerium } from "../lib/teriumRunner";

const PARAMETERS = { km: 1, vmax: 1, s0: 1 };

let wrapper: string;
const originalPython = process.env["TERRIUM_PYTHON"];

beforeAll(() => {
  // Resolve the genuine interpreter BEFORE TERRIUM_PYTHON is redirected, so
  // the wrapper has something real to delegate the probe to.
  const realPython = resolvePythonExecutable(REPO_ROOT);
  const dir = mkdtempSync(path.join(tmpdir(), "terium-runner-"));
  wrapper = path.join(dir, "misbehaving-python.sh");
  writeFileSync(
    wrapper,
    [
      "#!/bin/sh",
      '# Capability probe: behave exactly like the real interpreter.',
      'if [ "$1" = "-c" ]; then',
      `  exec ${JSON.stringify(realPython)} "$@"`,
      "fi",
      '# Running the runner script: misbehave as instructed.',
      'case "${TERIUM_TEST_MODE}" in',
      "  silent) exit 0 ;;",
      "  killed) kill -9 $$ ;;",
      '  noisy) echo "boom: model build failed" >&2; exit 3 ;;',
      "  quiet_failure) exit 4 ;;",
      "  *) exit 0 ;;",
      "esac",
    ].join("\n"),
    { mode: 0o755 },
  );
  chmodSync(wrapper, 0o755);
});

afterEach(() => {
  delete process.env["TERIUM_TEST_MODE"];
  if (originalPython === undefined) delete process.env["TERRIUM_PYTHON"];
  else process.env["TERRIUM_PYTHON"] = originalPython;
});

function useWrapper(mode: string): void {
  process.env["TERRIUM_PYTHON"] = wrapper;
  process.env["TERIUM_TEST_MODE"] = mode;
}

async function failureMessage(): Promise<string> {
  try {
    await runTerium("mm", PARAMETERS);
  } catch (err) {
    return err instanceof Error ? err.message : String(err);
  }
  throw new Error("runTerium resolved, but the runner was supposed to fail");
}

describe("runTerium failure reporting", () => {
  // The one that matters most, and the one an existing test had pinned
  // BACKWARDS: it asserted /Terium runner exited with code 1/ as correct.
  // The engine writes its reason to stdout and exits 1; the boundary read
  // the status first and discarded the reason, so every structured
  // rejection the engine has ever produced -- every ok=false, every
  // out-of-range parameter, the whole of constitution Rule 2 -- reached the
  // API user as an exit code. No wrapper here: this is the real engine
  // refusing a real over-budget request.
  it("gives the engine's own reason for a rejected run, not its exit status", async () => {
    const message = await (async () => {
      try {
        await runTerium("gillespie_ssa_bimolecular", { a0: 600_000, b0: 500_000 });
      } catch (err) {
        return err instanceof Error ? err.message : String(err);
      }
      throw new Error("the engine was supposed to reject this population");
    })();

    expect(message).toContain("MAX_API_SSA_POPULATION");
    expect(message).toContain("1100000");
    expect(message).not.toMatch(/exited with (code|status)/);
  });

  it("does not blame a successful exit status when the runner writes nothing", async () => {
    useWrapper("silent");

    const message = await failureMessage();

    expect(message).toContain("produced no result");
    // The old text. "exited with code 0" told the user that success was the
    // reason for the failure.
    expect(message).not.toContain("exited with code 0");
  });

  it("names the signal when the runner is killed, rather than reporting a null code", async () => {
    useWrapper("killed");

    const message = await failureMessage();

    expect(message).toContain("SIGKILL");
    expect(message).toContain("memory");
    expect(message).not.toContain("code null");
  });

  it("passes the runner's own stderr through when it explains itself", async () => {
    useWrapper("noisy");

    const message = await failureMessage();

    expect(message).toContain("boom: model build failed");
  });

  it("reports the exit status when a nonzero exit explains nothing", async () => {
    useWrapper("quiet_failure");

    const message = await failureMessage();

    expect(message).toContain("4");
    expect(message).toContain("nothing");
  });

  // Writing the request to a child that has already gone emits EPIPE on
  // stdin. An 'error' event with no listener is an uncaughtException in
  // Node, so this used to be an API-server crash rather than a failed job.
  //
  // The assertion is on a captured uncaughtException, not on the test
  // runner noticing: vitest does flag the stray EPIPE, but it flags it as a
  // process-level "unhandled error" attached to no test, which is exactly
  // the kind of failure that gets read as noise and ignored. Naming it
  // makes the guard legible.
  it("fails the job instead of crashing the process when the child dies early", async () => {
    useWrapper("silent");

    const uncaught: Error[] = [];
    const capture = (err: Error): void => {
      uncaught.push(err);
    };
    process.on("uncaughtException", capture);
    try {
      await expect(runTerium("mm", PARAMETERS)).rejects.toThrow(
        /produced no result/,
      );
      // The EPIPE arrives on the stream's own turn of the event loop, which
      // is after the promise settles.
      await new Promise((resolve) => setTimeout(resolve, 50));
    } finally {
      process.off("uncaughtException", capture);
    }

    expect(uncaught.map((e) => e.message)).toEqual([]);
  });
});

import {
  Router,
  type IRouter,
  type Request,
  type Response,
  type NextFunction,
} from "express";
import { access } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawn } from "node:child_process";
import { isDbAvailable } from "@workspace/db";
import * as queue from "../lib/queue";
import { resolvePythonExecutable } from "../lib/python";
import { findRepositoryRoot } from "../lib/repoRoot";
import { getDomainCitation } from "../lib/domain-literature";

const router: IRouter = Router();

const _dirname = path.dirname(fileURLToPath(import.meta.url));
const REPO_ROOT = findRepositoryRoot(_dirname);

async function fileExists(filePath: string): Promise<boolean> {
  try {
    await access(filePath);
    return true;
  } catch {
    return false;
  }
}

async function checkPython3(): Promise<{
  available: boolean;
  version: string | null;
}> {
  let executable: string;
  try {
    executable = resolvePythonExecutable(REPO_ROOT);
  } catch {
    return { available: false, version: null };
  }

  return new Promise((resolve) => {
    const proc = spawn(executable, ["--version"]);
    const timer = setTimeout(() => {
      proc.kill();
      resolve({ available: false, version: null });
    }, 4000);
    let out = "";
    proc.stdout.on("data", (chunk: Buffer) => {
      out += chunk.toString();
    });
    proc.stderr.on("data", (chunk: Buffer) => {
      out += chunk.toString();
    });
    proc.on("error", () => {
      clearTimeout(timer);
      resolve({ available: false, version: null });
    });
    proc.on("close", (code) => {
      clearTimeout(timer);
      if (code === 0) {
        resolve({ available: true, version: out.trim() });
      } else {
        resolve({ available: false, version: null });
      }
    });
  });
}

interface SubsystemStatus {
  ok: boolean;
  label: string;
  detail: string;
}

router.get(
  "/pipeline/status",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const scriptsDir = path.resolve(_dirname, "..", "src", "lib");
      const [teriumExists, scienceAgentExists, python, dbAvailable] =
        await Promise.all([
          fileExists(path.join(scriptsDir, "terium_runner.py")),
          fileExists(path.join(scriptsDir, "science_agent_runner.py")),
          checkPython3(),
          isDbAvailable(),
        ]);

      const subsystems: SubsystemStatus[] = [
        {
          ok: teriumExists,
          label: "terium_runner.py",
          detail: teriumExists
            ? "Script found"
            : "Missing — pipeline will fail at 'running' stage",
        },
        {
          ok: scienceAgentExists,
          label: "science_agent_runner.py",
          detail: scienceAgentExists
            ? "Script found"
            : "Missing — enzyme lookups will fail",
        },
        {
          ok: python.available,
          label: "python3",
          detail: python.available
            ? `Found: ${python.version}`
            : "Not found — pipeline cannot run Terium or science agent",
        },
        {
          ok: dbAvailable,
          label: "postgres (via drizzle)",
          detail: dbAvailable
            ? "DATABASE_URL configured and connected"
            : "Not configured — results are in-memory only (no persistence)",
        },
        {
          ok: !!process.env["OPENAI_API_KEY"] || !!process.env["LLM_API_KEY"],
          label: "openai / llm api key",
          detail:
            process.env["OPENAI_API_KEY"] || process.env["LLM_API_KEY"]
              ? "Configured — queries will use LLM resolution"
              : "Not set — falling back to keyword matching (no enzyme lookups via LLM)",
        },
      ];

      const allOk = subsystems.every((s) => s.ok);
      const queueJobs = queue.listJobs();
      const statusCounts: Record<string, number> = {};
      for (const job of queueJobs) {
        statusCounts[job.status] = (statusCounts[job.status] ?? 0) + 1;
      }

      res.json({
        status: allOk ? "healthy" : "degraded",
        uptime: process.uptime(),
        subsystems,
        queue: {
          total: queueJobs.length,
          byStatus: statusCounts,
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

router.get(
  "/metrics",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const jobs = queue.listJobs();
      const completed = jobs.filter((j) => j.status === "completed").length;
      const enqueued = jobs.filter(
        (j) =>
          j.status === "pending" ||
          j.status === "resolving" ||
          j.status === "running",
      ).length;
      const failed = jobs.filter((j) => j.status === "failed").length;

      let waitlistCount = 0;
      try {
        const { existsSync, readFileSync } = await import("node:fs");
        const { join } = await import("node:path");
        const dbPath =
          process.env.WAITLIST_FILE ||
          join(import.meta.dirname, "..", "data", "waitlist.json");
        if (existsSync(dbPath)) {
          const raw = JSON.parse(readFileSync(dbPath, "utf-8"));
          waitlistCount = Array.isArray(raw) ? raw.length : 0;
        }
      } catch {
        /* best effort */
      }

      res.json({
        totalSimulations: jobs.length,
        completedSimulations: completed,
        enqueuedSimulations: enqueued,
        failedSimulations: failed,
        waitlistSignups: waitlistCount,
        uptime: process.uptime(),
      });
    } catch (err) {
      next(err);
    }
  },
);

/**
 * GET /api/pipeline/literature
 *
 * Returns comprehensive literature backing status for all supported domains.
 * Each domain shows:
 * - Primary peer-reviewed reference with DOI
 * - Justification for default parameters
 * - Complete citation information
 */
router.get(
  "/pipeline/literature",
  async (_req: Request, res: Response, next: NextFunction) => {
    try {
      const domains = [
        "mm",
        "mm_competitive_inhibition",
        "sir",
        "seir",
        "wright_fisher",
        "gillespie_ssa",
        "pcr",
        "molecular_dynamics",
        "gillespie_ssa_bimolecular",
        "two_locus_wright_fisher",
        "lotka_volterra",
        "cell_cycle_oscillator",
        "repressilator",
      ];

      const domainLiterature = domains.map((domain) => ({
        domain,
        citation: getDomainCitation(domain),
      }));

      res.json({
        timestamp: new Date().toISOString(),
        // "All parameters in Terrium are backed by peer-reviewed
        // scientific literature. Every domain has primary references with
        // DOI." -- what this said until 2026-09-05. Both halves were
        // false, and the second is checkable in one pass over this very
        // file's data: mm_competitive_inhibition, seir, lotka_volterra and
        // monte_carlo_pi have NO reference carrying a DOI, because their
        // primary sources are books and pre-DOI papers (Copeland 2013,
        // Anderson & May 1991, Lotka 1925).
        //
        // The first half was false BY DESIGN, which is worse. Parameters
        // carry an origin: "resolved" came from literature, "user" came
        // from the person asking, and "llm"/"default" are BLOCKED rather
        // than reported. A product whose selling point is refusing to
        // invent numbers should not advertise that every number is
        // literature-backed -- the refusals are the feature.
        message:
          "Every simulation domain here carries at least one primary " +
          "reference. Not all of them have a DOI: several primary sources " +
          "are books or predate DOI assignment. This does NOT mean every " +
          "parameter is literature-backed -- parameters carry a separate " +
          "provenance origin, and values that are neither resolved from " +
          "literature nor supplied by you are refused rather than filled " +
          "in.",
        totalDomainsCovered: domains.length,
        domains: domainLiterature,
        literature: {
          // Same correction as the metrics endpoints: each line now says
          // what the work contributes, and the two that contributed
          // nothing are gone.
          queuing:
            "Little (1961) L = \u03BBW -- the steady-state relation the job " +
            "metrics can be checked against, not the method used to " +
            "produce them.",
          confidence:
            "Wilson (1927) -- computed: the binomial proportion interval " +
            "around the success rate.",
          enzyme:
            "Tipton et al. (2014) -- STRENDA reporting standards, applied: " +
            "a resolved kinetic value whose source omits pH or temperature " +
            "is reported flagged rather than verified.",
          epidemiology:
            "Kermack & McKendrick (1927) -- the compartmental model. Note " +
            "the engine integrates the frequency-dependent form " +
            "(\u03B2\u00B7S\u00B7I/N), not the density-dependent one in the " +
            "1927 paper.",
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

export default router;

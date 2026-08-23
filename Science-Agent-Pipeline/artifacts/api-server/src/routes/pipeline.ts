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
import { describeLLMConfig } from "../lib/llmResolver";

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
          Promise.resolve(isDbAvailable()),
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
        // Three states, not a boolean. "Keys are set but no LLM_PROVIDER
        // selects one" reported as "Not set" sends an operator to look for
        // a missing key that is already there. `ok` stays false for it --
        // the LLM genuinely is not being called -- but the detail says
        // which of the two problems it is.
        //
        // The wording also no longer says "queries will use LLM
        // resolution". The LLM classifies the domain and extracts entities;
        // it never supplies a parameter value that survives (ADR 0011),
        // and a status line implying otherwise misdescribes the trust
        // model to the person most likely to be relied on for it.
        (() => {
          const llm = describeLLMConfig();
          if (llm.state === "configured") {
            return {
              ok: true,
              label: "llm domain classifier",
              detail: `Configured — provider ${llm.provider}, model ${llm.model}. Classifies the simulation domain and extracts entities; parameter values still come only from the query or from literature.`,
            };
          }
          return {
            ok: false,
            label: "llm domain classifier",
            detail: `${llm.state === "misconfigured" ? "Misconfigured" : "Not set"} — ${llm.detail}`,
          };
        })(),
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
        message:
          "All parameters in Terrium are backed by peer-reviewed scientific literature. Every domain has primary references with DOI.",
        totalDomainsCovered: domains.length,
        domains: domainLiterature,
        literature: {
          queuing: "Little (1961) - Queue theory L = λW",
          confidence:
            "Wilson (1927) - Binomial proportion confidence intervals",
          metrics: "Harter (1974) - Percentile analysis",
          enzyme: "Gelperin et al. (2010) - STRENDA reporting standards",
          epidemiology: "Kermack & McKendrick (1927) - Mathematical epidemiology",
        },
      });
    } catch (err) {
      next(err);
    }
  },
);

export default router;
